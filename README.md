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
when growth is earned. `tastes/active.md` is the research taste the agent reads
for emphasis; point it at another `tastes/*.md` to change what gets
foregrounded.

For local standing context, copy `personal.example.md` to `personal.md`. The
local file is ignored by Git by default and may describe your background,
research agenda, language or notation, and working preferences. It shapes
emphasis and presentation, never evidence or wiki structure.

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

`scripts/check_wiki.py` runs after every write. It enforces required schema,
canonical source paths, declared work/surface/version/locator consistency,
contiguous normalized matches for explicit quotes, and unique internal-link
resolution. It does not prove that a paraphrase follows from its source, that a
marker is attached to the right claim, or that a page is worth writing; those
remain the agent's judgment.

Two advisory tools never block a write:

- `scripts/lint.py` reports content-health signals such as citation clutter,
  orphans, and duplicate titles;
- `scripts/stale.py` reports committed answers and durable pages whose compiled
  source pages have changed since the derived page's last revision or review.

A stale report is a maintenance queue, not a correctness verdict. The floor and
advisory tools are tested with `python3 -m unittest discover -s tests`.

## Source refreshes

`extract.py --refresh` replaces the tracked reading surface only for a new
capture of the same work. The source page and surface are then updated in one
operation, while Git retains the previous state. After a refresh, run:

```sh
python3 scripts/stale.py
```

The scan compares each committed answer, concept, entity, and synthesis with the
source-page blobs that existed at that page's last commit. It names pages to
review but does not rewrite or invalidate them automatically: an updated source
may leave a derived claim unchanged.

When a review concludes that the page remains valid, consume that queue item
without touching the knowledge page:

```sh
python3 scripts/stale.py --acknowledge wiki/answers/example.md
# or acknowledge one dependency only
python3 scripts/stale.py --acknowledge wiki/answers/example.md --work-id 1706.03762
```

The command binds the review to the current committed source-page blob in the
tracked `wiki/.stale-reviews.json` sidecar. Commit that sidecar with the
maintenance operation. If the source changes again, the candidate reopens.

## Evaluation

`scripts/eval.py` provides a runtime-agnostic evaluation harness without an LLM
client. It copies the framework into case workspaces, optionally applies fixture
overlays, initializes a baseline Git commit for the scoped-commit contract, lets
a user-supplied agent CLI execute each request, and grades observable outcomes:
`NO_OP` versus write, changed paths, content assertions, and the binding floor.

There are two deliberately different modes:

- `prepare` is convenient for manual/open-book acceptance runs. The copied
  workspace omits `.env`, `personal.md`, suites, fixtures, and grader tests, but
  the harness cannot stop a manually launched process from reading parent or
  repository paths unless the agent app supplies its own sandbox.
- `run` defaults to Linux Bubblewrap isolation. Its mount/PID namespace exposes
  the case workspace, request, response, a small read-only system root, and only
  explicitly allowed non-gold paths. The repository, suite, other cases, and run
  control files are absent from the adapter filesystem. A timeout terminates the
  adapter process group; Bubblewrap also contains descendants in its PID
  namespace.

The included `evals/smoke.json` is public acceptance material, not held-out gold.
Run it cheaply without pretending otherwise:

```sh
python3 scripts/eval.py run evals/smoke.json --force --isolation none \
  --adapter-command 'claude -p "$PATCHOULI_EVAL_REQUEST"'
```

For a held-out local run, keep the suite and its fixture directories private and
unpublished; overlay paths are resolved relative to the suite file. Install
`bwrap`, then run:

```sh
python3 scripts/eval.py run /private/evals/suite.json --force \
  --isolation bwrap \
  --sandbox-home ~/.patchouli-eval-home \
  --adapter-command 'your-agent-cli "$PATCHOULI_EVAL_REQUEST"'
```

Use a dedicated sandbox home outside the Patchouli repository and eval output,
containing only the adapter state it needs. Additional `--sandbox-read` and
`--sandbox-write` mounts are available, but the harness rejects mounts that
would expose repository, suite, or run-control paths. Network access remains
available for model APIs, so published benchmark material is necessarily
open-book. See `evals/README.md` for the full protocol.

## Layout

```
AGENTS.md   entry point: routing, the contracts, the binding floor (CLAUDE.md links here)
README.md   this file
personal.example.md   template for optional local personal.md (ignored by default)
pyproject.toml, uv.lock   common dependencies and mutually exclusive PDF profiles
docs/       the design argument (llm-wiki-philosophy.md)
evals/      public acceptance suites and synthetic fixture overlays
prompts/    one task file per operation
system/     page_templates.md — structural source of truth for every page type
scripts/    extract, search, checks, stale review, indexes, scoped commit, and eval
tests/      unittest suite for deterministic logistics and evaluation grading
tastes/     research tastes; active.md is the one in force
wiki/       the asset: sources, concepts, entities, syntheses, answers, hubs, indexes
extracted/  tracked current reading surfaces; explicit refreshes are retained by Git
raw/        current source captures used during extraction (gitignored)
searches/   candidate lists written by search.py, for you to pick ingests from
notes/      your own notes — human-written only; say "ingest notes/<file>" to add one to the wiki
```
