"""Tests for the binding floor — the durable, compounding half of the logistics.

check_wiki.py enforces the objective invariants every Patchouli write trusts: quote
faithfulness against the reading surface, the reading surface as provenance anchor,
work-id resolution, and the structural rules. That trust is only as good as the floor
is correct, so the floor is the code most worth a regression net. These build a
throwaway workspace per case and assert which CheckIssue codes fire.

Run from the repo root:  python3 -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from check_wiki import check_issues            # noqa: E402
from workspace_paths import Workspace          # noqa: E402

SURFACE = (
    "The recurrent networks process tokens sequentially and the model "
    "achieves strong results on the benchmark.\n"
)


class BindingFloor(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ws = Workspace.from_path(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def put(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def put_surface(self, work_id: str, text: str = SURFACE) -> None:
        self.put(f"extracted/{work_id}/text.md", text)

    def source(self, work_id: str = "1706", *, marker: bool = True, surface: str | None = "auto",
               version: str = "sha256-x", extra_body: str = "", quote: str | None = None) -> str:
        fm = ["title: Paper", "page_type: source", f"work_id: {work_id}", f"version_id: {version}"]
        if surface == "auto":
            fm.append(f"reading_surface: extracted/{work_id}/text.md")
        elif surface is not None:
            fm.append(f"reading_surface: {surface}")
        body = ["# Paper", ""]
        if marker:
            body.append(f"- a checkable claim (Work: {work_id})")
        if quote:
            body += ["", f"> {quote}"]
        if extra_body:
            body += ["", extra_body]
        return "---\n" + "\n".join(fm) + "\n---\n\n" + "\n".join(body) + "\n"

    def durable(self, page_type: str, dirname: str, *, body: str) -> None:
        self.put(f"wiki/{dirname}/d.md", f"---\ntitle: D\npage_type: {page_type}\n---\n\n# D\n\n{body}\n")

    def codes(self) -> set[str]:
        return {issue.code for issue in check_issues(self.ws)}

    # --- quote verification ------------------------------------------------

    def test_clean_source_with_faithful_quote_passes(self):
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source(quote="the model achieves strong results on the benchmark"))
        self.assertEqual(self.codes(), set())

    def test_fabricated_quote_with_absent_token_fails(self):
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source(quote="the model achieves strong results on the zebra benchmark"))
        self.assertIn("quote_unresolved", self.codes())

    def test_subsequence_of_present_tokens_passes(self):
        # Characterizes the accepted limit now stated honestly in quotes.py: matching is
        # token-subsequence containment, so tokens present in order but not contiguous
        # pass. If someone tightens the matcher, this test should be revisited, not
        # silently broken.
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source(quote="recurrent networks tokens model results"))
        self.assertNotIn("quote_unresolved", self.codes())

    # --- reading surface as provenance anchor (issue #3) -------------------

    def test_missing_reading_surface_fails_even_without_quotes(self):
        self.put("wiki/sources/p.md", self.source(surface=None))
        self.assertIn("source_surface_unreadable", self.codes())

    def test_unreadable_reading_surface_fails_without_quotes(self):
        self.put("wiki/sources/p.md", self.source(surface="extracted/ghost/text.md"))
        self.assertIn("source_surface_unreadable", self.codes())

    def test_valid_source_without_quotes_passes(self):
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source())
        self.assertEqual(self.codes(), set())

    # --- source provenance -------------------------------------------------

    def test_missing_work_id(self):
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source().replace("work_id: 1706\n", ""))
        self.assertIn("source_work_id_missing", self.codes())

    def test_duplicate_work_id(self):
        self.put_surface("1706")
        self.put("wiki/sources/a.md", self.source())
        self.put("wiki/sources/b.md", self.source())
        self.assertIn("duplicate_work_id", self.codes())

    def test_missing_inline_marker(self):
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source(marker=False))
        self.assertIn("source_marker_missing", self.codes())

    def test_missing_version_id(self):
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source().replace("version_id: sha256-x\n", ""))
        self.assertIn("source_version_id_missing", self.codes())

    def test_source_pollution_phrase(self):
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source(extra_body="TODO: revisit this"))
        self.assertIn("source_pollution", self.codes())

    # --- durable pages -----------------------------------------------------

    def test_single_work_synthesis(self):
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source())
        self.durable("synthesis", "syntheses",
                     body="## Thesis\n\nclaim (Work: 1706)\n\n## Supporting works\n\n- Paper — `1706`")
        self.assertIn("single_work_synthesis", self.codes())

    def test_unresolved_work_id_in_durable(self):
        self.durable("concept", "concepts",
                     body="## Definition\n\nclaim (Work: ghost)\n\n## Supporting works\n\n- X — `ghost`")
        self.assertIn("work_id_unresolved", self.codes())

    def test_durable_missing_supporting_works(self):
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source())
        self.durable("concept", "concepts", body="## Definition\n\nclaim (Work: 1706)")
        self.assertIn("support_list_missing", self.codes())

    def test_durable_missing_marker(self):
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source())
        self.durable("concept", "concepts",
                     body="## Definition\n\nno marker here\n\n## Supporting works\n\n- Paper — `1706`")
        self.assertIn("work_marker_missing", self.codes())

    # --- links and typing --------------------------------------------------

    def test_broken_link(self):
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source(extra_body="see [[Ghost Concept]]"))
        self.assertIn("broken_link", self.codes())

    def test_page_type_directory_mismatch(self):
        self.put("wiki/sources/x.md", "---\ntitle: X\npage_type: concept\n---\n\n# X\n")
        self.assertIn("page_type_path_mismatch", self.codes())


if __name__ == "__main__":
    unittest.main()
