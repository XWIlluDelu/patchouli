from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import extract  # noqa: E402


class IncompleteArxivCapture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._cwd = os.getcwd()
        os.chdir(self.root)
        self.degraded = extract.Extraction(
            "1706.03762",
            "https://arxiv.org/abs/1706.03762",
            "# Abstract only\n",
            (("arxiv-metadata.xml", b"metadata"),),
            complete=False,
        )

    def tearDown(self) -> None:
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def run_extract(self, *args: str) -> None:
        with (
            patch.object(extract, "extract_arxiv", return_value=self.degraded),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            extract.main(["1706.03762", *args])

    def test_first_ingest_does_not_publish_abstract_only_surface(self):
        with self.assertRaisesRegex(SystemExit, "incomplete capture"):
            self.run_extract()
        self.assertFalse((self.root / "raw/1706.03762").exists())
        self.assertFalse((self.root / "extracted/1706.03762").exists())

    def test_recheck_preserves_existing_complete_surface(self):
        surface = self.root / "extracted/1706.03762/text.md"
        raw = self.root / "raw/1706.03762/ar5iv.html"
        surface.parent.mkdir(parents=True)
        raw.parent.mkdir(parents=True)
        surface.write_text("# Complete\n", encoding="utf-8")
        raw.write_bytes(b"complete body")
        before_surface = surface.read_bytes()
        before_raw = raw.read_bytes()

        with self.assertRaisesRegex(SystemExit, "incomplete capture"):
            self.run_extract()
        self.assertEqual(surface.read_bytes(), before_surface)
        self.assertEqual(raw.read_bytes(), before_raw)


if __name__ == "__main__":
    unittest.main()
