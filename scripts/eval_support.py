from __future__ import annotations

"""Shared workspace and adapter utilities for Patchouli evaluations."""

from dataclasses import dataclass
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Iterable

DEFAULT_OUTPUT = Path(".patchouli-eval-runs")
DEFAULT_TIMEOUT_SECONDS = 900.0
DEFAULT_EXCLUDE = (
    ".git",
    ".git/**",
    ".env",
    "personal.md",
    ".venv",
    ".venv/**",
    ".venv-*",
    ".venv-*/**",
    ".pytest_cache",
    ".pytest_cache/**",
    "__pycache__",
    "**/__pycache__/**",
    "*.pyc",
    "**/*.pyc",
    ".patchouli-eval-runs",
    ".patchouli-eval-runs/**",
)


class EvalConfigError(ValueError):
    """The suite is malformed or references an unsafe path."""


@dataclass(frozen=True)
class CasePaths:
    root: Path
    workspace: Path
    request: Path
    response: Path
    stdout: Path
    stderr: Path
    baseline: Path
    adapter: Path
    result: Path


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EvalConfigError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise EvalConfigError(f"invalid JSON in {path}: {exc}") from exc


def _positive_seconds(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise EvalConfigError(f"{label} must be a positive number")
    return float(value)


def load_suite(path: Path) -> dict[str, Any]:
    suite = read_json(path)
    if not isinstance(suite, dict):
        raise EvalConfigError("suite root must be a JSON object")
    if "timeout_seconds" in suite:
        _positive_seconds(suite["timeout_seconds"], label="suite timeout_seconds")

    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        raise EvalConfigError("suite must contain a non-empty `cases` list")

    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for raw in cases:
        if not isinstance(raw, dict):
            raise EvalConfigError("each case must be a JSON object")
        case_id = raw.get("id")
        request = raw.get("request")
        expect = raw.get("expect")
        if not isinstance(case_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", case_id):
            raise EvalConfigError(f"invalid case id: {case_id!r}")
        if case_id in seen:
            raise EvalConfigError(f"duplicate case id: {case_id}")
        if not isinstance(request, str) or not request.strip():
            raise EvalConfigError(f"case {case_id}: request must be non-empty text")
        if not isinstance(expect, dict):
            raise EvalConfigError(f"case {case_id}: expect must be an object")
        outcome = expect.get("outcome", "any")
        if outcome not in {"any", "no_op", "write"}:
            raise EvalConfigError(f"case {case_id}: invalid outcome {outcome!r}")
        if "timeout_seconds" in raw:
            _positive_seconds(
                raw["timeout_seconds"], label=f"case {case_id} timeout_seconds"
            )
        seen.add(case_id)
        normalized.append(raw)

    result = dict(suite)
    result["cases"] = normalized
    return result


def load_run_suite(suite_path: Path, output_root: Path) -> dict[str, Any]:
    """Load the frozen suite used to prepare a run, when one exists."""

    frozen = output_root / "suite.json"
    return load_suite(frozen if frozen.is_file() else suite_path)


def patterns_for(suite: dict[str, Any], case: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = list(DEFAULT_EXCLUDE)
    for source in (suite.get("exclude", []), case.get("exclude", [])):
        if not isinstance(source, list) or not all(isinstance(item, str) for item in source):
            raise EvalConfigError("exclude must be a list of glob strings")
        values.extend(source)
    return tuple(dict.fromkeys(values))


def matches(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _excluded(rel: str, patterns: tuple[str, ...]) -> bool:
    parts = Path(rel).parts
    if any(part in {".git", ".pytest_cache", "__pycache__"} for part in parts):
        return True
    if any(part == ".venv" or part.startswith(".venv-") for part in parts):
        return True
    return matches(rel, patterns)


def _safe_relative(root: Path, value: str, *, label: str) -> Path:
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise EvalConfigError(f"{label} escapes repository root: {value}") from exc
    return candidate


def copy_workspace(source: Path, destination: Path, patterns: tuple[str, ...]) -> None:
    if destination.exists():
        raise EvalConfigError(f"workspace already exists: {destination}")
    destination.mkdir(parents=True)
    for path in sorted(source.rglob("*")):
        rel = path.relative_to(source).as_posix()
        if _excluded(rel, patterns):
            continue
        target = destination / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_symlink():
            target.parent.mkdir(parents=True, exist_ok=True)
            resolved = path.resolve()
            if resolved.is_file():
                shutil.copy2(resolved, target)
            elif resolved.is_dir():
                shutil.copytree(resolved, target, dirs_exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def apply_overlay(repo_root: Path, workspace: Path, overlay: str | None) -> None:
    if overlay is None:
        return
    overlay_path = _safe_relative(repo_root, overlay, label="overlay")
    if not overlay_path.is_dir():
        raise EvalConfigError(f"overlay is not a directory: {overlay}")
    shutil.copytree(overlay_path, workspace, dirs_exist_ok=True)


def initialize_git(workspace: Path) -> None:
    """Create the baseline history required by Patchouli's scoped commit contract."""

    commands = (
        ("init", "-q"),
        ("config", "user.name", "Patchouli Eval"),
        ("config", "user.email", "patchouli-eval@example.invalid"),
        ("config", "commit.gpgsign", "false"),
        ("add", "--", "."),
        ("commit", "-q", "-m", "eval: baseline fixture"),
    )
    for args in commands:
        try:
            subprocess.run(
                ["git", *args],
                cwd=workspace,
                check=True,
                text=True,
                capture_output=True,
            )
        except OSError as exc:
            raise EvalConfigError("git is required to prepare Patchouli eval cases") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "git command failed").strip()
            raise EvalConfigError(f"could not initialize eval Git history: {detail}") from exc


def _digest(path: Path) -> str:
    if path.is_symlink():
        return "symlink:" + os.readlink(path)
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return "sha256:" + hasher.hexdigest()


def snapshot(root: Path, patterns: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    if not root.exists():
        return result
    for path in sorted(root.rglob("*")):
        if not (path.is_file() or path.is_symlink()):
            continue
        rel = path.relative_to(root).as_posix()
        if _excluded(rel, patterns):
            continue
        result[rel] = _digest(path)
    return result


def changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


def case_paths(output_root: Path, case_id: str) -> CasePaths:
    root = output_root / case_id
    return CasePaths(
        root=root,
        workspace=root / "workspace",
        request=root / "request.txt",
        response=root / "response.txt",
        stdout=root / "stdout.txt",
        stderr=root / "stderr.txt",
        baseline=root / "baseline.json",
        adapter=root / "adapter.json",
        result=root / "result.json",
    )


def prepare_case(
    suite: dict[str, Any], case: dict[str, Any], repo_root: Path, output_root: Path
) -> CasePaths:
    paths = case_paths(output_root, case["id"])
    paths.root.mkdir(parents=True, exist_ok=False)
    patterns = patterns_for(suite, case)
    copy_workspace(repo_root, paths.workspace, patterns)
    apply_overlay(repo_root, paths.workspace, case.get("overlay"))
    initialize_git(paths.workspace)
    paths.request.write_text(case["request"].rstrip() + "\n", encoding="utf-8")
    paths.baseline.write_text(
        json.dumps(snapshot(paths.workspace, patterns), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return paths


def prepare_suite(
    suite_path: Path,
    repo_root: Path,
    output_root: Path,
    *,
    force: bool = False,
) -> list[CasePaths]:
    suite = load_suite(suite_path)
    try:
        output_rel = output_root.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        output_rel = None
    if output_rel:
        suite = dict(suite)
        suite["exclude"] = [
            *suite.get("exclude", []),
            output_rel,
            f"{output_rel}/**",
        ]
    if output_root.exists():
        if not force:
            raise EvalConfigError(
                f"output directory exists: {output_root}; pass --force to replace it"
            )
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)
    (output_root / "suite.json").write_text(
        json.dumps(suite, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return [prepare_case(suite, case, repo_root, output_root) for case in suite["cases"]]


def _timeout_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else value


def run_adapter(
    command: str,
    case: dict[str, Any],
    paths: CasePaths,
    *,
    timeout_seconds: float | None = None,
) -> int:
    env = os.environ.copy()
    env.update(
        {
            "PATCHOULI_EVAL_CASE_ID": case["id"],
            "PATCHOULI_EVAL_REQUEST": case["request"],
            "PATCHOULI_EVAL_REQUEST_FILE": str(paths.request.resolve()),
            "PATCHOULI_EVAL_RESPONSE_FILE": str(paths.response.resolve()),
            "PATCHOULI_EVAL_WORKSPACE": str(paths.workspace.resolve()),
        }
    )
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            cwd=paths.workspace,
            env=env,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
        stdout, stderr, returncode = completed.stdout, completed.stderr, completed.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout, stderr, returncode = _timeout_text(exc.stdout), _timeout_text(exc.stderr), 124

    paths.stdout.write_text(stdout, encoding="utf-8")
    paths.stderr.write_text(stderr, encoding="utf-8")
    if not paths.response.exists():
        paths.response.write_text(stdout, encoding="utf-8")
    paths.adapter.write_text(
        json.dumps(
            {
                "returncode": returncode,
                "timed_out": timed_out,
                "timeout_seconds": timeout_seconds,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return returncode
