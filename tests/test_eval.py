from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import eval as eval_module  # noqa: E402


class EvalHarness(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.repo = self.root / "repo"
        self.output = self.root / "runs"
        self.repo.mkdir()
        (self.repo / "scripts").mkdir()
        (self.repo / "wiki/answers").mkdir(parents=True)
        (self.repo / "base.txt").write_text("base\n", encoding="utf-8")
        (self.repo / "scripts/check_wiki.py").write_text(
            "print('wiki checks passed')\n", encoding="utf-8"
        )
        (self.repo / "overlay/wiki/sources").mkdir(parents=True)
        (self.repo / "overlay/wiki/sources/source.md").write_text(
            "source\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_suite(self, cases: list[dict]) -> Path:
        path = self.repo / "suite.json"
        path.write_text(
            json.dumps({"name": "test", "cases": cases}), encoding="utf-8"
        )
        return path

    def test_prepare_copies_repo_and_applies_overlay(self):
        suite_path = self.write_suite(
            [
                {
                    "id": "case",
                    "request": "do something",
                    "overlay": "overlay",
                    "expect": {"outcome": "any"},
                }
            ]
        )
        paths = eval_module.prepare_suite(suite_path, self.repo, self.output)[0]
        self.assertEqual((paths.workspace / "base.txt").read_text(), "base\n")
        self.assertEqual(
            (paths.workspace / "wiki/sources/source.md").read_text(), "source\n"
        )
        self.assertEqual(paths.request.read_text(), "do something\n")
        self.assertTrue((paths.workspace / ".git").is_dir())
        baseline = json.loads(paths.baseline.read_text())
        self.assertIn("base.txt", baseline)
        self.assertIn("wiki/sources/source.md", baseline)

    def test_noop_case_passes_without_changes(self):
        suite_path = self.write_suite(
            [
                {
                    "id": "noop",
                    "request": "unsupported question",
                    "expect": {
                        "outcome": "no_op",
                        "allowed_changes": [],
                        "check_wiki": True,
                    },
                }
            ]
        )
        paths = eval_module.prepare_suite(suite_path, self.repo, self.output)[0]
        paths.response.write_text("NO_OP: no supporting source\n", encoding="utf-8")
        result = eval_module.grade_suite(suite_path, self.output)[0]
        self.assertTrue(result["passed"], result["failures"])
        self.assertEqual(result["changed_paths"], [])

    def test_noop_case_rejects_unexpected_write(self):
        suite_path = self.write_suite(
            [
                {
                    "id": "noop",
                    "request": "unsupported question",
                    "expect": {"outcome": "no_op", "allowed_changes": []},
                }
            ]
        )
        paths = eval_module.prepare_suite(suite_path, self.repo, self.output)[0]
        paths.response.write_text("NO_OP: no supporting source\n", encoding="utf-8")
        (paths.workspace / "wiki/answers/bad.md").write_text("bad\n", encoding="utf-8")
        result = eval_module.grade_suite(suite_path, self.output)[0]
        self.assertFalse(result["passed"])
        self.assertTrue(
            any("unexpected changed paths" in failure for failure in result["failures"])
        )

    def test_write_case_checks_paths_content_and_floor(self):
        suite_path = self.write_suite(
            [
                {
                    "id": "write",
                    "request": "answer",
                    "expect": {
                        "outcome": "write",
                        "allowed_changes": ["wiki/answers/*.md"],
                        "required_changes": ["wiki/answers/*.md"],
                        "check_wiki": True,
                        "content": [
                            {
                                "path": "wiki/answers/*.md",
                                "contains": ["120", "demo-study"],
                            }
                        ],
                    },
                }
            ]
        )
        paths = eval_module.prepare_suite(suite_path, self.repo, self.output)[0]
        paths.response.write_text("Wrote an answer.\n", encoding="utf-8")
        (paths.workspace / "wiki/answers/result.md").write_text(
            "sample size 120 (Work: demo-study)\n", encoding="utf-8"
        )
        result = eval_module.grade_suite(suite_path, self.output)[0]
        self.assertTrue(result["passed"], result["failures"])

    def test_run_adapter_uses_stdout_as_response(self):
        suite_path = self.write_suite(
            [
                {
                    "id": "adapter",
                    "request": "unsupported",
                    "expect": {
                        "outcome": "no_op",
                        "allowed_changes": [],
                        "exit_code": 0,
                    },
                }
            ]
        )
        suite = eval_module.load_suite(suite_path)
        paths = eval_module.prepare_suite(suite_path, self.repo, self.output)[0]
        code = eval_module.run_adapter(
            f"{sys.executable} -c \"print('NO_OP: unsupported')\"",
            suite["cases"][0],
            paths,
        )
        self.assertEqual(code, 0)
        result = eval_module.grade_suite(suite_path, self.output)[0]
        self.assertTrue(result["passed"], result["failures"])


if __name__ == "__main__":
    unittest.main()
