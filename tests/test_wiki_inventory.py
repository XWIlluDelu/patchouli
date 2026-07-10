"""Tests for the wiki scanner's frontmatter list parsing.

parse_frontmatter is a hand-rolled YAML subset. Its list forms are the production
path for durable-page work_ids (`work_ids: [a, b]` per system/page_templates.md),
which feed the graph's work edges and the index; a regression there would corrupt
them silently, so both forms are pinned through scan_wiki.

Run from the repo root:  python3 -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from wiki_inventory import (  # noqa: E402
    parse_frontmatter,
    parse_inline_list,
    scan_wiki,
    work_ids_from_text,
)
from workspace_paths import Workspace                                         # noqa: E402


class FrontmatterLists(unittest.TestCase):
    def test_synthesis_marker_is_also_provenance(self):
        self.assertEqual(
            work_ids_from_text("claim (synthesis across Works: w1, w2)"),
            ("w1", "w2"),
        )

    def test_block_list_normalizes_to_inline_form(self):
        meta, body = parse_frontmatter("---\ntitle: T\nwork_ids:\n  - a1\n  - a2\n---\nbody\n")
        self.assertEqual(meta["work_ids"], "[a1, a2]")
        self.assertEqual(meta["title"], "T")
        self.assertEqual(body, "body\n")

    def test_inline_list_strips_quotes_and_backticks(self):
        self.assertEqual(parse_inline_list("[\"a1\", 'a2', `a3`]"), ("a1", "a2", "a3"))


class ScannedWorkIds(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ws = Workspace.from_path(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def scan_concept(self, work_ids_yaml: str) -> tuple[str, ...]:
        path = self.root / "wiki/concepts/c.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\ntitle: C\npage_type: concept\n{work_ids_yaml}\n---\n\n# C\n", encoding="utf-8")
        return scan_wiki(self.ws).pages[0].work_ids

    def test_inline_work_ids(self):
        self.assertEqual(self.scan_concept("work_ids: [w1, w2]"), ("w1", "w2"))

    def test_block_work_ids(self):
        self.assertEqual(self.scan_concept("work_ids:\n  - w1\n  - w2"), ("w1", "w2"))


if __name__ == "__main__":
    unittest.main()
