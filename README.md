# Patchouli

<img src="patchouli-knowledge.png" alt="Patchouli Knowledge" width="320" align="right" />

A research wiki you build by talking to an agent. You bring sources and
questions; the agent reads, compiles, and cross-references; what the evidence
cannot support, it declines to write. The wiki under `wiki/` is the compounding
asset: structured, interlinked markdown where every claim traces back to a
source, richer with every source ingested and every question asked. Everything
else in this folder is replaceable logistics around it.

<br clear="right" />

## Quick start

Start your agent in this folder (`pi`, `codex`, or `claude`); it reads
`AGENTS.md` and learns its operations. Then talk to it:

| You say | Operation | You get |
|---|---|---|
| "ingest 1706.03762" — an arxiv id, URL, or local file | ingest | one compiled source page in `wiki/sources/` |
| "find papers on attention as explanation" | search | a candidate list in `searches/` to pick ingests from |
| "what does the wiki say about attention as explanation?" | ask | an answer in `wiki/answers/`, grounded in compiled pages only |
| "synthesize the attention-as-explanation debate" | synthesize | one cross-work pattern in `wiki/syntheses/` |
| "organize the wiki" | organize | durable pages or a reading-path hub where one is earned |
| "maintain" or "this page is wrong" | maintain | evidence-grounded corrections or justified pruning |
| "polish notes/attention-as-explanation.md" — the whole note or one passage | polish | your note proofread in place — mechanics fixed, voice intact |

A knowledge or note change that is not justified returns `NO_OP: <reason>`
instead of writing; search still records discovery attempts. The wiki grows only
when growth is earned. `tastes/active.md` is the research
taste the agent reads for emphasis; point it at another `tastes/*.md` to change
what gets foregrounded.

## Setup

This workspace uses the high-quality `docling-enriched` PDF profile:

```sh
uv sync --extra pdf-quality
python3 scripts/extract.py paper.pdf --pdf-profile docling-enriched
```

Use `uv sync --extra pdf-quality-cpu` for the same parser with CPU-only PyTorch
wheels. `uv sync` without an extra installs only the HTML/text pipeline. Then
run `direnv allow`, or source `.venv/bin/activate` directly.

`pyproject.toml` and `uv.lock` also retain `pdf-balanced` and `pdf-fast`
comparison environments. The balanced profile includes a mandatory
noncommercial-or-commercial dependency; install it only after resolving the
license for the intended use. Exact versions, configurations, measurements, and
license boundaries are in [`docs/pdf-profiles.md`](docs/pdf-profiles.md).

The extras are mutually incompatible. An exact `uv sync --extra ...` switches
the environment rather than mixing parser stacks. Only `docling-enriched` is
wired into `scripts/extract.py`; the extractor never probes installed packages
or falls back to a different parser.

Virtual environments under `.venv/` or `.venv-*/` are ignored; dependency and
model caches use defaults outside the repository. Git contains only the
dependency declarations and lockfile. Docling downloads its model artifacts on
first use and keeps them outside the repository. Local inputs are limited to
`.pdf`, `.html`, `.htm`, `.md`, and `.txt`; other formats are rejected rather
than decoded as text.

Web-page ingest uses Firecrawl and discovery uses Exa. Copy `.env.example` to
`.env` and set `FIRECRAWL_API_KEY` / `EXA_API_KEY`. Repeating a key on multiple
lines pools them, with automatic failover.

## What is enforced vs. what is judgment

`scripts/check_wiki.py` runs after every write: required schema, provenance,
work ids, verbatim-quote faithfulness against the extracted reading surface,
link resolution — facts the agent cannot invent. Everything else — what is worth
saying, how deep to integrate, whether a page is worth writing at all — is the
agent's judgment. `scripts/lint.py` advises; it never blocks. The floor itself
is tested: `python3 -m unittest discover -s tests`.

## Layout

```
AGENTS.md   entry point: routing, the contracts, the binding floor (CLAUDE.md links here)
README.md   this file
pyproject.toml, uv.lock   common dependencies and mutually exclusive PDF profiles
docs/       the design argument (llm-wiki-philosophy.md)
prompts/    one task file per operation
system/     page_templates.md — structural source of truth for every page type
scripts/    extract, search, check_wiki, lint, indexes, scoped commit — deterministic parts
tests/      unittest suite for the deterministic logistics
tastes/     research tastes; active.md is the one in force
wiki/       the asset: sources, concepts, entities, syntheses, answers, hubs, indexes
extracted/  tracked current reading surfaces; explicit refreshes are retained by Git
raw/        current source captures used during extraction (gitignored)
searches/   candidate lists written by search.py, for you to pick ingests from
notes/      your own notes — human-written only; say "ingest notes/<file>" to add one to the wiki
```
