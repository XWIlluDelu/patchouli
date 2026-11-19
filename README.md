# Patchouli

<img src="patchouli-knowledge.png" alt="Patchouli Knowledge" width="320" align="right" />

A research wiki you build by talking to an agent. You bring goals, questions, ideas
and materials. The agent reads, extracts, connects,
synthesizes and maintains an interlinked Markdown knowledge base in which every claim
traces back to its evidence. A small CLI does the deterministic work, so neither of
you has to do bookkeeping.

Philosophy: [`patchouli-philosophy.md`](patchouli-philosophy.md) · design and rationale:
[`docs/design.md`](docs/design.md)

<br clear="right" />

## Install

```sh
uv tool install --editable '.[pdf]'          # core + pypdf for PDFs (or: pip install -e '.[pdf]')
uv tool install --editable '.[pdf-quality]'  # instead: Docling for high-quality PDFs, tables, OCR (~5 GB)
```

Python ≥ 3.10; the core has no dependencies. PDFs use Docling if installed, else `pypdf`
or poppler's `pdftotext`; basic extractions are flagged.

## Use

```sh
patchouli init ~/research/my-wiki && cd ~/research/my-wiki
```

Start your coding agent in that directory with `AGENTS.md` as its instructions, then just talk:

- "Our goal is to understand why X fails on long inputs."
- "I put three papers in the inbox." / "Add https://arxiv.org/pdf/…"
- "What do we know about Y? Do A and B actually disagree?"
- "Compare the methods for Z."
- "Look around and tell me what we're missing."
- "That's a good point, keep it."
- "Paper B has a v2; update things."
- "Polish my note on Q."

## Vault layout

```
inbox/      drop materials here
raw/        immutable originals          text/   line-numbered reading text (extracted)
wiki/       sources/ concepts/ syntheses/ answers/ hubs/ (overview) + index, log
notes/      your own writing (the agent only proofreads it on request)
tastes/     research lenses: mechanism, boundary, construct, evidence (set in config)
templates/  page skeletons + STYLE.md (GOOD/BAD examples)
contracts/  what each kind of task should deliver
AGENTS.md   the agent's operating guide
```

## What a page looks like

Plain Markdown, readable anywhere (GitHub, VS Code, any viewer). Prose stays clean;
evidence lives in footnotes, as in a paper:

```markdown
- On benchmark B, M cuts error by 12% relative to C, at batch sizes ≤ 64.[^1]
- The gain likely comes from regularization rather than capacity.[^2]
- Contradicts: [Smith 2025 on N](../sources/smith2025-n.md) — on long inputs

> exact wording that carries evidence

— [doe2024-m L88–89](../../text/doe2024-m.md#L88-L89)

[^1]: [doe2024-m L120–131](../../text/doe2024-m.md#L120-L131)
[^2]: Interpretation (moderate) — [doe2024-m L200–210](../../text/doe2024-m.md#L200-L210); untested beyond vision.
```

A footnote that just cites lines is the source's own finding; `Interpretation (…)` and
`Judgment (…)` mark the agent's reasoning, with a certainty. Citation links open the
reading text (jumping to the lines depends on the viewer; `patchouli read <link>` always
shows exactly those lines).

## CLI (mostly for the agent)

| command | purpose |
|---|---|
| `init DIR` · `status` | create a vault · what's pending |
| `add [PATH\|URL…]` | register materials (default: inbox/) and extract reading text |
| `read ID [-l A-B] [-g REGEX]` | numbered reading text (also takes a citation link) |
| `search QUERY` | full-text search over pages and text; prints ready-to-paste links and citations |
| `query "SQL"` | read-only SQL over pages, links, citations and claims (no args: schema + examples) |
| `new TYPE NAME` | start a page from its template |
| `sync --op OP -m MSG` | after any work: track changes, rebuild index and graph, log, git snapshot, check |
| `check` | errors (objective, must be fixed) and advice (form, optional) |
| `rename OLD NEW [--merge]` | rename a source/page or redirect a merged page; updates every reference |
| `extract ID --force \| --from FILE.md` | re-extract, or import a better conversion (citations are carried over) |

## Tests

`python -m unittest discover -s tests` — the deterministic layer only.
