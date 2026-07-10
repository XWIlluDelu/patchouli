# Page templates

One universal structure per page type. This file is the maintainer's single
source of truth for page structure. A taste may change emphasis, never
structure.

The structures below are the target. Each one ends in a GOOD/BAD pair where the
shape is easy to get wrong; copy the GOOD shape, avoid the BAD one. Show the
quality, do not describe it.

## Source page

```markdown
---
title: "Paper title"
page_type: source
work_id: <stable work id emitted by extract.py>
version_id: <content hash from extract.py>
reading_surface: extracted/<work_id>/text.md
source: <source locator emitted by extract.py>
---

# Paper title

## What this source is

One paragraph: what kind of source this is and what problem it addresses,
ending with `(Work: <work_id>)`. Scannable on its own — a reader who reads only
this line knows whether to keep reading.

## Source identity

- Title: ...
- Authors: ...
- Year: ...
- Venue: ...
- Work: `<work_id>`

## Key claims

- <One checkable claim with its specifics: numbers, parameters, dataset, metric,
  or theorem assumption when the source gives them.> (Work: <work_id>)
- <Next distinct claim — not a restatement.> (Work: <work_id>)

## Method and evidence

Connected prose that walks the actual experiment: the setup, what it is compared
against, the metric, and the hyperparameters, woven into a narrative a later
researcher can follow. Name the evidence strength in line (experiment,
observation, simulation, proof, review) rather than as a detached tag.

## Evidence status

One scannable label plus one line of reasoning: what kind of evidence this source
is overall (e.g. `mixed — conceptual proposal + toy proof + benchmark figures,
no tabulated metrics`).

## Reproducibility

What a replicator would need and what the source provides: code/data availability,
seeds, number of trials, confidence intervals, compute, full hyperparameters.
Universal across domains — for a proof, this is the assumptions and whether the
argument is complete; for a clinical study, the protocol, n, and pre-registration.

## Limits

Scientific scope only: population, method, and context the finding does not extend
to, and what the evidence does not show. Keep extraction problems out of here.

## Extraction caveats

What in THIS extraction is damaged or incomplete — a malformed equation, a missing
table, figures whose numbers are not in the text — so a later reader knows to
verify against the original before reuse. Omit if the extraction is clean.

## Tensions

Only when this source conflicts with another compiled work.

## Reading note

How a later researcher should use this source.
```

Itemize claims; one marker per claim. A claim is what this work itself
establishes — a result it cites from related work is context, not a claim.

```text
BAD (marker-saturated, compressed, not itemized):
The Transformer works well (Work: 1706.03762). It uses only attention (Work: 1706.03762)
and trains faster than RNNs (Work: 1706.03762).

GOOD (itemized, one marker, specific):
- On WMT 2014 English-to-German the Transformer reaches 28.4 BLEU, beating the prior
  best (including ensembles) by over 2 BLEU, while training in 3.5 days on 8 GPUs.
  (Work: 1706.03762)
```

Method and evidence is prose, not a bullet dump of strength tags.

```text
BAD (thin bullets, evidence strength as a detached tag):
- Benchmark on WMT 2014 EN-DE. Evidence strength: experiment.
- Comparison to RNN/CNN baselines. Evidence strength: experiment.

GOOD (connected prose: setup -> comparison -> metric -> hyperparameters):
For machine translation the authors evaluate on WMT 2014 English-to-German (4.5M
sentence pairs, byte-pair encoding, ~37k shared vocab) and English-to-French (36M
pairs, 32k word-piece vocab), comparing the Transformer against the best recurrent
and convolutional encoder-decoders. The base model uses N=6 encoder/decoder layers,
d_model=512, h=8 parallel attention heads with d_k=d_v=64; performance is BLEU on the
standard test sets, and training cost is reported in GPU-days — an experiment whose
headline numbers (28.4 and 41.8 BLEU) come from tables, not figures. (Work:
1706.03762)
```

Evidence status is one scannable line, not a vague adjective.

```text
BAD: Strong evidence overall.
GOOD: experiment — two WMT 2014 translation benchmarks with tabulated BLEU and
training-cost comparisons against RNN/CNN encoder-decoders, plus an English
constituency-parsing generalization check. (Work: 1706.03762)
```

Reproducibility names what a replicator gets and what they still lack, not a
verdict.

```text
BAD: The paper is reproducible; code is available.
GOOD: Code is public (tensor2tensor); training is pinned to step counts (100k base /
300k big, on 8 P100 GPUs), optimizer schedule (Adam, 4000 warmup steps), and
regularization (dropout 0.1, label smoothing 0.1). Reported BLEU averages the last
5 (base) / 20 (big) checkpoints, with beam 4 and length penalty 0.6. No seeds,
repeated trials, or confidence intervals — single-run results; expect variance.
(Work: 1706.03762)
```

Extraction caveats are about the extraction, separate from scientific Limits.

```text
BAD (scope limit and extraction damage conflated under Limits):
The model is only evaluated on translation and parsing, and the scaling factor formula is garbled.
GOOD (Limits = scope; Extraction caveats = this file):
## Limits
Evidence is machine translation (WMT 2014 EN-DE/EN-FR) and English constituency parsing;
do not generalize to non-text modalities or much longer sequences without further evidence.
(Work: 1706.03762)
## Extraction caveats
The scaling-factor formula `1/sqrt(d_k)` is malformed in extraction (rendered as
`1dk1...\frac{1}{\sqrt{d_k}}`); the equations generally carry raw LaTeX/subscript noise —
verify any formula against the PDF before formal reuse.
```

## Answer page

```markdown
---
title: "..."
page_type: answer
work_ids: [id-1, id-2]
---

# ...

## Short answer

One scannable paragraph: the thesis and the load-bearing reason, with the key
conclusion in bold and its grounding marker. A reader who stops here should have
the answer.

## Evidence

Dense per-source bullets, each leading with the work and carrying its specifics
plus its own caveat — what this source shows and where it is weak.

- `id-1`: <specific finding with numbers/metric>; <its caveat or boundary>. (Work: id-1)
- `id-2`: <specific finding>; <its caveat>. (Work: id-2)

## Synthesis

The developed narrative: with multiple works, how they relate, agree, or pull
apart and the non-obvious connection; with one work, the implication and
boundary the evidence supports. Use `(Work: ...)` for direct evidence and
`(synthesis across Works: ...)` for a cross-work inference.

## Limits and gaps

What the wiki does not yet support, and what source or evidence would change the
answer.
```

Short answer is a standalone thesis; Evidence is per-source and specific.

```text
BAD (thesis and evidence fused, no scannable top):
The sources suggest attention weights tell you something but maybe not why, for example
one study found weak correlation with gradient importance and another re-ran the
adversarial test with training, so overall it depends on what counts as an explanation...

GOOD (Short answer up front, then dense per-source Evidence):
## Short answer
Attention weights are informative summaries of model behavior, but the wiki does **not**
support reading them as faithful explanations by default — the works disagree over what
test would establish faithfulness, not just over the verdict. (synthesis across
Works: 1902.10186, 1908.04626)
## Evidence
- `1902.10186`: across BiLSTM text-classification and QA tasks, attention weights
  correlate only weakly with gradient and leave-one-out importance, and per-instance
  adversarial attention distributions leave predictions largely unchanged; single-head
  BiLSTM attention, not Transformer self-attention. (Work: 1902.10186)
- `1908.04626`: adversarial attention trained as a model-wide component (not found per
  instance) underperforms learned attention; proposes uniform-weight and seed-variance
  baselines; same task family, so the disagreement is over the test's design. (Work: 1908.04626)
```

## Synthesis page

```markdown
---
title: "..."
page_type: synthesis
work_ids: [id-1, id-2]
---

# ...

## Thesis

A contestable cross-work claim with a `(synthesis across Works: id-1, id-2)`
marker.

## Counter-evidence

The strongest work, condition, or result that weakens the thesis.

## Delta

What this page adds beyond the individual source pages.

## Evidence            <!-- optional; use when >=3 claims benefit; omit on short pages -->

| Claim | Works | Role | Limit |
|---|---|---|---|
| <one-line claim> | `id-1`, `id-2` | support / boundary / contradiction / context | <where it breaks> |

## Claim status        <!-- optional; one line, omit on short pages -->

Grounded: ... · Mixed: ... · Speculative: ... · Unresolved: ...

## Tensions

Preserve unresolved disagreements.

## Supporting works

- Title for id-1 — `id-1`
- Title for id-2 — `id-2`
```

The `## Evidence` and `## Claim status` blocks are optional. Use them when at
least three claims benefit from a scannable map; omit them on short pages or
when the prose already carries the grounding. They are presentation, not a
requirement — never add the table just to fill the section.

## Concept page

```markdown
---
title: "..."
page_type: concept
work_ids: [id-1, id-2]
---

# ...

## Definition

Define the mechanism, method, problem, or construct.

## Why it matters

Explain why the concept recurs across works.

## Evidence and limits

Summarize direct support with `(Works: ...)`; mark inferred relations as
`(synthesis across Works: ...)`.

## Evidence            <!-- optional; use when >=3 claims benefit; omit on short pages -->

| Claim | Works | Role | Limit |
|---|---|---|---|
| <one-line claim> | `id-1`, `id-2` | support / boundary | <where it breaks> |

## Claim status        <!-- optional; one line, omit on short pages -->

Grounded: ... · Mixed: ... · Speculative: ... · Unresolved: ...

## Supporting works

- Title for id-1 — `id-1`
- Title for id-2 — `id-2`
```

## Entity page

```markdown
---
title: "..."
page_type: entity
work_ids: [id-1, id-2]
---

# ...

## Identity

Name the model, dataset, benchmark, system, person, or organization.

## Role in the wiki

Explain what this entity enables or changes.

## Evidence and limits

Use `(Works: ...)` for directly grounded claims and `(synthesis across Works:
...)` for inferred relations.

## Supporting works

- Title for id-1 — `id-1`
- Title for id-2 — `id-2`
```

## Hub page

A hub is a navigation surface for the human reader, not an evidence page. Create
one only when a cluster of durable pages genuinely benefits from a reading
guide; it carries no primary claims and needs no `(Work: ...)` markers.

```markdown
---
title: "..."
page_type: hub
---

# ...

## What to read first

Guide the human reader through existing pages only.

## Reading path

An ordered route through existing pages.

## Main themes

A thematic map of why the pages group together.

## Open threads

Questions to revisit.
```

## No-op format

When an operation should not write, say so and say what would change it:

```text
NO_OP: <reason, and what would change the decision>
```
