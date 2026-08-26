from __future__ import annotations

import subprocess
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from stale import stale_report  # noqa: E402
from wiki_inventory import PageRecord, WikiInventory  # noqa: E402
from workspace_paths import Workspace  # noqa: E402


class StaleDependencies(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ws = Workspace.from_path(self.root)
        self.git("init", "-q")
        self.git("config", "user.name", "Patchouli Test")
        self.git("config", "user.email", "patchouli@example.test")
        self.git("config", "commit.gpgsign", "false")
        self.put("wiki/sources/work.md", "source v1\n")
        self.put("wiki/sources/other.md", "other v1\n")
        self.put("wiki/answers/answer.md", "answer\n")
        self.put("wiki/concepts/draft.md", "draft\n")
        self.git("add", "--", "wiki")
        self.git("commit", "-q", "-m", "baseline")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    def put(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def page(
        self,
        path: str,
        page_type: str,
        *,
        work_ids: tuple[str, ...] = (),
        work_id: str | None = None,
    ) -> PageRecord:
        frontmatter = {"work_id": work_id} if work_id else {}
        return PageRecord(
            path=path,
            wiki_path=path.removeprefix("wiki/"),
            page_type=page_type,
            title=Path(path).stem,
            aliases=(),
            work_ids=work_ids,
            frontmatter=frontmatter,
            body="",
            links=(),
        )

    def inventory(self, *, include_draft: bool = False) -> WikiInventory:
        pages = [
            self.page("wiki/sources/work.md", "source", work_id="work"),
            self.page("wiki/sources/other.md", "source", work_id="other"),
            self.page("wiki/answers/answer.md", "answer", work_ids=("work",)),
        ]
        if include_draft:
            pages.append(
                self.page("wiki/concepts/draft.md", "concept", work_ids=("work",))
            )
        return WikiInventory(pages=tuple(pages))

    def test_unchanged_source_is_clean(self):
        report = stale_report(self.ws, self.inventory())
        self.assertTrue(report.available)
        self.assertEqual(report.findings, ())

    def test_uncommitted_source_change_marks_derived_page(self):
        self.put("wiki/sources/work.md", "source v2\n")
        report = stale_report(self.ws, self.inventory())
        self.assertEqual(len(report.findings), 1)
        finding = report.findings[0]
        self.assertEqual(finding.page, "wiki/answers/answer.md")
        self.assertEqual(finding.work_id, "work")
        self.assertEqual(finding.reason, "source_page_changed")

    def test_committed_source_change_stays_stale_until_page_is_revised(self):
        self.put("wiki/sources/work.md", "source v2\n")
        self.git("add", "--", "wiki/sources/work.md")
        self.git("commit", "-q", "-m", "refresh source")
        self.assertEqual(len(stale_report(self.ws, self.inventory()).findings), 1)

        self.put("wiki/answers/answer.md", "answer reviewed against v2\n")
        self.git("add", "--", "wiki/answers/answer.md")
        self.git("commit", "-q", "-m", "maintain answer")
        self.assertEqual(stale_report(self.ws, self.inventory()).findings, ())

    def test_unreferenced_source_change_is_ignored(self):
        self.put("wiki/sources/other.md", "other v2\n")
        report = stale_report(self.ws, self.inventory())
        self.assertEqual(report.findings, ())

    def test_dirty_derived_page_is_skipped(self):
        self.put("wiki/concepts/draft.md", "active edit\n")
        self.put("wiki/sources/work.md", "source v2\n")
        report = stale_report(self.ws, self.inventory(include_draft=True))
        self.assertIn("wiki/concepts/draft.md", report.skipped_dirty_pages)
        self.assertEqual(
            [finding.page for finding in report.findings],
            ["wiki/answers/answer.md"],
        )

    def test_without_git_history_reports_unavailable(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        report = stale_report(Workspace.from_path(tmp.name), WikiInventory(pages=()))
        self.assertFalse(report.available)
        self.assertEqual(report.findings, ())


if __name__ == "__main__":
    unittest.main()
