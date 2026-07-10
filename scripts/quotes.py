"""Verbatim-quote verification for the binding floor.

A source-page quote must resolve in that work's canonical reading surface. The
matcher folds presentation drift and permits a small bounded amount of inserted
extraction noise; it never accepts tokens scattered arbitrarily across a document.
"""

from __future__ import annotations

from bisect import bisect_right
from typing import Any
import re

from wiki_inventory import PageRecord, WORK_MARKER_RE

MIN_QUOTE_CHARS = 25


def _is_bounded_subsequence(
    quote_tokens: list[str], surface_index: dict[str, list[int]]
) -> bool:
    """Match ordered quote tokens with only bounded inserted surface noise.

    Extraction may inject a page number or footnote into otherwise verbatim prose.
    Allow at most four skipped tokens, or one skipped token per four quote tokens for
    longer quotations. Trying every occurrence of the first token avoids a distant
    early occurrence hiding a valid later span; greedy advancement then minimizes the
    skipped-token count for that start.
    """

    if not quote_tokens:
        return True
    starts = surface_index.get(quote_tokens[0], [])
    max_skipped = max(4, len(quote_tokens) // 4)
    for start in starts:
        cursor = start
        skipped = 0
        matched = True
        for token in quote_tokens[1:]:
            positions = surface_index.get(token)
            if not positions:
                matched = False
                break
            index = bisect_right(positions, cursor)
            if index == len(positions):
                matched = False
                break
            next_pos = positions[index]
            skipped += next_pos - cursor - 1
            if skipped > max_skipped:
                matched = False
                break
            cursor = next_pos
        if matched:
            return True
    return False


# The normalizer folds presentation drift while content characters stay intact. It is
# applied to both quote and surface before bounded token-span matching.
_LATEX_FONT_RE = re.compile(r"\\(?:mathbb|mathrm|mathcal|mathbf|mathfrak|mathscr|mathit|boldsymbol|operatorname|text|textbf|textit|texttt|mathsf)\b")
_UNICODE_FOLD = {
    "“": " ", "”": " ", "„": " ",   # curly double quotes
    "‘": " ", "’": " ",                  # curly single quotes / apostrophes
    "–": "-", "—": "-", "−": "-",   # en/em dash and minus -> hyphen
    "′": " ", "″": " ",                  # prime, double prime
    "·": " ", "…": " ",                  # middle dot, ellipsis
}


def _normalize(text: str) -> str:
    t = WORK_MARKER_RE.sub(" ", text)
    t = _LATEX_FONT_RE.sub(" ", t)
    t = t.replace("\\cdot", " ")
    for delim in (r"\(", r"\)", r"\[", r"\]", r"\{", r"\}", "\\"):
        t = t.replace(delim, " ")
    t = t.replace("$", " ")
    for src, dst in _UNICODE_FOLD.items():
        t = t.replace(src, dst)
    t = re.sub(r"[*_~]+", " ", t)            # markdown emphasis
    # Superscript/subscript extraction drift: ^, [], {} collapse so y^3, y[3], y3 match.
    t = t.replace("^", " ").replace("[", " ").replace("]", " ")
    t = t.replace("{", " ").replace("}", " ")
    t = t.replace('"', " ").replace("'", " ").replace("`", " ")
    t = re.sub(r"\.\.+", " ", t)            # ellipsis -> separator
    t = re.sub(r"\s+", " ", t).strip()
    t = t.rstrip(".,;:")
    # Fold trailing sentence/clause punctuation off each token so span matching is
    # not tripped by `formulation,` vs `formulation`. Only trailing
    # punctuation is stripped; internal content (e.g. `(EVI)`) stays intact.
    t = " ".join(tok.rstrip(".,;:)") for tok in t.split())
    return t


def quotes_from_body(body: str) -> list[str]:
    quotes: list[str] = []
    block: list[str] = []

    def flush_block() -> None:
        if not block:
            return
        candidate = " ".join(part for part in block if part).strip().strip("*_")
        if len(candidate) >= MIN_QUOTE_CHARS:
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

    for match in re.finditer(r"\"([^\"\n]{%d,})\"" % MIN_QUOTE_CHARS, body):
        quotes.append(match.group(1))
    return quotes


def verify_source_quotes(page: PageRecord, surface_text: str) -> dict[str, Any]:
    """Check source-page quotes against one already-read canonical surface."""

    quotes = quotes_from_body(page.body)
    if not quotes:
        return {"ok": True, "page": page.path, "quotes_checked": 0, "unresolved": []}

    surface_index: dict[str, list[int]] = {}
    for position, token in enumerate(_normalize(surface_text).split()):
        surface_index.setdefault(token, []).append(position)
    results = []
    for quote in quotes:
        normalized = _normalize(quote)
        if len(normalized) < MIN_QUOTE_CHARS:
            resolved = True
        else:
            resolved = _is_bounded_subsequence(normalized.split(), surface_index)
        results.append({"quote": quote[:160], "resolved": resolved})
    unresolved = [item for item in results if not item["resolved"]]
    return {
        "ok": not unresolved,
        "page": page.path,
        "quotes_checked": len(results),
        "unresolved": unresolved,
    }
