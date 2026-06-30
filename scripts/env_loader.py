from __future__ import annotations

import os
import random
from pathlib import Path


class KeyRetry(Exception):
    """Raised by a caller to signal: this API key failed, try the next one."""


class KeyPoolExhausted(RuntimeError):
    """Every key in the pool failed, or the pool was empty."""


def load_key_pool(path: Path | str, key: str) -> list[str]:
    """Return all non-empty values for ``key`` from the .env file, in file order.

    Patchouli carries its own gitignored .env (Plan B): the keys live there, one
    ``KEY=value`` line each, and a key may repeat to pool several credentials.
    Values are deduplicated, order preserved. If the file names ``key`` nowhere,
    fall back to a shell-exported ``key`` so a runtime that does export it works too.
    """

    env_path = Path(path)
    values: list[str] = []
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == key:
                v = v.strip().strip("'\"")
                if v and v not in values:
                    values.append(v)
    if not values:
        env_val = os.environ.get(key, "").strip()
        if env_val:
            values = [env_val]
    return values


def with_key_retry(path: Path | str, key: str, fn):
    """Call ``fn(api_key)`` with a random key from the pool; on failure, try the
    rest until one succeeds or the pool is exhausted.

    ``fn`` receives one key and raises ``KeyRetry`` to say "this key failed, try
    another" (the caller decides which HTTP statuses are retryable). Random choice,
    not stateful round-robin: it spreads load across keys with no shared state, so
    concurrent invocations do not collide. Returns the first success; raises
    ``KeyPoolExhausted`` if every key fails or the pool is empty.
    """

    pool = load_key_pool(path, key)
    if not pool:
        raise KeyPoolExhausted(f"no {key} values found in .env or environment")
    random.shuffle(pool)
    last_error: Exception | None = None
    for api_key in pool:
        try:
            return fn(api_key)
        except KeyRetry as exc:
            last_error = exc
    raise KeyPoolExhausted(f"all {len(pool)} {key} key(s) failed: {last_error}")
