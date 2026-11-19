"""Derived SQLite index of the vault (`.patchouli/index.db`, not versioned).

Markdown stays the single source of truth: humans and the agent read and edit
pages directly, git diffs them, nothing can drift. This database is rebuilt from
the Markdown and the source registry, automatically, whenever it is used. It
provides what a database is good at:

* full-text search (FTS5, BM25) over pages and reading text, CJK-aware;
* structured queries over pages, links, citations and claims (`patchouli query`),
  e.g. low-certainty judgments, claims resting on a single source, concepts
  cited by many sources but lacking a synthesis.
"""
from __future__ import annotations

import hashlib
import sqlite3

from . import __version__
from . import graph as graphmod
from . import markup
from . import search as searchmod
from . import state as statemod
from .vault import Vault

FILE = "index.db"
VERSION = f"4-{__version__}"  # any code change that alters parsing bumps the package version

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS sources(
  id TEXT PRIMARY KEY, title TEXT, raw TEXT, text TEXT, lines INT,
  extractor TEXT, quality TEXT, added TEXT, has_page INT);
CREATE TABLE IF NOT EXISTS pages(
  slug TEXT PRIMARY KEY, type TEXT, title TEXT, summary TEXT, path TEXT,
  status TEXT, tags TEXT, changed TEXT, revised TEXT);
CREATE TABLE IF NOT EXISTS links(src TEXT, dst TEXT, rel TEXT, line INT, dst_exists INT);
CREATE TABLE IF NOT EXISTS citations(page TEXT, source TEXT, start INT, "end" INT, line INT, footnote TEXT,
  original TEXT);
CREATE TABLE IF NOT EXISTS page_sources(page TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS claims(
  id INTEGER PRIMARY KEY, page TEXT, footnote TEXT, line INT, kind TEXT, certainty TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS claim_sources(claim INT, source TEXT, start INT, "end" INT);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
  tokens, kind UNINDEXED, ref UNINDEXED, path UNINDEXED, title UNINDEXED,
  start UNINDEXED, "end" UNINDEXED, tokenize='unicode61');
"""

DOC = """Tables (read-only; rebuilt from the Markdown automatically):
  pages(slug, type, title, summary, path, status, tags, changed, revised)
  sources(id, title, raw, text, lines, extractor, quality, added, has_page)
  links(src, dst, rel, line, dst_exists)          -- rel: 'link', or the relation label (lower-case, e.g. 'contradicts')
  citations(page, source, start, "end", line, footnote, original)  -- original: locator in raw/ (e.g. 'page=3'), else NULL
  page_sources(page, source)                      -- sources a page rests on (as counted in the index)
  claims(id, page, footnote, line, kind, certainty, text)   -- kind: stated | interpretation | judgment | note
  claim_sources(claim, source, start, "end")      -- start/end NULL when its footnote names the source page

Examples:
  -- what builds on a source or page (before changing it)
  SELECT page AS src, 'cite' AS how FROM page_sources WHERE source = 'jain2019'
    UNION SELECT src, rel FROM links WHERE dst = 'jain2019' AND rel NOT IN (%s);
  -- judgments and interpretations, weakest first
  SELECT page, kind, certainty, text FROM claims WHERE kind IN ('judgment','interpretation')
    ORDER BY CASE certainty WHEN 'speculative' THEN 0 WHEN 'low' THEN 1 WHEN 'moderate' THEN 2 ELSE 3 END;
  -- judgments resting on a single source
  SELECT c.page, c.text FROM claims c JOIN claim_sources s ON s.claim = c.id
    WHERE c.kind = 'judgment' GROUP BY c.id HAVING COUNT(DISTINCT s.source) = 1;
  -- concepts drawing on 3+ sources that no synthesis links to
  SELECT p.slug, COUNT(*) n FROM pages p JOIN page_sources ps ON ps.page = p.slug
    WHERE p.type = 'concept' AND p.slug NOT IN
      (SELECT l.dst FROM links l JOIN pages q ON q.slug = l.src WHERE q.type = 'synthesis')
    GROUP BY p.slug HAVING n >= 3 ORDER BY n DESC;
  -- every recorded contradiction (any label of the contradiction family)
  SELECT src, rel, dst FROM links WHERE rel IN (%s);
""" % (", ".join(f"'{r}'" for r in sorted(markup.LOOSE)),
       ", ".join(f"'{r}'" for r in sorted(markup.CONTRADICTS)))


def path(v: Vault):
    return v.state_dir / FILE


def connect(v: Vault, readonly: bool = False) -> sqlite3.Connection:
    p = path(v)
    if readonly:
        return sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    v.state_dir.mkdir(exist_ok=True)
    return sqlite3.connect(p)


def _meta(con, key, default=None):
    row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def refresh(v: Vault, g=None, state=None) -> sqlite3.Connection:
    """Bring the index up to date (cheap when nothing changed) and return a connection."""
    con = connect(v)
    try:
        current = _meta(con, "version")
    except sqlite3.DatabaseError:  # no tables yet, or not a database
        current = None
    if current != VERSION:
        con.close()
        path(v).unlink(missing_ok=True)
        con = connect(v)
    con.executescript(SCHEMA)
    con.execute("INSERT OR REPLACE INTO meta VALUES('version', ?)", (VERSION,))
    g = g or graphmod.build(v)
    if state is None:
        state, _, _ = statemod.current(v, g)
    reg = v.registry

    sig = hashlib.sha256()
    for slug in sorted(g.pages):
        sig.update(f"{slug}:{state.get(slug, {}).get('sha')}:{state.get(slug, {}).get('revised')}\n".encode())
    for sid in sorted(reg):
        sig.update(f"{sid}:{reg[sid].get('text_sha256')}:{reg[sid].get('title')}\n".encode())
    sig = sig.hexdigest()
    if _meta(con, "pages_sig") != sig:
        _rebuild_pages(con, v, g, state)
        con.execute("INSERT OR REPLACE INTO meta VALUES('pages_sig', ?)", (sig,))
    _refresh_texts(con, v)
    con.commit()
    return con


def _rebuild_pages(con, v: Vault, g, state):
    reg = v.registry
    for t in ("sources", "pages", "links", "citations", "page_sources", "claims", "claim_sources"):
        con.execute(f"DELETE FROM {t}")
    con.execute("DELETE FROM fts WHERE kind = 'page'")
    for sid, e in reg.items():
        con.execute("INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?)",
                    (sid, e.get("title"), e.get("raw"), e.get("text"), e.get("lines"),
                     e.get("extractor"), e.get("quality"), e.get("added"), int(g.has_source_page(sid))))
    for slug, p in g.pages.items():
        st = state.get(slug, {})
        tags = p.meta.get("tags")
        con.execute("INSERT INTO pages VALUES(?,?,?,?,?,?,?,?,?)",
                    (slug, p.type, p.title, p.summary, p.rel, str(p.meta.get("status") or ""),
                     ",".join(tags) if isinstance(tags, list) else str(tags or ""), st.get("changed"),
                     st.get("revised")))
        m = g.marks[slug]
        for l in g.links(slug):
            con.execute("INSERT INTO links VALUES(?,?,?,?,?)", (slug, l.target, l.rel, l.line, int(l.target in g.pages)))
        for c in m.cites:
            con.execute("INSERT INTO citations VALUES(?,?,?,?,?,?,?)",
                        (slug, c.source, c.start, c.end, c.line, c.footnote, c.frag if c.raw else None))
        for sid in g.sources_of(slug):
            con.execute("INSERT INTO page_sources VALUES(?,?)", (slug, sid))
        for cl in m.claims:
            cur = con.execute("INSERT INTO claims(page, footnote, line, kind, certainty, text) VALUES(?,?,?,?,?,?)",
                              (slug, cl.label, cl.line, cl.kind, cl.certainty, cl.text))
            cid = cur.lastrowid
            for c in cl.cites:
                con.execute("INSERT INTO claim_sources VALUES(?,?,?,?)", (cid, c.source, c.start, c.end))
            cited = {c.source for c in cl.cites}
            fn = m.footnotes.get(cl.label) if cl.label else None
            for l in (fn.links if fn else []):  # a source page named in the evidence footnote
                if g.source_of(l) and l.target not in cited:
                    cited.add(l.target)
                    con.execute("INSERT INTO claim_sources VALUES(?,?,NULL,NULL)", (cid, l.target))
        tokens = searchmod.tokenize(p.body) + searchmod.tokenize(f"{p.title} {p.summary}") * 3
        if isinstance(tags, list):
            tokens += searchmod.tokenize(" ".join(tags)) * 2
        last = p.body_start + p.body.count("\n")
        con.execute("INSERT INTO fts VALUES(?,?,?,?,?,?,?)",
                    (" ".join(tokens), "page", slug, p.rel, p.title, p.body_start, last))


def _refresh_texts(con, v: Vault):
    reg = v.registry
    indexed = {k[5:]: val for k, val in con.execute("SELECT key, value FROM meta WHERE key LIKE 'text:%'")}
    for sid in set(indexed) - set(reg):
        con.execute("DELETE FROM fts WHERE kind='text' AND ref=?", (sid,))
        con.execute("DELETE FROM meta WHERE key=?", (f"text:{sid}",))
    for sid, e in reg.items():
        sha = e.get("text_sha256") or ""
        if indexed.get(sid) == sha:
            continue
        con.execute("DELETE FROM fts WHERE kind='text' AND ref=?", (sid,))
        lines = v.text_lines(sid) or []
        title = e.get("title") or sid
        rel = v.rel(v.text_path(sid))
        for s, e in searchmod.windows(lines):
            toks = searchmod.tokenize("\n".join(lines[s:e]))
            if toks:
                con.execute("INSERT INTO fts VALUES(?,?,?,?,?,?,?)",
                            (" ".join(toks), "text", sid, rel, title, s + 1, e))
        con.execute("INSERT OR REPLACE INTO meta VALUES(?, ?)", (f"text:{sid}", sha))
