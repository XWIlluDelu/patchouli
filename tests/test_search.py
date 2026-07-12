"""Regression tests for deterministic search-record identity."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import search as search_module  # noqa: E402
from workspace_paths import Workspace  # noqa: E402


class SearchRecords(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ws = Workspace.from_path(self.root)
        self.provider = patch.object(
            search_module,
            "_exa_search",
            side_effect=lambda query, n, env_path: {
                "results": [
                    {
                        "title": query[-12:],
                        "url": "https://example.test/result",
                        "text": query,
                    }
                ]
            },
        )
        self.provider.start()

    def tearDown(self) -> None:
        self.provider.stop()
        self._tmp.cleanup()

    def test_normal_query_writes_readable_stable_record(self):
        result = search_module.search("attention explanation", n=1, workspace=self.ws)
        self.assertTrue(result["path"].startswith("searches/attention-explanation-"))
        self.assertIn(
            "# Search: attention explanation",
            (self.root / result["path"]).read_text(encoding="utf-8"),
        )

    def test_distinct_long_queries_do_not_overwrite(self):
        first_query = "x" * 96 + " first"
        second_query = "x" * 96 + " second"
        first = search_module.search(first_query, n=1, workspace=self.ws)
        second = search_module.search(second_query, n=1, workspace=self.ws)
        self.assertNotEqual(first["path"], second["path"])
        self.assertIn(
            first_query,
            (self.root / first["path"]).read_text(encoding="utf-8"),
        )
        self.assertIn(
            second_query,
            (self.root / second["path"]).read_text(encoding="utf-8"),
        )

    def test_same_query_reuses_same_record(self):
        query = "same query"
        first = search_module.search(query, n=1, workspace=self.ws)
        second = search_module.search(query, n=1, workspace=self.ws)
        self.assertEqual(first["path"], second["path"])
        self.assertEqual(
            (self.root / first["path"]).read_text(encoding="utf-8").count(
                f"# Search: {query}"
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
