from __future__ import annotations

from dataclasses import dataclass
import re

from quotes import verify_source_quotes
from wiki_inventory import (
    DURABLE_TYPES,
    PAGE_DIRS,
    PAGE_TYPES,
    PageRecord,
    WikiInventory,
    link_key,
    link_target_map,
    scan_wiki,
    work_ids_from_text,
)
from workspace_paths import Workspace

# Page type -> its directory, e.g. concept -> concepts.
TYPE_DIR = {ptype: pdir for pdir, ptype in PAGE_DIRS.items()}
SUPPORT_HEADING_RE = re.compile(r"^##\s+Supporting works\s*$", re.IGNORECASE | re.MULTILINE)
SUPPORT_TOKEN_RE = re.compile(r"`([^`]+)`")
WORKS_MARKER_RE = re.compile(r"\(Works?:\s*([^)]+)\)")
# Workflow/process phrases that must not pollute a source card.
SOURCE_POLLUTION_PHRASES = (
    "suggested wiki update",
    "maintenance note",
    "integration note",
    "navigation recommendation",
    "todo:",
)


@dataclass(frozen=True)
class CheckIssue:
    """One binding verifier failure. ``fix`` is addressed to the writing agent."""

    code: str
    path: str
    message: str
    fix: str

    def render(self) -> str:
        return f"{self.path}: [{self.code}] {self.message}"

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message, "fix": self.fix}


def _split_support(body: str) -> tuple[str, str]:
    """Return (claim_body, support_body) split at the ``## Supporting works`` heading."""

    match = SUPPORT_HEADING_RE.search(body)
    if not match:
        return body, ""
    return body[: match.start()], body[match.start() :]


def support_work_ids(support_body: str) -> set[str]:
    """Work ids named in a support section: backticked tokens and (Works: ...) markers."""

    found: set[str] = set()
    for token in SUPPORT_TOKEN_RE.findall(support_body):
        value = token.strip().strip("[]")
        if value:
            found.add(value)
    for marker in WORKS_MARKER_RE.finditer(support_body):
        for part in re.split(r"\s*(?:,|;|\s+and\s+)\s*", marker.group(1)):
            value = part.strip().strip("`[]")
            if value:
                found.add(value)
    return found


def _source_work_ids(inventory: WikiInventory) -> set[str]:
    ids: set[str] = set()
    for page in inventory.pages:
        if page.page_type == "source":
            work_id = page.frontmatter.get("work_id", "").strip()
            if work_id:
                ids.add(work_id)
    return ids


def _check_source(page: PageRecord, seen_work_ids: dict[str, str], workspace: Workspace) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    work_id = page.frontmatter.get("work_id", "").strip()
    version_id = page.frontmatter.get("version_id", "").strip()
    if not work_id:
        issues.append(CheckIssue("source_work_id_missing", page.path, "source page has no work_id frontmatter", "add `work_id: <id>` to the source frontmatter"))
    elif work_id in seen_work_ids:
        issues.append(CheckIssue("duplicate_work_id", page.path, f"work_id {work_id!r} already used by {seen_work_ids[work_id]}", "one source page per work; merge or rename"))
    else:
        seen_work_ids[work_id] = page.path
    if not version_id:
        issues.append(CheckIssue("source_version_id_missing", page.path, "source page has no version_id frontmatter", "add `version_id: <id>` to the source frontmatter"))
    if work_id and work_id not in set(work_ids_from_text(page.body)):
        issues.append(CheckIssue("source_marker_missing", page.path, f"source page has no inline (Work: {work_id}) marker", "mark one key source claim with `(Work: <id>)`; one marker is enough, do not saturate"))
    body_lower = page.body.lower()
    for phrase in SOURCE_POLLUTION_PHRASES:
        if phrase in body_lower:
            issues.append(CheckIssue("source_pollution", page.path, f"source card contains workflow phrase {phrase!r}", "source cards record the source only; drop wiki/maintenance/navigation instructions"))
    quote_result = verify_source_quotes(workspace, page)
    if "error" in quote_result:
        # A source page's reading surface is its provenance anchor and the authority for
        # quote checks, so it must be present and readable whether or not the page quotes
        # yet. Gating this on quote presence would let a broken surface sit unnoticed
        # until someone added a quote.
        issues.append(CheckIssue("source_surface_unreadable", page.path, f"reading surface missing or unreadable: {quote_result['error']}", "add `reading_surface: <extracted/.../text.md>` to the source frontmatter or fix the path"))
    else:
        for item in quote_result.get("unresolved", []):
            issues.append(CheckIssue("quote_unresolved", page.path, f"quote not found verbatim in the reading surface: {item['quote']!r}", "quote the source verbatim or drop the blockquote; the normalizer already folds emphasis, curly quotes, and formula drift"))
    return issues


def _check_durable(page: PageRecord, source_work_ids: set[str]) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    claim_body, support_body = _split_support(page.body)
    inline_ids = set(work_ids_from_text(claim_body))
    if not inline_ids:
        issues.append(CheckIssue("work_marker_missing", page.path, "durable page has no inline (Work: ...) marker on its claims", "mark each durable claim with (Work: <id>) or (Works: <id>, <id>)"))
    if not support_body:
        issues.append(CheckIssue("support_list_missing", page.path, "durable page has no ## Supporting works section", "end the page with a ## Supporting works list of backticked work ids"))
    referenced = inline_ids | support_work_ids(support_body)
    for work_id in sorted(referenced):
        if work_id not in source_work_ids:
            issues.append(CheckIssue("work_id_unresolved", page.path, f"work id {work_id!r} has no source page", "cite only ingested works; ingest the source or remove the marker"))
    if page.page_type == "synthesis" and len({wid for wid in referenced if wid in source_work_ids}) < 2:
        issues.append(CheckIssue("single_work_synthesis", page.path, "synthesis rests on fewer than two resolved works", "a synthesis needs >=2 works; widen support or no-op with a reason"))
    return issues


def check_issues(workspace: Workspace, inventory: WikiInventory | None = None) -> list[CheckIssue]:
    """Binding verifier: the structural and provenance failures that must be fixed
    before a page is publishable. Stylistic depth stays advisory in ``lint``."""

    inventory = inventory or scan_wiki(workspace)
    issues: list[CheckIssue] = [
        CheckIssue("unreadable", problem.split(":")[0], problem, "the file is not valid UTF-8 markdown; rewrite it")
        for problem in inventory.problems
    ]
    seen_work_ids: dict[str, str] = {}
    source_work_ids = _source_work_ids(inventory)
    link_targets = link_target_map(inventory)
    for page in inventory.pages:
        if page.page_type not in PAGE_TYPES:
            issues.append(CheckIssue("unknown_page_type", page.path, f"unknown page_type {page.page_type!r}", "write only source/concept/entity/synthesis/answer/hub pages"))
            continue
        if page.page_type == "index":
            continue
        expected_dir = TYPE_DIR.get(page.page_type)
        if expected_dir and not page.path.startswith(f"wiki/{expected_dir}/"):
            issues.append(CheckIssue("page_type_path_mismatch", page.path, f"page_type {page.page_type!r} does not match its directory", f"move it under wiki/{expected_dir}/ or fix page_type"))
        for target in page.links:
            if link_key(target) not in link_targets:
                issues.append(CheckIssue("broken_link", page.path, f"link target not found: {target}", "link to an existing page title, alias, source work_id, or file stem"))
        if page.page_type == "source":
            issues.extend(_check_source(page, seen_work_ids, workspace))
        elif page.page_type in DURABLE_TYPES:
            issues.extend(_check_durable(page, source_work_ids))
    return issues


def check_wiki(workspace: Workspace) -> list[str]:
    """Rendered binding failures; empty list means the wiki passes."""

    return [issue.render() for issue in check_issues(workspace)]


def main() -> int:
    workspace = Workspace.from_path(None)
    inventory = scan_wiki(workspace)
    issues = check_issues(workspace, inventory)
    if issues:
        print("wiki checks failed:")
        for issue in issues:
            print(f"- {issue.render()}")
        return 1
    print(f"wiki checks passed: {len(inventory.pages)} page(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
