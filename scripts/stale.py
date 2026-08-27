from __future__ import annotations

"""Advisory review candidates when compiled source pages have changed.

A derived page is a candidate when the current source-page blob for one of its
works differs from the blob that existed at the derived page's last commit. A
review that keeps the page unchanged can acknowledge the current source blob in
a small tracked sidecar so the queue is consumed without rewriting knowledge.
"""

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable

from file_state import atomic_write_text
from wiki_inventory import PageRecord, WikiInventory, scan_wiki
from workspace_paths import Workspace

DERIVED_TYPES = {"answer", "concept", "entity", "synthesis"}
REVIEW_STATE_REL = "wiki/.stale-reviews.json"
REVIEW_SCHEMA_VERSION = 1
_BLOB_RE = re.compile(r"[0-9a-f]{40,64}\Z")


class StaleStateError(ValueError):
    """The acknowledgement sidecar or requested review operation is invalid."""


@dataclass(frozen=True)
class StaleFinding:
    page: str
    work_id: str
    source_page: str
    derived_commit: str
    previous_blob: str | None
    current_blob: str | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "work_id": self.work_id,
            "source_page": self.source_page,
            "derived_commit": self.derived_commit,
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


def _derived_pages(inventory: WikiInventory) -> dict[str, PageRecord]:
    return {
        page.path: page
        for page in inventory.pages
        if page.page_type in DERIVED_TYPES
    }


def _review_state_path(workspace: Workspace) -> Path:
    return workspace.root / REVIEW_STATE_REL


def _load_review_state(workspace: Workspace) -> dict[str, dict[str, str]]:
    path = _review_state_path(workspace)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StaleStateError(f"could not read {REVIEW_STATE_REL}: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != REVIEW_SCHEMA_VERSION:
        raise StaleStateError(
            f"{REVIEW_STATE_REL} must have schema_version {REVIEW_SCHEMA_VERSION}"
        )
    reviews = raw.get("reviews")
    if not isinstance(reviews, dict):
        raise StaleStateError(f"{REVIEW_STATE_REL}: reviews must be an object")

    normalized: dict[str, dict[str, str]] = {}
    for page, works in reviews.items():
        if not isinstance(page, str) or not isinstance(works, dict):
            raise StaleStateError(
                f"{REVIEW_STATE_REL}: each page review must be an object"
            )
        page_reviews: dict[str, str] = {}
        for work_id, blob in works.items():
            if (
                not isinstance(work_id, str)
                or not isinstance(blob, str)
                or not _BLOB_RE.fullmatch(blob)
            ):
                raise StaleStateError(
                    f"{REVIEW_STATE_REL}: invalid acknowledgement for {page!r}"
                )
            page_reviews[work_id] = blob
        if page_reviews:
            normalized[page] = page_reviews
    return normalized


def _prune_reviews(
    reviews: dict[str, dict[str, str]], inventory: WikiInventory
) -> dict[str, dict[str, str]]:
    pages = _derived_pages(inventory)
    pruned: dict[str, dict[str, str]] = {}
    for path, works in reviews.items():
        page = pages.get(path)
        if page is None:
            continue
        valid = set(page.work_ids)
        kept = {work_id: blob for work_id, blob in works.items() if work_id in valid}
        if kept:
            pruned[path] = kept
    return pruned


def _write_review_state(
    workspace: Workspace, reviews: dict[str, dict[str, str]]
) -> None:
    payload = {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "reviews": {
            page: dict(sorted(works.items()))
            for page, works in sorted(reviews.items())
        },
    }
    atomic_write_text(
        _review_state_path(workspace),
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


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
    try:
        reviews = _load_review_state(workspace)
    except StaleStateError as exc:
        return StaleReport(available=False, findings=(), message=str(exc))
    sources = _source_pages(inventory)
    findings: list[StaleFinding] = []
    skipped: list[str] = []
    current_blobs: dict[str, str | None] = {}
    source_dirty: dict[str, bool] = {}

    derived_pages = sorted(_derived_pages(inventory).values(), key=lambda page: page.path)
    for page in derived_pages:
        # An uncommitted page is an active draft, not a historical artifact to review.
        if _is_dirty(workspace, page.path):
            skipped.append(page.path)
            continue
        derived_commit = _last_commit(workspace, page.path)
        if derived_commit is None:
            skipped.append(page.path)
            continue
        for work_id in sorted(set(page.work_ids)):
            source = sources.get(work_id)
            if source is None:
                continue  # check_wiki owns unresolved work ids.
            if source.path not in current_blobs:
                current_blobs[source.path] = _working_blob(workspace, source.path)
                source_dirty[source.path] = _is_dirty(workspace, source.path)
            current_blob = current_blobs[source.path]
            acknowledged = reviews.get(page.path, {}).get(work_id)
            if (
                current_blob is not None
                and not source_dirty[source.path]
                and acknowledged == current_blob
            ):
                continue
            previous_blob = _blob_at(workspace, derived_commit, source.path)
            if previous_blob == current_blob and previous_blob is not None:
                continue
            if previous_blob is None:
                reason = "source_not_present_at_derived_revision"
            elif current_blob is None:
                reason = "source_page_missing"
            else:
                reason = "source_page_changed"
            findings.append(
                StaleFinding(
                    page=page.path,
                    work_id=work_id,
                    source_page=source.path,
                    derived_commit=derived_commit,
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


def _normalize_page_path(workspace: Workspace, value: str) -> str:
    try:
        path = workspace.abspath(value)
        rel = workspace.relpath(path)
    except ValueError as exc:
        raise StaleStateError(str(exc)) from exc
    if not path.is_file():
        raise StaleStateError(f"derived page does not exist: {rel}")
    return rel


def acknowledge_reviews(
    workspace: Workspace,
    page_path: str,
    *,
    work_ids: Iterable[str] | None = None,
    inventory: WikiInventory | None = None,
) -> tuple[str, ...]:
    """Acknowledge current stale findings after an evidence-grounded no-change review."""

    inventory = inventory or scan_wiki(workspace)
    page_path = _normalize_page_path(workspace, page_path)
    page = _derived_pages(inventory).get(page_path)
    if page is None:
        raise StaleStateError(
            f"acknowledgements apply only to committed answers/concepts/entities/syntheses: "
            f"{page_path}"
        )
    if _is_dirty(workspace, page.path):
        raise StaleStateError(
            f"refusing to acknowledge an uncommitted derived page: {page.path}"
        )

    report = stale_report(workspace, inventory)
    if not report.available:
        raise StaleStateError(report.message)
    candidates = {
        finding.work_id: finding
        for finding in report.findings
        if finding.page == page.path
    }
    requested = tuple(dict.fromkeys(work_ids or candidates))
    if not requested:
        return ()
    unknown = [work_id for work_id in requested if work_id not in candidates]
    if unknown:
        raise StaleStateError(
            f"not current stale candidate(s) for {page.path}: {', '.join(unknown)}"
        )

    for work_id in requested:
        finding = candidates[work_id]
        if finding.current_blob is None:
            raise StaleStateError(
                f"cannot acknowledge missing source page for work {work_id!r}"
            )
        if _is_dirty(workspace, finding.source_page):
            raise StaleStateError(
                f"commit the source page before acknowledging its review: "
                f"{finding.source_page}"
            )

    reviews = _prune_reviews(_load_review_state(workspace), inventory)
    page_reviews = reviews.setdefault(page.path, {})
    for work_id in requested:
        current_blob = candidates[work_id].current_blob
        assert current_blob is not None
        page_reviews[work_id] = current_blob
    _write_review_state(workspace, reviews)
    return requested


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
                f"{finding.source_page} since {finding.derived_commit[:12]} "
                f"[{finding.reason}]\n"
            )
    if report.skipped_dirty_pages:
        lines.append(
            "- skipped uncommitted derived page(s): "
            + ", ".join(report.skipped_dirty_pages)
            + "\n"
        )
    return "".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Advisory scan for derived pages whose compiled sources changed"
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--acknowledge",
        metavar="PAGE",
        help="record that a stale page was reviewed and remains valid",
    )
    parser.add_argument(
        "--work-id",
        action="append",
        default=[],
        help="acknowledge one current work dependency (repeatable; default: all for PAGE)",
    )
    args = parser.parse_args(argv)
    workspace = Workspace.from_path(None)

    if args.acknowledge:
        if args.json:
            parser.error("--json cannot be combined with --acknowledge")
        try:
            acknowledged = acknowledge_reviews(
                workspace,
                args.acknowledge,
                work_ids=args.work_id or None,
            )
        except StaleStateError as exc:
            print(f"stale acknowledgement failed: {exc}", file=sys.stderr)
            return 2
        if not acknowledged:
            print(f"stale: no current review candidates for {args.acknowledge}")
            return 0
        print(
            f"stale: acknowledged {', '.join(acknowledged)} for {args.acknowledge}\n"
            f"commit {REVIEW_STATE_REL} with this maintenance operation"
        )
        return 0

    if args.work_id:
        parser.error("--work-id requires --acknowledge")
    report = stale_report(workspace)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(render_report(report), end="")
    return 0 if report.available else 1


if __name__ == "__main__":
    raise SystemExit(main())
