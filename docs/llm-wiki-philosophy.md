# The philosophy of an agent-built wiki

This document explains why Patchouli is shaped the way it is. It is philosophy,
not a changelog and not a theorem: some claims are imported from research or
first-party engineering reports, some are analogies, and some are explicit
product choices. Where a principle and observed reality disagree, the principle
or the code must change; the disagreement is not explained away.

## How to read this document

The argument is organized by provenance:

- **Part I — Imported foundations.** Design visions, empirical findings, and
  engineering lessons taken from outside Patchouli. Each states the boundary of
  the transfer, especially where the project applies a result by analogy.
- **Part II — Patchouli requirements.** Choices made for this product: the
  asset/logistics split, one coherent contract episode, the objective floor,
  first-class no-op, source evolution, and operation boundaries. These choices
  are answerable to the implementation rather than to citation authority.
- **Part III — Prior project experience.** One informal comparison from a
  predecessor project. It is useful as experience and carries little evidential
  weight.
- **Part IV — Named principles.** PR1–PR10, the compact vocabulary used to
  inspect contracts and code.
- **Part V — Confidence and self-audit.** What is strong, what remains an
  analogy, and what would make the design change.

## The thesis

An LLM wiki is a persistent, compounding artifact rather than a query-time
retrieval result. Sources are compiled once into maintained, interlinked
Markdown; supported questions may become durable answers; later operations build
on that compiled layer instead of reconstructing everything from raw material
[1]. Unsupported or redundant operations may no-op, so growth is selective
rather than automatic.

This repository is the framework. In a user's clone, `wiki/`, `extracted/`,
`notes/`, and Git history become the evolving research record. That record is
the asset. Scripts, prompts, parser choices, and host-agent integrations are
logistics around it. Some logistics encode durable invariants and deserve deep
investment; others are assumptions about today's tools and should remain easy to
replace.

---

# Part I — Imported foundations

## I.1 The wiki as a compounding artifact (Karpathy)

Karpathy's LLM Wiki framing places a structured, interlinked Markdown corpus
between the human and raw sources: Obsidian is the IDE, the LLM is the
programmer, and the wiki is the codebase [1]. The human remains product owner —
choosing sources, exploring, and asking — while the agent performs the recurring
work of reading, summarizing, cross-referencing, and filing.

**Boundary.** This is a product vision, not an empirical result. Patchouli adopts
its role assignment and tests the usefulness of the resulting artifact through
use.

## I.2 Capability lives in the model; scaffolding must pay its tax

The model supplies the judgment capability; a methodology arranges the
conditions under which that capability operates [2]. Every tool, intermediate
format, fixed stage, and special rule consumes attention, implementation effort,
or both. Patchouli therefore treats scaffolding as a tax that must buy a larger
structural benefit.

The longer-horizon bias comes from Sutton's bitter lesson: general methods that
scale with computation have repeatedly outlasted hand-engineered domain
machinery [3]. Applying that lesson to agent orchestration is an extrapolation,
not a theorem; Lincoln states the stronger version directly as orchestration
being depreciating capital [4]. Patchouli uses the extrapolation to keep
model-specific orchestration thin while investing in durable file semantics and
verification.

**Boundary.** This does not say that every workflow is harmful or that every
script will decay. It says that complexity begins with a burden of proof, and
that model-specific control flow should be easier to replace than the user's
knowledge.

## I.3 One coherent contract episode, not one API call

Patchouli's unit is semantic: one human request is routed to one contract and
completed in one coherent agent episode. It is **not** a count of model API
calls, tool turns, context continuations, or Transformer forward passes. A host
runtime may use many of those while preserving one continuous contract
execution. A Transformer forward pass is an internal model computation [7]; it
does not define the human–agent interface used here.

The fragmentation Patchouli resists occurs one level higher: a harness divides
one judgment-bearing operation into fixed stages connected by lossy serialized
handoffs [2]. An agent reading files, observing tool results, and deciding what
to inspect next inside the same episode is not fragmented in this sense. An
additional Patchouli-level stage earns its place when the task truly requires a
separate environmental observation or when observed use shows that the stage
pays for itself.

**Boundary.** This is an architectural default and an experiential bias. It says
nothing about the number of internal turns used by Codex, Claude Code, Pi, or
another host agent.

## I.4 Proxy optimization can displace the real objective

Goodhart-style failure is formalized in reward-model overoptimization: pushing
harder on an imperfect proxy eventually lowers ground-truth performance [8].
DeepMind describes the corresponding agent failure as specification gaming —
satisfying a literal objective without achieving the intended result [10]. An
inference-time study also reports degradation under output-format restrictions,
with stronger restrictions producing larger drops [9], while Anthropic's harness
guidance recommends turning subjective goals into useful development criteria
rather than relying on vague run-time self-certification [5].

Patchouli transfers this evidence cautiously. A run-time finish-gate inside one
contract is not the same setting as reward-model training or search. The
mechanism is an analogy: once an imperfect quality proxy becomes the target, the
model can spend its authoring budget satisfying the proxy instead of producing
the best knowledge artifact.

This is **not** an argument for zero structure. Patchouli deliberately imposes
page roles, provenance markers, canonical paths, and a few required sections.
Those constraints shape form and therefore also pay a tax. They are retained
because they encode durable external relationships — what work a page represents,
where its reading surface lives, whether a quote exists, whether a link resolves
— rather than pretending to measure integration depth or insight. The project
should remove a structural rule when its long-term value no longer pays for its
cost.

**Boundary.** The direct format-restriction evidence [9] is contested by later
work on constrained decoding, and the training/search results [8, 10] reach
inference-time authoring only by analogy. The conclusion is a design bias, not a
universal law.

## I.5 Context is finite; off-target context is not free

Anthropic describes context as a finite attention budget that degrades as it
fills with lower-signal material [6]. Irrelevant context can sharply lower
reasoning accuracy [11]; related-but-irrelevant documents can be more harmful
than plainly unrelated ones [12]; and even relevant information is used unevenly
as inputs grow, especially in the middle of long contexts [13].

A maintained wiki is unusual because today's output becomes tomorrow's candidate
context. A thin or near-duplicate page is therefore not merely a weak artifact;
when selected for a later operation it becomes a related distractor. This is the
reason selectivity and maintenance matter over time.

**Boundary.** A page that is never read does not consume a later context. The
claim is that every page changes the candidate context available to future
operations, not that every page affects every operation. The analogy from RAG
noise to wiki pollution is directional rather than exact.

---

# Part II — Patchouli requirements

## II.1 Separate the compounding asset from replaceable logistics

From the thesis and I.2. The user's compiled wiki and its history are the asset.
Inside the logistics, file topology, page roles, provenance conventions,
`work_id`/`version_id`, and objective checks are comparatively durable because
they define what a valid knowledge artifact is. Prompt wording, parser backends,
search providers, and runtime integrations encode assumptions about current
tools and should remain replaceable.

This is why the public repository can be an empty framework while each clone
becomes a distinct knowledge instance. The framework is valuable only insofar as
it helps the instance compound.

## II.2 Complete each contract in one coherent agent episode

From I.3 and I.4. The human-facing surface is one operation: ingest, search, ask,
synthesize, organize, maintain, or polish. Within that episode the host runtime
may loop, call models, read files, and use tools as needed. Patchouli itself does
not impose a fixed model-calling pipeline or require serialized intermediate
artifacts.

Two harness-level fragmenters remain excluded by default:

- a predetermined multi-stage pipeline that removes the agent's control over
  what to inspect and when;
- an interpretive finish-gate that blocks completion until a subjective proxy is
  satisfied.

The required post-write loop is different: deterministic failures from the
binding floor are corrected and rechecked. That loop repairs an observable
invariant rather than judging insight.

## II.3 Bind objective facts; advise on interpretive consequences

`check_wiki.py` enforces facts that can be determined without pretending to
judge scientific quality: work IDs resolve, source paths and versions match,
explicit quotes occur in their reading surfaces, internal links resolve, page
types match directories, and declared support is structurally consistent.

These checks can shape form — every schema does. Their distinction is not that
they are costless, but that they target durable external relationships rather
than approximate scores for narrative completeness, integration depth, citation
density, or originality. Interpretive quality remains the agent's judgment;
`lint.py` may surface heuristics but never blocks a write.

Source evolution has the same split. It is objective that a compiled source page
changed after another page was last revised. It is not objective that the
dependent page became wrong. `stale.py` therefore reports review candidates and
never enters the binding floor. The agent rereads the current support and either
revises the page or keeps it with a reason.

## II.4 Make no-op a first-class path

A wiki that grows only when a change is justified compounds more cleanly than
one that writes on every request. Patchouli therefore gives every
judgment-bearing contract an explicit no-op result and asks the agent to state
what would change the decision.

Operation boundaries make selectivity practical: ingest creates one source page
and never auto-promotes concepts; search records candidates without ingesting;
synthesize requires a genuine relation and the floor rejects a single-work
synthesis; organize is expected to decline most boundaries; ask and synthesize
update matching pages before creating duplicates. The final decision to refuse
is still model judgment, not a mechanically provable property.

## II.5 Treat the wiki as future candidate context

Every source page, answer, synthesis, concept, and entity becomes material a
later agent may read. Good pages provide compressed, grounded context; weak or
duplicate pages compete for the same attention. Selectivity, update-before-
duplicate, tensions, pruning, and stale review are therefore not housekeeping
around the product — they shape the future working context of the product.

## II.6 Contracts are the surface; scripts provide deterministic leverage

The contracts define what the human can ask for. Scripts handle stable mechanics:

- `extract.py` produces a reading surface and provenance;
- `search.py` fetches and formats external discovery candidates;
- `check_wiki.py` binds objective invariants;
- `lint.py` and `stale.py` report advisory maintenance candidates;
- `indexes.py` exposes deterministic navigation and graph data;
- `commit.py` confines one contract's history to its owned files.

Indexes and search results may expose candidates, but they do not choose the
wiki context the agent must read or decide what a page should say. Final
relevance, reading depth, synthesis, and no-op decisions remain with the agent.
The scripts neither call a model nor form a model-calling orchestration layer.

## II.7 Keep the human in the research agenda, not the generation critical path

The human's irreducible roles are choosing or approving sources, setting the
research direction, exploring, and asking questions. Selecting candidates from a
search result belongs to sourcing. Repeated page-level drafting, cross-linking,
format checking, and ordinary maintenance can leave the critical path and be
handled by the agent plus deterministic checks.

Personal context may shape assumed background, communication, and standing
research goals, but it is not evidence. Taste may shape which mechanism,
boundary, or construct is foregrounded, but it cannot alter page roles or
provenance discipline.

---

# Part III — Prior project experience

A predecessor project compared several authoring arrangements. Two observations
informed Patchouli:

- a loop that required the model to prove structural or stylistic compliance
  before stopping produced more truncated synthesis and citation clutter than an
  arrangement that kept interpretive criteria advisory and let the model author
  in one coherent episode;
- an arrangement that permitted no-op and separated organize from ingest created
  far fewer durable pages than auto-promotion variants, without a human deciding
  each individual page.

This experience is weak evidence: it was one informal, uncontrolled comparison,
confounded by differences between arrangements and judged with a project-specific
rubric. It illustrates I.4 and I.5; it does not establish them. Better evidence
or repeated contrary use should revise a principle. This anecdote yields first,
not reality.

---

# Part IV — Named principles (PR1–PR10)

**PR1 — The wiki instance is the user's asset; logistics are replaceable.**
Schema and objective checks are relatively durable; prompts, parsers, providers,
and runtime integrations should be easy to replace. *(I.1, I.2; II.1.)*

**PR2 — Capability lives in the model; every scaffold must pay its tax.** Add a
tool, rule, stage, or format only for a larger structural gain. *(I.2; II.1,
II.6.)*

**PR3 — Trust the model with judgment; move deterministic work into scripts.**
The model decides relevance, depth, relation, and refusal. Scripts extract,
fetch, resolve, verify, index, and confine history. *(I.3, I.4; II.2, II.6.)*

**PR4 — Complete one human–agent contract in one coherent episode.** Runtime
model calls and tool loops do not count as fragmentation. Add another
Patchouli-level stage only when the task or observed use justifies it. *(I.3;
II.2.)*

**PR5 — Bind objective invariants; keep interpretive consequences advisory.**
Quotes, IDs, links, versions, and paths may block. Insight, integration, and the
meaning of a source change may not. *(I.4; II.3.)*

**PR6 — No-op is a first-class result; update before duplicate.** Growth is
valuable only when the new artifact or revision earns its future context cost.
*(I.4, I.5; II.4, II.5.)*

**PR7 — Every page changes the candidate context available to future work.** A
weak page costs attention when selected later; selectivity and maintenance
therefore compound. *(I.5; II.5.)*

**PR8 — Expose operations; keep scripts deterministic and non-interpretive.**
Scripts may fetch, index, and report candidates, but they do not choose the
agent's read set or author knowledge. *(I.2, I.3; II.6.)*

**PR9 — The human owns the research agenda, not routine page production.** The
human chooses sources and questions; the agent handles recurring generation and
maintenance inside that agenda. *(I.1; II.7.)*

**PR10 — Objective verification tends to compound; model-specific orchestration
tends to depreciate.** Invest first in invariants grounded outside the model and
keep runtime-specific control flow thin. *(I.2, I.4; II.1, II.3, II.6.)*

---

# Part V — Confidence and self-audit

## What is well supported

The strongest part of the design is the structural argument: a persistent wiki
can be treated as an asset; deterministic provenance checks are different from
interpretive quality judgments; and lower-signal context is not free. The
specific Patchouli contracts are still product choices, but they follow a clear
chain from those premises.

## What remains uncertain

- **Proxy gating is an analogy.** Reward-model overoptimization and
  specification gaming are not identical to an inference-time authoring gate,
  and the direct format-restriction study is contested. Patchouli adopts a
  conservative default, not a proved law.
- **One coherent episode is a default, not a universal optimum.** Some tasks may
  benefit from an additional explicit stage. Repeated use should decide whether
  the stage pays for itself.
- **Wiki pollution is conditional on selection.** A weak page harms later work
  only when it enters the read set. The design therefore needs selective reading
  as well as selective writing.
- **No-op quality remains model judgment.** The architecture makes refusal
  available and removes automatic promotion; it cannot mechanically prove that
  a refusal or write was the better research decision.

## Self-audit

- Is each human request handled as one coherent contract episode while leaving
  runtime-internal turns unconstrained? **Yes.**
- Are objective invariants binding and interpretive findings advisory?
  **Yes:** `check_wiki.py` binds; `lint.py` and `stale.py` advise.
- Can every judgment-bearing contract decline or avoid duplication? **Yes:**
  no-op is explicit, and answer/synthesis/organize update before duplicate.
- Does ingest avoid automatic durable-page promotion? **Yes.**
- Does source evolution create a review queue rather than automatic rewriting?
  **Yes.**
- Do scripts provide deterministic leverage without calling models or choosing
  knowledge content? **Yes.**
- Does the human retain source selection and the research agenda? **Yes.**

A "no" is a concrete reason to reconsider the relevant contract or script.

---

## Sources

Ordered by first appearance. First-party engineering reports and peer-reviewed
or archived research carry the factual load; design essays are used as design
inspiration and are bounded accordingly.

- [1] Karpathy, Andrej, "LLM Wiki" (2026).
  <https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f>.
  The wiki/codebase reframe and human/product-owner role.
- [2] Anthropic engineering, "Building Effective Agents," "Effective Context
  Engineering for AI Agents," "Writing Tools for AI Agents," and "Building
  Agents with the Claude Agent SDK." Model capability, simple composable
  patterns, context management, and tool design.
- [3] Sutton, Richard, "The Bitter Lesson" (2019).
  <http://www.incompleteideas.net/IncIdeas/BitterLesson.html>. General methods
  that scale with computation repeatedly outlast hand-engineered knowledge.
- [4] Lincoln, Logan, "The Bitter Lesson Kills Your Orchestration Layer" (2025).
  <https://loganlincoln.com/blog/bitter-lesson-kills-your-orchestration-layer>.
  A blog extrapolation of [3] to agent orchestration; inspiration, not proof.
- [5] Anthropic, "Harness design for long-running application development"
  (2026). <https://www.anthropic.com/engineering/harness-design-long-running-apps>.
  Generator/evaluator design and turning subjective goals into useful
  development criteria.
- [6] Anthropic, "Effective Context Engineering for AI Agents" (2025).
  <https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents>.
  Context as a finite attention budget and context rot.
- [7] Vaswani et al., "Attention Is All You Need" (2017).
  <https://arxiv.org/abs/1706.03762>. Architecture background: a Transformer
  forward pass is an internal model computation, not Patchouli's contract unit.
- [8] Gao, Leo, John Schulman, and Jacob Hilton, "Scaling Laws for Reward Model
  Overoptimization" (2022). <https://arxiv.org/abs/2210.10760>. Optimizing an
  imperfect proxy beyond a point degrades ground-truth performance.
- [9] Tam, Zhi Rui, et al., "Let Me Speak Freely? A Study on the Impact of
  Format Restrictions on Performance of Large Language Models," EMNLP 2024
  Industry Track. <https://arxiv.org/abs/2408.02442>. Directional evidence on
  inference-time format restrictions; the result is contested.
- [10] Krakovna, Victoria, et al., "Specification gaming: the flip side of AI
  ingenuity," DeepMind (2020).
  <https://deepmind.google/blog/specification-gaming-the-flip-side-of-ai-ingenuity/>.
  Literal objective satisfaction without the intended outcome.
- [11] Shi, Freda, et al., "Large Language Models Can Be Easily Distracted by
  Irrelevant Context," ICML 2023. <https://arxiv.org/abs/2302.00093>.
- [12] Cuconasu, Florin, et al., "The Power of Noise: Redefining Retrieval for
  RAG Systems" (2024). <https://arxiv.org/abs/2401.14887>. The specific finding
  used here is that related-but-irrelevant material can be especially harmful.
- [13] Liu, Nelson F., et al., "Lost in the Middle: How Language Models Use Long
  Contexts" (2023). <https://arxiv.org/abs/2307.03172>. Relevant information is
  used unevenly by position and input length.
