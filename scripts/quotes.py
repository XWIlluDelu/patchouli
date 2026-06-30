"""Verbatim-quote verification for the binding floor.

A source page's quotes must resolve in its reading surface; check_wiki.py enforces
that and calls the matcher here. The match is tolerant by design — it folds
presentation and extraction drift so a faithful quote survives, and it catches the
realistic failure of a non-adversarial writer: a quote carrying a token absent from
the surface (paraphrase, hallucination, misattribution). It is containment, not
contiguity, so it does not defend against crafted fabrication — see
verify_source_quotes for the exact guarantee and its limit.
"""

from __future__ import annotations

from typing import Any
import re

from wiki_inventory import PageRecord
from workspace_paths import Workspace

MIN_QUOTE_CHARS = 25


def _is_subsequence(quote_tokens: list[str], surface_index: dict[str, list[int]]) -> bool:
    """True if quote_tokens appear in surface_index in order (not necessarily contiguous).

    Greedy monotonic match: for each quote token, advance to the first surface position
    strictly after the cursor. A token absent from the surface, or one that would
    require going backwards, fails the match. So a quote loses if any token is missing
    from the surface, while a quote whose tokens all occur in order passes even with
    arbitrary noise between them. This is containment, not contiguity: it deliberately
    tolerates intervening extraction noise, and correspondingly does not reject a quote
    whose tokens merely happen to occur in order across distant parts of the surface.
    """
    cursor = -1
    for tok in quote_tokens:
        positions = surface_index.get(tok)
        if not positions:
            return False
        # Advance to the first position > cursor (strictly after the previous match).
        next_pos = next((p for p in positions if p > cursor), None)
        if next_pos is None:
            return False
        cursor = next_pos
    return True


# Tolerant-quote normalizer folds presentation and extraction drift so a faithful verbatim
# quote survives binding, while content characters stay intact. Applied to both the quote
# and the reading surface, so substring containment remains meaningful.
_LATEX_FONT_RE = re.compile(r"\\(?:mathbb|mathrm|mathcal|mathbf|mathfrak|mathscr|mathit|boldsymbol|operatorname|text|textbf|textit|texttt|mathsf)\b")
_WORK_MARKER_RE = re.compile(r"\(Works?:\s*[^)]*\)")
_UNICODE_FOLD = {
    "“": " ", "”": " ", "„": " ",   # curly double quotes
    "‘": " ", "’": " ",                  # curly single quotes / apostrophes
    "–": "-", "—": "-", "−": "-",   # en/em dash and minus -> hyphen
    "′": " ", "″": " ",                  # prime, double prime
    "·": " ", "…": " ",                  # middle dot, ellipsis
}


def _normalize(text: str) -> str:
    t = _WORK_MARKER_RE.sub(" ", text)
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
    # Fold trailing sentence/clause punctuation off each token so token-subsequence
    # matching is not tripped by `formulation,` vs `formulation`. Only trailing
    # punctuation is stripped; internal content (e.g. `(EVI)`) stays intact.
    t = " ".join(tok.rstrip(".,;:)") for tok in t.split())
    return t


def quotes_from_body(body: str) -> list[str]:
    quotes: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("> "):
            candidate = stripped[2:].strip().strip("*_")
            if len(candidate) >= MIN_QUOTE_CHARS:
                quotes.append(candidate)
    for match in re.finditer(r"\"([^\"\n]{%d,})\"" % MIN_QUOTE_CHARS, body):
        quotes.append(match.group(1))
    return quotes


def verify_source_quotes(workspace: Workspace, page: PageRecord) -> dict[str, Any]:
    """Check that quotes on a source page resolve in its reading surface.

    Quotes are blockquote lines and long double-quoted strings. Matching is
    token-subsequence containment against the normalized extracted text. The caller
    passes the already-scanned page, so this reads only the reading surface.
    """

    surface_rel = page.frontmatter.get("reading_surface", "")
    if not surface_rel:
        return {"ok": False, "error": "source page has no reading_surface frontmatter"}
    try:
        surface_text = workspace.abspath(surface_rel).read_text(encoding="utf-8")
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        return {"ok": False, "error": f"cannot read reading surface {surface_rel}: {exc}"}
    haystack = _normalize(surface_text)
    surface_tokens = haystack.split()
    surface_index: dict[str, list[int]] = {}
    for pos, tok in enumerate(surface_tokens):
        surface_index.setdefault(tok, []).append(pos)
    results = []
    for quote in quotes_from_body(page.body):
        normalized = _normalize(quote)
        # A quote that collapses below the minimum under normalization is mostly markup;
        # treat it as resolved rather than match a short, meaningless substring.
        if len(normalized) < MIN_QUOTE_CHARS:
            resolved = True
        else:
            # Ordered token-subsequence containment: the quote's tokens must appear in
            # the surface in the quote's order, not necessarily contiguously. This
            # absorbs insertion-level extraction drift (footnotes, page numbers, figure
            # captions injected mid-sentence) the character normalizer cannot fold. A
            # token absent from the surface fails the quote — the realistic drift a
            # trusted writer produces. Being containment, not contiguity, it does not
            # defend against a crafted quote whose tokens happen to occur in order
            # elsewhere; that limit is accepted given a non-adversarial agent.
            quote_tokens = normalized.split()
            resolved = _is_subsequence(quote_tokens, surface_index)
        results.append({"quote": quote[:160], "resolved": resolved})
    unresolved = [item for item in results if not item["resolved"]]
    return {
        "ok": not unresolved,
        "page": page.path,
        "quotes_checked": len(results),
        "unresolved": unresolved,
    }
