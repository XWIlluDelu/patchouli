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
        (self.repo / ".env").write_text("SECRET=do-not-copy\n", encoding="utf-8")
        (self.repo / "personal.md").write_text("private context\n", encoding="utf-8")
        (self.repo / "scripts/check_wiki.py").write_text(
            "print('wiki checks passed')\n", encoding="utf-8"
        )
        fixture = self.repo / "evals/fixtures/demo/wiki/sources/source.md"
        fixture.parent.mkdir(parents=True)
        fixture.write_text("source\n", encoding="utf-8")
        (self.repo / "evals/gold.txt").write_text("do not show the agent\n", encoding="utf-8")
        (self.repo / "tests").mkdir()
        (self.repo / "tests/gold.py").write_text("EXPECTED = True\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_suite(self, cases: list[dict], **extra: object) -> Path:
        path = self.repo / "suite.json"
        path.write_text(
            json.dumps({"name": "test", **extra, "cases": cases}), encoding="utf-8"
        )
        return path

    def simple_case(self, case_id: str = "case") -> dict:
        return {
            "id": case_id,
            "request": "do something",
            "expect": {"outcome": "any"},
        }

    def test_prepare_applies_overlay_without_copying_gold_or_local_context(self):
        case = self.simple_case()
        case["overlay"] = "evals/fixtures/demo"
        suite_path = self.write_suite([case])
        paths = eval_module.prepare_suite(suite_path, self.repo, self.output)[0]
        self.assertEqual((paths.workspace / "base.txt").read_text(), "base\n")
        self.assertEqual(
            (paths.workspace / "wiki/sources/source.md").read_text(), "source\n"
        )
        self.assertFalse((paths.workspace / ".env").exists())
        self.assertFalse((paths.workspace / "personal.md").exists())
        self.assertFalse((paths.workspace / "evals").exists())
        self.assertFalse((paths.workspace / "tests").exists())
        self.assertFalse((paths.workspace / "suite.json").exists())
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

    def test_timed_out_adapter_is_recorded_as_failure(self):
        suite_path = self.write_suite(
            [
                {
                    "id": "timeout",
                    "request": "hang",
                    "expect": {"outcome": "any", "allowed_changes": []},
                }
            ]
        )
        suite = eval_module.load_suite(suite_path)
        paths = eval_module.prepare_suite(suite_path, self.repo, self.output)[0]
        code = eval_module.run_adapter(
            f"{sys.executable} -c \"import time; time.sleep(2)\"",
            suite["cases"][0],
            paths,
            timeout_seconds=0.05,
        )
        self.assertEqual(code, 124)
        result = eval_module.grade_suite(suite_path, self.output)[0]
        self.assertFalse(result["passed"])
        self.assertTrue(any("timed out" in item for item in result["failures"]))

    def test_grade_uses_the_frozen_prepared_suite(self):
        suite_path = self.write_suite(
            [
                {
                    "id": "frozen",
                    "request": "unsupported",
                    "expect": {"outcome": "no_op", "allowed_changes": []},
                }
            ]
        )
        paths = eval_module.prepare_suite(suite_path, self.repo, self.output)[0]
        paths.response.write_text("NO_OP: unsupported\n", encoding="utf-8")
        self.write_suite(
            [
                {
                    "id": "different",
                    "request": "write",
                    "expect": {"outcome": "write"},
                }
            ]
        )
        results = eval_module.grade_suite(suite_path, self.output)
        self.assertEqual([result["id"] for result in results], ["frozen"])
        self.assertTrue(results[0]["passed"], results[0]["failures"])

    def test_timeout_must_be_positive(self):
        suite_path = self.write_suite(
            [
                {
                    "id": "bad-timeout",
                    "request": "x",
                    "timeout_seconds": 0,
                    "expect": {"outcome": "any"},
                }
            ]
        )
        with self.assertRaisesRegex(eval_module.EvalConfigError, "positive"):
            eval_module.load_suite(suite_path)

    def test_force_refuses_repository_root(self):
        suite_path = self.write_suite([self.simple_case()])
        with self.assertRaisesRegex(eval_module.EvalConfigError, "repository root"):
            eval_module.prepare_suite(suite_path, self.repo, self.repo, force=True)
        self.assertEqual((self.repo / "base.txt").read_text(), "base\n")

    def test_force_refuses_unrelated_nonempty_directory_even_with_suite_json(self):
        suite_path = self.write_suite([self.simple_case()])
        unrelated = self.root / "unrelated"
        unrelated.mkdir()
        (unrelated / "suite.json").write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(eval_module.EvalConfigError, "unrelated directory"):
            eval_module.prepare_suite(suite_path, self.repo, unrelated, force=True)
        self.assertEqual((unrelated / "suite.json").read_text(), "{}\n")

    def test_force_replaces_a_recognized_eval_run(self):
        suite_path = self.write_suite([self.simple_case()])
        eval_module.prepare_suite(suite_path, self.repo, self.output)
        (self.output / "temporary.txt").write_text("replace me\n", encoding="utf-8")
        eval_module.prepare_suite(suite_path, self.repo, self.output, force=True)
        self.assertFalse((self.output / "temporary.txt").exists())
        self.assertTrue((self.output / ".patchouli-eval-run").is_file())

    def test_prepare_rejects_symlink_outside_repository(self):
        outside = self.root / "outside.txt"
        outside.write_text("private\n", encoding="utf-8")
        link = self.repo / "outside-link.txt"
        try:
            link.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        suite_path = self.write_suite([self.simple_case()])
        with self.assertRaisesRegex(eval_module.EvalConfigError, "escapes repository"):
            eval_module.prepare_suite(suite_path, self.repo, self.output)

    def test_prepare_rejects_directory_symlink(self):
        target = self.repo / "real-directory"
        target.mkdir()
        (target / "item.txt").write_text("item\n", encoding="utf-8")
        link = self.repo / "directory-link"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        suite_path = self.write_suite([self.simple_case()])
        with self.assertRaisesRegex(eval_module.EvalConfigError, "directory symlinks"):
            eval_module.prepare_suite(suite_path, self.repo, self.output)

    def test_overlay_cannot_be_repository_root(self):
        case = self.simple_case()
        case["overlay"] = "."
        suite_path = self.write_suite([case])
        with self.assertRaisesRegex(eval_module.EvalConfigError, "subdirectory"):
            eval_module.prepare_suite(suite_path, self.repo, self.output)


if __name__ == "__main__":
    unittest.main()
