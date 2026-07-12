"""Explicit-quote verification for the binding floor.

Every non-empty source-page blockquote must occur as one contiguous normalized
token span in that work's reading surface. Inline quotation marks are checked
only for substantial passages so ordinary scare quotes do not become evidence.
Normalization removes presentation markup, not semantic tokens.
"""

from __future__ import annotations

from typing import Any
import re

from wiki_inventory import PageRecord, WORK_MARKER_RE

MIN_INLINE_QUOTE_CHARS = 25

_LATEX_OPERATOR_FOLD = {
    r"\cdot": " * ",
    r"\times": " * ",
    r"\div": " / ",
    r"\pm": " ± ",
    r"\mp": " ∓ ",
    r"\leq": " <= ",
    r"\le": " <= ",
    r"\geq": " >= ",
    r"\ge": " >= ",
    r"\neq": " != ",
}
_UNICODE_FOLD = {
    "“": '"',
    "”": '"',
    "„": '"',
    "‘": "'",
    "’": "'",
    "′": "'",
    "″": "''",
    "−": "-",
    "×": "*",
    "·": "*",
    "÷": "/",
    "≤": "<=",
    "≥": ">=",
    "≠": "!=",
    "…": "...",
}
_TOKEN_RE = re.compile(
    r"\\[A-Za-z]+|"
    r"(?:\d+(?:\.\d+)?(?:[eE][+-]?\d+)?'*)|"
    r"(?:[^\W\d_]+(?:'[^\W\d_]+)*'*)|"
    r"(?:<=|>=|!=|==|->|<-)|"
    r"[+\-*/=<>^_%±∓(){}\[\]$€£¥°']",
    re.UNICODE,
)


def _strip_symmetric_markup(text: str, delimiter: str) -> str:
    """Remove paired presentation delimiters in one pass; retain unmatched ones."""

    opening: int | None = None
    remove: set[int] = set()
    index = 0
    width = len(delimiter)
    while index <= len(text) - width:
        if not text.startswith(delimiter, index):
            index += 1
            continue
        before = text[index - 1] if index else ""
        after_index = index + width
        after = text[after_index] if after_index < len(text) else ""
        can_open = bool(after and not after.isspace() and not before.isalnum())
        can_close = bool(before and not before.isspace() and not after.isalnum())
        if opening is not None and can_close:
            remove.update(range(opening, opening + width))
            remove.update(range(index, index + width))
            opening = None
        elif opening is None and can_open:
            opening = index
        index += width
    return "".join(character for index, character in enumerate(text) if index not in remove)


def _strip_distinct_markup(text: str, opening: str, closing: str) -> str:
    remove: set[int] = set()
    start: int | None = None
    index = 0
    while index < len(text):
        if start is None and text.startswith(opening, index):
            start = index
            index += len(opening)
        elif start is not None and text.startswith(closing, index):
            remove.update(range(start, start + len(opening)))
            remove.update(range(index, index + len(closing)))
            start = None
            index += len(closing)
        else:
            index += 1
    return "".join(character for index, character in enumerate(text) if index not in remove)


def _tokens(text: str) -> list[str]:
    """Return comparison tokens while retaining mathematical meaning."""

    normalized = WORK_MARKER_RE.sub(" ", text)
    for source, target in _LATEX_OPERATOR_FOLD.items():
        normalized = normalized.replace(source, target)
    normalized = _strip_distinct_markup(normalized, r"\(", r"\)")
    normalized = _strip_distinct_markup(normalized, r"\[", r"\]")
    for delimiter in ("$$", "**", "__", "~~", "*", "_", "$", "`"):
        normalized = _strip_symmetric_markup(normalized, delimiter)
    for source, target in _UNICODE_FOLD.items():
        normalized = normalized.replace(source, target)
    normalized = re.sub(r"([_^])\{([A-Za-z0-9.]+)\}", r"\1\2", normalized)
    return _TOKEN_RE.findall(normalized)


def _token_span(tokens: list[str]) -> str:
    separator = "\x1f"
    return separator + separator.join(tokens) + separator


def quotes_from_body(body: str) -> list[str]:
    quotes: list[str] = []
    block: list[str] = []

    def flush_block() -> None:
        if not block:
            return
        candidate = " ".join(part for part in block if part).strip()
        if candidate:
            quotes.append(candidate)
        block.clear()

    for line in body.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(">"):
            part = stripped[1:]
            if part.startswith(" "):
                part = part[1:]
            block.append(part.strip())
        else:
            flush_block()
    flush_block()

    inline_patterns = (
        rf'"([^"\n]{{{MIN_INLINE_QUOTE_CHARS},}})"',
        rf'“([^”\n]{{{MIN_INLINE_QUOTE_CHARS},}})”',
    )
    for pattern in inline_patterns:
        quotes.extend(match.group(1) for match in re.finditer(pattern, body))
    return quotes


def verify_source_quotes(page: PageRecord, surface_text: str) -> dict[str, Any]:
    """Check source-page quotes against one already-read canonical surface."""

    quotes = quotes_from_body(page.body)
    if not quotes:
        return {"ok": True, "page": page.path, "quotes_checked": 0, "unresolved": []}

    surface_span = _token_span(_tokens(surface_text))
    results = []
    for quote in quotes:
        quote_tokens = _tokens(quote)
        resolved = bool(quote_tokens) and _token_span(quote_tokens) in surface_span
        results.append({"quote": quote[:160], "resolved": resolved})
    unresolved = [item for item in results if not item["resolved"]]
    return {
        "ok": not unresolved,
        "page": page.path,
        "quotes_checked": len(results),
        "unresolved": unresolved,
    }
