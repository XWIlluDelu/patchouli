from __future__ import annotations

"""Adapter isolation and process-tree lifecycle for Patchouli evaluations."""

import json
import os
from pathlib import Path, PurePosixPath
import shutil
import signal
import subprocess
import sys
import time
from typing import Any, Sequence

from eval_support import CasePaths, EvalConfigError

DEFAULT_ISOLATION = "bwrap"
PROCESS_TERMINATION_GRACE_SECONDS = 1.0
SANDBOX_WORKSPACE = "/workspace"
SANDBOX_CONTROL = "/patchouli-eval"


def _timeout_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else value


def _paths_overlap(left: Path, right: Path) -> bool:
    left = left.resolve()
    right = right.resolve()
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _validate_sandbox_source(
    value: Path | str,
    *,
    label: str,
    forbidden_paths: Sequence[Path],
) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.exists():
        raise EvalConfigError(f"{label} does not exist: {path}")
    if path == Path(path.anchor):
        raise EvalConfigError(f"{label} must not expose a filesystem root: {path}")
    for forbidden in forbidden_paths:
        if _paths_overlap(path, forbidden):
            raise EvalConfigError(
                f"{label} would expose evaluation control or gold data: {path}"
            )
    return path


def _sandbox_dirs(path: str) -> list[str]:
    pure = PurePosixPath(path)
    values: list[str] = []
    current = PurePosixPath("/")
    for part in pure.parts[1:-1]:
        current /= part
        values.append(str(current))
    return values


def _append_mount(
    argv: list[str],
    *,
    source: Path,
    destination: str,
    read_only: bool,
    created_dirs: set[str],
) -> None:
    for directory in _sandbox_dirs(destination):
        if directory not in created_dirs:
            argv.extend(("--dir", directory))
            created_dirs.add(directory)
    argv.extend(("--ro-bind" if read_only else "--bind", str(source), destination))


def build_bwrap_command(
    command: str,
    paths: CasePaths,
    *,
    forbidden_paths: Sequence[Path],
    sandbox_home: Path | str | None = None,
    sandbox_read: Sequence[Path | str] = (),
    sandbox_write: Sequence[Path | str] = (),
    bwrap_path: str | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Construct a Linux mount/PID sandbox that exposes no eval control files."""

    if not sys.platform.startswith("linux"):
        raise EvalConfigError("bubblewrap isolation is supported only on Linux")
    binary = bwrap_path or shutil.which("bwrap")
    if not binary:
        raise EvalConfigError(
            "bubblewrap (`bwrap`) is required for held-out `run`; install it or "
            "pass `--isolation none` for an explicitly open-book smoke run"
        )

    paths.response.parent.mkdir(parents=True, exist_ok=True)
    paths.response.touch(exist_ok=True)
    created_dirs = {"/"}
    argv = [
        binary,
        "--die-with-parent",
        "--new-session",
        "--unshare-user",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--cap-drop",
        "ALL",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
    ]

    # A small, read-only system root; host home, repository and run-control paths
    # are absent unless the caller explicitly mounts a non-overlapping directory.
    for system_path in (Path("/usr"), Path("/etc")):
        if system_path.exists():
            if any(_paths_overlap(system_path, item) for item in forbidden_paths):
                raise EvalConfigError(
                    f"evaluation control data lies under required sandbox system mount: "
                    f"{system_path}"
                )
            _append_mount(
                argv,
                source=system_path,
                destination=str(system_path),
                read_only=True,
                created_dirs=created_dirs,
            )
    for link in (Path("/bin"), Path("/lib"), Path("/lib64"), Path("/sbin")):
        if link.is_symlink():
            destination = str(link)
            parent = str(PurePosixPath(destination).parent)
            if parent not in created_dirs:
                argv.extend(("--dir", parent))
                created_dirs.add(parent)
            argv.extend(("--symlink", os.readlink(link), destination))
        elif link.exists():
            _append_mount(
                argv,
                source=link,
                destination=str(link),
                read_only=True,
                created_dirs=created_dirs,
            )

    _append_mount(
        argv,
        source=paths.workspace.resolve(),
        destination=SANDBOX_WORKSPACE,
        read_only=False,
        created_dirs=created_dirs,
    )
    _append_mount(
        argv,
        source=paths.request.resolve(),
        destination=f"{SANDBOX_CONTROL}/request.txt",
        read_only=True,
        created_dirs=created_dirs,
    )
    _append_mount(
        argv,
        source=paths.response.resolve(),
        destination=f"{SANDBOX_CONTROL}/response.txt",
        read_only=False,
        created_dirs=created_dirs,
    )

    if sandbox_home is None:
        argv.extend(("--dir", "/home", "--dir", "/home/agent"))
        home = "/home/agent"
    else:
        source = _validate_sandbox_source(
            sandbox_home,
            label="sandbox home",
            forbidden_paths=forbidden_paths,
        )
        if not source.is_dir():
            raise EvalConfigError(f"sandbox home is not a directory: {source}")
        _append_mount(
            argv,
            source=source,
            destination="/home/agent",
            read_only=False,
            created_dirs=created_dirs,
        )
        home = "/home/agent"

    for index, value in enumerate(sandbox_read):
        source = _validate_sandbox_source(
            value,
            label=f"sandbox read path {index + 1}",
            forbidden_paths=forbidden_paths,
        )
        _append_mount(
            argv,
            source=source,
            destination=str(source),
            read_only=True,
            created_dirs=created_dirs,
        )
    for index, value in enumerate(sandbox_write):
        source = _validate_sandbox_source(
            value,
            label=f"sandbox write path {index + 1}",
            forbidden_paths=forbidden_paths,
        )
        _append_mount(
            argv,
            source=source,
            destination=str(source),
            read_only=False,
            created_dirs=created_dirs,
        )

    env_updates = {
        "HOME": home,
        "XDG_CONFIG_HOME": f"{home}/.config",
        "XDG_CACHE_HOME": f"{home}/.cache",
        "XDG_DATA_HOME": f"{home}/.local/share",
        "PATCHOULI_EVAL_WORKSPACE": SANDBOX_WORKSPACE,
        "PATCHOULI_EVAL_REQUEST_FILE": f"{SANDBOX_CONTROL}/request.txt",
        "PATCHOULI_EVAL_RESPONSE_FILE": f"{SANDBOX_CONTROL}/response.txt",
    }
    for key, value in env_updates.items():
        argv.extend(("--setenv", key, value))
    argv.extend(("--chdir", SANDBOX_WORKSPACE, "/bin/sh", "-lc", command))
    return argv, env_updates


def _direct_command(command: str) -> list[str]:
    if os.name == "nt":
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", command]
    return ["/bin/sh", "-lc", command]


def _process_group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    """Terminate the process group/session created for one adapter invocation."""

    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + PROCESS_TERMINATION_GRACE_SECONDS
        while time.monotonic() < deadline and _process_group_exists(process.pid):
            process.poll()  # reap the group leader so an empty group disappears
            time.sleep(0.02)
        if _process_group_exists(process.pid):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        return

    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                capture_output=True,
                text=True,
            )
            return
        except OSError:
            pass
    try:
        process.kill()
    except OSError:
        pass


def _run_process(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: float | None,
) -> tuple[str, str, int, bool]:
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    try:
        process = subprocess.Popen(
            list(argv),
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=(os.name == "posix"),
            creationflags=creationflags,
        )
    except OSError as exc:
        raise EvalConfigError(f"could not start adapter: {exc}") from exc

    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        return stdout, stderr, process.returncode, False
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        stdout, stderr = process.communicate()
        return _timeout_text(stdout), _timeout_text(stderr), 124, True


def run_adapter(
    command: str,
    case: dict[str, Any],
    paths: CasePaths,
    *,
    timeout_seconds: float | None = None,
    isolation: str = "none",
    repo_root: Path | None = None,
    suite_path: Path | None = None,
    output_root: Path | None = None,
    sandbox_home: Path | str | None = None,
    sandbox_read: Sequence[Path | str] = (),
    sandbox_write: Sequence[Path | str] = (),
    bwrap_path: str | None = None,
) -> int:
    env = os.environ.copy()
    env["PATCHOULI_EVAL_CASE_ID"] = case["id"]
    env["PATCHOULI_EVAL_REQUEST"] = case["request"]

    if isolation == "bwrap":
        if repo_root is None or suite_path is None or output_root is None:
            raise EvalConfigError(
                "bwrap isolation needs repo_root, suite_path, and output_root"
            )
        forbidden = (repo_root.resolve(), suite_path.resolve(), output_root.resolve())
        argv, sandbox_env = build_bwrap_command(
            command,
            paths,
            forbidden_paths=forbidden,
            sandbox_home=sandbox_home,
            sandbox_read=sandbox_read,
            sandbox_write=sandbox_write,
            bwrap_path=bwrap_path,
        )
        env.update(sandbox_env)
    elif isolation == "none":
        env.update(
            {
                "PATCHOULI_EVAL_REQUEST_FILE": str(paths.request.resolve()),
                "PATCHOULI_EVAL_RESPONSE_FILE": str(paths.response.resolve()),
                "PATCHOULI_EVAL_WORKSPACE": str(paths.workspace.resolve()),
            }
        )
        argv = _direct_command(command)
    else:
        raise EvalConfigError(f"unknown adapter isolation mode: {isolation!r}")

    response_existed = paths.response.exists()
    response_before = paths.response.read_bytes() if response_existed else None
    stdout, stderr, returncode, timed_out = _run_process(
        argv,
        cwd=paths.workspace,
        env=env,
        timeout_seconds=timeout_seconds,
    )
    paths.stdout.write_text(stdout, encoding="utf-8")
    paths.stderr.write_text(stderr, encoding="utf-8")

    response_after = paths.response.read_bytes() if paths.response.exists() else None
    adapter_wrote_response = response_after != response_before or (
        not response_existed and response_after is not None
    )
    if not adapter_wrote_response:
        paths.response.write_text(stdout, encoding="utf-8")

    paths.adapter.write_text(
        json.dumps(
            {
                "returncode": returncode,
                "timed_out": timed_out,
                "timeout_seconds": timeout_seconds,
                "isolation": isolation,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return returncode
