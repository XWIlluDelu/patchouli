from __future__ import annotations

import json
from pathlib import Path
import shlex
import shutil
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import eval as eval_module  # noqa: E402


@unittest.skipUnless(
    sys.platform.startswith("linux") and shutil.which("bwrap"),
    "Bubblewrap integration requires a Linux host with bwrap installed",
)
class BubblewrapBoundary(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.repo = self.root / "repo"
        self.output = self.root / "runs"
        self.private = self.root / "private-gold"
        self.repo.mkdir()
        self.private.mkdir()
        (self.repo / "scripts").mkdir()
        (self.repo / "wiki/answers").mkdir(parents=True)
        (self.repo / "base.txt").write_text("base\n", encoding="utf-8")
        (self.repo / "scripts/check_wiki.py").write_text(
            "print('wiki checks passed')\n", encoding="utf-8"
        )
        self.suite = self.private / "suite.json"
        self.suite.write_text(
            json.dumps(
                {
                    "name": "private boundary probe",
                    "cases": [
                        {
                            "id": "boundary",
                            "request": "verify the isolated case",
                            "expect": {"outcome": "no_op"},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_repository_gold_and_run_control_are_absent(self) -> None:
        case = eval_module.load_suite(self.suite)["cases"][0]
        paths = eval_module.prepare_suite(
            self.suite, self.repo, self.output
        )[0]
        hidden = (
            self.suite,
            self.repo / "base.txt",
            self.output / "suite.json",
            paths.baseline,
        )
        visible_probe = " || ".join(
            f"[ -e {shlex.quote(str(path))} ]" for path in hidden
        )
        command = (
            "test -f /workspace/base.txt || exit 8; "
            f"if {visible_probe}; then exit 9; fi; "
            "printf 'sandbox write\n' > /workspace/sandbox-write.txt; "
            "printf 'NO_OP: isolated\n'"
        )
        code = eval_module.run_adapter(
            command,
            case,
            paths,
            timeout_seconds=5,
            isolation="bwrap",
            repo_root=self.repo,
            suite_path=self.suite,
            output_root=self.output,
        )
        self.assertEqual(code, 0, paths.stderr.read_text(encoding="utf-8"))
        self.assertEqual(
            (paths.workspace / "sandbox-write.txt").read_text(encoding="utf-8"),
            "sandbox write\n",
        )
        self.assertIn(
            "NO_OP: isolated",
            paths.response.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
