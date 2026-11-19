"""Verbatim-quote verification against reading text (an objective, binding check).

A quote is a `> blockquote` attributed to a source — by a citation link or
footnote inside it, or on an attribution line right after it
(`— [jain2019 L88](../../text/jain2019.md#L88)`), or, on a source page,
implicitly to that page's own source — or an inline "quoted passage" of 25+
characters followed directly by a citation link, so quoted titles and scare quotes
are never mistaken for evidence. The quote must occur as one contiguous run of
normalized tokens in the reading text; if it carries a line locator, inside that span
(with a little slack). Normalization folds typography and Markdown emphasis, never
words, numbers or the signs around them (`< 10` is not `> 10`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import markup

MIN_INLINE_CHARS = 25
SLACK_LINES = 3
_SEP = "\x1f"

# typography folds to ASCII; emphasis and code marks become spaces (never letters, digits or signs)
_FOLD = str.maketrans({"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'", "−": "-", "–": "-", "—": "-",
                       "≤": "<=", "≥": ">=", "≠": "!=", "…": "...", "\u00a0": " ", "ﬁ": "fi", "ﬂ": "fl",
                       "×": " ", "·": " ", "*": " ", "_": " ", "`": " ", "~": " "})
# words, numbers (with a signed exponent), and the signs that change what a number means
_TOKEN_RE = re.compile(r"<=|>=|!=|[<>=±%]|(?<![\w.])[-+](?=\d)|\d+(?:\.\d+)?(?:e[-+]?\d+)?|[^\W\d_]+"
                       r"|[㐀-鿿぀-ヿ가-힯]", re.UNICODE)
_CJK_RE = re.compile(r"[㐀-鿿぀-ヿ가-힯]")
_AFTER_QUOTE_RE = re.compile(r"\s*[,.;:，。；：]?\s*[(（]?\s*")
_INLINE_RE = re.compile(r'"([^"\n]{%d,})"|“([^”\n]{%d,})”' % (MIN_INLINE_CHARS, MIN_INLINE_CHARS))


def tokens(text: str) -> list[str]:
    if "<!--" in text:  # page markers and comments are not text (and `-->` is not a sign)
        text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    if "[" in text:  # keep a link's visible text, drop footnote refs
        text = markup.FOOTREF_RE.sub(" ", markup.LINK_RE.sub(lambda m: f" {m.group(2)} ", text))
    text = text.translate(_FOLD)
    if "-\n" in text:
        text = re.sub(r"-\n(?=\w)", "", text)  # hyphenated line breaks in PDFs
    out: list[str] = []
    for t in _TOKEN_RE.findall(text.lower()):
        if len(t) > 1 and not t.isascii() and _CJK_RE.match(t):
            out.extend(t)  # unsegmented CJK: one token per character
        else:
            out.append(t)
    return out


class TextIndex:
    """Token stream of a reading text with the line each token came from, built on first use."""

    def __init__(self, lines: list[str]):
        self.lines = lines
        self._toks: list[str] | None = None
        self._dehyph: str | None = None

    def _build(self):
        self._toks, self._line_of = [], []
        for i, line in enumerate(self.lines, 1):
            t = tokens(line)
            self._toks += t
            self._line_of += [i] * len(t)
        self._blob = _SEP + _SEP.join(self._toks) + _SEP

    @property
    def toks(self) -> list[str]:
        if self._toks is None:
            self._build()
        return self._toks

    @property
    def line_of(self) -> list[int]:
        self.toks  # noqa: B018 — builds the index
        return self._line_of

    def find_all(self, qtoks: list[str]) -> list[tuple[int, int]]:
        """All (first_line, last_line) occurrences of the token sequence."""
        if not qtoks or not self.toks:
            return []
        needle = _SEP + _SEP.join(qtoks) + _SEP
        res, start = [], 0
        while (pos := self._blob.find(needle, start)) >= 0:
            ti = self._blob.count(_SEP, 0, pos)
            res.append((self._line_of[ti], self._line_of[min(ti + len(qtoks) - 1, len(self._line_of) - 1)]))
            start = pos + 1
        if not res:  # retry on the dehyphenated whole text (PDF line-break hyphens)
            if self._dehyph is None:
                self._dehyph = _SEP + _SEP.join(tokens("\n".join(self.lines))) + _SEP
            if needle in self._dehyph:
                res.append((0, 0))  # found, but line unknown
        return res


@dataclass
class Quote:
    text: str
    line: int
    source: str | None
    start: int | None
    end: int | None


def _cites_on(line: str, lineno: int, page_dir: str, footnotes: dict) -> list:
    _, cites, refs = markup.parse_line(line, lineno, page_dir)
    for r in refs:
        f = footnotes.get(r)
        if f:
            cites += f.cites
    return cites


def _strip_citations(text: str, page_dir: str) -> str:
    """Remove citation links and footnote refs from quoted text (keep other links' text)."""
    def repl(m):
        item = markup.classify(page_dir, m.group(3), 0)
        return "" if isinstance(item, markup.Citation) else m.group(2)
    return markup.FOOTREF_RE.sub("", markup.LINK_RE.sub(repl, text))


def extract_quotes(body: str, first_line: int, own_source: str | None, page_dir: str = "wiki/sources",
                   footnotes: dict | None = None) -> list[Quote]:
    footnotes = footnotes or {}
    lines = markup.mask(body)
    quotes: list[Quote] = []
    i = 0
    n = len(lines)
    while i < n:
        s = lines[i].lstrip()
        if s.startswith(">") and not re.match(r">\s*\[!\w+\]", s):  # skip callout boxes
            j, parts = i, []
            while j < n and lines[j].lstrip().startswith(">"):
                parts.append(lines[j].lstrip()[1:].strip())
                j += 1
            text = _strip_citations(" ".join(p for p in parts if p), page_dir)
            cites = [c for k in range(i, j) for c in _cites_on(lines[k], first_line + k, page_dir, footnotes)]
            if not cites:  # attribution line right after the quote: "— [jain2019 L3](…#L3)"
                k = j
                while k < n and not lines[k].strip() and k - j < 1:
                    k += 1
                if k < n and markup.ATTRIBUTION_RE.match(lines[k]) and not re.match(r"^\s*[-*+]\s+\w", lines[k]):
                    cites = _cites_on(lines[k], first_line + k, page_dir, footnotes)
            _add(quotes, text, first_line + i, cites, own_source)
            i = j
            continue
        for m in _INLINE_RE.finditer(lines[i]):
            # an inline "…" is a quote only when a citation link follows it directly: "…" ([id L5](…))
            # (a quoted title or term elsewhere in a cited sentence is not)
            lm = markup.LINK_RE.match(lines[i], _AFTER_QUOTE_RE.match(lines[i], m.end()).end())
            item = markup.classify(page_dir, lm.group(3), first_line + i) if lm and not lm.group(1) else None
            if isinstance(item, markup.Citation):
                _add(quotes, _strip_citations(m.group(1) or m.group(2), page_dir), first_line + i, [item], None)
        i += 1
    return quotes


def _add(quotes, text, line, cites, own_source):
    text = text.strip(" -—–")
    if not text.strip():
        return
    good = [c for c in cites if c.ok and not c.unsure]
    if good:
        c = good[0]
        quotes.append(Quote(text, line, c.source, c.start, c.end))
    elif own_source:
        quotes.append(Quote(text, line, own_source, None, None))
    # unattributed quotes (e.g. of the researcher) are not checked


def verify(q: Quote, index: TextIndex) -> tuple[bool, str]:
    """Return (ok, message). A located quote is looked for in its cited span first (cheap);
    the whole text is tokenized only for unlocated quotes or to say where a quote really is."""
    qtoks = tokens(q.text)
    if q.start is not None:
        lo, hi = max(1, q.start - SLACK_LINES), (q.end or q.start) + SLACK_LINES
        if TextIndex(index.lines[lo - 1:hi]).find_all(qtoks):
            return True, ""
    hits = index.find_all(qtoks)
    if not hits:
        return False, "not found verbatim in the reading text"
    if q.start is None or any(a == 0 for a, _ in hits):
        return True, ""
    where = ", ".join(f"L{a}" + (f"-L{b}" if b != a else "") for a, b in hits[:3])
    return False, f"found at {where}, not in the cited span L{q.start}-L{q.end}"
