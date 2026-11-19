"""Carry line citations across a re-extraction of reading text.

Line locators are only stable while the reading text is. When a source is
re-extracted (a better PDF parser, a corrected conversion), the old and new texts
are aligned token by token and every citation link (`…/text/<id>.md#La-Lb`) is rewritten to
the matching span of the new text (link anchor and the range in its text). A span
that cannot be found with confidence — too little of it aligns, or any number or sign
in it doesn't — gets a trailing `?` (`…md#L120-L134?`), which
the checker reports as an error until the passage is located again — never a
silently wrong pointer.
"""
from __future__ import annotations

import bisect
import difflib
import re

from . import markup, quotes

MIN_COVERAGE = 0.75  # share of a span's tokens that must align
_KEY_RE = re.compile(r"^(?:\d|[<>=!±%+-])")  # numbers and signs: losing or gaining one can change the claim
_SIGN_RE = re.compile(r"^[<>=!±%+-]")


class Aligner:
    def __init__(self, old_lines: list[str], new_lines: list[str]):
        self.a = quotes.TextIndex(old_lines)
        self.b = quotes.TextIndex(new_lines)
        self.amap: dict[int, int] = {}
        sm = difflib.SequenceMatcher(None, self.a.toks, self.b.toks, autojunk=True)
        for blk in sm.get_matching_blocks():
            for k in range(blk.size):
                self.amap[blk.a + k] = blk.b + k
        self.bset = set(self.amap.values())

    def map_span(self, start: int, end: int) -> tuple[int, int] | None:
        lo = bisect.bisect_left(self.a.line_of, start)
        hi = bisect.bisect_right(self.a.line_of, end)
        idxs = range(lo, hi)
        if not idxs:
            return None
        mapped = sorted(self.amap[i] for i in idxs if i in self.amap)
        if len(mapped) < MIN_COVERAGE * len(idxs):
            return None
        if any(i not in self.amap for i in idxs if _KEY_RE.match(self.a.toks[i])):
            return None  # the generic wording survived but a number didn't: let the agent look
        # robust to a few stray matches elsewhere: keep the cluster around the median
        med = mapped[len(mapped) // 2]
        win = 2 * len(idxs) + 20
        core = [m for m in mapped if abs(m - med) <= win]
        lo_b, hi_b = core[0], core[-1]
        new_toks = self.b.toks
        if any(_KEY_RE.match(new_toks[j]) and j not in self.bset for j in range(lo_b, hi_b + 1)):
            return None  # a number or sign inside the passage is new
        if any(0 <= j < len(new_toks) and _SIGN_RE.match(new_toks[j]) and j not in self.bset
               for j in (lo_b - 1, hi_b + 1)):
            return None  # a sign appeared right at its edge: "12 percent" became "−12 percent"
        return self.b.line_of[lo_b], self.b.line_of[hi_b]


_TEXT_RANGE_RE = re.compile(r"L(\d+)(?:\s*[–\-]\s*L?(\d+))?")


def rewrite_text(text: str, sid: str, aligner: Aligner, page_dir: str) -> tuple[str, int, int]:
    """Rewrite citations of `sid` in one page. Returns (text, moved, unresolved)."""
    moved = unresolved = 0

    def fix(m):
        nonlocal moved, unresolved
        item = markup.classify(page_dir, m.group(3), 0)
        if m.group(1) or not isinstance(item, markup.Citation) or item.source != sid or item.start is None or item.unsure:
            return m.group(0)
        a, b = item.start, item.end
        span = aligner.map_span(a, b)
        base = m.group(3).split("#", 1)[0]
        label = m.group(2)
        if span is None:
            unresolved += 1
            return f"[{label}]({base}#{markup.fmt_range(a, b)}?)"
        if span != (a, b):
            moved += 1
        new_loc = markup.fmt_range(*span)

        def relabel(lm):  # keep the human-readable range in the link text in step
            la, lb = int(lm.group(1)), int(lm.group(2) or lm.group(1))
            return markup.cite_label(*span) if (la, lb) == (a, b) else lm.group(0)

        return f"[{_TEXT_RANGE_RE.sub(relabel, label)}]({base}#{new_loc})"

    return markup.sub_links(text, fix), moved, unresolved


def relocate(vault, sid: str, old_lines: list[str], new_lines: list[str]) -> dict:
    """Rewrite every citation of `sid` across the wiki. Returns a summary."""
    aligner = Aligner(old_lines, new_lines)
    summary = {"pages": [], "moved": 0, "unresolved": 0}
    for page in vault.iter_pages():
        text = page.path.read_text(encoding="utf-8")
        if f"{sid}.md#" not in text:
            continue
        new, moved, unres = rewrite_text(text, sid, aligner, page.dir)
        if new != text:
            page.path.write_text(new, encoding="utf-8")
            summary["pages"].append(page.rel)
        summary["moved"] += moved
        summary["unresolved"] += unres
    return summary
