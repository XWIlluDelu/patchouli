"""Tests for extraction identity, confinement, and write ordering."""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import extract  # noqa: E402
from workspace_paths import Workspace  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
