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
from quotes import _tokens  # noqa: E402
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
            "wiki/sources/1706.md",
            self.source(quote="the model achieves strong results on the benchmark"),
        )
        self.assertEqual(self.codes(), set())

    def test_inserted_extraction_noise_fails(self):
        surface = (
            "- Source: https://example.test/paper\n\n"
            "The model achieves strong page 12 inserted note results on the benchmark.\n"
        )
        self.put_surface("1706", surface)
        self.put(
            "wiki/sources/1706.md",
            self.source(
                version=content_version_id(surface),
                quote="The model achieves strong results on the benchmark",
            ),
        )
        self.assertIn("quote_unresolved", self.codes())

    def test_negation_cannot_be_skipped(self):
        surface = (
            "- Source: https://example.test/paper\n\n"
            "The treatment did not reduce mortality in the randomized clinical trial.\n"
        )
        self.put_surface("1706", surface)
        self.put(
            "wiki/sources/1706.md",
            self.source(
                version=content_version_id(surface),
                quote="The treatment did reduce mortality in the randomized clinical trial",
            ),
        )
        self.assertIn("quote_unresolved", self.codes())

    def test_short_blockquote_is_checked(self):
        self.put_surface("1706")
        self.put(
            "wiki/sources/1706.md",
            self.source(quote="No benefit was found."),
        )
        self.assertIn("quote_unresolved", self.codes())

    def test_curly_inline_quote_is_checked(self):
        self.put_surface("1706")
        self.put(
            "wiki/sources/1706.md",
            self.source(
                extra_body="The authors state “No benefit was found in the randomized trial.”"
            ),
        )
        self.assertIn("quote_unresolved", self.codes())

    def test_faithful_curly_inline_quote_passes(self):
        surface = (
            "- Source: https://example.test/paper\n\n"
            "No benefit was found in the randomized clinical trial.\n"
        )
        self.put_surface("1706", surface)
        self.put(
            "wiki/sources/1706.md",
            self.source(
                version=content_version_id(surface),
                extra_body="The authors state “No benefit was found in the randomized clinical trial.”",
            ),
        )
        self.assertNotIn("quote_unresolved", self.codes())

    def test_unmatched_markup_normalizes_without_rescanning_suffixes(self):
        tokens = _tokens("**a " * 20_000)
        self.assertEqual(tokens.count("a"), 20_000)

    def test_semantic_math_and_measurement_changes_fail(self):
        cases = (
            ("The dose was 5 mg.", "The dose was 50 mg."),
            ("The dose was 5 mg.", "The dose was 5 g."),
            ("The change was +2 units.", "The change was -2 units."),
            ("The result is x + y.", "The result is x - y."),
            ("The result is x^2.", "The result is x^3."),
            ("The result is x_1.", "The result is x_2."),
        )
        for surface_claim, quote in cases:
            with self.subTest(quote=quote):
                surface = f"- Source: https://example.test/paper\n\n{surface_claim}\n"
                self.put_surface("1706", surface)
                self.put(
                    "wiki/sources/1706.md",
                    self.source(version=content_version_id(surface), quote=quote),
                )
                self.assertIn("quote_unresolved", self.codes())

    def test_presentation_only_quote_normalization_passes(self):
        surface = (
            "- Source: https://example.test/paper\n\n"
            "The “model” uses $x^{2}$ and **5 mg** of treatment.\n"
        )
        self.put_surface("1706", surface)
        self.put(
            "wiki/sources/1706.md",
            self.source(
                version=content_version_id(surface),
                quote='The "model" uses \\(x^{2}\\) and 5 mg of treatment',
            ),
        )
        self.assertNotIn("quote_unresolved", self.codes())

    def test_distant_present_tokens_fail(self):
        self.put_surface("1706")
        self.put(
            "wiki/sources/1706.md",
            self.source(quote="recurrent networks tokens model results"),
        )
        self.assertIn("quote_unresolved", self.codes())

    def test_fabricated_quote_with_absent_token_fails(self):
        self.put_surface("1706")
        self.put(
            "wiki/sources/1706.md",
            self.source(quote="the model achieves strong results on the zebra benchmark"),
        )
        self.assertIn("quote_unresolved", self.codes())

    def test_wrapped_fabricated_blockquote_fails(self):
        self.put_surface("1706")
        self.put(
            "wiki/sources/1706.md",
            self.source(extra_body="> fabricated statement\n> never in this source"),
        )
        self.assertIn("quote_unresolved", self.codes())

    def test_surface_for_another_work_fails(self):
        self.put_surface("other")
        self.put(
            "wiki/sources/1706.md",
            self.source(surface="extracted/other/text.md"),
        )
        self.assertIn("source_surface_mismatch", self.codes())

    def test_missing_reading_surface_field_fails(self):
        self.put("wiki/sources/1706.md", self.source(surface=None))
        self.assertIn("source_surface_unreadable", self.codes())

    def test_missing_canonical_surface_file_fails(self):
        self.put("wiki/sources/1706.md", self.source())
        self.assertIn("source_surface_unreadable", self.codes())

    # Source provenance.

    def test_valid_source_without_quotes_passes(self):
        self.put_surface("1706")
        self.put("wiki/sources/1706.md", self.source())
        self.assertEqual(self.codes(), set())

    def test_source_filename_must_match_work_id(self):
        self.put_surface("1706")
        self.put("wiki/sources/not-1706.md", self.source())
        self.assertIn("source_path_mismatch", self.codes())

    def test_missing_work_id(self):
        self.put_surface("1706")
        self.put("wiki/sources/1706.md", self.source().replace("work_id: 1706\n", ""))
        self.assertIn("source_work_id_missing", self.codes())

    def test_invalid_work_id(self):
        self.put("wiki/sources/1706.md", self.source(work_id="../notes"))
        self.assertIn("source_work_id_invalid", self.codes())

    def test_duplicate_work_id(self):
        self.put_surface("1706")
        self.put("wiki/sources/a.md", self.source())
        self.put("wiki/sources/b.md", self.source())
        self.assertIn("duplicate_work_id", self.codes())

    def test_source_marker_for_other_work_must_resolve(self):
        self.put_surface("1706")
        self.put(
            "wiki/sources/1706.md",
            self.source(extra_body="A comparison claim (Work: ghost)"),
        )
        self.assertIn("work_id_unresolved", self.codes())

    def test_missing_inline_marker(self):
        self.put_surface("1706")
        self.put("wiki/sources/1706.md", self.source(marker=False))
        self.assertIn("source_marker_missing", self.codes())

    def test_missing_version_id(self):
        self.put_surface("1706")
        self.put("wiki/sources/1706.md", self.source(version=None))
        self.assertIn("source_version_id_missing", self.codes())

    def test_missing_source_locator(self):
        self.put_surface("1706")
        self.put("wiki/sources/1706.md", self.source(locator=None))
        self.assertIn("source_locator_missing", self.codes())

    def test_source_locator_must_match_surface(self):
        self.put_surface("1706")
        self.put(
            "wiki/sources/1706.md",
            self.source(locator="https://wrong.example/paper"),
        )
        self.assertIn("source_locator_mismatch", self.codes())

    def test_stale_version_id_fails(self):
        self.put_surface("1706")
        self.put(
            "wiki/sources/1706.md",
            self.source(version="sha256-deadbeefdeadbeef"),
        )
        self.assertIn("source_version_stale", self.codes())

    def test_workflow_phrase_is_advisory(self):
        self.put_surface("1706")
        self.put(
            "wiki/sources/1706.md",
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
        self.put("wiki/sources/1706.md", self.source())
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
        self.put("wiki/sources/1706.md", self.source())
        self.durable(
            "concept",
            "concepts",
            work_ids=None,
            body="## Definition\n\nclaim (Work: 1706)\n\n## Supporting works\n\n- P — `1706`",
        )
        self.assertIn("work_ids_missing", self.codes())

    def test_durable_work_ids_must_match_citations(self):
        self.put_surface("1706")
        self.put("wiki/sources/1706.md", self.source())
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
        self.put("wiki/sources/1706.md", self.source())
        self.durable(
            "concept",
            "concepts",
            work_ids=["1706"],
            body="## Definition\n\nclaim (Work: 1706)",
        )
        self.assertIn("support_list_missing", self.codes())

    def test_durable_missing_marker(self):
        self.put_surface("1706")
        self.put("wiki/sources/1706.md", self.source())
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
        self.put("wiki/sources/1706.md", self.source())
        self.put(
            "wiki/answers/a.md",
            "---\ntitle: A\npage_type: answer\nwork_ids: [1706]\n---\n\n# A\n\nclaim (Work: 1706)\n",
        )
        self.assertEqual(self.codes(), set())

    # Links and typing.

    def test_broken_link(self):
        self.put_surface("1706")
        self.put(
            "wiki/sources/1706.md",
            self.source(extra_body="see [[Ghost Concept]]"),
        )
        self.assertIn("broken_link", self.codes())

    def test_markdown_fragment_link_checks_page_target(self):
        self.put(
            "wiki/hubs/referrer.md",
            "---\ntitle: Referrer\npage_type: hub\n---\n\n[Ghost](missing.md#section)\n",
        )
        self.assertIn("broken_link", self.codes())

    def test_existing_relative_markdown_fragment_link_passes(self):
        self.put("wiki/hubs/target.md", "---\ntitle: Target\npage_type: hub\n---\n")
        self.put(
            "wiki/hubs/referrer.md",
            "---\ntitle: Referrer\npage_type: hub\n---\n\n[Target](target.md#section)\n",
        )
        self.assertNotIn("broken_link", self.codes())

    def test_standard_markdown_destination_forms_are_checked(self):
        valid = (
            '[Target](target.md "title")',
            "[Target](target.md?view=1)",
            "[Target](<target.md#section>)",
        )
        broken = (
            '[Ghost](missing.md "title")',
            "[Ghost](missing.md?view=1)",
            "[Ghost](<missing.md#section>)",
        )
        self.put("wiki/hubs/target.md", "---\ntitle: Target\npage_type: hub\n---\n")
        for link in valid:
            with self.subTest(link=link):
                self.put(
                    "wiki/hubs/referrer.md",
                    f"---\ntitle: Referrer\npage_type: hub\n---\n\n{link}\n",
                )
                self.assertNotIn("broken_link", self.codes())
        for link in broken:
            with self.subTest(link=link):
                self.put(
                    "wiki/hubs/referrer.md",
                    f"---\ntitle: Referrer\npage_type: hub\n---\n\n{link}\n",
                )
                self.assertIn("broken_link", self.codes())

    def test_markdown_link_uses_referrer_relative_path(self):
        self.put("wiki/concepts/item.md", "---\ntitle: Item\npage_type: concept\n---\n")
        self.put(
            "wiki/hubs/referrer.md",
            "---\ntitle: Referrer\npage_type: hub\n---\n\n[Wrong](item.md#section)\n",
        )
        self.assertIn("broken_link", self.codes())
        self.put(
            "wiki/hubs/referrer.md",
            "---\ntitle: Referrer\npage_type: hub\n---\n\n[Right](../concepts/item.md#section)\n",
        )
        self.assertNotIn("broken_link", self.codes())

    def test_markdown_link_cannot_escape_wiki(self):
        self.put("README.md", "# Outside\n")
        self.put(
            "wiki/hubs/referrer.md",
            "---\ntitle: Referrer\npage_type: hub\n---\n\n[Outside](../../README.md)\n",
        )
        self.assertIn("broken_link", self.codes())

    def test_referenced_duplicate_title_is_ambiguous(self):
        self.put("wiki/hubs/a.md", "---\ntitle: Duplicate\npage_type: hub\n---\n")
        self.put("wiki/hubs/b.md", "---\ntitle: Duplicate\npage_type: hub\n---\n")
        self.put(
            "wiki/hubs/referrer.md",
            "---\ntitle: Referrer\npage_type: hub\n---\n\n[[Duplicate]]\n",
        )
        self.assertIn("ambiguous_link", self.codes())

    def test_title_alias_collision_is_ambiguous(self):
        self.put(
            "wiki/hubs/a.md",
            "---\ntitle: Alpha\npage_type: hub\naliases: [Shared]\n---\n",
        )
        self.put("wiki/hubs/b.md", "---\ntitle: Shared\npage_type: hub\n---\n")
        self.put(
            "wiki/hubs/referrer.md",
            "---\ntitle: Referrer\npage_type: hub\n---\n\n[[Shared]]\n",
        )
        self.assertIn("ambiguous_link", self.codes())

    def test_same_stem_across_directories_is_ambiguous(self):
        self.put("wiki/concepts/item.md", "---\ntitle: Concept item\npage_type: concept\n---\n")
        self.put("wiki/entities/item.md", "---\ntitle: Entity item\npage_type: entity\n---\n")
        self.put(
            "wiki/hubs/referrer.md",
            "---\ntitle: Referrer\npage_type: hub\n---\n\n[[item]]\n",
        )
        self.assertIn("ambiguous_link", self.codes())

    def test_path_wikilink_disambiguates_same_stem(self):
        self.put("wiki/concepts/item.md", "---\ntitle: Concept item\npage_type: concept\n---\n")
        self.put("wiki/entities/item.md", "---\ntitle: Entity item\npage_type: entity\n---\n")
        self.put(
            "wiki/hubs/referrer.md",
            "---\ntitle: Referrer\npage_type: hub\n---\n\n[[concepts/item]]\n",
        )
        self.assertFalse({"broken_link", "ambiguous_link"} & self.codes())

    def test_page_type_directory_mismatch(self):
        self.put(
            "wiki/sources/x.md",
            "---\ntitle: X\npage_type: concept\nwork_ids: [x]\n---\n\n# X\n",
        )
        self.assertIn("page_type_path_mismatch", self.codes())


if __name__ == "__main__":
    unittest.main()
