"""Parsing of Patchouli pages — plain Markdown, no private syntax.

Pages use only standard Markdown (plus footnotes, a common extension):

* Page links      — ordinary relative links: `[Self-attention](../concepts/self-attention.md)`
* Typed relations — a list item opening with a short label and a colon, read as
                    "this page <label> the target":
                    `- Contradicts: [Attention is explanation](../concepts/attention-is-explanation.md)`
                    Any label works (Extends, Defines, Applies, 反驳…); a few have
                    meaning to the scripts (CONTRADICTS feeds the index's Tensions).
* Citations       — links into reading text with a line anchor:
                    `[jain2019 L88–95](../../text/jain2019.md#L88-L95)`, or to the original
                    for what the text lacks (a figure, a page): `[jain2019 fig. 1](../../raw/jain2019.pdf#page=3)`
* Evidence notes  — footnotes. The claim stays clean prose ending in `[^3]`; the footnote
                    says what kind of statement it is and what it rests on:
                    `[^3]: Judgment (moderate) — from [jain2019](../sources/jain2019.md) and …`
                    A footnote with no kind word that cites text is a *stated* claim of the
                    source; `Interpretation` / `Judgment` mark the agent's reading and
                    cross-source judgments, followed by a certainty.

Code (fenced or inline) and HTML comments are masked out before parsing.
"""
from __future__ import annotations

import bisect
import posixpath
import re
from dataclasses import dataclass, field

# Relation labels are free; these sets give a few of them meaning to the scripts.
CONTRADICTS = {"contradicts", "contradicted-by", "conflicts-with", "disputes", "refutes", "challenges",
               "矛盾", "冲突", "反驳", "相悖"}
LOOSE = {"link", "related", "see", "see-also", "相关", "参见"}  # relations that don't mean "builds on"

_FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
LINK_RE = re.compile(r"(!?)\[((?:[^\[\]\n]|\[[^\[\]\n]*\])*)\]\(\s*<?([^()\s<>]+)>?(?:\s+\"[^\"\n]*\")?\s*\)")
FOOTREF_RE = re.compile(r"\[\^([^\]\s]+)\](?!:)")
FOOTDEF_RE = re.compile(r"^\[\^([^\]\s]+)\]:\s?(.*)$")
_ANCHOR_RE = re.compile(r"^L(\d+)(?:-L?(\d+))?(\?)?$")
_KIND_RE = re.compile(r"^\W*(stated|interpretation|judge?ment)\b", re.I)
_LEVEL_RE = re.compile(r"\b(high|moderate|low|speculative)\b", re.I)
_EM = r"(?:\*\*|__|\*|_)?"
_REL_RE = re.compile(rf"^\s*(?:[-*+]|\d+[.)])\s+{_EM}([^\W\d_][\w \-]{{0,30}}?)\s*{_EM}\s*[:：]\s*{_EM}\s*(?=\[)")
_LEAD_RE = re.compile(r"^\s*(?:>\s?)*(?:(?:[-*+]|\d+[.)]|#{1,6})\s+)?")
_BLOCK_START_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+|^\s*#{1,6}\s|^\s*\|")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s")
_ATTR_WORDS = r"source|from|via|来源|出处|引自|见"
ATTRIBUTION_RE = re.compile(
    rf"^\s*(?:[*_]\s*)?(?:[-—–―─]{{1,2}}\s*)?(?:(?:{_ATTR_WORDS})\s*[:：]?\s*)?[(（]?\s*\[",
    re.I,
)
_ATTR_NOISE_RE = re.compile(rf"[\s\-—–―─:;,.()*_：；，。（）【】、]|{_ATTR_WORDS}", re.I)


@dataclass
class Citation:
    source: str
    start: int | None
    end: int | None
    line: int
    target: str = ""
    path_ok: bool = True
    unsure: bool = False
    ok: bool = True
    footnote: str | None = None
    raw: bool = False  # points at the original file (raw/…), located by its fragment if any
    path: str = ""  # root-relative path the link resolves to
    frag: str = ""


@dataclass
class Link:
    target: str  # page slug
    line: int
    rel: str = "link"
    path: str = ""  # root-relative path the link resolves to
    raw: str = ""


@dataclass
class Footnote:
    label: str
    line: int
    text: str
    kind: str  # stated | interpretation | judgment | note
    certainty: str | None
    cites: list[Citation] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)


@dataclass
class Block:
    start: int
    lines: list[str] = field(default_factory=list)  # masked (for parsing)
    raw: list[str] = field(default_factory=list)  # original (for display)
    links: list[Link] = field(default_factory=list)
    cites: list[Citation] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)  # footnote labels referenced

    @property
    def text(self) -> str:
        t = " ".join(l.strip().lstrip(">").strip() for l in self.raw)
        t = FOOTREF_RE.sub("", t)
        return re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", t).strip()

    @property
    def is_quote(self) -> bool:
        return all(l.lstrip().startswith(">") for l in self.lines)

    @property
    def is_attribution(self) -> bool:
        """A line that only points at evidence, e.g. `— [jain2019 L88](…)` or `—— 来源：[…]`."""
        rest = FOOTREF_RE.sub("", LINK_RE.sub("", " ".join(self.lines)))
        return bool(self.cites or self.refs) and not _ATTR_NOISE_RE.sub("", rest)


@dataclass
class Claim:
    label: str | None
    line: int
    text: str
    kind: str
    certainty: str | None
    cites: list[Citation]


@dataclass
class PageMarkup:
    footnotes: dict[str, Footnote]
    links: list[Link]
    cites: list[Citation]  # body + footnotes
    refs: dict[str, list[int]]  # footnote label -> lines where referenced
    claims: list[Claim]
    duplicate_footnotes: list[tuple[str, int, int]]  # (label, first line, repeated at)


def mask(text: str) -> list[str]:
    """Blank out fenced code, inline code and HTML comments, keeping line count and line length."""
    out: list[str] = []
    fence = None
    in_comment = False
    for line in text.split("\n"):
        if fence:
            if line.strip().startswith(fence):
                fence = None
            out.append("")
            continue
        m = _FENCE_RE.match(line)
        if m and not in_comment:
            fence = m.group(1)[:3]
            out.append("")
            continue
        res, i = "", 0
        while i < len(line):
            if in_comment:
                j = line.find("-->", i)
                if j < 0:
                    res += " " * (len(line) - i)
                    break
                res += " " * (j + 3 - i)
                in_comment, i = False, j + 3
            else:
                j = line.find("<!--", i)
                if j < 0:
                    res += line[i:]
                    break
                res += line[i:j] + "    "
                in_comment, i = True, j + 4
        out.append(_INLINE_CODE_RE.sub(lambda mm: " " * len(mm.group()), res))
    return out


def resolve(page_dir: str, target: str) -> tuple[str, str]:
    """Return (root-relative path, fragment) for a relative link target."""
    path, _, frag = target.partition("#")
    if not path:
        return "", frag
    return posixpath.normpath(posixpath.join(page_dir, path)), frag


def classify(page_dir: str, target: str, line: int):
    """A link target → Citation, Link, or None (external / non-page)."""
    if re.match(r"^[a-z][a-z0-9+.\-]*:", target, re.I) or target.startswith(("/", "#")):
        return None
    norm, frag = resolve(page_dir, target)
    parts = norm.split("/")
    if parts[0] == "raw" and len(parts) == 2:  # the original material
        return Citation(posixpath.splitext(parts[1])[0], None, None, line, target, raw=True, path=norm, frag=frag)
    if not parts[-1].endswith(".md") or parts[0] == "raw":
        return None  # an image, a PDF elsewhere: not a page
    stem = parts[-1][:-3]
    if len(parts) >= 2 and parts[-2] == "text":
        c = Citation(stem, None, None, line, target, path_ok=(norm == f"text/{stem}.md"), path=norm, frag=frag)
        if frag:
            m = _ANCHOR_RE.match(frag)
            if not m:
                c.ok = False
            else:
                c.start = int(m.group(1))
                c.end = int(m.group(2) or m.group(1))
                c.unsure = bool(m.group(3))
        return c
    return Link(stem, line, "link", norm, target)


def sub_links(text: str, fn) -> str:
    """Replace every live link (not inside code or an HTML comment) with `fn(match)`."""
    lines = text.split("\n")
    for i, (line, live) in enumerate(zip(lines, mask(text))):
        if "](" in live:
            lines[i] = LINK_RE.sub(
                lambda m, live=live: fn(m) if live[m.start(3):m.end(3)] == m.group(3) else m.group(0), line)
    return "\n".join(lines)


def parse_line(line: str, lineno: int, page_dir: str):
    links, cites = [], []
    rm = _REL_RE.match(line)
    rel = re.sub(r"[\s_]+", "-", rm.group(1).strip().lower()) if rm else None
    for m in LINK_RE.finditer(line):
        if m.group(1) == "!":
            continue
        item = classify(page_dir, m.group(3), lineno)
        if isinstance(item, Citation):
            cites.append(item)
        elif isinstance(item, Link):
            if rel:
                item.rel, rel = rel, None  # a leading relation word types the first link
            links.append(item)
    refs = FOOTREF_RE.findall(LINK_RE.sub(" ", line))
    return links, cites, refs


def _footnote(label: str, lineno: int, text: str, page_dir: str) -> Footnote:
    links, cites, _ = parse_line(text, lineno, page_dir)
    km = _KIND_RE.match(text)
    if km:
        kind = km.group(1).lower().replace("judgement", "judgment")
        lm = _LEVEL_RE.search(text[km.end(): km.end() + 40])
        level = lm.group(1).lower() if lm else None
    else:
        kind, level = ("stated" if cites else "note"), None
    for c in cites:
        c.footnote = label
    return Footnote(label, lineno, text.strip(), kind, level, cites, links)


def parse(body: str, first_line: int = 1, page_dir: str = "wiki/concepts") -> PageMarkup:
    masked = mask(body)
    original = body.split("\n")
    blocks: list[Block] = []
    footnotes: dict[str, Footnote] = {}
    refs: dict[str, list[int]] = {}
    cur: Block | None = None
    prev_heading = False
    fn: tuple[str, int, list[str]] | None = None
    duplicates: list[tuple[str, int, int]] = []

    def close_fn():
        nonlocal fn
        if fn:
            if fn[0] in footnotes:  # keep the first; a reused label is an error, not a silent swap
                duplicates.append((fn[0], footnotes[fn[0]].line, fn[1]))
            else:
                footnotes[fn[0]] = _footnote(fn[0], fn[1], " ".join(fn[2]), page_dir)
            fn = None

    for i, line in enumerate(masked):
        lineno = first_line + i
        fm = FOOTDEF_RE.match(line)
        if fm:
            close_fn()
            cur = None
            fn = (fm.group(1), lineno, [fm.group(2)])
            continue
        if fn and (line.startswith(("    ", "\t")) and line.strip()):
            fn[2].append(line.strip())
            continue
        if fn and not line.strip():
            continue  # blank lines may separate footnote paragraphs
        close_fn()
        if not line.strip():
            cur = None
            prev_heading = False
            continue
        quote_edge = cur is not None and (line.lstrip().startswith(">") != cur.lines[-1].lstrip().startswith(">"))
        if cur is None or prev_heading or quote_edge or _BLOCK_START_RE.match(line):
            cur = Block(start=lineno)
            blocks.append(cur)
        cur.lines.append(line)
        cur.raw.append(original[i])
        l, c, r = parse_line(line, lineno, page_dir)
        cur.links += l
        cur.cites += c
        cur.refs += r
        for label in r:
            refs.setdefault(label, []).append(lineno)
        prev_heading = bool(_HEADING_RE.match(line))
    close_fn()

    claims: list[Claim] = []
    for k, b in enumerate(blocks):
        prev = blocks[k - 1] if k else None
        unattributed_quote = bool(prev and prev.is_quote and not (prev.refs or prev.cites))
        attaches = (unattributed_quote and len(b.lines) == 1 and bool(b.cites or b.refs)
                    and bool(ATTRIBUTION_RE.match(b.lines[0])) and not re.match(r"^\s*[-*+]\s+\w", b.lines[0]))
        if b.is_attribution or attaches:
            if not unattributed_quote:
                continue  # a bare pointer to evidence is not a claim
            segments = [(prev.start, prev.text, b.refs, b.cites)]  # the quote it attributes is the claim
        else:
            segments = _segments(b, page_dir)
        for line, text, labels, seg_cites in segments:
            if not text:
                continue
            for label in dict.fromkeys(labels):
                f = footnotes.get(label)
                if f is not None:
                    claims.append(Claim(label, line, text, f.kind, f.certainty, f.cites + seg_cites))
            if not labels and any(c.start is not None for c in seg_cites):  # cited lines, not a file link
                claims.append(Claim(None, line, text, "stated", None, seg_cites))

    links = [l for b in blocks for l in b.links] + [l for f in footnotes.values() for l in f.links]
    cites = [c for b in blocks for c in b.cites] + [c for f in footnotes.values() for c in f.cites]
    return PageMarkup(footnotes, links, cites, refs, claims, duplicates)


def _segments(b: Block, page_dir: str):
    """Split a block at its footnote references: "A holds.[^1] B follows.[^2]" is two claims.

    Yields (line, text, footnote labels, citations) per segment; inline citations belong to
    the segment they sit in. Masked and raw lines have equal lengths, so offsets carry over.
    """
    jm, jr, starts, pos = [], [], [], 0
    for ml, rl in zip(b.lines, b.raw):
        k = _LEAD_RE.match(rl).end()  # quote marker, bullet or heading hashes
        jm.append(" " * k + ml[k:])
        jr.append(" " * k + rl[k:])
        starts.append(pos)
        pos += len(ml) + 1
    jm, jr = " ".join(jm), " ".join(jr)
    items = [(m.start(), m.end(), classify(page_dir, m.group(3), b.start)) for m in LINK_RE.finditer(jm)
             if m.group(1) != "!"]
    runs: list[list] = []  # [start, end, labels] of adjacent footnote references
    for m in FOOTREF_RE.finditer(jm):
        if any(a <= m.start() < z for a, z, _ in items):
            continue
        if runs and not jm[runs[-1][1]:m.start()].strip():
            runs[-1][1] = m.end()
            runs[-1][2].append(m.group(1))
        else:
            runs.append([m.start(), m.end(), [m.group(1)]])
    out, prev = [], 0
    for s, e, labels in runs + [[len(jm), len(jm), []]]:
        seg = jr[prev:s]
        text = re.sub(r"\s+", " ", FOOTREF_RE.sub("", seg)).strip()
        text = re.sub(r"^[.,;:)\]。，；：）、！？]+\s*", "", text)
        inside = [it for a, _, it in items if prev <= a < s]
        offset = prev + len(seg) - len(seg.lstrip())
        line = b.start + max(bisect.bisect_right(starts, offset) - 1, 0)
        out.append((line, text, labels, [c for c in inside if isinstance(c, Citation)]))
        prev = e
    return out


def fmt_range(a: int, b: int) -> str:
    """The anchor form: L5, L5-L9."""
    return f"L{a}" if a == b else f"L{a}-L{b}"


def cite_label(a: int, b: int) -> str:
    """The readable form for link text: L5, L5–9."""
    return f"L{a}" if a == b else f"L{a}–{b}"


def cite_link(sid: str, a: int, b: int, page_dir: str = "wiki/concepts") -> str:
    """A citation link as written on a page in `page_dir` (any wiki page: same relative path)."""
    return f"[{sid} {cite_label(a, b)}]({posixpath.relpath(f'text/{sid}.md', page_dir)}#{fmt_range(a, b)})"
