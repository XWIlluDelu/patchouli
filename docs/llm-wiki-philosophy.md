# The philosophy of an agent-built wiki

The design rationale for Patchouli. This is philosophy, not a changelog — where a
principle and the code disagree, that is a bug in one of them, to be reconciled
rather than narrated.

## How to read this document

The document is organized by *provenance*, because the strength of a claim
depends on where it comes from, and the earlier versions of this file blurred
that. Three layers, in descending order of how much weight they can bear:

- **Part I — Imported foundations.** What we take from the literature: the
  reframe, the model-capability thesis, the single forward pass, the two failure
  modes (gating on a proxy, polluting the context). Each names its source and
  its boundary — including where we apply a result *by analogy* rather than on
  its own terms. This layer is load-bearing.
- **Part II — Our requirements.** The engineering decisions those foundations
  and the product goal dictate: the asset/logistics split, one undivided pass,
  the objective floor, the first-class no-op, the contracts. These are *our*
  choices, not imported truths; they are testable against the code, and a reader
  who disputes one is disputing a decision, not a citation.
- **Part III — Our experience.** One in-house comparison from the predecessor
  eval. It is the weakest evidence here and is treated as such: it *illustrates*
  the foundations, it does not establish them.

**Part IV** distills the whole into named principles PR1–PR10, each tagged with
the foundation and requirement it rests on; those labels are the *why* behind
every contract in `AGENTS.md` and every script in `scripts/`. **Part V** states
what is well-supported and what is not.

## The thesis

An LLM wiki is a persistent, compounding artifact, not a query-time retrieval
system: knowledge is compiled once at ingest and kept current by refresh and
maintenance, and the wiki gets richer with every source added and every question
asked (the reframe is Karpathy's [1]; I.1). This inverts the usual engineering
problem. In ordinary software the code is the asset and the data is passive;
here the *wiki* is the asset, and everything around it — the scripts, the
contracts, the templates — is replaceable logistics. The two are not the same
kind of thing, and the discipline applies differently to each. That asymmetry is
the root of every requirement in Part II.

---

# Part I — Imported foundations

## I.1 The wiki as a compounding artifact (Karpathy)

The foundational reframe is Karpathy's [1]: the wiki is a structured,
interlinked collection of markdown files that sits between the human and the raw
sources, compiled once and kept current, not re-derived per query. Karpathy's
metaphor fixes the roles: Obsidian is the IDE, the LLM is the programmer, the
wiki is the codebase [1]. The human is not the programmer; the human is the
product owner — sourcing, exploring, asking — and the agent does the grunt work
of reading, summarizing, cross-referencing, and filing. This is not a chatbot
with file access; it is a long-running research librarian.

**Boundary.** This is a design vision, not an empirical result. We adopt its
framing and test it by building, not because it has been measured.

## I.2 Capability lives in the model; orchestration depreciates (Anthropic, Sutton, Lincoln)

Capability lives in the model; the surrounding methodology only arranges the
conditions under which it operates [2]. Elaborate scaffolding around a model is,
more often than engineers trained on the older paradigm admit, a way of
consuming the model's own capacity while maintaining the illusion that the
scaffolding is the source of the system's intelligence [2]. Every tool, step,
and custom format is a tax on the model's effectiveness and must pay that tax
with a larger gain or be removed. Over a longer horizon the bitter lesson
applies [3]: general methods that scale with compute defeat hand-engineered
domain knowledge, and by extension hand-built orchestration around a model tends
to lose to better models running with less of it, on a shelf life measured in
months [4].

**Boundary.** Sutton [3] is a claim about compute-scaled *learning* beating
hand-engineered knowledge over decades; Lincoln [4] is a blog extrapolation of
it to agent orchestration. The strong form — "all orchestration decays" — is
directional, not a theorem. We use it to bias toward thin, replaceable logistics
and thick durable invariants, not as a proof that any given script is doomed.

## I.3 The single forward pass, and when a loop is actually needed (Vaswani, Anthropic)

A single forward pass maps the whole context to output in one conditioned
computation: attention ranges over the entire context and tokens are emitted
against the result [9]. The cost an anti-multi-turn instinct is reaching for is
paid when a *harness fragments one cognitive operation into several API calls
joined by lossy serialization* [2]: one continuous reasoning process becomes two
truncated ones, each rebuilt from a compressed summary of the last. An agent
reading the files it chooses to read is *not* that — it is the model directing
its own attention-gathering inside one continuous session, which is what these
runtimes are built to do well. A genuine agentic loop earns its place only when
the action space cannot be loaded into static context — when the next action
depends on observing the consequences of the last in an environment [2].

**Boundary.** This bounds when a loop is *necessary* by the structure of the
task, not by a measured survey of tasks. It is an architectural argument; Part V
flags it as such.

## I.4 Gating on a proxy degrades substance (Goodhart/Gao, Krakovna, Tam, Anthropic, yAI)

When a checkable proxy is made the target, optimizing it costs the true
objective. This is Goodhart's law, and it is not folklore here: it is formalized
for RLHF as reward-model overoptimization, where pushing on an imperfect proxy
reward past a point measurably lowers ground-truth performance [10], and it is
named for agents as *specification gaming* — behaviour that satisfies the literal
specification of an objective without achieving the intended outcome [12].
Constraining generation toward a *required structure* shows the same signature
directly: reasoning quality drops under format restrictions, and drops further as
the restriction tightens [11]. The design response follows: turn subjective
quality into gradable criteria at *design* time rather than gate on it at run
time [5], because an agent cannot self-certify subjective quality at run time
without spending its authoring budget on self-validation [6].

**Boundary — read this carefully, it is where the rigor lives.** [10] and [12]
describe *training-time and search-time* optimization; applying them to an
*inference-time* finish-gate inside one generation is an **analogy** — the
mechanism (a proxy made into a target is optimized at the expense of the
objective) transfers, the setting differs. [11] is directly about inference-time
output constraints and is the most on-point, but it is *contested* by later work
on constrained decoding; it is cited as directional, not decisive. [6] is a
blog. No single one of these carries the claim. What carries it is their
*convergence*: a named principle, a formal result, an independent RL-agent
framing, an on-point (if disputed) empirical study, and Anthropic's own harness
guidance all point the same way.

## I.5 Context is a finite budget; off-target context degrades output (Anthropic, Shi, Cuconasu, Liu)

Context is a finite attention budget, and quality degrades as that budget fills
with lower-signal material — context rot [8]. The effect is measured: irrelevant
context in the prompt sharply lowers reasoning accuracy [13]; and the sharper,
less obvious finding is that documents which are *related but not relevant* do
more damage than plainly unrelated ones [14] — which is precisely what a thin or
near-duplicate page is to a later read. Even genuinely relevant context is not
used uniformly: models underuse the middle of long inputs and degrade as the
input grows, so adding more retrieved material is not free [15].

**Boundary.** [14] The Power of Noise's headline result is that *random* noise
can sometimes help RAG; we use only its robust, specific finding that
related-but-irrelevant material is the most harmful kind, the direct analogue of
a near-duplicate wiki page — not a general "noise is bad" claim. [15] is about
position and length, not pollution; we use it only for "more context is not
free."

---

# Part II — Our requirements

These are *our* engineering decisions. Each is derived from the foundations
above and is answerable to the code, not to a citation.

## II.1 Split the logistics into durable and replaceable

From the thesis and I.2. The logistics are not uniform. Some parts are durable:
the file topology, the page roles, the evidence conventions (`(Work:)` markers,
`## Supporting works`, `work_id`/`version_id`, the verbatim-quote rule), and the
objective-invariant checks in `check_wiki.py`. These describe what a correct
page *is*, so they outlive any particular runtime. Other parts are replaceable:
prompt wording, the extraction and discovery scripts — the parts that encode
assumptions about today's tools. The common error is to pour effort into the
replaceable machinery and under-invest in the durable structure. Invest in the
wiki's structure and its invariants; expect to replace the rest.

## II.2 Author in one undivided pass; forbid the two fragmenters

From I.3 and I.4. Each contract is one authoring pass: the agent reads the
filesystem for context, decides, and writes. Two things fragment such a pass,
and Patchouli forbids both. A *harness-imposed multi-call pipeline* — the
program-that-calls-a-model shape — is gone by construction, because there is no
program making the calls; the coding agent the user starts is the runtime, and
it makes no model API calls of its own. An *interpretive finish-gate* — a loop
that makes the model satisfy a quality check before it may stop, on a step
budget — is forbidden by contract, because it is exactly the proxy-gating of I.4
turned into a control-flow loop. The only loop after a write is the
deterministic correction on the objective floor (II.3), which is not a quality
judgment.

## II.3 Verify objective invariants outside the pass; never gate on interpretive form

From I.4. Verification is owed, but of one kind and in one place. The right kind
is *objective invariants only*: work-ids resolve to source pages, verbatim
quotes match the reading surface, internal links resolve, page types match their
directories, provenance is present, a source page's `version_id` matches its
surface. These are deterministic and depend on no judgment, so checking them
cannot deform the output — there is no proxy to deform toward. This is
`check_wiki.py`, the binding floor: it runs after every write and a failure is
fixed and re-checked until it passes, which is the model correcting an objective
error it can see, not a gate on quality. The wrong kind is *interpretive form* —
integration depth, relation-label fluency, citation density, narrative
completeness. A run-time gate on these either blocks good work or deforms it
toward the proxy (I.4). They are improved at *design* time [5] and reported, never
enforced, by `lint.py`.

Two refinements keep this from collapsing into carelessness. "No gates" means no
gate on *interpretive form*; objective verification stays, and is where
investment compounds. And one undivided pass is not an *unprepared* pass — the
agent still reads the relevant wiki before it writes; what is removed is the
harness standing in the middle of the reading, not the reading.

## II.4 The no-op is a first-class output; selectivity is architectural

From I.4 and I.5. A wiki that grows only when growth is justified compounds; one
that grows on every operation pollutes itself (II.5). So the no-op is a
first-class output: the model is trusted to refuse to write and required to say
what would change the refusal. This is enforced by *architecture*, not
exhortation. Ingest never auto-creates durable pages. Targeted synthesis requires
an explicit request and at least two genuinely relating works (the floor binds
the two-work minimum). Organize discovers durable boundaries and is expected to
decline most candidates. Search records a discovery attempt without touching the
wiki at all.

## II.5 The wiki is its own future context

From I.5. In most systems context engineering happens once per call. In an LLM
wiki the wiki *is* the curated context for every future operation: every ingest
curates the context for the next ask, every synthesis becomes an artifact the
next one builds on, every concept page becomes a neighbor future ingests link
to. So the system's output becomes its own input. The cost of a weak page is not
paid once — it is paid every time it is retrieved into a later context, where it
acts as exactly the related-but-off-target distractor I.5 identifies as the most
harmful kind. This is the mechanism that makes selectivity (II.4) compound and
pollution compound, and it is why the wiki is capital while the logistics
depreciate.

## II.6 Contracts are the surface; scripts are the floor

The human-facing surface is the contracts — ingest, search, ask, synthesize,
organize, maintain, and polish — matched to natural language by the routing
table in `AGENTS.md`. The scripts are deliberately *not* an orchestration layer.
`extract.py` turns a source into a clean reading surface and prints its
provenance; `search.py` discovers candidates into `searches/` and touches
nothing in the wiki; `check_wiki.py` is the objective floor; `indexes.py`
rebuilds navigation; `lint.py` advises; `commit.py` confines each contract's
commit to its exact files. None of them retrieves wiki context for the model or
decides what a page should say — that is the agent's, by reading and judging.
Retrieval is *not* on the mechanical side: deciding what to read and what is
relevant is judgment, and the inversion (a methodology directing an agent, not a
program calling a model) is what lets the agent do it by reading the filesystem
natively, within one session (I.3).

## II.7 The human leaves the generation path but stays in the research agenda

From I.1. The human's irreducible roles are sourcing, exploration, and asking —
product-owner decisions that cannot be delegated without delegating the research
agenda itself. The reducible roles are review, curation, and run-time quality
judgment. We take the human off that critical path not by skipping quality but by
replacing it with mechanisms that do not compete with generation: objective
invariants checked after the write (II.3), selectivity via the first-class no-op
(II.4), and subjective quality tuned at design time (I.4). When the user actually
uses the wiki, no judge runs.

---

# Part III — Our experience

One comparison, from the A/P-series arms of the predecessor eval (a
*program-that-calls-a-model* design that Patchouli inverts). Two observations,
both *consistent with* Part I and neither *establishing* it:

- An arm whose loop made the model prove structural compliance before it could
  stop produced more truncated, aggregated synthesis and citation clutter than
  an arm that kept the same conventions advisory and let the model write in one
  pass. This is the signature I.4 predicts.
- Given the same organize command, a selective arm declined most boundaries and
  produced far fewer durable pages than auto-promoting arms, with no human making
  the difference — the selectivity II.4 builds in, arising on its own. The
  cost of the auto-promoted pages is the pollution I.5 describes.

**How much this proves: very little, and it is cited accordingly.** It is a
single, uncontrolled, in-house run in a separate project, confounded by every
difference between the arms, scored by one eval whose rubric is not reproduced
here. It *illustrates* the imported principles; it is not independent evidence
for them. Everywhere the document leans on those principles, the weight is
carried by Part I, and this experience is named only as a consistent instance.
If a future controlled comparison contradicts a principle, the principle
governs and the arm observation is discarded, not the reverse.

---

# Part IV — Named principles (PR1–PR10)

The distilled foundation for future discussion. Each principle carries the
foundation it imports and the requirement it drives, so its provenance is legible
at a glance.

**PR1 — The wiki is the user's asset; the logistics are replaceable.** Inside
the logistics, schema and objective checks are durable; prompts and scripts are
depreciating capital. *(Foundations I.1, I.2; requirement II.1.)*

**PR2 — Capability lives in the model; the methodology arranges conditions.**
Elaborate scaffolding is taxation on the model; demand each piece pay its tax
with structural gain. *(Foundation I.2; requirements II.1, II.6.)*

**PR3 — Trust the model with judgment; absorb the *deterministic* into scripts.**
The model writes, synthesizes, decides relevance, and retrieves by reading; the
scripts extract, verify, resolve, and index. Mechanical-compliance work inside
the authoring budget deforms judgment toward proxies. *(Foundations I.3, I.4;
requirements II.2, II.6.)*

**PR4 — Author in one undivided pass; add a loop only when the task needs
environmental observation.** The two fragmenters — a harness multi-call pipeline
and an interpretive finish-gate — are both absent by construction. *(Foundation
I.3; requirement II.2.)*

**PR5 — Verify objective invariants outside the pass; never gate on interpretive
form.** Work-ids, quotes, links, page types, provenance: checked after,
corrected, re-checked. Integration depth, citation density: improved at design
time, never gated at run time. *(Foundation I.4; requirement II.3.)*

**PR6 — The no-op is a first-class output; selectivity compounds.** A wiki that
grows only when justified compounds; trust the model to refuse and require it to
say what would change the refusal. *(Foundations I.4, I.5; requirement II.4.)*

**PR7 — The wiki is its own future context; every page added changes every
future operation.** The output becomes the input; a weak page is a distractor
charged against every later read. *(Foundation I.5; requirement II.5.)*

**PR8 — Expose operations; keep the scripts to the floor.** The surface is the
contracts; the scripts do the deterministic work and do not orchestrate or
retrieve. *(Foundation I.2; requirement II.6.)*

**PR9 — The human leaves the generation critical path but stays in the research
agenda.** The human decides what to ingest and what to ask; objective invariants
and selectivity are automatic. *(Foundation I.1; requirement II.7.)*

**PR10 — Verification is where investment compounds; orchestration is where it
decays.** Build verification thick (objective, deterministic, grounded in the
world) and orchestration thin. If scaffolding grows faster on the orchestration
side than the verification side, the system is being built backward.
*(Foundations I.2, I.4; requirements II.3, II.6.)*

---

# Part V — Confidence and self-audit

## What is well-supported and what is not

The **structural argument** — wiki as asset and logistics as depreciating
capital (I.1, I.2, II.1), one undivided pass with objective verification outside
it (I.3, I.4, II.2, II.3), and selectivity because the wiki is its own future
context (I.5, II.4, II.5) — is well-supported by the imported foundations, which
are peer-reviewed or first-party engineering sources.

Two honest weak points, stated plainly:

- **The proxy-gating claim (I.4) rests on analogy and on a contested study.** The
  formal results [10, 12] are about training/search-time optimization, not
  inference-time gating; the on-point empirical study [11] is disputed. The claim
  should be read as *"we follow the established design principle that gating on a
  proxy degrades substance,"* not as *"this is proven for a single-generation
  finish-gate."* Its strength is convergence, not any one source.
- **The "wiki operations almost never need an agentic loop" claim (I.3) is
  structural, not measured.** It is stated as a default with an explicit escape
  clause — an operation whose next action genuinely depends on observing the last
  would narrow it — not as a law.

The **A/P-series arm experience (Part III) is the weakest evidence in this
document and does not bear weight anywhere.** It illustrates; it does not
establish.

## Self-audit

The same checklist the design is meant to pass:

- One undivided authoring pass per contract, the agent reading the filesystem for
  context (PR3, PR4)? Yes — each contract is a read-decide-write pass.
- Objective invariants verified outside the pass, advisory on the rest, never
  gating on form (PR5, PR10)? Yes — `check_wiki.py` binds, `lint.py` advises.
- The no-op first-class, the model trusted to refuse (PR6)? Yes — every
  judgment-bearing authoring contract carries it; search records discovery
  without changing the wiki.
- A selective wiki, not auto-promotion (PR6, PR7)? Ingest never promotes;
  targeted synthesis and selective organize are the only durable-page paths.
- The human in sourcing and asking, out of the generation path (PR9)? Yes.
- Logistics thin on orchestration, thick on objective verification (PR10)? The
  scripts are extraction, discovery, scoped commits, the floor, and indexes —
  there is no orchestration layer.

A "no" on any line is a named reason to reconsider, not a vague worry.

---

## Sources

Ordered by first appearance. On authority: [1]–[3], [5], [8]–[15] are
first-party engineering writing or peer-reviewed / archived research and are the
load-bearing tier; [4], [6], [7] are independent blog commentary that
corroborates but that no conclusion rests on alone; [11] is peer-reviewed but its
result is actively contested, and is used as directional only.

- [1] Karpathy, Andrej, "LLM Wiki" (2026).
  <https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f>. The
  reframe: wiki as compounding artifact; Obsidian as IDE, LLM as programmer, wiki
  as codebase; the human as product owner.
- [2] Anthropic engineering, "Building Effective Agents," "Effective Context
  Engineering for AI Agents," "Writing Tools for AI Agents," and "Building Agents
  with the Claude Agent SDK." Capability lives in the model; the cost of
  fragmenting reasoning across serialized turns; when an agentic loop is
  warranted.
- [3] Sutton, Richard, "The Bitter Lesson" (2019).
  <http://www.incompleteideas.net/IncIdeas/BitterLesson.html>. General methods
  that scale with compute defeat hand-engineered domain knowledge.
- [4] Lincoln, Logan, "The Bitter Lesson Kills Your Orchestration Layer" (2025).
  <https://loganlincoln.com/blog/bitter-lesson-kills-your-orchestration-layer>.
  Orchestration as depreciating capital with a months-long shelf life. Blog
  extrapolation of [3].
- [5] Anthropic, "Harness design for long-running application development"
  (2026).
  <https://www.anthropic.com/engineering/harness-design-long-running-apps>. The
  generator-evaluator pattern; turning subjective judgment into gradable criteria
  at design time.
- [6] yAI, "The Verification Paradox: Why Agents Cannot Automatically Validate
  Themselves."
  <https://yaihq.com/research/verification-paradox-agents-cannot-validate-themselves>.
  Why subjective quality cannot be self-certified by the agent at run time.
- [7] Agent Hypervisor, "The Bitter Lesson of Agentic Coding."
  <https://agent-hypervisor.ai/posts/bitter-lesson-of-agentic-coding/>. "Thin on
  orchestration and thick on verification and memory."
- [8] Anthropic, "Effective Context Engineering for AI Agents" (2025).
  <https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents>.
  Context as a finite attention budget; context rot.
- [9] Vaswani et al., "Attention Is All You Need" (2017).
  <https://arxiv.org/abs/1706.03762>. The forward pass: attention conditions on
  the whole context in one mapping from context to output.
- [10] Gao, Leo, John Schulman, and Jacob Hilton, "Scaling Laws for Reward Model
  Overoptimization" (2022). <https://arxiv.org/abs/2210.10760>. Goodhart's law
  formalized: optimizing an imperfect proxy reward past a point degrades
  ground-truth performance.
- [11] Tam, Zhi Rui, et al., "Let Me Speak Freely? A Study on the Impact of
  Format Restrictions on Performance of Large Language Models," EMNLP 2024
  Industry Track. <https://arxiv.org/abs/2408.02442>. Format restrictions
  measurably reduce reasoning quality; stricter restrictions, larger drops.
  *Contested by later constrained-decoding work; cited as directional.*
- [12] Krakovna, Victoria, et al., "Specification gaming: the flip side of AI
  ingenuity," DeepMind (2020).
  <https://deepmind.google/blog/specification-gaming-the-flip-side-of-ai-ingenuity/>.
  Behaviour that satisfies the literal specification of an objective without the
  intended outcome.
- [13] Shi, Freda, et al., "Large Language Models Can Be Easily Distracted by
  Irrelevant Context," ICML 2023. <https://arxiv.org/abs/2302.00093>. Irrelevant
  context in the prompt sharply degrades reasoning accuracy.
- [14] Cuconasu, Florin, et al., "The Power of Noise: Redefining Retrieval for RAG
  Systems" (2024). <https://arxiv.org/abs/2401.14887>. Related-but-irrelevant
  documents harm RAG accuracy more than plainly unrelated ones.
- [15] Liu, Nelson F., et al., "Lost in the Middle: How Language Models Use Long
  Contexts" (2023). <https://arxiv.org/abs/2307.03172>. Relevant information is
  used unevenly by position, and performance falls as the context grows — more
  context is not free.

The principles are a synthesis from these sources, illustrated by the A/P-series
arm evidence in the LLM Wiki Iterate eval project (Part III); the comparative
analysis that produced them lives there, not in this product. They are the
foundation for iteration, to be revised when evidence contradicts them.
