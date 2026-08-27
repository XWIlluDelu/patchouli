"""Tests for the wiki scanner's frontmatter and work-identity semantics.

The scanner feeds link resolution, generated indexes, the graph, stale review,
and the binding floor. A source page owns exactly its frontmatter work_id even
when its prose cites another work; durable and answer pages own their declared
support set.

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
    LinkResolver,
    parse_frontmatter,
    parse_inline_list,
    scan_wiki,
    work_ids_from_text,
)
from workspace_paths import Workspace  # noqa: E402


class FrontmatterLists(unittest.TestCase):
    def test_synthesis_marker_is_also_provenance(self):
        self.assertEqual(
            work_ids_from_text("claim (synthesis across Works: w1, w2)"),
            ("w1", "w2"),
        )

    def test_block_list_normalizes_to_inline_form(self):
        meta, body = parse_frontmatter(
            "---\ntitle: T\nwork_ids:\n  - a1\n  - a2\n---\nbody\n"
        )
        self.assertEqual(meta["work_ids"], "[a1, a2]")
        self.assertEqual(meta["title"], "T")
        self.assertEqual(body, "body\n")

    def test_inline_list_strips_quotes_and_backticks(self):
        self.assertEqual(
            parse_inline_list("[\"a1\", 'a2', `a3`]"),
            ("a1", "a2", "a3"),
        )


class ScannedWorkIds(unittest.TestCase):
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

    def scan_concept(self, work_ids_yaml: str) -> tuple[str, ...]:
        self.put(
            "wiki/concepts/c.md",
            f"---\ntitle: C\npage_type: concept\n{work_ids_yaml}\n---\n\n# C\n",
        )
        return scan_wiki(self.ws).pages[0].work_ids

    def test_inline_work_ids(self):
        self.assertEqual(
            self.scan_concept("work_ids: [w1, w2]"),
            ("w1", "w2"),
        )

    def test_block_work_ids(self):
        self.assertEqual(
            self.scan_concept("work_ids:\n  - w1\n  - w2"),
            ("w1", "w2"),
        )

    def test_source_owns_only_its_frontmatter_work_id(self):
        self.put(
            "wiki/sources/a.md",
            "---\ntitle: A\npage_type: source\nwork_id: a\n---\n\n"
            "# A\n\nclaim (Work: a)\n\n## Tensions\n\nconflict (Work: b)\n",
        )
        page = scan_wiki(self.ws).pages[0]
        self.assertEqual(page.work_ids, ("a",))

    def test_cross_work_source_marker_does_not_claim_another_work_id(self):
        self.put(
            "wiki/sources/a.md",
            "---\ntitle: A\npage_type: source\nwork_id: a\n---\n\n"
            "# A\n\nclaim (Work: a)\n\n## Tensions\n\nconflict (Work: b)\n",
        )
        self.put(
            "wiki/sources/b.md",
            "---\ntitle: B\npage_type: source\nwork_id: b\n---\n\n"
            "# B\n\nclaim (Work: b)\n",
        )
        self.put(
            "wiki/hubs/referrer.md",
            "---\ntitle: Referrer\npage_type: hub\n---\n\n[[b]]\n",
        )
        inventory = scan_wiki(self.ws)
        referrer = next(page for page in inventory.pages if page.title == "Referrer")
        resolved = LinkResolver.from_inventory(inventory).resolve(
            referrer, referrer.links[0]
        )
        self.assertEqual(resolved, ("wiki/sources/b.md",))


if __name__ == "__main__":
    unittest.main()
