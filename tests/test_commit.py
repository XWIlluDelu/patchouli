"""Tests for operation-scoped Git commits."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from commit import commit_paths, staged_paths  # noqa: E402
from workspace_paths import Workspace  # noqa: E402


class ScopedCommit(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ws = Workspace.from_path(self.root)
        self.git("init", "-q")
        self.git("config", "user.name", "Patchouli Test")
        self.git("config", "user.email", "patchouli@example.test")
        self.git("config", "commit.gpgsign", "false")
        self.put("owned.md", "old\n")
        self.put("other.md", "old\n")
        self.git("add", "owned.md", "other.md")
        self.git("commit", "-q", "-m", "initial")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    def put(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_commits_only_exact_owned_file(self):
        self.put("owned.md", "new\n")
        self.put("unrelated.tmpdata", "leave me\n")
        committed = commit_paths(self.ws, "test: owned", ["owned.md"])
        self.assertEqual(committed, ("owned.md",))
        self.assertEqual(self.git("show", "--format=", "--name-only", "HEAD").strip(), "owned.md")
        self.assertEqual(staged_paths(self.ws), ())
        self.assertIn("?? unrelated.tmpdata", self.git("status", "--short"))

    def test_refuses_pre_staged_changes(self):
        self.put("other.md", "staged\n")
        self.git("add", "other.md")
        self.put("owned.md", "new\n")
        with self.assertRaises(SystemExit):
            commit_paths(self.ws, "test: owned", ["owned.md"])
        self.assertEqual(staged_paths(self.ws), ("other.md",))

    def test_rejecting_hook_restores_clean_index(self):
        hook = self.root / ".git/hooks/pre-commit"
        hook.write_text(
            "#!/bin/sh\nprintf 'hook change\\n' > other.md\ngit add other.md\nexit 1\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)
        original_head = self.git("rev-parse", "HEAD").strip()
        self.put("owned.md", "new\n")
        with self.assertRaises(SystemExit):
            commit_paths(self.ws, "test: rejected hook", ["owned.md"])
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), original_head)
        self.assertEqual(staged_paths(self.ws), ())
        self.assertEqual((self.root / "owned.md").read_text(), "new\n")
        self.assertEqual((self.root / "other.md").read_text(), "hook change\n")

    def test_hook_expansion_rolls_back_commit(self):
        hook = self.root / ".git/hooks/pre-commit"
        hook.write_text(
            "#!/bin/sh\nprintf 'hook change\\n' > other.md\ngit add other.md\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)
        original_head = self.git("rev-parse", "HEAD").strip()
        self.put("owned.md", "new\n")
        with self.assertRaises(SystemExit):
            commit_paths(self.ws, "test: hook scope", ["owned.md"])
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), original_head)
        self.assertEqual(staged_paths(self.ws), ())
        self.assertEqual((self.root / "owned.md").read_text(), "new\n")
        self.assertEqual((self.root / "other.md").read_text(), "hook change\n")

    def test_commits_owned_deletion(self):
        (self.root / "owned.md").unlink()
        self.assertEqual(commit_paths(self.ws, "test: delete", ["owned.md"]), ("owned.md",))
        self.assertIn("D\towned.md", self.git("show", "--format=", "--name-status", "HEAD"))

    def test_rejects_directory_pathspec(self):
        with self.assertRaises(SystemExit):
            commit_paths(self.ws, "test: directory", ["."])

    def test_rejects_path_outside_workspace(self):
        with self.assertRaises(SystemExit):
            commit_paths(self.ws, "test: outside", [str(self.root.parent / "outside.md")])


if __name__ == "__main__":
    unittest.main()
