from __future__ import annotations

"""Run low-cost, runtime-agnostic evaluations of Patchouli agent contracts."""

import argparse
from pathlib import Path
import sys

from eval_grading import grade_suite, render_summary
from eval_support import (
    DEFAULT_OUTPUT,
    DEFAULT_TIMEOUT_SECONDS,
    EvalConfigError,
    case_paths,
    load_run_suite,
    load_suite,
    prepare_suite,
    run_adapter,
)

# Re-export the programmatic surface used by tests and custom adapters.
__all__ = [
    "case_paths",
    "grade_suite",
    "load_suite",
    "prepare_suite",
    "render_summary",
    "run_adapter",
]


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
            sub.add_argument(
                "--timeout-seconds",
                type=float,
                default=DEFAULT_TIMEOUT_SECONDS,
                help=(
                    "default timeout per case; a case-level timeout_seconds overrides it "
                    f"(default: {DEFAULT_TIMEOUT_SECONDS:g})"
                ),
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    suite_path = _resolve(args.suite)
    repo_root = _resolve(args.repo_root)
    output_root = _resolve(args.output)
    try:
        if args.command == "prepare":
            cases = prepare_suite(suite_path, repo_root, output_root, force=args.force)
            for paths in cases:
                print(f"prepared {paths.root.name}: {paths.workspace}")
            return 0
        if args.command == "run":
            if args.timeout_seconds <= 0:
                raise EvalConfigError("--timeout-seconds must be positive")
            suite = load_suite(suite_path)
            prepare_suite(suite_path, repo_root, output_root, force=args.force)
            suite_timeout = suite.get("timeout_seconds", args.timeout_seconds)
            for case in suite["cases"]:
                paths = case_paths(output_root, case["id"])
                timeout = float(case.get("timeout_seconds", suite_timeout))
                print(f"running {case['id']}...", flush=True)
                run_adapter(
                    args.adapter_command,
                    case,
                    paths,
                    timeout_seconds=timeout,
                )
            results = grade_suite(suite_path, output_root)
        else:
            results = grade_suite(suite_path, output_root)
    except EvalConfigError as exc:
        print(f"eval configuration error: {exc}", file=sys.stderr)
        return 2

    summary = render_summary(load_run_suite(suite_path, output_root), results)
    print(summary, end="")
    return 0 if all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
