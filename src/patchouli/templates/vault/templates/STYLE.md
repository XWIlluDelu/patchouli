# What good pages look like

The templates give skeletons; this file shows the quality to aim for. Copy the GOOD
shape, avoid the BAD one. Sections are there to help: omit one that has nothing to
say, add one the knowledge needs. A taste changes emphasis, never these basics.

## Markup: plain Markdown, evidence in footnotes

Pages are read by people. Keep the prose clean and put the evidence apparatus in
footnotes, as in a good paper. Every page sits at `wiki/<kind>/<slug>.md`, so the same
relative paths work from any page:

| what | how |
|---|---|
| link to a page | `[Self-attention](../concepts/self-attention.md)` |
| typed relation | a list item opening with a label and a colon, read "this page — label — target": `- Contradicts: [Attention is explanation](../concepts/attention-is-explanation.md) — on long inputs` |
| cite lines of a source | `[jain2019 L88–95](../../text/jain2019.md#L88-L95)` — the anchor is what counts; `search` and `read -l` print the link ready to paste |
| cite the original, for what the reading text lacks (a figure, a table, a page) | `[jain2019 fig. 2](../../raw/jain2019.pdf#page=4)` |
| a claim's evidence | end the claim with `[^1]`; define `[^1]:` at the bottom of the page |
| a source's own finding | footnote with just the citation: `[^1]: [jain2019 L88–95](../../text/jain2019.md#L88-L95)` |
| your interpretation | `[^2]: Interpretation (moderate) — [vaswani2017 L230–244](../../text/vaswani2017.md#L230-L244); untested at long lengths.` |
| a cross-source judgment | `[^3]: Judgment (low) — from [jain2019](../sources/jain2019.md) and [wiegreffe2019](../sources/wiegreffe2019.md); only BiLSTM classifiers studied.` |

Certainty is one of **high · moderate · low · speculative** and must match the evidence and
the reasoning; for low/speculative, say in the footnote what it rests on and what would
undercut it. Relation labels are free — pick the most precise one (Extends, Refines,
Applies, Defines, Answers, Supersedes…); `Contradicts` also feeds the index's Tensions.
`patchouli sync` fixes wrong relative paths when the target is known, so get the slug
right and don't fuss over `../`.

Not every sentence needs a footnote: give one to each claim someone might want to check
or build on. Labels are unique per page: when extending a page, take the next free number.

---

## Source page — one material, faithfully

**What this source is** — one paragraph a reader can stop after: kind of material,
the problem it addresses, its main move. **Key claims** — what *this* work
establishes (results it merely cites are context), one claim per bullet, specific
enough to check, with conditions and a footnote to the lines. **Method and evidence** —
connected prose walking the actual design: setup, comparison, metric, key parameters,
which evidence backs which claim, closing with one line on the kind and strength of the
evidence. **Conditions and limits** — scientific scope: where the findings do not reach.
**Interpretation** — your reading, with Interpretation footnotes. **Connections** — typed
links to concepts and other sources.

Add when they apply: **Reproducibility** (what a replicator gets and lacks) ·
**Tensions** (conflict with other ingested works) · **Open questions** ·
**Extraction caveats** (damage in *this* extraction — kept apart from scientific
limits) · **Revision notes** (dated, what changed and why).

Claims — itemized, specific, conditioned:

```text
BAD:
The Transformer works well and trains faster than RNNs.[^1]

GOOD:
- On WMT 2014 En→De the big Transformer reaches 28.4 BLEU, more than 2 BLEU above the
  best prior models including ensembles, after 3.5 days on 8 P100 GPUs.[^1]
- Self-attention connects any two positions in O(1) sequential steps, against O(n)
  for recurrent layers, at O(n²·d) cost per layer.[^2]

[^1]: [vaswani2017 L412–420](../../text/vaswani2017.md#L412-L420)
[^2]: [vaswani2017 L230–244](../../text/vaswani2017.md#L230-L244)
```

Method — prose, not a bullet dump:

```text
BAD:
- Benchmark: WMT 2014. Evidence: experiment.
- Baselines: RNN/CNN. Evidence: experiment.

GOOD:
The authors train on WMT 2014 En→De (4.5M sentence pairs, ~37k shared BPE vocabulary)
and En→Fr (36M pairs), against the strongest recurrent and convolutional
encoder–decoders of the time. The base model has 6 layers, d_model = 512 and 8 heads;
BLEU on newstest2014 is the metric, with training cost in GPU-days. The headline numbers
come from tables, averaged over the last checkpoints.[^3]
```

The evidence line closing the method — scannable, not an adjective:

```text
BAD:  Strong evidence.
GOOD: Experiment — two translation benchmarks with tabulated BLEU and cost comparisons,
      plus one parsing transfer check; single runs, no variance reported.
```

Limits vs extraction caveats — keep them apart:

```text
## Conditions and limits
Evidence covers text translation and English constituency parsing at sequence lengths
typical of those tasks; nothing here speaks to much longer inputs or other modalities.

## Extraction caveats
The scaled dot-product formula is garbled in the reading text (line 236); check the PDF
before reusing any equation.
```

Interpretation — visible reasoning, honest certainty:

```text
BAD:  This is clearly the future of NLP.
GOOD: - The O(n²) attention cost is the likely bottleneck for long documents, since every
        reported gain is at short lengths.[^4]

      [^4]: Interpretation (moderate) — [vaswani2017 L230–244](../../text/vaswani2017.md#L230-L244);
          no experiment here tests long inputs.
```

## Concept page — something that recurs across materials

An idea, method, problem or construct — or a named thing: a model, dataset, benchmark,
person. **What it is** (and how definitions differ across sources; for a named thing: kind,
version, who made it) · **Why it matters** for the research goals · **Variants across
sources** · **Evidence and limits** — what is known, under which conditions, how strong ·
**Relations**, typed · **Open questions**. A page earns its place by what the sources say
about the thing, not by the thing existing: no encyclopedia stubs.

```text
BAD (a pile of per-paper summaries):
Paper A uses attention. Paper B also uses attention. Paper C studies attention.

GOOD (organized by what the sources jointly show, and honest about how many measured it):
- Attention weights correlate only weakly with gradient-based importance on text
  classifiers. One study measured this; the other accepted the result rather than
  re-measuring it, so it rests on a single measurement.[^1]
- The studies disagree on what a different experiment shows about explanation, not on
  that correlation: B trains its adversaries, A searches for them per instance.[^2] See
  [the attention-as-explanation debate](../syntheses/attention-as-explanation-debate.md).

[^1]: [jain2019 L88–95](../../text/jain2019.md#L88-L95); acceptance in [wiegreffe2019 L120–131](../../text/wiegreffe2019.md#L120-L131)
[^2]: Judgment (moderate) — from [jain2019](../sources/jain2019.md) and [wiegreffe2019](../sources/wiegreffe2019.md).
```

## Synthesis page — understanding across sources

**Question and thesis** — the precise question and one contestable answer, saying what
it adds beyond the individual pages · **Sources compared** — a table when it helps
(question · assumptions · method/data · key result · conditions) · **Agreement and
divergence** — where they agree (and whether those sources are independent), where they
part and why (different questions, assumptions, designs, data, metrics), and the
conditions under which each conclusion holds · **Counter-evidence** — the strongest case
against the thesis · **Judgment**, with Judgment footnotes · **Open questions**.

```text
BAD (catalogue):
A says X. B says Y. C says Z. Overall the results are mixed.

GOOD (one argument):
## Question and thesis
Are attention weights faithful explanations? Not by default: the disagreement is about
the test of faithfulness, and under the stricter test (trained adversaries) attention
does carry model-specific information.[^1]

## Agreement and divergence
A's per-instance adversaries show that alternative weights *exist*;[^2] B's trained
adversaries show they are not what the model *learns*[^3] — different questions, both
answered correctly.
```

## Answer page — a question worth keeping

**Question** (as asked, plus clarified scope) · **Short answer** — a standalone thesis
with its certainty · **Evidence** — what the answer rests on, organized by the argument,
each piece with its specifics and caveat ·
**Reasoning** — how the evidence leads to the answer, and when it would flip · **Limits
and gaps** — what the wiki can't yet support and what would change the answer.
`status: open` for important questions not yet answerable.

```text
BAD (thesis buried in a paragraph of hedges):
The sources suggest that it may depend on what one means by explanation, for example...

GOOD:
## Short answer
Attention weights summarize model behavior but are **not** faithful explanations by
default; the sources disagree on the test, not the data.[^1]

## Evidence
- jain2019: weak correlation with gradient importance on BiLSTM classifiers; single-head
  recurrent attention, not Transformer self-attention.[^2]
```

## Hub page — navigation only

What to read first · a reading path · themes · open threads. Hubs carry no primary
claims.

## Quotes

Quote only when the exact wording carries evidence. Put the citation inside the quote or
on the line right after it; the wording is checked against the reading text. A short
inline quote is checked when its citation link follows it directly —
`they call it "a fundamentally different test" ([wiegreffe2019 L45](…#L45))` — so quoting
a title or a term elsewhere is fine.

```text
> the special crossref field tells BibTeX that the no-gnats entry should inherit any
> fields it's missing from the entry it cross references

— [patashnik1988 L88–90](../../text/patashnik1988.md#L88-L90)
```

## Revision notes

On any page, after a substantive change (it also flags the pages that build on this
one for re-checking; routine edits need no note). Re-checked a page and it still holds?
Set `reviewed: <date>` in its frontmatter instead of adding a note (re-reviewing on the
same day, add the time: `reviewed: 2026-11-20 15:30`):

```text
## Revision notes
- 2026-11-20: Narrowed the BLEU claim to En→De after re-reading Table 2 (lines 412–420);
  the En→Fr numbers were from a different model size.
```
