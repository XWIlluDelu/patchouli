"""Commit exactly the files written by one Patchouli contract.

Usage:
    python3 scripts/commit.py -m "ingest: 1706.03762" path [path ...]

The index must be clean before invocation. Paths must be exact files inside the
workspace; directories and repository-wide staging are rejected.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

from workspace_paths import Workspace


def _git(workspace: Workspace, *args: str, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(workspace.root), *args],
        check=True,
        text=True,
        capture_output=capture,
    )


def _nul_paths(output: str) -> tuple[str, ...]:
    return tuple(path for path in output.split("\0") if path)


def staged_paths(workspace: Workspace) -> tuple[str, ...]:
    result = _git(workspace, "diff", "--cached", "--name-only", "-z")
    return _nul_paths(result.stdout)


def head_paths(workspace: Workspace) -> tuple[str, ...]:
    result = _git(
        workspace,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        "-z",
        "HEAD",
    )
    return _nul_paths(result.stdout)


def _exact_paths(workspace: Workspace, values: list[str]) -> tuple[str, ...]:
    paths: list[str] = []
    for value in values:
        try:
            absolute = workspace.abspath(value)
            relative = workspace.relpath(absolute)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        if relative == ".git" or relative.startswith(".git/"):
            raise SystemExit("refusing to stage Git metadata")
        if absolute.is_dir():
            raise SystemExit(f"pass exact files, not a directory: {relative}")
        if relative not in paths:
            paths.append(relative)
    if not paths:
        raise SystemExit("at least one operation-owned file is required")
    return tuple(paths)


def commit_paths(workspace: Workspace, message: str, values: list[str]) -> tuple[str, ...]:
    before = staged_paths(workspace)
    if before:
        raise SystemExit(
            "refusing to mix this contract with pre-staged changes: " + ", ".join(before)
        )
    requested = _exact_paths(workspace, values)
    _git(workspace, "add", "--", *requested)
    staged = staged_paths(workspace)
    unexpected = sorted(set(staged) - set(requested))
    if unexpected:
        raise SystemExit("staged paths escaped the operation-owned set: " + ", ".join(unexpected))
    if not staged:
        print("no changes to commit")
        return ()
    try:
        _git(
            workspace,
            "commit",
            "--only",
            "-m",
            message,
            "--",
            *requested,
            capture=False,
        )
    except subprocess.CalledProcessError as exc:
        _git(workspace, "reset", "--mixed", "HEAD")
        raise SystemExit(
            "git commit failed; the previously clean index was restored and "
            "working-tree changes were preserved"
        ) from exc
    committed = head_paths(workspace)
    if set(committed) != set(staged):
        _git(workspace, "reset", "--mixed", "HEAD^")
        raise SystemExit(
            "a commit hook expanded the owned path set; the commit was rolled back. "
            f"Expected {sorted(staged)!r}, observed {sorted(committed)!r}"
        )
    return committed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Commit exact operation-owned files")
    parser.add_argument("-m", "--message", required=True, help="commit subject")
    parser.add_argument("paths", nargs="+", help="exact files written by the active contract")
    args = parser.parse_args(argv)
    committed = commit_paths(Workspace.from_path(None), args.message, args.paths)
    if committed:
        print("committed: " + ", ".join(committed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
