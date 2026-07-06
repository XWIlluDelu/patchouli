"""Tests for the reading-surface immutability guard in extract.py.

The extracted surface is the quote-binding anchor for its source page, so a
re-extraction whose content changed must refuse to overwrite it unless the
caller says --refresh. Exercised offline through the local-file input path.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import extract                                  # noqa: E402


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
            return extract.main([str(self.note), *extra])

    def test_reextraction_of_identical_content_is_idempotent(self):
        self.run_extract()
        self.assertEqual(self.run_extract(), 0)

    def test_changed_content_refuses_to_overwrite(self):
        self.run_extract()
        self.note.write_text("revised content of the note\n", encoding="utf-8")
        with self.assertRaises(SystemExit):
            self.run_extract()
        surface = (self.root / "extracted" / "n" / "text.md").read_text(encoding="utf-8")
        self.assertIn("original content", surface)

    def test_refresh_replaces_the_surface(self):
        self.run_extract()
        self.note.write_text("revised content of the note\n", encoding="utf-8")
        self.assertEqual(self.run_extract("--refresh"), 0)
        surface = (self.root / "extracted" / "n" / "text.md").read_text(encoding="utf-8")
        self.assertIn("revised content", surface)


if __name__ == "__main__":
    unittest.main()
