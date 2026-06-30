"""Tests for the deterministic index/graph builder.

Advisory logistics, not the binding floor — but build_graph and render_index are
deterministic and silently corrupting the graph (e.g. re-admitting generated catalogs
as nodes) would go unnoticed, so the core behavior is pinned here. render_recent's
dating rule — commit time for committed pages, mtime only for writes git has not
recorded — is what keeps recency meaningful across clones, so it is pinned too.

Run from the repo root:  python3 -m unittest discover -s tests
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from indexes import build_graph, render_index, render_recent    # noqa: E402
from wiki_inventory import scan_wiki                            # noqa: E402
from workspace_paths import Workspace                           # noqa: E402

SOURCE = "---\ntitle: {title}\npage_type: source\nwork_id: {wid}\n---\n\n# {title}\n\nclaim (Work: {wid})\n"
CONCEPT = "---\ntitle: C\npage_type: concept\n---\n\n# C\n\ndef (Work: {wid})\n\n## Supporting works\n\n- P — `{wid}`\n"


class WorkspaceCase(unittest.TestCase):
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


class GraphBuilder(WorkspaceCase):
    def graph(self) -> dict:
        return build_graph(self.ws, scan_wiki(self.ws))

    def test_generated_index_pages_are_not_graph_nodes(self):
        self.put("wiki/index.md", "# Wiki index\n\n- [P](sources/p.md)\n")
        self.put("wiki/recent.md", "# Recent pages\n")
        self.put("wiki/sources/p.md", SOURCE.format(title="P", wid="1706"))
        graph = self.graph()
        self.assertIn("wiki/sources/p.md", graph["nodes"])
        self.assertNotIn("wiki/index.md", graph["nodes"])
        self.assertNotIn("wiki/recent.md", graph["nodes"])
        self.assertFalse([e for e in graph["edges"] if e["source"].endswith(("index.md", "recent.md"))])

    def test_shared_work_edge_between_co_citing_pages(self):
        self.put("wiki/sources/p.md", SOURCE.format(title="P", wid="1706"))
        self.put("wiki/concepts/c.md", CONCEPT.format(wid="1706"))
        shared = [e for e in self.graph()["edges"] if e["type"] == "shared_work"]
        self.assertTrue(any(e["work_id"] == "1706" for e in shared))

    def test_render_index_lists_a_source(self):
        self.put("wiki/sources/p.md", SOURCE.format(title="Attention", wid="1706"))
        out = render_index(scan_wiki(self.ws))
        self.assertIn("Attention", out)
        self.assertIn("sources/p.md", out)


class RecentPages(WorkspaceCase):
    def git(self, *args: str, env: dict | None = None) -> None:
        subprocess.run(
            ["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@t",
             "-c", "commit.gpgsign=false", *args],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
        )

    def test_committed_page_dated_by_commit_time_not_mtime(self):
        self.put("wiki/sources/a.md", SOURCE.format(title="Old", wid="1"))
        self.git("init")
        self.git("add", "-A")
        when = "2020-01-01T00:00:00Z"
        self.git("commit", "-m", "x", env={**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when})
        self.put("wiki/sources/b.md", SOURCE.format(title="New", wid="2"))
        out = render_recent(self.ws, scan_wiki(self.ws))
        # a.md's mtime is now (as after any clone/checkout); the commit time must win.
        self.assertIn("2020-01-01 — [Old]", out)
        first = next(line for line in out.splitlines() if line.startswith("- "))
        self.assertIn("[New]", first)

    def test_without_git_repo_falls_back_to_mtime(self):
        self.put("wiki/sources/a.md", SOURCE.format(title="P", wid="1"))
        out = render_recent(self.ws, scan_wiki(self.ws))
        self.assertIn("[P]", out)


if __name__ == "__main__":
    unittest.main()
