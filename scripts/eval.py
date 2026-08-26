from __future__ import annotations

"""Low-cost, runtime-agnostic evaluation harness for Patchouli.

The harness copies the framework into one isolated workspace per case, optionally
applies a small fixture overlay, runs an external agent command, and grades only
observable outcomes: changed paths, NO_OP/write behavior, content assertions, and
Patchouli's deterministic binding floor.

Examples, from the repository root:

    python3 scripts/eval.py prepare evals/smoke.json
    # Run an agent manually in each generated workspace, then write response.txt.
    python3 scripts/eval.py grade evals/smoke.json

    python3 scripts/eval.py run evals/smoke.json \
      --adapter-command 'claude -p "$PATCHOULI_EVAL_REQUEST"'

The adapter command is deliberately a shell string because coding-agent CLIs have
incompatible argument shapes. It runs with cwd set to the case workspace and gets
PATCHOULI_EVAL_* environment variables. Its stdout becomes response.txt unless the
adapter writes PATCHOULI_EVAL_RESPONSE_FILE itself.
"""

import argparse
from dataclasses import dataclass
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Iterable

DEFAULT_OUTPUT = Path(".patchouli-eval-runs")
DEFAULT_EXCLUDE = (
    ".git",
    ".git/**",
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
NO_OP_RE = re.compile(r"(?m)^\s*NO_OP:\s*\S")


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


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EvalConfigError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise EvalConfigError(f"invalid JSON in {path}: {exc}") from exc


def load_suite(path: Path) -> dict[str, Any]:
    suite = _read_json(path)
    if not isinstance(suite, dict):
        raise EvalConfigError("suite root must be a JSON object")
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
        seen.add(case_id)
        normalized.append(raw)
    suite = dict(suite)
    suite["cases"] = normalized
    return suite


def _patterns(suite: dict[str, Any], case: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = list(DEFAULT_EXCLUDE)
    for source in (suite.get("exclude", []), case.get("exclude", [])):
        if not isinstance(source, list) or not all(isinstance(item, str) for item in source):
            raise EvalConfigError("exclude must be a list of glob strings")
        values.extend(source)
    return tuple(dict.fromkeys(values))


def _matches(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _excluded(path: Path, rel: str, patterns: tuple[str, ...]) -> bool:
    parts = Path(rel).parts
    if any(part in {".git", ".pytest_cache", "__pycache__"} for part in parts):
        return True
    if any(part == ".venv" or part.startswith(".venv-") for part in parts):
        return True
    return _matches(rel, patterns)


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
        if _excluded(path, rel, patterns):
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
        if _excluded(path, rel, patterns):
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
    patterns = _patterns(suite, case)
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


def run_adapter(command: str, case: dict[str, Any], paths: CasePaths) -> int:
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
    completed = subprocess.run(
        command,
        cwd=paths.workspace,
        env=env,
        shell=True,
        text=True,
        capture_output=True,
    )
    paths.stdout.write_text(completed.stdout, encoding="utf-8")
    paths.stderr.write_text(completed.stderr, encoding="utf-8")
    if not paths.response.exists():
        paths.response.write_text(completed.stdout, encoding="utf-8")
    paths.adapter.write_text(
        json.dumps({"returncode": completed.returncode}, indent=2) + "\n",
        encoding="utf-8",
    )
    return completed.returncode


def _read_response(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _glob_files(root: Path, pattern: str) -> list[Path]:
    return sorted(path for path in root.glob(pattern) if path.is_file())


def _grade_content(workspace: Path, checks: Any, failures: list[str]) -> None:
    if checks is None:
        return
    if not isinstance(checks, list):
        failures.append("expect.content must be a list")
        return
    for index, item in enumerate(checks, start=1):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            failures.append(f"content check {index} must contain a path glob")
            continue
        matches = _glob_files(workspace, item["path"])
        min_matches = item.get("min_matches", 1)
        if not isinstance(min_matches, int) or min_matches < 0:
            failures.append(f"content check {index}: min_matches must be a non-negative integer")
            continue
        if len(matches) < min_matches:
            failures.append(
                f"content check {index}: {item['path']!r} matched {len(matches)} file(s), "
                f"expected at least {min_matches}"
            )
            continue
        contains = item.get("contains", [])
        not_contains = item.get("not_contains", [])
        if (
            not isinstance(contains, list)
            or not isinstance(not_contains, list)
            or not all(isinstance(value, str) for value in [*contains, *not_contains])
        ):
            failures.append(
                f"content check {index}: contains/not_contains must be lists of strings"
            )
            continue
        for path in matches:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                failures.append(f"content check {index}: non-UTF-8 file {path}")
                continue
            for value in contains:
                if value not in text:
                    failures.append(
                        f"content check {index}: {path.relative_to(workspace)} lacks {value!r}"
                    )
            for value in not_contains:
                if value in text:
                    failures.append(
                        f"content check {index}: {path.relative_to(workspace)} contains forbidden {value!r}"
                    )


def grade_case(
    suite: dict[str, Any], case: dict[str, Any], output_root: Path
) -> dict[str, Any]:
    paths = case_paths(output_root, case["id"])
    patterns = _patterns(suite, case)
    before = _read_json(paths.baseline)
    if not isinstance(before, dict):
        raise EvalConfigError(f"case {case['id']}: baseline must be an object")
    after = snapshot(paths.workspace, patterns)
    changed = changed_paths(before, after)
    response = _read_response(paths.response)
    expect = case["expect"]
    failures: list[str] = []

    if paths.adapter.exists():
        adapter = _read_json(paths.adapter)
        expected_exit = expect.get("exit_code", 0)
        if adapter.get("returncode") != expected_exit:
            failures.append(
                f"adapter exit code {adapter.get('returncode')}, expected {expected_exit}"
            )

    outcome = expect.get("outcome", "any")
    is_no_op = bool(NO_OP_RE.search(response))
    if outcome == "no_op" and not is_no_op:
        failures.append("response does not contain a first-class NO_OP line")
    if outcome == "write":
        if is_no_op:
            failures.append("response returned NO_OP but a write was expected")
        if not changed:
            failures.append("no file changed but a write was expected")

    allowed = expect.get("allowed_changes")
    if allowed is not None:
        if not isinstance(allowed, list) or not all(isinstance(value, str) for value in allowed):
            failures.append("allowed_changes must be a list of glob strings")
        else:
            unexpected = [path for path in changed if not _matches(path, allowed)]
            if unexpected:
                failures.append("unexpected changed paths: " + ", ".join(unexpected))

    required = expect.get("required_changes", [])
    if not isinstance(required, list) or not all(isinstance(value, str) for value in required):
        failures.append("required_changes must be a list of glob strings")
    else:
        for pattern in required:
            if not any(fnmatch.fnmatchcase(path, pattern) for path in changed):
                failures.append(f"required change pattern not observed: {pattern}")

    response_contains = expect.get("response_contains", [])
    response_not_contains = expect.get("response_not_contains", [])
    if (
        not isinstance(response_contains, list)
        or not isinstance(response_not_contains, list)
        or not all(
            isinstance(value, str)
            for value in [*response_contains, *response_not_contains]
        )
    ):
        failures.append("response containment checks must be lists of strings")
    else:
        for value in response_contains:
            if value not in response:
                failures.append(f"response lacks {value!r}")
        for value in response_not_contains:
            if value in response:
                failures.append(f"response contains forbidden {value!r}")

    _grade_content(paths.workspace, expect.get("content"), failures)

    check_result: dict[str, Any] | None = None
    if expect.get("check_wiki", False):
        checker = paths.workspace / "scripts" / "check_wiki.py"
        if not checker.is_file():
            failures.append("check_wiki requested but scripts/check_wiki.py is missing")
        else:
            completed = subprocess.run(
                [sys.executable, str(checker)],
                cwd=paths.workspace,
                text=True,
                capture_output=True,
            )
            check_result = {
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
            if completed.returncode != 0:
                failures.append("binding floor failed")

    result = {
        "id": case["id"],
        "passed": not failures,
        "changed_paths": changed,
        "failures": failures,
        "binding_floor": check_result,
    }
    paths.result.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return result


def render_summary(suite: dict[str, Any], results: list[dict[str, Any]]) -> str:
    passed = sum(bool(result["passed"]) for result in results)
    lines = [
        f"# Eval: {suite.get('name', 'unnamed')}\n",
        f"\n{passed}/{len(results)} case(s) passed.\n\n",
    ]
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        lines.append(f"- **{status}** `{result['id']}`")
        if result["failures"]:
            lines.append(" — " + "; ".join(result["failures"]))
        lines.append("\n")
    return "".join(lines)


def grade_suite(suite_path: Path, output_root: Path) -> list[dict[str, Any]]:
    suite = load_suite(suite_path)
    results = [grade_case(suite, case, output_root) for case in suite["cases"]]
    (output_root / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (output_root / "summary.md").write_text(render_summary(suite, results), encoding="utf-8")
    return results


def _resolve(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run and grade Patchouli agent evaluations")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "grade", "run"):
        sub = subparsers.add_parser(command)
        sub.add_argument("suite", help="suite JSON path")
        sub.add_argument(
            "--repo-root",
            default=".",
            help="Patchouli repository root (default: current directory)",
        )
        sub.add_argument(
            "--output",
            default=str(DEFAULT_OUTPUT),
            help=f"run directory (default: {DEFAULT_OUTPUT})",
        )
        if command in {"prepare", "run"}:
            sub.add_argument("--force", action="store_true", help="replace an existing output")
        if command == "run":
            sub.add_argument(
                "--adapter-command",
                required=True,
                help="shell command used to run one agent case",
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    suite_path = _resolve(args.suite)
    repo_root = _resolve(args.repo_root)
    output_root = _resolve(args.output)
    try:
        if args.command == "prepare":
            cases = prepare_suite(
                suite_path, repo_root, output_root, force=args.force
            )
            for paths in cases:
                print(f"prepared {paths.root.name}: {paths.workspace}")
            return 0
        if args.command == "run":
            suite = load_suite(suite_path)
            prepare_suite(suite_path, repo_root, output_root, force=args.force)
            for case in suite["cases"]:
                paths = case_paths(output_root, case["id"])
                print(f"running {case['id']}...", flush=True)
                run_adapter(args.adapter_command, case, paths)
            results = grade_suite(suite_path, output_root)
        else:
            results = grade_suite(suite_path, output_root)
    except EvalConfigError as exc:
        print(f"eval configuration error: {exc}", file=sys.stderr)
        return 2

    summary = render_summary(load_suite(suite_path), results)
    print(summary, end="")
    return 0 if all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
