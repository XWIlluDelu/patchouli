# Patchouli

<img src="patchouli-knowledge.png" alt="Patchouli Knowledge" width="320" align="right" />

A research wiki you build by talking to an agent. You bring sources and questions;
the agent reads, compiles, and cross-references; what the evidence cannot support,
it declines to write. The wiki under `wiki/` is the compounding asset: structured,
interlinked markdown where every claim traces back to a source, richer with every
source ingested and every question asked. Everything else in this folder is
replaceable logistics around it.

<br clear="right" />

## Quick start

Start your agent in this folder (`pi`, `codex`, or `claude`); it reads `AGENTS.md`
and learns its operations. Then talk to it:

| You say | Operation | You get |
|---|---|---|
| "ingest 1706.03762" — an arxiv id, URL, or local file | ingest | one compiled source page in `wiki/sources/` |
| "find papers on catastrophic forgetting in BNNs" | search | a candidate list in `searches/` to pick ingests from |
| "what does the wiki say about X?" | ask | an answer in `wiki/answers/`, grounded in compiled pages only |
| "synthesize the continual-learning approaches" | synthesize | one cross-work pattern in `wiki/syntheses/` |
| "organize the wiki" | organize | concept/entity/synthesis pages where a boundary earns one |
| "maintain" | maintain | pruned duplicates, orphans, and superseded pages |
| "polish notes/attention-as-explanation.md" — the whole note or one passage | polish | your note proofread in place — mechanics fixed, voice intact |

An operation that is not justified returns `NO_OP: <reason>` instead of writing —
the wiki grows only when growth is earned. `tastes/active.md` is the research taste
the agent reads for emphasis; point it at another `tastes/*.md` to change what gets
foregrounded.

## Setup

The scripts run on the Python 3 standard library alone; a bare `python3` covers
everything except two add-ons:

- Local `.pdf` ingest needs `pypdf`: `uv venv && uv pip install -r requirements.txt`,
  then `direnv allow` (or `source .venv/bin/activate` if you don't use direnv).
- Web-page ingest uses Firecrawl and discovery uses Exa: copy `.env.example` to
  `.env` and set `FIRECRAWL_API_KEY` / `EXA_API_KEY`. Repeating a key on multiple
  lines pools them, with automatic failover.

## What is enforced vs. what is judgment

`scripts/check_wiki.py` runs after every write: provenance, work ids, verbatim-quote
faithfulness against the extracted reading surface, link resolution — facts the agent
cannot invent. Everything else — what is worth saying, how deep to integrate, whether
a page is worth writing at all — is the agent's judgment. `scripts/lint.py` advises;
it never blocks. The floor itself is tested: `python3 -m unittest discover -s tests`.

## Layout

```
AGENTS.md   entry point: routing, the contracts, the binding floor (CLAUDE.md links here)
README.md   this file
docs/       the design argument (llm-wiki-philosophy.md)
prompts/    one task file per operation
system/     page_templates.md — structural source of truth for every page type
scripts/    extract, search, check_wiki, lint, indexes — the deterministic parts
tests/      unittest suite for the binding floor
tastes/     research tastes; active.md is the one in force
wiki/       the asset: sources, concepts, entities, syntheses, answers, hubs, indexes
extracted/  clean reading surfaces produced at ingest; quotes are checked against these
raw/        original downloaded material (gitignored)
searches/   candidate lists written by search.py, for you to pick ingests from
notes/      your own notes — human-written only; say "ingest notes/<file>" to add one to the wiki
```
