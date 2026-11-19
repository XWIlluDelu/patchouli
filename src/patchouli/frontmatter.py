"""Minimal YAML-frontmatter reader/writer (stdlib only).

Supports the subset Patchouli pages use: scalar values, inline lists
(`key: [a, b]`) and block lists (`key:` followed by `  - item`).
"""
from __future__ import annotations

import re

_KEY_RE = re.compile(r"^([A-Za-z_][\w\-]*)\s*:(.*)$")


def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        inner = s[1:-1]
        return inner.replace('\\"', '"') if s[0] == '"' else inner.replace("''", "'")
    return s


def _split_inline_list(s: str) -> list[str]:
    items, buf, quote = [], "", None
    for ch in s:
        if quote:
            buf += ch
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            buf += ch
        elif ch == ",":
            items.append(buf)
            buf = ""
        else:
            buf += ch
    if buf.strip():
        items.append(buf)
    return [_unquote(i) for i in items if i.strip()]


def _parse_value(raw: str):
    v = raw.strip()
    if v.startswith("[") and v.endswith("]"):
        return _split_inline_list(v[1:-1])
    if v and v[0] not in "\"'" and " #" in v:  # trailing comment
        v = v.split(" #", 1)[0].rstrip()
    return _unquote(v)


def split(text: str):
    """Return (frontmatter_lines | None, body, body_start_line[1-based])."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, text, 1
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            return lines[1:i], "\n".join(lines[i + 1 :]), i + 2
    return None, text, 1


def parse_lines(fm_lines: list[str]) -> dict:
    meta: dict = {}
    key = None
    for line in fm_lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _KEY_RE.match(line)
        if m and not line.startswith((" ", "\t")):
            key = m.group(1)
            rest = m.group(2)
            meta[key] = _parse_value(rest) if rest.strip() else ""
            continue
        s = line.strip()
        if key is not None and (s.startswith("- ") or s == "-"):
            if not isinstance(meta.get(key), list):
                meta[key] = []
            meta[key].append(_unquote(s[2:]))
    return meta


def parse(text: str):
    """Return (meta, body, body_start_line, has_frontmatter)."""
    fm_lines, body, start = split(text)
    if fm_lines is None:
        return {}, body, start, False
    return parse_lines(fm_lines), body, start, True


def dump_scalar(v) -> str:
    s = "" if v is None else str(v)
    if s == "":
        return '""'
    needs_quote = (
        s[0] in "!&*[]{}|>%@`#,?:-\"'" or ": " in s or " #" in s or s.strip() != s
        or s.lower() in ("true", "false", "null", "yes", "no")
    )
    if needs_quote:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s
