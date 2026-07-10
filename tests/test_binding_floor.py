"""Regression tests for Patchouli's objective wiki invariants."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from check_wiki import check_issues  # noqa: E402
from lint import lint_wiki  # noqa: E402
from text_helpers import content_version_id  # noqa: E402
from workspace_paths import Workspace  # noqa: E402

SURFACE = (
    "- Source: https://example.test/paper\n\n"
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

    def source(
        self,
        work_id: str = "1706",
        *,
        marker: bool = True,
        surface: str | None = "auto",
        version: str | None = "auto",
        locator: str | None = "https://example.test/paper",
        extra_body: str = "",
        quote: str | None = None,
    ) -> str:
        if version == "auto":
            version = content_version_id(SURFACE)
        fm = ["title: Paper", "page_type: source", f"work_id: {work_id}"]
        if version is not None:
            fm.append(f"version_id: {version}")
        if surface == "auto":
            fm.append(f"reading_surface: extracted/{work_id}/text.md")
        elif surface is not None:
            fm.append(f"reading_surface: {surface}")
        if locator is not None:
            fm.append(f"source: {locator}")
        body = ["# Paper", ""]
        if marker:
            body.append(f"- a checkable claim (Work: {work_id})")
        if quote:
            body += ["", f"> {quote}"]
        if extra_body:
            body += ["", extra_body]
        return "---\n" + "\n".join(fm) + "\n---\n\n" + "\n".join(body) + "\n"

    def durable(
        self, page_type: str, dirname: str, *, work_ids: list[str] | None, body: str
    ) -> None:
        work_line = f"work_ids: [{', '.join(work_ids)}]\n" if work_ids is not None else ""
        self.put(
            f"wiki/{dirname}/d.md",
            f"---\ntitle: D\npage_type: {page_type}\n{work_line}---\n\n# D\n\n{body}\n",
        )

    def codes(self) -> set[str]:
        return {issue.code for issue in check_issues(self.ws)}

    # Quotes and surface binding.

    def test_clean_source_with_faithful_quote_passes(self):
        self.put_surface("1706")
        self.put(
            "wiki/sources/p.md",
            self.source(quote="the model achieves strong results on the benchmark"),
        )
        self.assertEqual(self.codes(), set())

    def test_bounded_extraction_noise_passes(self):
        surface = (
            "- Source: https://example.test/paper\n\n"
            "The model achieves strong page 12 inserted note results on the benchmark.\n"
        )
        self.put_surface("1706", surface)
        self.put(
            "wiki/sources/p.md",
            self.source(
                version=content_version_id(surface),
                quote="The model achieves strong results on the benchmark",
            ),
        )
        self.assertNotIn("quote_unresolved", self.codes())

    def test_distant_present_tokens_fail(self):
        self.put_surface("1706")
        self.put(
            "wiki/sources/p.md",
            self.source(quote="recurrent networks tokens model results"),
        )
        self.assertIn("quote_unresolved", self.codes())

    def test_fabricated_quote_with_absent_token_fails(self):
        self.put_surface("1706")
        self.put(
            "wiki/sources/p.md",
            self.source(quote="the model achieves strong results on the zebra benchmark"),
        )
        self.assertIn("quote_unresolved", self.codes())

    def test_wrapped_fabricated_blockquote_fails(self):
        self.put_surface("1706")
        self.put(
            "wiki/sources/p.md",
            self.source(extra_body="> fabricated statement\n> never in this source"),
        )
        self.assertIn("quote_unresolved", self.codes())

    def test_surface_for_another_work_fails(self):
        self.put_surface("other")
        self.put(
            "wiki/sources/p.md",
            self.source(surface="extracted/other/text.md"),
        )
        self.assertIn("source_surface_mismatch", self.codes())

    def test_missing_reading_surface_field_fails(self):
        self.put("wiki/sources/p.md", self.source(surface=None))
        self.assertIn("source_surface_unreadable", self.codes())

    def test_missing_canonical_surface_file_fails(self):
        self.put("wiki/sources/p.md", self.source())
        self.assertIn("source_surface_unreadable", self.codes())

    # Source provenance.

    def test_valid_source_without_quotes_passes(self):
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source())
        self.assertEqual(self.codes(), set())

    def test_missing_work_id(self):
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source().replace("work_id: 1706\n", ""))
        self.assertIn("source_work_id_missing", self.codes())

    def test_invalid_work_id(self):
        self.put("wiki/sources/p.md", self.source(work_id="../notes"))
        self.assertIn("source_work_id_invalid", self.codes())

    def test_duplicate_work_id(self):
        self.put_surface("1706")
        self.put("wiki/sources/a.md", self.source())
        self.put("wiki/sources/b.md", self.source())
        self.assertIn("duplicate_work_id", self.codes())

    def test_source_marker_for_other_work_must_resolve(self):
        self.put_surface("1706")
        self.put(
            "wiki/sources/p.md",
            self.source(extra_body="A comparison claim (Work: ghost)"),
        )
        self.assertIn("work_id_unresolved", self.codes())

    def test_missing_inline_marker(self):
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source(marker=False))
        self.assertIn("source_marker_missing", self.codes())

    def test_missing_version_id(self):
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source(version=None))
        self.assertIn("source_version_id_missing", self.codes())

    def test_missing_source_locator(self):
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source(locator=None))
        self.assertIn("source_locator_missing", self.codes())

    def test_source_locator_must_match_surface(self):
        self.put_surface("1706")
        self.put(
            "wiki/sources/p.md",
            self.source(locator="https://wrong.example/paper"),
        )
        self.assertIn("source_locator_mismatch", self.codes())

    def test_stale_version_id_fails(self):
        self.put_surface("1706")
        self.put(
            "wiki/sources/p.md",
            self.source(version="sha256-deadbeefdeadbeef"),
        )
        self.assertIn("source_version_stale", self.codes())

    def test_workflow_phrase_is_advisory(self):
        self.put_surface("1706")
        self.put(
            "wiki/sources/p.md",
            self.source(extra_body="TODO: revisit this"),
        )
        self.assertNotIn("source_pollution", self.codes())
        self.assertIn("source_pollution", {finding.code for finding in lint_wiki(self.ws)})

    # Authored schema, durable pages, and answers.

    def test_authored_page_requires_explicit_frontmatter(self):
        self.put("wiki/hubs/h.md", "# H\n")
        self.assertTrue({"title_missing", "page_type_missing"} <= self.codes())

    def test_single_work_synthesis(self):
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source())
        self.durable(
            "synthesis",
            "syntheses",
            work_ids=["1706"],
            body="## Thesis\n\nclaim (Work: 1706)\n\n## Supporting works\n\n- Paper — `1706`",
        )
        self.assertIn("single_work_synthesis", self.codes())

    def test_unresolved_work_id_in_durable(self):
        self.durable(
            "concept",
            "concepts",
            work_ids=["ghost"],
            body="## Definition\n\nclaim (Work: ghost)\n\n## Supporting works\n\n- X — `ghost`",
        )
        self.assertIn("work_id_unresolved", self.codes())

    def test_durable_requires_declared_work_ids(self):
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source())
        self.durable(
            "concept",
            "concepts",
            work_ids=None,
            body="## Definition\n\nclaim (Work: 1706)\n\n## Supporting works\n\n- P — `1706`",
        )
        self.assertIn("work_ids_missing", self.codes())

    def test_durable_work_ids_must_match_citations(self):
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source())
        self.durable(
            "concept",
            "concepts",
            work_ids=["1706", "ghost"],
            body="## Definition\n\nclaim (Work: 1706)\n\n## Supporting works\n\n- P — `1706`",
        )
        self.assertIn("work_ids_mismatch", self.codes())

    def test_each_supporting_work_must_ground_an_inline_claim(self):
        self.put_surface("a")
        self.put_surface("b")
        self.put("wiki/sources/a.md", self.source(work_id="a"))
        self.put("wiki/sources/b.md", self.source(work_id="b"))
        self.durable(
            "concept",
            "concepts",
            work_ids=["a", "b"],
            body=(
                "## Definition\n\nclaim (Work: a)\n\n## Supporting works\n\n"
                "- A — `a`\n- B — `b`"
            ),
        )
        self.assertIn("support_work_ids_mismatch", self.codes())

    def test_durable_missing_supporting_works(self):
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source())
        self.durable(
            "concept",
            "concepts",
            work_ids=["1706"],
            body="## Definition\n\nclaim (Work: 1706)",
        )
        self.assertIn("support_list_missing", self.codes())

    def test_durable_missing_marker(self):
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source())
        self.durable(
            "concept",
            "concepts",
            work_ids=["1706"],
            body="## Definition\n\nno marker here\n\n## Supporting works\n\n- Paper — `1706`",
        )
        self.assertIn("work_marker_missing", self.codes())

    def test_answer_with_unresolved_work_id_fails(self):
        self.put(
            "wiki/answers/a.md",
            "---\ntitle: A\npage_type: answer\nwork_ids: [ghost]\n---\n\n# A\n\nclaim (Work: ghost)\n",
        )
        self.assertIn("work_id_unresolved", self.codes())

    def test_answer_requires_inline_citation(self):
        self.put(
            "wiki/answers/a.md",
            "---\ntitle: A\npage_type: answer\nwork_ids: [1706]\n---\n\n# A\n\nclaim\n",
        )
        self.assertIn("work_marker_missing", self.codes())

    def test_answer_with_resolved_work_id_passes(self):
        self.put_surface("1706")
        self.put("wiki/sources/p.md", self.source())
        self.put(
            "wiki/answers/a.md",
            "---\ntitle: A\npage_type: answer\nwork_ids: [1706]\n---\n\n# A\n\nclaim (Work: 1706)\n",
        )
        self.assertEqual(self.codes(), set())

    # Links and typing.

    def test_broken_link(self):
        self.put_surface("1706")
        self.put(
            "wiki/sources/p.md",
            self.source(extra_body="see [[Ghost Concept]]"),
        )
        self.assertIn("broken_link", self.codes())

    def test_page_type_directory_mismatch(self):
        self.put(
            "wiki/sources/x.md",
            "---\ntitle: X\npage_type: concept\nwork_ids: [x]\n---\n\n# X\n",
        )
        self.assertIn("page_type_path_mismatch", self.codes())


if __name__ == "__main__":
    unittest.main()
