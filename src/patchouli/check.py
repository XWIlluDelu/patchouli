"""Deterministic checks, split into two kinds.

* **error** (binding): objective facts a script can verify and the agent cannot
  invent — pages are identifiable, citations point at real lines of real text,
  footnotes exist, quotes are verbatim, raw material is untouched. Fix until none.
* **advice**: signals about form and upkeep (evidence notes, missing pages,
  orphans, pages to re-check, summaries). Act on what is real, ignore the rest;
  they never block, because gating writing on form makes pages worse.

Whether a citation *supports* its claim, whether sources truly disagree, and
whether certainty is calibrated are judgments — not checked here.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass

from . import quotes
from . import state as statemod
from .graph import Graph, build
from .vault import INTEGRATED_TYPES, PAGE_TYPES, Vault, sha256_file, stat_of

LEVELS = ("error", "advice")


@dataclass
class Issue:
    level: str
    code: str
    path: str
    line: int
    message: str

    def format(self) -> str:
        loc = f"{self.path}:{self.line}" if self.line else self.path
        return f"{'E' if self.level == 'error' else 'a'} {self.code} {loc}  {self.message}"


def run(vault: Vault, g: Graph | None = None, state: dict | None = None) -> list[Issue]:
    g = g or build(vault)
    if state is None:
        state, _, _ = statemod.current(vault, g)
    reg = vault.registry
    issues: list[Issue] = []

    def err(code, path, line, msg):
        issues.append(Issue("error", code, path, line, msg))

    def adv(code, path, line, msg):
        issues.append(Issue("advice", code, path, line, msg))

    # ---- registry / raw / text
    texts: dict[str, list[str]] = {}
    text_shas: dict[str, str] = {}
    for sid, e in sorted(reg.items()):
        raw = vault.root / e["raw"]
        if not raw.exists():
            err("SRC001", e["raw"], 0, f"raw file for `{sid}` is missing")
        elif e.get("raw_stat") != list(stat_of(raw)) and sha256_file(raw) != e["raw_sha256"]:  # hash only if touched
            err("SRC002", e["raw"], 0, f"raw file for `{sid}` was modified; raw material is immutable — "
                "restore it, or register the revised material as a new source")
        lines = vault.text_lines(sid)
        if lines is None:
            adv("SRC003", e["raw"], 0, f"`{sid}` has no reading text (`patchouli extract {sid}`)")
            continue
        texts[sid] = lines
        text_shas[sid] = vault.text_sha(sid)
        if text_shas[sid] != e.get("text_sha256"):
            adv("SRC007", vault.rel(vault.text_path(sid)), 0, "reading text was edited by hand; re-extract instead")
        if e.get("quality") == "basic":
            adv("SRC008", e["raw"], 0, f"`{sid}` used basic PDF extraction ({e.get('extractor')}); "
                "tables, formulas and layout may be damaged — note it under Extraction caveats, or install the "
                "pdf-quality extra and re-extract (citations are carried over)")
        if not g.has_source_page(sid):
            adv("SRC004", e["raw"], 0, f"`{sid}` awaits ingestion")

    indexes: dict[str, quotes.TextIndex] = {}

    def text_index(sid):
        if sid not in indexes:
            indexes[sid] = quotes.TextIndex(texts[sid])
        return indexes[sid]

    for slug, paths in g.duplicates.items():
        err("FM005", paths[0], 0, f"slug `{slug}` is used by {', '.join(paths)}; slugs must be unique")

    linked = {l.target for s in g.marks for l in g.links(s) if l.target != s}
    linked |= {c.source for s in g.marks for c in g.cites(s) if c.source != s}
    known = sorted(set(g.pages) | set(reg))
    for slug, page in sorted(g.pages.items()):
        t = page.type
        m = g.marks[slug]
        if not page.has_frontmatter or not t or not page.meta.get("title"):
            err("FM001", page.rel, 1, "frontmatter needs `type` and `title`")
        elif t not in PAGE_TYPES:
            err("FM002", page.rel, 1, f"type `{t}` is not one of {', '.join(PAGE_TYPES)}")
        if page.has_frontmatter and not page.summary and t != "hub":
            adv("FM004", page.rel, 1, "a one-line `summary` makes the index useful")

        if slug in reg and t and t != "source":
            err("FM006", page.rel, 1, f"`{slug}` is a source id; rename this {t} page (`patchouli rename`) so "
                "links to the source and to this page can't be confused")
        if t == "source":
            if slug not in reg:
                err("SRC006", page.rel, 1, f"no registered source `{slug}` (a source page's slug is its source id)")
            else:
                recorded = state.get(slug, {}).get("text_sha")
                cur = text_shas.get(slug)
                if recorded and cur and recorded != cur:
                    adv("SRC005", page.rel, 0, "the reading text changed after this page was last checked against "
                        "it; re-read the changed parts, then revise the page (with a revision note) or, if it "
                        "still holds, set `reviewed: <date>` in its frontmatter")

        # links between pages
        for l in m.links:  # (a wrong path to a known page is corrected by `sync`)
            if l.target in g.pages or (vault.root / l.path).exists():
                continue
            if l.path.startswith("wiki/"):
                close = difflib.get_close_matches(l.target, known, n=1, cutoff=0.8)
                hint = f" — did you mean `{close[0]}`?" if close else " (listed under Wanted pages in the index)"
                adv("LNK001", page.rel, l.line, f"`{l.raw}` does not exist yet{hint}")
        if t != "hub" and slug not in linked:
            adv("LNK002", page.rel, 0, "nothing links here")

        # citations
        for c in m.cites:
            if not c.ok:
                err("CIT000", page.rel, c.line, f"`{c.target}`: write the anchor as #L12 or #L12-L30")
            elif c.source not in reg:
                close = difflib.get_close_matches(c.source, list(reg), n=1, cutoff=0.8)
                err("CIT001", page.rel, c.line, f"`{c.source}` is not a registered source"
                    + (f" — did you mean `{close[0]}`?" if close else ""))
            elif c.raw:
                if reg[c.source].get("raw") != c.path:
                    err("CIT001", page.rel, c.line, f"`{c.target}` is not the registered original of `{c.source}` "
                        f"({reg[c.source].get('raw')})")
            elif c.source not in texts:
                err("CIT003", page.rel, c.line, f"`{c.source}` has no reading text to cite")
            elif c.unsure:
                err("CIT004", page.rel, c.line, f"`{c.target}`: the reading text was re-extracted and this "
                    "passage could not be located automatically — find it again (`patchouli read`/`search`) "
                    "and fix the anchor")
            elif c.start is not None and (c.start < 1 or c.end < c.start or c.end > len(texts[c.source])):
                err("CIT002", page.rel, c.line, f"`{c.target}` is outside lines 1–{len(texts[c.source])}")

        # footnotes
        for label, lines_ in m.refs.items():
            if label not in m.footnotes:
                err("FN001", page.rel, lines_[0], f"[^{label}] has no definition")
        for label, first, again in m.duplicate_footnotes:
            err("FN003", page.rel, again, f"[^{label}] is defined twice (lines {first} and {again}); "
                "each claim needs its own label")
        for label, f in m.footnotes.items():
            if label not in m.refs:
                adv("FN002", page.rel, f.line, f"[^{label}] is defined but never referenced")
            if f.kind in ("interpretation", "judgment"):
                if f.certainty is None:
                    adv("EVD002", page.rel, f.line, f"[^{label}] {f.kind}: add a certainty "
                        "(high / moderate / low / speculative)")
                if not (f.cites or f.links) and not (t == "source" and f.kind == "interpretation"):
                    adv("EVD004", page.rel, f.line, f"[^{label}] {f.kind} names no basis (a citation or page)")

        # quotes
        own = slug if t == "source" and slug in texts else None
        for q in quotes.extract_quotes(page.body, page.body_start, own, page.dir, m.footnotes):
            if q.source not in texts:
                continue
            ok, msg = quotes.verify(q, text_index(q.source))
            if not ok:
                short = q.text if len(q.text) < 90 else q.text[:87] + "..."
                err("QUO001", page.rel, q.line, f"quote from `{q.source}` {msg}: “{short}”")

        if t == "synthesis" and len(g.sources_of(slug)) < 2:
            adv("SYN001", page.rel, 0, "a synthesis usually compares two or more sources")

        if t in INTEGRATED_TYPES:
            # when this page last answered to its basis: created, revised, or marked reviewed
            st = state.get(slug, {})
            mine = st.get("basis") or st.get("changed", "")
            for dep in sorted(g.dependencies(slug)):
                revised = state.get(dep, {}).get("revised", "") if dep in g.pages else ""
                if mine and revised and revised > mine:
                    adv("STL001", page.rel, 0, f"`{dep}` was revised ({revised[:16]}) after this page was last "
                        "checked against it; re-check what this page takes from it — revise it (with a revision "
                        "note), or if it still holds set `reviewed: <today>` in its frontmatter (already today? add the "
                        "time, `reviewed: 2026-05-04 15:30`)")

    order = {lvl: i for i, lvl in enumerate(LEVELS)}
    issues.sort(key=lambda i: (order[i.level], i.path, i.line, i.code))
    return issues
