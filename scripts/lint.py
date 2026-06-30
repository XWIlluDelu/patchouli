from __future__ import annotations

from dataclasses import dataclass
import re

from wiki_inventory import DURABLE_TYPES, WikiInventory, link_key, link_target_map, scan_wiki
from workspace_paths import Workspace

_SENTENCE_END_RE = re.compile(r"[.!?](?=\s|$)")
_MARKER_RE = re.compile(r"\(Works?:")
_BULLET_RE = re.compile(r"^\s*[-*] ")


@dataclass(frozen=True)
class LintFinding:
    path: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "code": self.code, "message": self.message}


def lint_wiki(workspace: Workspace, inventory: WikiInventory | None = None) -> list[LintFinding]:
    """Advisory content lint. Never blocks writes; produces follow-up items.

    Binding invariants (unreadable, broken_link, quote_unresolved, work markers,
    support list, single-work synthesis, page_type/dir mismatch) live in
    check_wiki.py, with the quote machinery in quotes.py. This function reports only
    the advisory signals a maintainer may revise but that never gate a write:
    missing frontmatter, citation clutter, no-outgoing-link durables, orphans, and
    duplicate titles.
    """

    inventory = inventory or scan_wiki(workspace)
    findings: list[LintFinding] = []
    link_targets = link_target_map(inventory)
    inbound: dict[str, int] = {page.path: 0 for page in inventory.pages}
    titles: dict[str, list[str]] = {}

    for page in inventory.pages:
        if page.page_type == "index":
            continue
        titles.setdefault(page.title.strip().lower(), []).append(page.path)
        if not page.frontmatter:
            findings.append(LintFinding(page.path, "missing_frontmatter", "page has no YAML frontmatter"))
        for target in page.links:
            resolved = link_targets.get(link_key(target))
            if resolved is not None and resolved != page.path:
                inbound[resolved] = inbound.get(resolved, 0) + 1
        if page.page_type == "source":
            # Advisory: inline markers denser than the prose signal citation clutter.
            # Markers on itemized `## Key claims` bullets are healthy (one per claim);
            # the defect is a marker on nearly every prose sentence.
            prose_lines = [ln for ln in page.body.splitlines() if ln.strip() and not _BULLET_RE.match(ln)]
            prose = "\n".join(prose_lines)
            prose_markers = len(_MARKER_RE.findall(prose))
            prose_sentences = len(_SENTENCE_END_RE.findall(prose))
            if prose_markers >= 3 and prose_sentences >= 3 and prose_markers * 5 >= prose_sentences * 4:
                findings.append(LintFinding(page.path, "marker_saturation", f"{prose_markers} inline markers across {prose_sentences} prose sentences; mark each claim once, not every sentence"))
        if page.page_type in DURABLE_TYPES:
            if not page.links:
                findings.append(LintFinding(page.path, "no_outgoing_links", "durable page links to no other wiki page"))

    for page in inventory.pages:
        if page.page_type in DURABLE_TYPES and inbound.get(page.path, 0) == 0:
            findings.append(LintFinding(page.path, "orphan", "no inbound links from other wiki pages"))
    for title, paths in titles.items():
        if len(paths) > 1:
            findings.append(LintFinding(paths[0], "duplicate_title", f"title {title!r} used by: {', '.join(paths)}"))

    return findings


def render_report(findings: list[LintFinding]) -> str:
    if not findings:
        return "lint: no findings\n"
    lines = [f"lint: {len(findings)} finding(s)\n"]
    for finding in findings:
        lines.append(f"- {finding.path}: [{finding.code}] {finding.message}\n")
    return "".join(lines)


def main() -> int:
    workspace = Workspace.from_path(None)
    print(render_report(lint_wiki(workspace)), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
