from __future__ import annotations

from datetime import datetime, timezone
import json
import subprocess
from typing import Any

from file_state import atomic_write_text
from wiki_inventory import LinkResolver, WikiInventory, scan_wiki
from workspace_paths import Workspace

INDEX_ORDER = ["synthesis", "concept", "entity", "source", "answer", "hub"]
RECENT_LIMIT = 15


def build_graph(workspace: Workspace, inventory: WikiInventory) -> dict[str, Any]:
    links = LinkResolver.from_inventory(inventory)
    # index.md / recent.md are generated navigation, not knowledge — keep them out of
    # the graph's nodes and edges alike (a hub the agent authored is knowledge and stays).
    pages = [page for page in inventory.pages if page.page_type != "index"]
    nodes: dict[str, Any] = {}
    edges: list[dict[str, str]] = []
    for page in pages:
        nodes[page.path] = {
            "title": page.title,
            "page_type": page.page_type,
            "work_ids": list(page.work_ids),
        }
        for work_id in page.work_ids:
            edges.append({"type": "page_work", "source": page.path, "target": work_id})
        for link in page.links:
            resolved = links.resolve(page, link)
            if len(resolved) == 1 and resolved[0] != page.path:
                edges.append({"type": "link", "source": page.path, "target": resolved[0]})
    by_work: dict[str, list[str]] = {}
    for page in pages:
        for work_id in page.work_ids:
            by_work.setdefault(work_id, []).append(page.path)
    for work_id, paths in sorted(by_work.items()):
        for i, source in enumerate(paths):
            for target in paths[i + 1 :]:
                edges.append({"type": "shared_work", "source": source, "target": target, "work_id": work_id})
    return {"schema_version": 1, "nodes": nodes, "edges": edges}


def render_index(inventory: WikiInventory) -> str:
    lines = ["# Wiki index\n", "\nGenerated catalog. Knowledge-first ordering: syntheses and concepts before sources.\n"]
    for page_type in INDEX_ORDER:
        pages = inventory.by_type(page_type)
        if not pages:
            continue
        lines.append(f"\n## {page_type.capitalize()} pages\n\n")
        for page in sorted(pages, key=lambda item: item.title.lower()):
            works = f" — `{', '.join(page.work_ids)}`" if page.work_ids else ""
            lines.append(f"- [{page.title}]({page.wiki_path}){works}\n")
    return "".join(lines)


def _git(workspace: Workspace, *args: str) -> str | None:
    """Stdout of a git command in the workspace, or None when git or the repo is absent.

    Callers parse paths literally. A filename containing ``"``, ``\\``, or control
    characters would be C-quoted by git despite quotepath=false and miss both maps,
    degrading that page to the mtime fallback. Wiki slugs are ASCII-safe, so decoding
    C-quoting is out of scope.
    """

    try:
        return subprocess.run(
            ["git", "-C", str(workspace.root), "-c", "core.quotepath=false", *args],
            capture_output=True, text=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def _committed_times(workspace: Workspace) -> dict[str, float]:
    """Newest commit time per wiki file (repo-relative path → unix time).

    ``git log`` is newest-first, so the first commit that names a file wins.
    Empty outside a git repo.
    """

    log = _git(workspace, "log", "--format=%x00%ct", "--name-only", "--", "wiki")
    times: dict[str, float] = {}
    when = 0.0
    for line in (log or "").splitlines():
        if line.startswith("\x00"):
            when = float(line[1:])
        elif line:
            times.setdefault(line, when)
    return times


def _uncommitted_paths(workspace: Workspace) -> set[str]:
    status = _git(workspace, "status", "--porcelain", "--", "wiki")
    return {line[3:].split(" -> ")[-1].strip('"') for line in (status or "").splitlines()}


def render_recent(workspace: Workspace, inventory: WikiInventory) -> str:
    # mtime does not survive clone/checkout, so committed pages are dated by their
    # last commit; mtime speaks only for writes git has not recorded yet.
    committed = _committed_times(workspace)
    uncommitted = _uncommitted_paths(workspace)
    stamped = []
    for page in inventory.pages:
        if page.page_type == "index":
            continue
        when = committed.get(page.path)
        if when is None or page.path in uncommitted:
            when = workspace.abspath(page.path).stat().st_mtime
        stamped.append((when, page))
    stamped.sort(key=lambda item: -item[0])
    lines = ["# Recent pages\n", "\nGenerated from git history; uncommitted pages dated by file mtime.\n\n"]
    for when, page in stamped[:RECENT_LIMIT]:
        day = datetime.fromtimestamp(when, tz=timezone.utc).strftime("%Y-%m-%d")
        lines.append(f"- {day} — [{page.title}]({page.wiki_path}) ({page.page_type})\n")
    if not stamped:
        lines.append("- No pages yet.\n")
    return "".join(lines)


def rebuild_indexes(workspace: Workspace, inventory: WikiInventory | None = None) -> list[str]:
    """Regenerate index.md, recent.md, and the graph. Returns the paths whose content changed."""

    inventory = inventory or scan_wiki(workspace)
    graph_text = json.dumps(build_graph(workspace, inventory), indent=2, sort_keys=True) + "\n"
    targets = {
        workspace.wiki / "index.md": render_index(inventory),
        workspace.wiki / "recent.md": render_recent(workspace, inventory),
        workspace.wiki / "indexes" / "wiki-graph.json": graph_text,
    }
    changed: list[str] = []
    for path, text in targets.items():
        previous = path.read_text(encoding="utf-8") if path.exists() else None
        if previous != text:
            atomic_write_text(path, text)
            changed.append(workspace.relpath(path))
    return changed


def main() -> int:
    workspace = Workspace.from_path(None)
    changed = rebuild_indexes(workspace)
    print("\n".join(changed) or "no changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
