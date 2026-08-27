from __future__ import annotations

"""Advisory review candidates when compiled source pages have changed.

Answers and durable pages depend on their declared work_ids. A source page may
also contain cross-work judgment under ``## Tensions``; work markers other than
its own canonical work_id are dependencies as well. A changed dependency means
"review this page", never "this page is wrong".
"""

import argparse
from dataclasses import dataclass
import json
import subprocess
from typing import Any

from wiki_inventory import PageRecord, WikiInventory, scan_wiki, work_ids_from_text
from workspace_paths import Workspace

REVIEWABLE_TYPES = {"source", "answer", "concept", "entity", "synthesis"}


@dataclass(frozen=True)
class StaleFinding:
    page: str
    work_id: str
    source_page: str
    page_commit: str
    previous_blob: str | None
    current_blob: str | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "work_id": self.work_id,
            "source_page": self.source_page,
            "page_commit": self.page_commit,
            "previous_blob": self.previous_blob,
            "current_blob": self.current_blob,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class StaleReport:
    available: bool
    findings: tuple[StaleFinding, ...]
    skipped_dirty_pages: tuple[str, ...] = ()
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "findings": [finding.to_dict() for finding in self.findings],
            "skipped_dirty_pages": list(self.skipped_dirty_pages),
            "message": self.message,
        }


def _git(workspace: Workspace, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            [
                "git",
                "-C",
                str(workspace.root),
                "-c",
                "core.quotepath=false",
                *args,
            ],
            check=True,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None


def _last_commit(workspace: Workspace, path: str) -> str | None:
    result = _git(workspace, "log", "-1", "--format=%H", "--", path)
    value = result.stdout.strip() if result is not None else ""
    return value or None


def _blob_at(workspace: Workspace, commit: str, path: str) -> str | None:
    result = _git(workspace, "rev-parse", f"{commit}:{path}")
    value = result.stdout.strip() if result is not None else ""
    return value or None


def _working_blob(workspace: Workspace, path: str) -> str | None:
    absolute = workspace.root / path
    if not absolute.is_file():
        return None
    result = _git(workspace, "hash-object", "--", path)
    value = result.stdout.strip() if result is not None else ""
    return value or None


def _is_dirty(workspace: Workspace, path: str) -> bool:
    result = _git(
        workspace,
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--",
        path,
    )
    return bool(result and result.stdout.strip())


def _source_pages(inventory: WikiInventory) -> dict[str, PageRecord]:
    pages: dict[str, PageRecord] = {}
    for page in inventory.pages:
        if page.page_type != "source":
            continue
        work_id = page.frontmatter.get("work_id", "").strip()
        if work_id:
            pages[work_id] = page
    return pages


def dependency_work_ids(page: PageRecord) -> tuple[str, ...]:
    """Return works whose compiled source pages this page must be reviewed against."""

    if page.page_type == "source":
        own = page.frontmatter.get("work_id", "").strip()
        return tuple(
            sorted(work_id for work_id in set(work_ids_from_text(page.body)) if work_id != own)
        )
    return tuple(sorted(set(page.work_ids)))


def stale_report(
    workspace: Workspace, inventory: WikiInventory | None = None
) -> StaleReport:
    if _git(workspace, "rev-parse", "--verify", "HEAD") is None:
        return StaleReport(
            available=False,
            findings=(),
            message="Git history is unavailable; stale dependencies cannot be compared.",
        )

    inventory = inventory or scan_wiki(workspace)
    sources = _source_pages(inventory)
    findings: list[StaleFinding] = []
    skipped: list[str] = []

    pages = sorted(
        (page for page in inventory.pages if page.page_type in REVIEWABLE_TYPES),
        key=lambda page: page.path,
    )
    for page in pages:
        dependencies = dependency_work_ids(page)
        if not dependencies:
            continue
        # An uncommitted page is an active draft, not a historical artifact to review.
        if _is_dirty(workspace, page.path):
            skipped.append(page.path)
            continue
        page_commit = _last_commit(workspace, page.path)
        if page_commit is None:
            skipped.append(page.path)
            continue
        for work_id in dependencies:
            source = sources.get(work_id)
            if source is None:
                continue  # check_wiki owns unresolved work ids.
            previous_blob = _blob_at(workspace, page_commit, source.path)
            current_blob = _working_blob(workspace, source.path)
            if previous_blob == current_blob and previous_blob is not None:
                continue
            if previous_blob is None:
                reason = "source_not_present_at_page_revision"
            elif current_blob is None:
                reason = "source_page_missing"
            else:
                reason = "source_page_changed"
            findings.append(
                StaleFinding(
                    page=page.path,
                    work_id=work_id,
                    source_page=source.path,
                    page_commit=page_commit,
                    previous_blob=previous_blob,
                    current_blob=current_blob,
                    reason=reason,
                )
            )

    return StaleReport(
        available=True,
        findings=tuple(findings),
        skipped_dirty_pages=tuple(skipped),
    )


def render_report(report: StaleReport) -> str:
    if not report.available:
        return f"stale: unavailable — {report.message}\n"
    if not report.findings:
        lines = ["stale: no review candidates\n"]
    else:
        pages = len({finding.page for finding in report.findings})
        lines = [
            f"stale: {len(report.findings)} changed source dependency/dependencies "
            f"across {pages} page(s)\n"
        ]
        for finding in report.findings:
            lines.append(
                f"- {finding.page}: work {finding.work_id!r} changed in "
                f"{finding.source_page} since {finding.page_commit[:12]} "
                f"[{finding.reason}]\n"
            )
    if report.skipped_dirty_pages:
        lines.append(
            "- skipped uncommitted review page(s): "
            + ", ".join(report.skipped_dirty_pages)
            + "\n"
        )
    return "".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Advisory scan for knowledge pages whose compiled sources changed"
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)
    report = stale_report(Workspace.from_path(None))
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(render_report(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
