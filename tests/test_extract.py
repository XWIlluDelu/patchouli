"""Tests for extraction content, identity, confinement, and publication."""

from __future__ import annotations

import contextlib
from dataclasses import replace
import io
import os
import re
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import extract  # noqa: E402
from workspace_paths import Workspace  # noqa: E402


class PdfPackaging(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        cls.config = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    def test_runtime_profile_matches_quality_extra(self):
        extras = self.config["project"]["optional-dependencies"]
        profile = extract.PDF_PROFILES["docling-enriched"]
        pattern = re.compile(
            rf"^{re.escape(profile.distribution)}(?:\[[^]]+\])?"
            rf"=={re.escape(profile.version)}$"
        )
        for extra in profile.install_extras:
            self.assertTrue(any(pattern.match(item) for item in extras[extra]))

    def test_quality_install_variants_share_one_parser_profile(self):
        extras = self.config["project"]["optional-dependencies"]
        self.assertEqual(extras["pdf-quality"], extras["pdf-quality-cpu"])

    def test_reference_profiles_pin_benchmarked_backends(self):
        extras = self.config["project"]["optional-dependencies"]
        self.assertTrue(
            {
                "pymupdf==1.28.0",
                "pymupdf-layout==1.28.0",
                "pymupdf4llm==1.28.0",
                "rapidocr-onnxruntime==1.4.4",
            }.issubset(extras["pdf-balanced"])
        )
        self.assertEqual(extras["pdf-fast"], ["kreuzberg==4.10.0"])
        self.assertEqual(
            self.config["project"]["requires-python"], ">=3.11,<3.13"
        )

    def test_pdf_install_extras_are_pairwise_conflicting(self):
        profiles = (
            "pdf-quality",
            "pdf-quality-cpu",
            "pdf-balanced",
            "pdf-fast",
        )
        required = {
            frozenset((left, right))
            for index, left in enumerate(profiles)
            for right in profiles[index + 1 :]
        }
        declared = {
            frozenset(item["extra"] for item in conflict)
            for conflict in self.config["tool"]["uv"]["conflicts"]
        }
        self.assertEqual(declared, required)


def minimal_pdf(text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content = f"BT /F1 24 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        b"5 0 obj\n<< /Length "
        + str(len(content)).encode("ascii")
        + b" >>\nstream\n"
        + content
        + b"\nendstream\nendobj\n",
    ]
    document = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(document))
        document.extend(obj)
    xref = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    document.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    return bytes(document)


class SurfaceGuard(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._cwd = os.getcwd()
        os.chdir(self.root)
        self.note = self.root / "n.md"
        self.note.write_text("original content of the note\n", encoding="utf-8")

    def tearDown(self) -> None:
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def run_extract(self, *extra: str) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            return extract.main([str(self.note), "--work-id", "n", *extra])

    def test_reextraction_of_identical_content_is_idempotent(self):
        self.run_extract()
        self.assertEqual(self.run_extract(), 0)

    def test_changed_content_refuses_without_mutating_any_artifact(self):
        self.run_extract()
        surface = self.root / "extracted/n/text.md"
        raw = self.root / "raw/n/n.md"
        before_surface = surface.read_bytes()
        before_raw = raw.read_bytes()
        self.note.write_text("revised content of the note\n", encoding="utf-8")
        with self.assertRaises(SystemExit):
            self.run_extract()
        self.assertEqual(surface.read_bytes(), before_surface)
        self.assertEqual(raw.read_bytes(), before_raw)

    def test_refresh_replaces_current_raw_and_surface(self):
        self.run_extract()
        self.note.write_text("revised content of the note\n", encoding="utf-8")
        self.assertEqual(self.run_extract("--refresh"), 0)
        self.assertIn(
            "revised content",
            (self.root / "extracted/n/text.md").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            (self.root / "raw/n/n.md").read_text(encoding="utf-8"),
            "revised content of the note\n",
        )

    def test_work_id_must_be_one_safe_segment(self):
        victim = self.root / "notes/n.md"
        victim.parent.mkdir()
        victim.write_text("human note\n", encoding="utf-8")
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stdout(io.StringIO()):
                extract.main([str(self.note), "--work-id", "../notes"])
        self.assertEqual(victim.read_text(encoding="utf-8"), "human note\n")

    def test_raw_work_symlink_cannot_redirect_writes_or_pruning(self):
        notes = self.root / "notes"
        notes.mkdir()
        victim = notes / "victim.md"
        victim.write_text("human note\n", encoding="utf-8")
        raw = self.root / "raw"
        raw.mkdir()
        (raw / "n").symlink_to(notes, target_is_directory=True)
        with self.assertRaises(SystemExit):
            self.run_extract()
        self.assertEqual(victim.read_text(encoding="utf-8"), "human note\n")

    def test_extracted_work_symlink_cannot_redirect_surface(self):
        wiki = self.root / "wiki"
        wiki.mkdir()
        extracted = self.root / "extracted"
        extracted.mkdir()
        (extracted / "n").symlink_to(wiki, target_is_directory=True)
        with self.assertRaises(SystemExit):
            self.run_extract()
        self.assertFalse((wiki / "text.md").exists())

    def test_same_root_raw_alias_cannot_redirect_pruning(self):
        raw = self.root / "raw"
        other = raw / "other"
        other.mkdir(parents=True)
        victim = other / "victim.md"
        victim.write_text("keep\n", encoding="utf-8")
        (raw / "n").symlink_to(other, target_is_directory=True)
        with self.assertRaises(SystemExit):
            self.run_extract()
        self.assertEqual(victim.read_text(encoding="utf-8"), "keep\n")

    def test_same_root_extracted_alias_cannot_redirect_surface(self):
        extracted = self.root / "extracted"
        other = extracted / "other"
        other.mkdir(parents=True)
        target = other / "text.md"
        target.write_text("keep\n", encoding="utf-8")
        (extracted / "n").symlink_to(other, target_is_directory=True)
        with self.assertRaises(SystemExit):
            self.run_extract()
        self.assertEqual(target.read_text(encoding="utf-8"), "keep\n")


class SourceIdentity(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ws = Workspace.from_path(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_explicit_arxiv_version_is_preserved_for_fetch(self):
        for malformed in (
            "https://not-arxiv.example/abs/1706.03762v3",
            "https://arxiv.org/help/1706.03762",
            "https://arxiv.org/abs/1706.037620",
            "https://arxiv.org/abs/1706.03762v3junk",
        ):
            self.assertIsNone(extract.parse_arxiv_ref(malformed))
        ref = extract.parse_arxiv_ref("https://arxiv.org/abs/1706.03762v3")
        self.assertEqual(ref.work_id, "1706.03762")
        self.assertEqual(ref.fetch_id, "1706.03762v3")

        metadata = b'''<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Paper</title>
<author><name>A. Author</name></author><published>2017-06-01T00:00:00Z</published>
<summary>Abstract.</summary></entry></feed>'''
        requested: list[str] = []

        def fake_get(url: str) -> bytes:
            requested.append(url)
            return metadata if "export.arxiv.org" in url else b"<article><p>Body.</p></article>"

        with patch.object(extract, "_get", side_effect=fake_get):
            result = extract.extract_arxiv(ref)
        self.assertTrue(all("1706.03762v3" in url for url in requested))
        self.assertEqual(result.source, "https://arxiv.org/abs/1706.03762v3")
        self.assertIn("arXiv: 1706.03762v3", result.text)

    def test_same_url_keeps_id_when_title_changes(self):
        first = {"data": {"markdown": "one", "metadata": {"title": "First title"}}}
        second = {"data": {"markdown": "two", "metadata": {"title": "Renamed title"}}}
        with patch.object(extract, "with_key_retry", return_value=first):
            a = extract.extract_url("https://EXAMPLE.test/paper#section", self.ws, None)
        with patch.object(extract, "with_key_retry", return_value=second):
            b = extract.extract_url("https://example.test/paper", self.ws, None)
        self.assertEqual(a.work_id, b.work_id)
        self.assertEqual(a.source, "https://example.test/paper")

    def test_distinct_urls_with_same_title_get_distinct_ids(self):
        result = {"data": {"markdown": "body", "metadata": {"title": "Paper"}}}
        with patch.object(extract, "with_key_retry", return_value=result):
            a = extract.extract_url("https://a.test/paper", self.ws, None)
            b = extract.extract_url("https://b.test/paper", self.ws, None)
        self.assertNotEqual(a.work_id, b.work_id)

    def test_in_workspace_locator_id_is_stable_across_checkout_roots(self):
        other_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(other_tmp.cleanup)
        other_root = Path(other_tmp.name)
        first = self.root / "notes/paper.md"
        second = other_root / "notes/paper.md"
        first.parent.mkdir()
        second.parent.mkdir()
        first.write_text("same", encoding="utf-8")
        second.write_text("same", encoding="utf-8")
        self.assertEqual(
            extract.extract_file(first, self.ws, None).work_id,
            extract.extract_file(second, Workspace.from_path(other_root), None).work_id,
        )

    def test_same_basename_at_distinct_paths_gets_distinct_ids(self):
        a = self.root / "a/paper.md"
        b = self.root / "b/paper.md"
        a.parent.mkdir()
        b.parent.mkdir()
        a.write_text("a", encoding="utf-8")
        b.write_text("b", encoding="utf-8")
        self.assertNotEqual(
            extract.extract_file(a, self.ws, None).work_id,
            extract.extract_file(b, self.ws, None).work_id,
        )

    def test_refresh_prunes_stale_raw_artifacts(self):
        surface = self.root / "extracted/w/text.md"
        first = extract.Extraction("w", "https://example.test", "first", (("old.bin", b"old"),))
        second = extract.Extraction("w", "https://example.test", "second", (("new.bin", b"new"),))
        extract._publish(first, self.ws, surface)
        extract._publish(second, self.ws, surface)
        self.assertFalse((self.root / "raw/w/old.bin").exists())
        self.assertEqual((self.root / "raw/w/new.bin").read_bytes(), b"new")

    def test_source_page_path_depends_only_on_work_id(self):
        self.assertEqual(extract._source_page("1706.03762"), "wiki/sources/1706.03762.md")

    def test_incomplete_arxiv_refresh_preserves_existing_capture(self):
        surface = self.root / "extracted/1706.03762/text.md"
        raw = self.root / "raw/1706.03762/ar5iv.html"
        surface.parent.mkdir(parents=True)
        raw.parent.mkdir(parents=True)
        surface.write_text("# Complete\n", encoding="utf-8")
        raw.write_bytes(b"complete body")
        before_surface = surface.read_bytes()
        before_raw = raw.read_bytes()
        degraded = extract.Extraction(
            "1706.03762",
            "https://arxiv.org/abs/1706.03762",
            "# Abstract only\n",
            (("arxiv-metadata.xml", b"metadata"),),
            complete=False,
        )
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            with patch.object(extract, "extract_arxiv", return_value=degraded):
                with self.assertRaisesRegex(SystemExit, "incomplete capture"):
                    extract.main(["1706.03762", "--refresh"])
        finally:
            os.chdir(cwd)
        self.assertEqual(surface.read_bytes(), before_surface)
        self.assertEqual(raw.read_bytes(), before_raw)


class LocalContent(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ws = Workspace.from_path(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_unsupported_binary_is_rejected_before_read(self):
        path = self.root / "paper.docx"
        path.write_bytes(b"PK fake office archive")
        with patch.object(Path, "read_bytes", side_effect=AssertionError("must not read")):
            with self.assertRaisesRegex(SystemExit, "unsupported local file type"):
                extract.extract_file(path, self.ws, None)

    def test_text_input_must_be_utf8(self):
        path = self.root / "paper.txt"
        path.write_bytes(b"\xff\xfe")
        with self.assertRaisesRegex(SystemExit, "not valid UTF-8"):
            extract.extract_file(path, self.ws, None)

    def test_pdf_requires_explicit_profile_before_read(self):
        path = self.root / "paper.pdf"
        path.write_bytes(b"%PDF")
        with patch.object(
            Path, "read_bytes", side_effect=AssertionError("must not read")
        ):
            with self.assertRaisesRegex(SystemExit, "requires --pdf-profile"):
                extract.extract_file(path, self.ws, None)

    def test_pdf_profile_is_rejected_for_non_pdf_before_read(self):
        path = self.root / "paper.txt"
        path.write_text("body", encoding="utf-8")
        with patch.object(
            Path, "read_bytes", side_effect=AssertionError("must not read")
        ):
            with self.assertRaisesRegex(SystemExit, "only for a local \\.pdf"):
                extract.extract_file(
                    path, self.ws, None, "docling-enriched"
                )

    def test_pdf_uses_structured_converter_on_captured_bytes(self):
        path = self.root / "extracted-title.pdf"
        captured = b"%PDF captured once"
        path.write_bytes(captured)
        markdown = (
            "## Extracted title\n\n## Abstract\n\n"
            "| Method | Score |\n|---|---|\n| A | 98 |\n"
        )
        with patch.object(extract, "pdf_to_markdown", return_value=markdown) as convert:
            result = extract.extract_file(
                path, self.ws, None, "docling-enriched"
            )
        convert.assert_called_once_with(
            captured, "extracted-title.pdf", "docling-enriched"
        )
        self.assertTrue(result.text.startswith("# Extracted title\n\n- Source:"))
        self.assertIn("- PDF backend: docling==2.111.0", result.text)
        self.assertIn("- PDF profile: docling-enriched@1", result.text)
        self.assertEqual(result.text.count("Extracted title"), 1)
        self.assertIn("| Method | Score |", result.text)
        self.assertEqual(result.raw_files, (("extracted-title.pdf", captured),))

    def test_abstract_does_not_turn_first_section_into_title(self):
        path = self.root / "paper.pdf"
        path.write_bytes(b"%PDF captured once")
        markdown = "## Introduction\n\nBody.\n\n## Abstract\n\nSummary.\n"
        with patch.object(extract, "pdf_to_markdown", return_value=markdown):
            result = extract.extract_file(
                path, self.ws, None, "docling-enriched"
            )
        self.assertTrue(result.text.startswith("# paper\n\n- Source:"))
        self.assertIn("## Introduction\n\nBody.", result.text)
        self.assertIn("## Abstract\n\nSummary.", result.text)

    def test_markdown_without_title_keeps_first_section(self):
        path = self.root / "paper.md"
        path.write_text("## Methods\n\nBody.\n", encoding="utf-8")
        result = extract.extract_file(path, self.ws, None)
        self.assertTrue(result.text.startswith("# paper\n\n- Source:"))
        self.assertIn("## Methods\n\nBody.", result.text)

    def test_title_cleanup_never_removes_a_later_heading(self):
        markdown = "# Other\n\n## Introduction\n\nBody.\n"
        self.assertEqual(
            extract._drop_title_heading(markdown, "Introduction"),
            markdown,
        )

    def test_html_preserves_structure(self):
        path = self.root / "paper.html"
        path.write_text(
            "<html><body><nav>menu</nav><article><h1>Structured title</h1>"
            "<p>Strong <b>evidence</b>.</p><table><tr><th>A</th><th>B</th></tr>"
            "<tr><td>1</td><td>2</td></tr></table></article></body></html>",
            encoding="utf-8",
        )
        result = extract.extract_file(path, self.ws, None)
        self.assertTrue(result.text.startswith("# Structured title\n\n- Source:"))
        self.assertEqual(result.text.count("Structured title"), 1)
        self.assertIn("**evidence**", result.text)
        self.assertRegex(result.text, r"\|\s+A\s+\|\s+B\s+\|")
        self.assertNotIn("menu", result.text)
        self.assertNotIn("PDF backend", result.text)
        self.assertNotIn("PDF profile", result.text)

    def test_pdf_dispatches_the_workspace_profile(self):
        with patch.object(
            extract,
            "_docling_pdf_to_markdown",
            return_value="# Docling\n",
        ) as selected:
            self.assertEqual(
                extract.pdf_to_markdown(
                    b"%PDF", "paper.pdf", "docling-enriched"
                ),
                "# Docling\n",
            )
        selected.assert_called_once_with(b"%PDF", "paper.pdf")

    def test_unknown_profile_is_rejected_without_conversion(self):
        with patch.object(
            extract,
            "_docling_pdf_to_markdown",
            side_effect=AssertionError("unknown profile must not convert"),
        ):
            with self.assertRaisesRegex(ValueError, "unknown PDF profile"):
                extract.pdf_to_markdown(b"%PDF", "paper.pdf", "unknown")

    def test_backend_version_must_match_profile(self):
        profile = extract.PDF_PROFILES["docling-enriched"]
        with patch.object(extract, "distribution_version", return_value="2.110.0"):
            with self.assertRaisesRegex(SystemExit, "requires docling==2.111.0"):
                extract._require_backend_version(profile)

    def test_missing_backend_names_both_install_variants(self):
        profile = extract.PRODUCTION_PDF_PROFILE
        with patch.object(
            extract,
            "distribution_version",
            side_effect=extract.PackageNotFoundError,
        ):
            with self.assertRaises(SystemExit) as raised:
                extract._require_backend_version(profile)
        self.assertIn("pdf-quality`", str(raised.exception))
        self.assertIn("pdf-quality-cpu`", str(raised.exception))

    def test_pdf_initialization_failure_is_reported(self):
        with patch.object(
            extract,
            "_pdf_pipeline_options",
            side_effect=RuntimeError("initialization failed"),
        ):
            with self.assertRaisesRegex(SystemExit, "could not convert PDF to Markdown"):
                extract.pdf_to_markdown(
                    b"%PDF", "paper.pdf", "docling-enriched"
                )

    def test_pdf_pipeline_options_are_pinned_and_enabled(self):
        options = extract._pdf_pipeline_options()
        self.assertTrue(options.do_ocr)
        self.assertTrue(options.do_table_structure)
        self.assertTrue(options.do_formula_enrichment)
        self.assertEqual(options.ocr_options.backend, "onnxruntime")
        self.assertEqual(options.ocr_options.lang, ["chinese"])
        self.assertEqual(
            options.layout_options.model_spec.revision,
            extract.DOCLING_LAYOUT_REVISION,
        )
        self.assertEqual(
            options.code_formula_options.model_spec.revision,
            extract.DOCLING_FORMULA_REVISION,
        )
        self.assertTrue(options.heading_hierarchy_options.enabled)
        self.assertFalse(options.enable_remote_services)

    def test_identical_pdf_reuses_surface_without_conversion(self):
        path = self.root / "paper.pdf"
        path.write_bytes(b"%PDF stable capture")
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            args = [
                str(path),
                "--work-id",
                "paper",
                "--pdf-profile",
                "docling-enriched",
            ]
            with patch.object(extract, "pdf_to_markdown", return_value="# Paper\n\nBody.\n"):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(extract.main(args), 0)
            with patch.object(
                extract,
                "pdf_to_markdown",
                side_effect=AssertionError("identical PDF must not be reconverted"),
            ):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(extract.main(args), 0)
        finally:
            os.chdir(cwd)

    def test_identical_pdf_profile_revision_change_requires_refresh(self):
        path = self.root / "paper.pdf"
        path.write_bytes(b"%PDF stable capture")
        revised = replace(extract.PRODUCTION_PDF_PROFILE, revision=2)
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            first = [
                str(path),
                "--work-id",
                "paper",
                "--pdf-profile",
                "docling-enriched",
            ]
            second = [
                str(path),
                "--work-id",
                "paper",
                "--pdf-profile",
                "docling-enriched",
            ]
            with patch.object(extract, "pdf_to_markdown", return_value="first body"):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(extract.main(first), 0)
            surface = self.root / "extracted/paper/text.md"
            raw = self.root / "raw/paper/paper.pdf"
            before_surface = surface.read_bytes()
            before_raw = raw.read_bytes()
            with (
                patch.dict(extract.PDF_PROFILES, {revised.name: revised}),
                patch.object(
                    extract,
                    "pdf_to_markdown",
                    side_effect=AssertionError(
                        "mismatch must fail before conversion"
                    ),
                ),
            ):
                with self.assertRaisesRegex(SystemExit, "Re-run with --refresh"):
                    extract.main(second)
            self.assertEqual(surface.read_bytes(), before_surface)
            self.assertEqual(raw.read_bytes(), before_raw)
        finally:
            os.chdir(cwd)

    def test_refresh_reextracts_identical_pdf_with_new_profile_revision(self):
        path = self.root / "paper.pdf"
        path.write_bytes(b"%PDF stable capture")
        revised = replace(extract.PRODUCTION_PDF_PROFILE, revision=2)
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            common = [str(path), "--work-id", "paper", "--pdf-profile"]
            with patch.object(extract, "pdf_to_markdown", return_value="first body"):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(
                        extract.main([*common, "docling-enriched"]), 0
                    )
            with (
                patch.dict(extract.PDF_PROFILES, {revised.name: revised}),
                patch.object(
                    extract, "pdf_to_markdown", return_value="second body"
                ) as convert,
            ):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(
                        extract.main([*common, "docling-enriched", "--refresh"]), 0
                    )
            convert.assert_called_once_with(
                b"%PDF stable capture", "paper.pdf", "docling-enriched"
            )
            surface = (self.root / "extracted/paper/text.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("- PDF backend: docling==2.111.0", surface)
            self.assertIn("- PDF profile: docling-enriched@2", surface)
            self.assertIn("second body", surface)
            self.assertNotIn("first body", surface)
        finally:
            os.chdir(cwd)

    def test_legacy_pdf_surface_requires_refresh(self):
        path = self.root / "paper.pdf"
        path.write_bytes(b"%PDF stable capture")
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            args = [
                str(path),
                "--work-id",
                "paper",
                "--pdf-profile",
                "docling-enriched",
            ]
            with patch.object(extract, "pdf_to_markdown", return_value="body"):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(extract.main(args), 0)
            surface = self.root / "extracted/paper/text.md"
            legacy = "\n".join(
                line
                for line in surface.read_text(encoding="utf-8").splitlines()
                if not line.startswith(("- PDF backend:", "- PDF profile:"))
            ) + "\n"
            surface.write_text(legacy, encoding="utf-8")
            before = surface.read_bytes()
            with patch.object(
                extract,
                "pdf_to_markdown",
                side_effect=AssertionError("legacy surface must fail before conversion"),
            ):
                with self.assertRaisesRegex(SystemExit, "unrecorded profile"):
                    extract.main(args)
            self.assertEqual(surface.read_bytes(), before)
        finally:
            os.chdir(cwd)

    def test_profile_is_rejected_for_url_before_network(self):
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            with patch.object(
                extract,
                "extract_url",
                side_effect=AssertionError("must not access network"),
            ):
                with self.assertRaisesRegex(SystemExit, "only for a local \\.pdf"):
                    extract.main(
                        [
                            "https://example.test/paper.pdf",
                            "--pdf-profile",
                            "docling-enriched",
                        ]
                    )
        finally:
            os.chdir(cwd)

    @unittest.skipUnless(
        os.environ.get("PATCHOULI_PDF_INTEGRATION") == "1",
        "set PATCHOULI_PDF_INTEGRATION=1 to run the model-backed PDF smoke test",
    )
    def test_docling_pdf_integration(self):
        path = self.root / "integration.pdf"
        path.write_bytes(minimal_pdf("Patchouli PDF Integration"))
        result = extract.extract_file(
            path, self.ws, None, "docling-enriched"
        )
        self.assertIn("Patchouli PDF Integration", result.text)


if __name__ == "__main__":
    unittest.main()
