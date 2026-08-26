from __future__ import annotations

"""Deterministic graders for Patchouli agent-evaluation cases."""

import fnmatch
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

from eval_support import (
    EvalConfigError,
    case_paths,
    changed_paths,
    load_run_suite,
    matches,
    patterns_for,
    read_json,
    snapshot,
)

NO_OP_RE = re.compile(r"(?m)^\s*NO_OP:\s*\S")


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
        matched_paths = _glob_files(workspace, item["path"])
        min_matches = item.get("min_matches", 1)
        if not isinstance(min_matches, int) or isinstance(min_matches, bool) or min_matches < 0:
            failures.append(
                f"content check {index}: min_matches must be a non-negative integer"
            )
            continue
        if len(matched_paths) < min_matches:
            failures.append(
                f"content check {index}: {item['path']!r} matched {len(matched_paths)} "
                f"file(s), expected at least {min_matches}"
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
        for path in matched_paths:
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
                        f"content check {index}: {path.relative_to(workspace)} contains "
                        f"forbidden {value!r}"
                    )


def grade_case(
    suite: dict[str, Any], case: dict[str, Any], output_root: Path
) -> dict[str, Any]:
    paths = case_paths(output_root, case["id"])
    patterns = patterns_for(suite, case)
    before = read_json(paths.baseline)
    if not isinstance(before, dict):
        raise EvalConfigError(f"case {case['id']}: baseline must be an object")
    after = snapshot(paths.workspace, patterns)
    changed = changed_paths(before, after)
    response = _read_response(paths.response)
    expect = case["expect"]
    failures: list[str] = []

    if paths.adapter.exists():
        adapter = read_json(paths.adapter)
        expected_exit = expect.get("exit_code", 0)
        if adapter.get("timed_out"):
            failures.append(
                f"adapter timed out after {adapter.get('timeout_seconds')} second(s)"
            )
        elif adapter.get("returncode") != expected_exit:
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
            unexpected = [path for path in changed if not matches(path, allowed)]
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
    suite = load_run_suite(suite_path, output_root)
    results = [grade_case(suite, case, output_root) for case in suite["cases"]]
    (output_root / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (output_root / "summary.md").write_text(render_summary(suite, results), encoding="utf-8")
    return results
