from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import tempfile
import time
import unittest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import eval as eval_module  # noqa: E402
from eval_runtime import build_bwrap_command  # noqa: E402


class EvalFixes(unittest.TestCase):
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
        fixture = self.repo / "fixtures/demo/wiki/sources/source.md"
        fixture.parent.mkdir(parents=True)
        fixture.write_text("source\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_suite(self, cases: list[dict], *, directory: Path | None = None) -> Path:
        directory = directory or self.repo
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "suite.json"
        path.write_text(json.dumps({"name": "test", "cases": cases}), encoding="utf-8")
        return path

    def case(self, *, overlay: str | None = None) -> dict:
        case = {"id": "case", "request": "do something", "expect": {"outcome": "any"}}
        if overlay is not None:
            case["overlay"] = overlay
        return case

    def test_overlay_is_resolved_relative_to_private_suite(self):
        private = self.root / "private-gold"
        overlay = private / "fixtures/demo/wiki/sources"
        overlay.mkdir(parents=True)
        (overlay / "private.md").write_text("private fixture\n", encoding="utf-8")
        suite = self.write_suite([self.case(overlay="fixtures/demo")], directory=private)
        paths = eval_module.prepare_suite(suite, self.repo, self.output)[0]
        self.assertEqual(
            (paths.workspace / "wiki/sources/private.md").read_text(),
            "private fixture\n",
        )

    def test_overlay_path_cannot_escape_suite_directory(self):
        private = self.root / "private-gold"
        private.mkdir()
        outside = self.root / "outside-fixture"
        outside.mkdir()
        suite = self.write_suite(
            [self.case(overlay="../outside-fixture")], directory=private
        )
        with self.assertRaisesRegex(eval_module.EvalConfigError, "escapes the suite"):
            eval_module.prepare_suite(suite, self.repo, self.output)

    def test_overlay_directory_symlink_cannot_escape_fixture(self):
        private = self.root / "private-gold"
        fixture = private / "fixture"
        fixture.mkdir(parents=True)
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("secret\n", encoding="utf-8")
        link = fixture / "leak"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        suite = self.write_suite([self.case(overlay="fixture")], directory=private)
        with self.assertRaisesRegex(
            eval_module.EvalConfigError, "escapes repository/source tree"
        ):
            eval_module.prepare_suite(suite, self.repo, self.output)

    def test_overlay_file_symlink_cannot_escape_fixture(self):
        private = self.root / "private-gold"
        fixture = private / "fixture"
        fixture.mkdir(parents=True)
        outside = self.root / "secret.txt"
        outside.write_text("secret\n", encoding="utf-8")
        link = fixture / "leak.txt"
        try:
            link.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        suite = self.write_suite([self.case(overlay="fixture")], directory=private)
        with self.assertRaisesRegex(
            eval_module.EvalConfigError, "escapes repository/source tree"
        ):
            eval_module.prepare_suite(suite, self.repo, self.output)

    @unittest.skipUnless(os.name == "posix", "process-group assertion is POSIX-specific")
    def test_timeout_terminates_adapter_process_group(self):
        suite = self.write_suite([self.case()])
        case = eval_module.load_suite(suite)["cases"][0]
        paths = eval_module.prepare_suite(suite, self.repo, self.output)[0]
        marker = paths.workspace / "child-survived.txt"
        child = (
            "import pathlib,time; time.sleep(0.35); "
            f"pathlib.Path({str(marker)!r}).write_text('survived', encoding='utf-8')"
        )
        parent = (
            "import subprocess,sys,time; "
            f"subprocess.Popen([sys.executable, '-c', {child!r}]); "
            "time.sleep(5)"
        )
        command = f"{shlex.quote(sys.executable)} -c {shlex.quote(parent)}"
        code = eval_module.run_adapter(
            command,
            case,
            paths,
            timeout_seconds=0.05,
            isolation="none",
        )
        self.assertEqual(code, 124)
        time.sleep(0.5)
        self.assertFalse(marker.exists())

    def test_bwrap_extra_mount_cannot_expose_repo_or_control(self):
        suite = self.write_suite([self.case()])
        paths = eval_module.prepare_suite(suite, self.repo, self.output)[0]
        with self.assertRaisesRegex(eval_module.EvalConfigError, "control or gold"):
            build_bwrap_command(
                "true",
                paths,
                forbidden_paths=(self.repo, suite, self.output),
                sandbox_read=[self.root],
                bwrap_path="/usr/bin/bwrap",
            )

    def test_bwrap_command_mounts_only_case_and_explicit_system_paths(self):
        suite = self.write_suite([self.case()])
        paths = eval_module.prepare_suite(suite, self.repo, self.output)[0]
        argv, env = build_bwrap_command(
            "printf ok",
            paths,
            forbidden_paths=(self.repo, suite, self.output),
            bwrap_path="/usr/bin/bwrap",
        )
        self.assertIn("--unshare-pid", argv)
        self.assertIn("--die-with-parent", argv)
        self.assertIn("/workspace", argv)
        self.assertEqual(env["PATCHOULI_EVAL_WORKSPACE"], "/workspace")
        # The host suite/repository are not bind destinations; only the selected
        # case workspace and request/response files are source mounts.
        destinations = [
            argv[i + 2]
            for i, token in enumerate(argv[:-2])
            if token in {"--bind", "--ro-bind"}
        ]
        self.assertNotIn(str(self.repo), destinations)
        self.assertNotIn(str(suite), destinations)
        self.assertNotIn(str(self.output), destinations)

    @unittest.skipUnless(
        sys.platform.startswith("linux")
        and shutil.which("bwrap")
        and os.environ.get("PATCHOULI_BWRAP_INTEGRATION") == "1",
        "set PATCHOULI_BWRAP_INTEGRATION=1 on a bubblewrap-capable Linux host",
    )
    def test_bwrap_hides_local_suite_repository_and_run_control(self):
        suite = self.write_suite([self.case()])
        case = eval_module.load_suite(suite)["cases"][0]
        paths = eval_module.prepare_suite(suite, self.repo, self.output)[0]
        targets = [str(suite), str(self.repo / "base.txt"), str(self.output / "suite.json")]
        probe = (
            "import pathlib,sys; "
            f"paths={targets!r}; "
            "visible=[p for p in paths if pathlib.Path(p).exists()]; "
            "print('NO_OP: isolated' if not visible else 'visible=' + ','.join(visible)); "
            "sys.exit(0 if not visible else 9)"
        )
        command = f"{shlex.quote(sys.executable)} -c {shlex.quote(probe)}"
        code = eval_module.run_adapter(
            command,
            case,
            paths,
            timeout_seconds=5,
            isolation="bwrap",
            repo_root=self.repo,
            suite_path=suite,
            output_root=self.output,
        )
        self.assertEqual(code, 0, paths.stderr.read_text())
        self.assertIn("NO_OP: isolated", paths.response.read_text())


if __name__ == "__main__":
    unittest.main()
