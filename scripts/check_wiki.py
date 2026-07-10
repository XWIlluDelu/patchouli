from __future__ import annotations

from dataclasses import dataclass
import re

from quotes import verify_source_quotes
from text_helpers import content_version_id, is_valid_work_id
from wiki_inventory import (
    DURABLE_TYPES,
    PAGE_DIRS,
    PAGE_TYPES,
    PageRecord,
    WikiInventory,
    link_key,
    link_target_map,
    page_type_for,
    parse_inline_list,
    scan_wiki,
    work_ids_from_text,
)
from workspace_paths import Workspace

TYPE_DIR = {page_type: page_dir for page_dir, page_type in PAGE_DIRS.items()}
SUPPORT_HEADING_RE = re.compile(r"^##\s+Supporting works\s*$", re.IGNORECASE | re.MULTILINE)
SUPPORT_TOKEN_RE = re.compile(r"`([^`]+)`")
SURFACE_SOURCE_RE = re.compile(r"^- Source:\s*(.+?)\s*$", re.MULTILINE)


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
    match = SUPPORT_HEADING_RE.search(body)
    if not match:
        return body, ""
    return body[: match.start()], body[match.start() :]


def support_work_ids(support_body: str) -> set[str]:
    found: set[str] = set()
    for token in SUPPORT_TOKEN_RE.findall(support_body):
        value = token.strip().strip("[]")
        if value:
            found.add(value)
    found.update(work_ids_from_text(support_body))
    return found


def _declared_work_ids(page: PageRecord) -> set[str]:
    return set(parse_inline_list(page.frontmatter.get("work_ids", "")))


def _source_work_ids(inventory: WikiInventory) -> set[str]:
    return {
        page.frontmatter.get("work_id", "").strip()
        for page in inventory.pages
        if page.page_type == "source" and page.frontmatter.get("work_id", "").strip()
    }


def _unresolved_work_issues(
    page: PageRecord, referenced: set[str], source_work_ids: set[str]
) -> list[CheckIssue]:
    return [
        CheckIssue(
            "work_id_unresolved",
            page.path,
            f"work id {work_id!r} has no source page",
            "cite only ingested works; ingest the source or remove the marker",
        )
        for work_id in sorted(referenced)
        if work_id not in source_work_ids
    ]


def _check_frontmatter(page: PageRecord) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    if not page.frontmatter.get("title", "").strip():
        issues.append(
            CheckIssue(
                "title_missing",
                page.path,
                "authored page has no explicit title frontmatter",
                "add `title: ...` to the page frontmatter",
            )
        )
    if not page.frontmatter.get("page_type", "").strip():
        issues.append(
            CheckIssue(
                "page_type_missing",
                page.path,
                "authored page has no explicit page_type frontmatter",
                "add the page type required by its wiki directory",
            )
        )
    return issues


def _check_source(
    page: PageRecord,
    seen_work_ids: dict[str, str],
    source_work_ids: set[str],
    workspace: Workspace,
) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    work_id = page.frontmatter.get("work_id", "").strip()
    version_id = page.frontmatter.get("version_id", "").strip()
    surface_rel = page.frontmatter.get("reading_surface", "").strip()

    if not work_id:
        issues.append(
            CheckIssue(
                "source_work_id_missing",
                page.path,
                "source page has no work_id frontmatter",
                "add `work_id: <id>` to the source frontmatter",
            )
        )
    elif not is_valid_work_id(work_id):
        issues.append(
            CheckIssue(
                "source_work_id_invalid",
                page.path,
                f"work_id {work_id!r} is not one path-safe segment",
                "use the work_id emitted by extract.py",
            )
        )
    elif work_id in seen_work_ids:
        issues.append(
            CheckIssue(
                "duplicate_work_id",
                page.path,
                f"work_id {work_id!r} already used by {seen_work_ids[work_id]}",
                "one source page per work; merge or rename",
            )
        )
    else:
        seen_work_ids[work_id] = page.path

    if not version_id:
        issues.append(
            CheckIssue(
                "source_version_id_missing",
                page.path,
                "source page has no version_id frontmatter",
                "add the version_id emitted by extract.py",
            )
        )
    if not page.frontmatter.get("source", "").strip():
        issues.append(
            CheckIssue(
                "source_locator_missing",
                page.path,
                "source page has no source locator frontmatter",
                "add the `source` value emitted by extract.py",
            )
        )
    body_work_ids = set(work_ids_from_text(page.body))
    if work_id and work_id not in body_work_ids:
        issues.append(
            CheckIssue(
                "source_marker_missing",
                page.path,
                f"source page has no inline (Work: {work_id}) marker",
                "mark each substantive claim once with `(Work: <id>)`; do not saturate prose",
            )
        )
    issues.extend(_unresolved_work_issues(page, body_work_ids, source_work_ids))

    expected_surface = f"extracted/{work_id}/text.md" if work_id else ""
    canonical = False
    if not surface_rel:
        issues.append(
            CheckIssue(
                "source_surface_unreadable",
                page.path,
                "source page has no reading_surface frontmatter",
                "add the reading_surface emitted by extract.py",
            )
        )
    elif expected_surface:
        try:
            canonical = workspace.relpath(workspace.abspath(surface_rel)) == expected_surface
        except ValueError:
            canonical = False
        if not canonical:
            issues.append(
                CheckIssue(
                    "source_surface_mismatch",
                    page.path,
                    f"reading_surface must be {expected_surface}",
                    "use the canonical surface emitted for this work_id; never bind another file",
                )
            )

    if canonical:
        try:
            surface_bytes = workspace.abspath(expected_surface).read_bytes()
            surface_text = surface_bytes.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            issues.append(
                CheckIssue(
                    "source_surface_unreadable",
                    page.path,
                    f"reading surface missing or unreadable: {exc}",
                    "restore the canonical extracted surface or correct the frontmatter",
                )
            )
        else:
            quote_result = verify_source_quotes(page, surface_text)
            for item in quote_result.get("unresolved", []):
                issues.append(
                    CheckIssue(
                        "quote_unresolved",
                        page.path,
                        f"quote not found verbatim in the reading surface: {item['quote']!r}",
                        "quote the source faithfully or drop the blockquote",
                    )
                )
            source_match = SURFACE_SOURCE_RE.search(surface_text)
            surface_source = source_match.group(1).strip() if source_match else ""
            declared_source = page.frontmatter.get("source", "").strip()
            if declared_source and declared_source != surface_source:
                issues.append(
                    CheckIssue(
                        "source_locator_mismatch",
                        page.path,
                        f"source locator {declared_source!r} does not match the reading surface {surface_source!r}",
                        "use the exact `source` value emitted by extract.py",
                    )
                )
            if version_id:
                surface_version = content_version_id(surface_bytes)
                if version_id != surface_version:
                    issues.append(
                        CheckIssue(
                            "source_version_stale",
                            page.path,
                            f"version_id {version_id} does not match the reading surface ({surface_version})",
                            f"re-read the surface, update the page, and set version_id: {surface_version}",
                        )
                    )
    return issues


def _work_list_issues(
    page: PageRecord, referenced: set[str], source_work_ids: set[str]
) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    declared = _declared_work_ids(page)
    if not declared:
        issues.append(
            CheckIssue(
                "work_ids_missing",
                page.path,
                "page has no declared work_ids frontmatter",
                "declare every cited work in `work_ids: [...]`",
            )
        )
    issues.extend(_unresolved_work_issues(page, referenced | declared, source_work_ids))
    if declared and declared != referenced:
        issues.append(
            CheckIssue(
                "work_ids_mismatch",
                page.path,
                f"declared work_ids {sorted(declared)!r} do not match cited/supporting ids {sorted(referenced)!r}",
                "make frontmatter, inline markers, and Supporting works name the same works",
            )
        )
    return issues


def _check_durable(page: PageRecord, source_work_ids: set[str]) -> list[CheckIssue]:
    issues: list[CheckIssue] = []
    claim_body, support_body = _split_support(page.body)
    inline_ids = set(work_ids_from_text(claim_body))
    if not inline_ids:
        issues.append(
            CheckIssue(
                "work_marker_missing",
                page.path,
                "durable page has no inline (Work: ...) marker on its claims",
                "mark each durable claim with (Work: <id>) or (Works: <id>, <id>)",
            )
        )
    if not support_body:
        issues.append(
            CheckIssue(
                "support_list_missing",
                page.path,
                "durable page has no ## Supporting works section",
                "end the page with a ## Supporting works list of backticked work ids",
            )
        )
    support_ids = support_work_ids(support_body)
    if support_body and inline_ids != support_ids:
        issues.append(
            CheckIssue(
                "support_work_ids_mismatch",
                page.path,
                f"inline work ids {sorted(inline_ids)!r} do not match Supporting works {sorted(support_ids)!r}",
                "cite every supporting work on a claim, and list every claim's work under Supporting works",
            )
        )
    referenced = inline_ids | support_ids
    issues.extend(_work_list_issues(page, referenced, source_work_ids))
    resolved = referenced & source_work_ids
    if page.page_type == "synthesis" and len(resolved) < 2:
        issues.append(
            CheckIssue(
                "single_work_synthesis",
                page.path,
                "synthesis rests on fewer than two resolved works",
                "a synthesis needs at least two works; widen support or no-op",
            )
        )
    return issues


def _check_answer(page: PageRecord, source_work_ids: set[str]) -> list[CheckIssue]:
    inline_ids = set(work_ids_from_text(page.body))
    issues: list[CheckIssue] = []
    if not inline_ids:
        issues.append(
            CheckIssue(
                "work_marker_missing",
                page.path,
                "answer has no inline work marker",
                "file an answer only when its evidence is cited with (Work: ...) markers",
            )
        )
    issues.extend(_work_list_issues(page, inline_ids, source_work_ids))
    return issues


def check_issues(
    workspace: Workspace, inventory: WikiInventory | None = None
) -> list[CheckIssue]:
    """Return objective structural and provenance failures for the compiled wiki."""

    inventory = inventory or scan_wiki(workspace)
    issues: list[CheckIssue] = [
        CheckIssue(
            "unreadable",
            problem.split(":")[0],
            problem,
            "the file is not valid UTF-8 markdown; rewrite it",
        )
        for problem in inventory.problems
    ]
    seen_work_ids: dict[str, str] = {}
    source_work_ids = _source_work_ids(inventory)
    link_targets = link_target_map(inventory)

    for page in inventory.pages:
        path_type = page_type_for(workspace, workspace.abspath(page.path))
        if path_type == "index" and page.page_type == "index":
            continue
        issues.extend(_check_frontmatter(page))
        if page.page_type not in PAGE_TYPES:
            issues.append(
                CheckIssue(
                    "unknown_page_type",
                    page.path,
                    f"unknown page_type {page.page_type!r}",
                    "write only source/concept/entity/synthesis/answer/hub pages",
                )
            )
            continue
        expected_dir = TYPE_DIR.get(page.page_type)
        if expected_dir and not page.path.startswith(f"wiki/{expected_dir}/"):
            issues.append(
                CheckIssue(
                    "page_type_path_mismatch",
                    page.path,
                    f"page_type {page.page_type!r} does not match its directory",
                    f"move it under wiki/{expected_dir}/ or fix page_type",
                )
            )
        for target in page.links:
            if link_key(target) not in link_targets:
                issues.append(
                    CheckIssue(
                        "broken_link",
                        page.path,
                        f"link target not found: {target}",
                        "link to an existing page title, alias, source work_id, or file stem",
                    )
                )
        if page.page_type == "source":
            issues.extend(_check_source(page, seen_work_ids, source_work_ids, workspace))
        elif page.page_type in DURABLE_TYPES:
            issues.extend(_check_durable(page, source_work_ids))
        elif page.page_type == "answer":
            issues.extend(_check_answer(page, source_work_ids))
    return issues


def check_wiki(workspace: Workspace) -> list[str]:
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
    authored = [
        page
        for page in inventory.pages
        if not (
            page_type_for(workspace, workspace.abspath(page.path)) == "index"
            and page.page_type == "index"
        )
    ]
    print(f"wiki checks passed: {len(authored)} authored page(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
