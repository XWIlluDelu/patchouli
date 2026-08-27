from __future__ import annotations

import json
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from stale import (  # noqa: E402
    REVIEW_STATE_REL,
    StaleStateError,
    acknowledge_reviews,
    stale_report,
)
from wiki_inventory import PageRecord, WikiInventory  # noqa: E402
from workspace_paths import Workspace  # noqa: E402


class StaleAcknowledgements(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ws = Workspace.from_path(self.root)
        self.git("init", "-q")
        self.git("config", "user.name", "Patchouli Test")
        self.git("config", "user.email", "patchouli@example.test")
        self.git("config", "commit.gpgsign", "false")
        self.put("wiki/sources/work.md", "source v1\n")
        self.put("wiki/answers/answer.md", "answer\n")
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

    def page(self, path: str, page_type: str, *, work_ids=(), work_id=None):
        return PageRecord(
            path=path,
            wiki_path=path.removeprefix("wiki/"),
            page_type=page_type,
            title=Path(path).stem,
            aliases=(),
            work_ids=tuple(work_ids),
            frontmatter={"work_id": work_id} if work_id else {},
            body="",
            links=(),
        )

    def inventory(self):
        return WikiInventory(
            pages=(
                self.page("wiki/sources/work.md", "source", work_id="work"),
                self.page("wiki/answers/answer.md", "answer", work_ids=("work",)),
            )
        )

    def refresh(self, text: str = "source v2\n") -> None:
        self.put("wiki/sources/work.md", text)
        self.git("add", "--", "wiki/sources/work.md")
        self.git("commit", "-q", "-m", "refresh source")

    def test_acknowledgement_consumes_no_change_review_without_touching_page(self):
        self.refresh()
        inventory = self.inventory()
        self.assertEqual(len(stale_report(self.ws, inventory).findings), 1)
        before = (self.root / "wiki/answers/answer.md").read_bytes()
        acknowledged = acknowledge_reviews(
            self.ws, "wiki/answers/answer.md", inventory=inventory
        )
        self.assertEqual(acknowledged, ("work",))
        self.assertEqual((self.root / "wiki/answers/answer.md").read_bytes(), before)
        self.assertEqual(stale_report(self.ws, inventory).findings, ())
        state = json.loads((self.root / REVIEW_STATE_REL).read_text())
        self.assertIn("work", state["reviews"]["wiki/answers/answer.md"])

        self.git("add", "--", REVIEW_STATE_REL)
        self.git("commit", "-q", "-m", "maintain: reviewed answer")
        self.assertEqual(stale_report(self.ws, inventory).findings, ())

    def test_later_source_change_reopens_acknowledged_candidate(self):
        self.refresh()
        inventory = self.inventory()
        acknowledge_reviews(self.ws, "wiki/answers/answer.md", inventory=inventory)
        self.git("add", "--", REVIEW_STATE_REL)
        self.git("commit", "-q", "-m", "maintain: reviewed answer")
        self.refresh("source v3\n")
        findings = stale_report(self.ws, inventory).findings
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].work_id, "work")

    def test_acknowledgement_refuses_uncommitted_source(self):
        self.put("wiki/sources/work.md", "source draft\n")
        inventory = self.inventory()
        self.assertEqual(len(stale_report(self.ws, inventory).findings), 1)
        with self.assertRaisesRegex(StaleStateError, "commit the source"):
            acknowledge_reviews(self.ws, "wiki/answers/answer.md", inventory=inventory)

    def test_malformed_sidecar_never_silently_suppresses_findings(self):
        self.refresh()
        self.put(REVIEW_STATE_REL, "not json\n")
        report = stale_report(self.ws, self.inventory())
        self.assertFalse(report.available)
        self.assertIn(REVIEW_STATE_REL, report.message)


if __name__ == "__main__":
    unittest.main()
