# Patchouli Design Notes

How `patchouli-philosophy.md` is realized, and why.

## Goals

1. **User-friendly.** The researcher spends attention on goals, questions, ideas and
   judgment. They talk; the agent works; scripts do the bookkeeping.
2. **Semantically rich knowledge.** Pages that are specific, conditioned, connected and
   honest about certainty — not summaries stacked on summaries.

## Lineage

- **Karpathy's "LLM Wiki" (2026)**: an agent compiles sources into a persistent,
  interlinked Markdown wiki instead of re-retrieving raw documents per query — immutable
  raw sources, an LLM-owned wiki, a schema file (`AGENTS.md`), an index read first and
  an append-only log.
- **Legacy Patchouli**: binding quote checks, the binding-vs-advisory split, no-op
  outcomes, the trust boundary, tastes, `notes/`, scoped commits, the Docling profile.
  Its rigid procedures (numbered steps, gates on what ingest may create) were dropped.
- **This version** went through two independent agent reviews with small real pilots;
  their findings shaped the decisions below.

## Layers and division of labor

```
raw/      original files, hashed, never edited
text/     reading text extracted from raw/: line-addressed, never hand-edited
wiki/     sources/ (one page per material) → concepts/ syntheses/ answers/ (+ hubs/)
```

Knowledge flows up; traceability flows down — every claim links to the lines (or the
original page/figure) it rests on. The agent does everything that needs understanding;
the CLI does everything deterministic: extraction, line-addressed reading, search, the
index, change tracking, checks, the log, renames, git snapshots. Task *contracts* state
objective, resources, deliverables and a quality bar — never steps.

## Markup: plain Markdown, evidence in footnotes

| what | written as |
|---|---|
| link | `[Self-attention](../concepts/self-attention.md)` — every page is at `wiki/<kind>/<slug>.md`, so paths are the same from any page; `sync` repairs wrong ones |
| typed relation | a list item `- <Label>: [target](…)`, read "this page — label — target". Labels are free (any language); the contradiction family feeds the index's Tensions, `related`/`see also` are navigation |
| citation | `[jain2019 L88–95](../../text/jain2019.md#L88-L95)`, or the original for what the text lacks: `[jain2019 fig. 1](../../raw/jain2019.pdf#page=3)` |
| evidence kind | the claim ends in `[^n]`; a footnote with only citations is the source's *stated* finding; `Interpretation (moderate) — …` / `Judgment (low) — …` mark the agent's reasoning with a certainty |
| substantive change | a dated line under `## Revision notes`; a re-check that changes nothing sets `reviewed: <date>` |

Why footnotes rather than inline tags or a database of claims: prose stays readable in
any viewer, a footnote naturally holds basis and caveat, and nothing can drift because
the page itself is the record.

## Checks: errors vs advice

**Errors** are objective facts a script can verify and the agent cannot argue with:
page identity (type, title, unique slug, source ids reserved), citations that resolve
to registered sources and real lines, footnotes defined once, quotes found verbatim in
the cited span, raw files untouched. `sync` logs and snapshots only when there are none.

**Advice** covers form and upkeep: wanted pages, orphans, missing summaries or
certainty, a judgment with no basis, a thin synthesis, pages to re-check. It never
blocks — gating writing on form makes the agent optimize the proxy (Goodhart) — and
`sync` shows only the advice about what just changed.

Quote checking compares normalized tokens: typography and emphasis fold; words,
numbers and the signs around them (`< 10`, `1e-6`, `−12`) do not. An inline `"…"` is a
quote only when a citation link follows it directly, so titles and terms aren't checked.

## Keeping it true over time

- **Change tracking** (`.patchouli/pages.json`) is automatic: content hash, `changed`,
  `revised` (when the revision notes changed) and `basis` (when the page last answered
  to what it rests on: created, revised, or a new `reviewed:` value). A page is flagged
  (STL001) when something it *depends on* — citations, evidence footnotes, typed
  relations — was revised after its basis. Routine edits neither flag nor clear.
- **Re-extraction** (a better PDF parser) aligns old and new text token by token and
  rewrites every citation of that source. A span is carried over only if most of it
  aligns and every number and sign in it survives in both directions; otherwise it
  becomes `#L…?`, an error for the agent to resolve. The source page is flagged for a
  re-read (SRC005) until revised or reviewed.
- **Rename/merge** updates every reference by resolved path (never a same-named note or
  an outside URL); a merged page is kept in `.patchouli/trash/`.
- **The registry** (`.patchouli/sources.json`) is written entry by entry under a lock,
  so overlapping `add`s don't lose each other's work. Raw files are re-hashed only when
  their size or modification time changed.

## Search and the database

`.patchouli/index.db` is a SQLite file rebuilt from the Markdown whenever it is used and
never versioned. It provides FTS5 search over pages and reading text (CJK as unigrams
and bigrams; text hits come back as citable line spans) and read-only SQL through
`patchouli query` over pages, links, citations, page sources and claims — e.g. weakest
judgments, judgments resting on one source, concepts with many sources but no synthesis.
It is derived, not primary: a second store would drift from the pages, force the agent
to record claims through commands, and make the wiki unreadable without the tool.

## Mapping the philosophy

| Philosophy | Mechanism |
|---|---|
| Material compilation, interactive distillation | `ingest` and `distill` contracts; `ask`/`explore` write lasting insight back |
| Lasting value, placement | research goals in `wiki/hubs/overview.md`; "enrich > restructure > create"; declining is a valid outcome |
| Page types | source, concept, synthesis, answer (+ hub for navigation) |
| Layers and traceability | raw → text → source pages → integrated pages; line-anchored citation links; `read` |
| On-demand reading | `ask` descends from compiled knowledge to text and originals as needed; `search` |
| Evidence and reasoning | footnote kinds and certainty; conditions kept with conclusions; disagreement explained, independence checked |
| Maintenance via the citation network | change tracking, revision notes, re-check flags, relocation, `rename` |
| Contracts and division of labor | 7 contracts; the CLI does all deterministic work |
| Improvement through use | `meta/feedback.md`; guide, contracts, templates and tastes live in the vault |

## Known limits

- Tests cover the deterministic layer only; page quality is judged in real use.
- Basic PDF extraction loses tables, formulas and superscripts; such sources are flagged.
- Search is lexical (BM25 over ~1,500-character windows); embeddings could join the same index later.
