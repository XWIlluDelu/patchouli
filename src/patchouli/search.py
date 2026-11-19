"""Search over wiki pages and reading text, backed by the SQLite FTS5 index.

Text hits come back as tight line spans, ready to cite. CJK text is indexed as
character unigrams + bigrams so substrings of unsegmented text are findable.
"""
from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass

from . import markup

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[\-_'][a-z0-9]+)*|[぀-ヿ㐀-䶿一-鿿가-힯]+")
_CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")
STOP = set("a an and are as at be by for from has have in is it its of on or that the this to was were with "
           "which we our not but can".split())
CHUNK = 1500  # characters per indexed text window (lines vary: 60-char PDF lines, whole-paragraph lines)


def windows(lines: list[str]):
    """(start, end) line indices of overlapping windows of about CHUNK characters."""
    i, n = 0, len(lines)
    while i < n:
        j, size = i, 0
        while j < n and (j == i or size < CHUNK):
            size += len(lines[j]) + 1
            j += 1
        yield i, j
        if j >= n:
            return
        i = max(i + 1, (i + j) // 2)


def tokenize(text: str) -> list[str]:
    toks = []
    for m in _TOKEN_RE.finditer(text.lower()):
        w = m.group()
        if _CJK_RE.match(w):
            toks.extend(w)
            toks.extend(w[i: i + 2] for i in range(len(w) - 1))
        else:
            w = w.replace("'", "")
            if w in STOP:
                continue
            toks.append(w)
            if "-" in w or "_" in w:
                toks.extend(p for p in re.split(r"[\-_]", w) if p and p not in STOP)
    return toks


@dataclass
class Hit:
    kind: str  # page | text
    ref: str
    path: str
    title: str
    start: int
    end: int
    best_line: int
    snippet: str

    def cite(self) -> str:
        """The link to paste into a wiki page (the same from any of them)."""
        if self.kind == "text":
            return markup.cite_link(self.ref, self.start, self.end)
        return f"[{self.title}]({posixpath.relpath(self.path, 'wiki/concepts')})"


def search(vault, query: str, scope: str = "all", k: int = 10) -> list[Hit]:
    from . import db

    q = list(dict.fromkeys(tokenize(query)))
    if not q:
        return []
    con = db.refresh(vault)
    kinds = {"all": ("page", "text"), "wiki": ("page",), "text": ("text",)}[scope]
    match = " OR ".join(f'"{t}"' for t in q)
    rows = con.execute(
        f"SELECT kind, ref, path, title, start, \"end\", bm25(fts) FROM fts WHERE fts MATCH ? "
        f"AND kind IN ({','.join('?' * len(kinds))}) ORDER BY bm25(fts) LIMIT ?",
        (match, *kinds, k * 4)).fetchall()
    con.close()
    qset = set(q)
    hits, seen_text = [], {}
    cache: dict[str, list[str]] = {}
    for kind, ref, path, title, start, end, _ in rows:
        if path not in cache:
            try:
                cache[path] = (vault.root / path).read_text(encoding="utf-8").split("\n")
            except OSError:
                continue
        lines = cache[path][start - 1: end]
        scores = [len(qset & set(tokenize(l))) for l in lines]
        best = max(range(len(lines)), key=lambda i: scores[i]) if lines else 0
        if kind == "text":  # the best line, plus neighbours that match about as well
            lo = hi = best
            while lo > 0 and scores[lo - 1] * 2 >= scores[best] > 0:
                lo -= 1
            while hi < len(lines) - 1 and scores[hi + 1] * 2 >= scores[best] > 0:
                hi += 1
            s, e = start + lo, start + hi
            prev = seen_text.setdefault(ref, [])
            if any(not (e < a or s > z) for a, z in prev):
                continue
            prev.append((s, e))
        else:
            s = e = start + best
        snippet = lines[best].strip() if lines else ""
        if len(snippet) > 200:
            snippet = snippet[:197] + "..."
        hits.append(Hit(kind, ref, path, title, s, e, start + best, snippet))
        if len(hits) >= k:
            break
    return hits
