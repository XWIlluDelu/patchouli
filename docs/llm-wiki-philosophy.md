# The philosophy of an agent-built wiki

The design rationale for Patchouli. The named principles (PR1–PR10) at the end are the
*why* behind every contract in `AGENTS.md` and every script in `scripts/`; the sections
build to them. This is philosophy, not a changelog — where a principle and the code
disagree, that is a bug in one of them, to be reconciled rather than narrated.

---

## 1. The reframe: the wiki is a compounding artifact

The foundational insight is Karpathy's [1]: an LLM wiki is not a query-time retrieval
system. It is a persistent, compounding artifact — a structured, interlinked collection
of markdown files that sits between the human and the raw sources. Knowledge is compiled
once at ingest and kept current, not re-derived on every query. The wiki gets richer with
every source added and every question asked.

This reframe changes the engineering problem. In traditional software the code is the
asset and the data is passive. Here the wiki is the asset, and everything around it — the
scripts, the contracts in `AGENTS.md`, the templates — is replaceable logistics. The two
are not the same kind of thing, and the discipline applies differently to each.

The logistics have an internal split where the asset-vs-logistics discipline bites. Some
parts are durable: the file topology, the page roles, the evidence conventions (`(Work:)`
markers, `## Supporting works`, `work_id`/`version_id`, the verbatim-quote rule), and the
objective-invariant checks in `check_wiki.py`. These describe what a correct wiki page
*is*, so they outlive any particular agent runtime. Other parts are replaceable: prompt
wording, the extraction scripts, the discovery script — the parts that encode assumptions
about today's tools and age against tomorrow's. The common error is to pour effort into
the replaceable machinery and under-invest in the durable structure.

Karpathy's metaphor fixes the roles: Obsidian is the IDE, the LLM is the programmer, the
wiki is the codebase [1]. The human is not the programmer; the human is the product owner
— sourcing, exploring, asking. The agent does the grunt work of reading, summarizing,
cross-referencing, filing. This is not a chatbot with file access; it is a long-running
research librarian.

---

## 2. The inversion: a methodology that directs an agent, not a program that calls a model

The predecessors of this product (the A and P-series arms) were *programs that call an
LLM*: a harness assembled a context, called the model, and post-processed the result.
Patchouli is the inversion — *a methodology plus a few deterministic tools that direct an
agent*. It makes no API calls of its own. The LLM is the runtime: the coding agent (pi,
codex, claude code) the user starts inside the folder. `AGENTS.md` is the operating
contract that agent reads; the scripts are the deterministic operations it calls.

The inversion relocates the line between what the harness does and what the model does
(Sections 3, 9). In a program-that-calls-a-model, retrieval has to be scripted: the model
cannot read files between calls without paying a serialization tax, so the harness reads
for it. In a methodology-that-directs-an-agent, the agent reads the filesystem itself —
natively, within one continuous session — so retrieval moves back to the agent, where the
relevance judgment it requires belongs. The scripts retreat to what is genuinely
deterministic: extraction, the objective floor, index rebuilds, discovery.

Capability lives in the model; the methodology arranges the conditions under which it
operates [2]. The engineer is not building the intelligence — the model is the intelligence
— and elaborate scaffolding around it is, more often than engineers trained on the older
paradigm admit, a way of consuming the model's capacity to maintain the illusion that the
scaffolding is the source of the system's intelligence [2]. Every tool, every step, every
custom format is a tax on the model's effectiveness; each must pay its tax with a larger
gain or be removed. The bitter lesson transfers [3, 4]: hand-engineered orchestration
around a model loses to better models running with less of it, and that orchestration has
a shelf life measured in months. The wiki does not. Invest in the wiki; keep the logistics
thin and replaceable.

---

## 3. The trust asymmetry: judgment yes, mechanical compliance no

Trust in the agent is not binary; it is calibrated by what the model is good at and what
degrades it.

The model is good at judgment: synthesis, writing, deciding what is relevant, deciding
when a boundary is durable enough to deserve a page, deciding when sources genuinely
relate rather than merely sit near each other. This is the work it should do, and it does
it best given the whole task in one undivided pass.

The model is degraded by mechanical-compliance work: counting works to satisfy a two-works
gate, saturating prose with markers to satisfy a marker-presence check, filling template
sections to satisfy a structural rule. Not because it cannot — because asking it to deform
its output toward a proxy degrades the judgment work the output was for [5]. The arm
evidence showed this directly: an arm whose loop made the model prove structural
compliance before it could stop produced truncated, aggregated synthesis and citation
clutter; an arm that kept the same conventions as advisory norms and let the model write
in one pass produced cleaner, better-organized pages that used those sections only when
they strengthened the page.

The principle: trust the model with judgment; absorb the *mechanical* into scripts. Quote
verification, link checking, work-id resolution, provenance, index building — deterministic,
and they belong in `check_wiki.py` and `indexes.py`, before or after the writing, never
inside it. Note what the inversion changed: retrieval is *not* on the mechanical side
here. Deciding what to read and what is relevant is judgment, and the agent does it by
reading the filesystem. The scripts do not retrieve.

---

## 4. One undivided authoring pass is the trust expression

"Favor single-shot generation over multi-turn with gates and blocks" is directionally
right, but the agent-runtime frame sharpens what "single-shot" means.

A single forward pass is a one-shot mapping from context to output; inside it the model
attends across the whole context and emits tokens conditioned on the result [2]. The latent
reasoning that drives this is far richer than the visible chain-of-thought. The cost the
instinct is reaching for is paid when a *harness fragments one cognitive operation into
several API calls joined by lossy serialization* [2]: one continuous reasoning process
becomes two truncated ones, each rebuilt from a compressed summary of the last.

An agent reading the files it chooses to read is not that. It is the model directing its
own attention-gathering inside one continuous session — exactly what these runtimes are
built to do well. So the principle is not "make exactly one tool call." It is: author in
one undivided pass, and let nothing fragment it. Two things fragment it, and Patchouli
forbids both. A *harness-imposed multi-call pipeline* that splits authoring across
serialized turns — the program-that-calls-a-model shape — is gone by construction, because
there is no program making the calls. An *interpretive finish-gate* — a loop that makes the
model satisfy a quality check before it may stop, on a step budget — is forbidden by the
contract: the agent reads what it needs, decides, writes, and the only loop afterward is
the deterministic correction on the objective floor (Section 5), which is not a quality
judgment.

A task needs a genuine agentic loop only when its action space cannot be loaded into a
static context — when the next action depends on observing the consequences of the last in
an environment [2]. Reading a fixed wiki to write a page is not that; the agent gathers
what it needs and writes. This is the trust: give the model the whole task and do not
interrupt it.

---

## 5. Verification outside the authoring pass

This is where "trust the agent" most easily slides into "skip verification" by mistake.
The resolution is not "no verification" but verification of the right kind in the right
place.

The right kind is *objective invariants only*. Work-ids resolve to source pages. Verbatim
quotes match the reading surface. Internal links resolve. Page types match their
directories. Provenance is present. These are deterministic and do not depend on judgment,
so checking them cannot deform the output — there is no proxy to deform toward. This is
`check_wiki.py`, the binding floor: it runs after every write, and a failure is fixed and
re-checked until it passes. That re-check loop is not a gate on quality; it is the model
correcting an objective error it can see.

The wrong kind is *interpretive form*: synthesis-integration depth, relation-label
fluency, citation density, narrative completeness. These are subjective. A run-time gate on
them either blocks good work unjustly or deforms the output toward the proxy, and the agent
cannot self-certify them at run time without spending the authoring budget on
self-validation [6]. They are improved at *design* time — by judging bundles of output
across versions and revising the methodology — not inspected on every generation. `lint.py`
carries the advisory half of this: it reports interpretive smells (citation clutter,
orphans, duplicate titles) and never blocks.

This is the layer where investment compounds rather than decays [2]. A check grounded in
the world — does this quote actually appear in the source — stays true as models improve;
an orchestration layer built around today's model does not. The logistics should be thin on
orchestration and thick on objective verification [7].

---

## 6. Selectivity is the highest form of trust

The selective arm's hidden strength, surfaced by the analysis, was that it produced very
few durable pages per domain where the auto-promoting arms produced dozens — and the
smaller, selective bundles scored higher. Given the same organize command, the selective
arm's model autonomously judged most boundaries not worth a durable page and declined; the
others promoted aggressively. No human made the difference. Selectivity here is
architectural and model-driven: it comes from (a) ingest never auto-creating durable pages
— they come only from the separate organize judgment — and (b) the model exercising that
judgment to decline most candidates.

The principle: the no-op is a first-class output. A wiki that grows only when growth is
justified compounds; one that grows on every operation pollutes itself. Trust the model to
refuse to write, and require it to say what would change the refusal. Every Patchouli
contract ends with a no-op clause for this reason.

---

## 7. The wiki is its own context engineering

This is the deep reason selectivity matters. Context engineering [8] is curating what the
model sees at inference to get better results. In most systems that happens once per call.
In an LLM wiki, the wiki itself is the curated context for every future operation: every
ingest curates the context for the next ask; every synthesis becomes a retrievable artifact
the next one builds on; every concept page becomes a neighbor future ingests link to.

So the system's output becomes its own input. A clean, selective wiki produces clean future
operations; a polluted one degrades every future read. The cost of a weak page is not paid
once — it is paid every time it is retrieved into a later context, spending the attention
budget [8] of every subsequent operation. This is why the wiki is compounding capital and
the logistics are depreciating capital: build the wiki carefully and selectively, build the
logistics thin.

---

## 8. Minimal human intervention, precisely

"Minimal human intervention" must be defined so it does not become "no verification." The
human's irreducible roles, per Karpathy [1], are sourcing, exploration, and asking:
deciding what to ingest, what to explore, what to ask. These are product-owner decisions
and cannot be delegated without delegating the research agenda itself.

The reducible roles are review, curation, and quality judgment. The goal is to take the
human off that critical path — not by skipping quality judgment but by replacing it with
mechanisms that do not compete with generation: objective invariants checked automatically
after the write (Section 5); selectivity via the first-class no-op (Section 6); and
subjective quality handled at design time, not run time. When the user actually uses the
wiki, no judge runs. Run-time quality rests on front-loaded selectivity (the no-op) and
back-loaded objective verification (the floor).

So the human leaves the generation critical path but stays in the research agenda. The
human does not review each page or decide each boundary; the human decides what to ingest
and what to ask, and the system writes, verifies, and stays selective.

---

## 9. The contracts are the surface; the scripts are the floor

The human-facing surface is the contracts in `AGENTS.md` — ingest, search, ask,
synthesize, organize, maintain, and polish, which proofreads the human's own notes and,
like search, never touches the wiki — matched to natural language by the routing table.
Each is one authoring pass: the agent assembles its context by reading the filesystem,
writes, and, after any write to `wiki/`, runs the binding floor.

The scripts are deliberately *not* an orchestration layer. `extract.py` turns a source
into a clean reading surface (arxiv via the arxiv API and ar5iv, web via Firecrawl, local
files directly) and prints the deterministic target path plus the provenance frontmatter.
`search.py` discovers candidates via Exa into a file under `searches/` and touches nothing in the wiki.
`check_wiki.py` is the objective floor; `indexes.py` rebuilds the navigation; `lint.py`
advises. None of them retrieves wiki context for the model or decides what a page should
say — that is the agent's, by reading and judging. This is the inversion in one line: the
scripts do what is deterministic, the agent does what is judgment, and nothing scripted
stands between the agent and the authoring pass.

---

## 10. What "no gates" does and does not mean

Two refinements keep the trust position from collapsing into carelessness. First, "no
gates, no blocking" is right only as *no gate on interpretive form*; objective-invariant
verification stays, and is where investment compounds. Skipping it does not trust the agent
more — it leaves objective errors uncaught and pushes subjective quality onto a human or
onto nobody [6]. Second, one undivided pass is not an *unprepared* pass: the agent still
reads the relevant wiki before it writes. The trust is in the model's authoring and its
relevance judgment, not in skipping the reading. The reading is the agent's to do; what is
removed is the harness standing in the middle of it.

---

## 11. Named principles

The foundation for future discussion, PR1–PR10.

**PR1 — The wiki is the user's asset; the logistics are replaceable.** Inside the logistics,
schema and objective checks are durable; prompts and scripts are depreciating capital with
a shelf life of months. Invest in the wiki's structure and its invariants; expect to
replace the rest as runtimes improve.

**PR2 — Capability lives in the model; the methodology arranges conditions.** The engineer
arranges context, operations, and verification; the model supplies the intelligence.
Elaborate scaffolding is taxation on the model — demand each piece pay its tax with
structural gain.

**PR3 — Trust the model with judgment; absorb the *deterministic* into scripts.** The model
writes, synthesizes, decides relevance, decides when a boundary is durable, and retrieves
by reading the filesystem. The scripts extract, verify quotes and links, resolve work-ids,
and build indexes. Mechanical-compliance work inside the authoring budget deforms judgment
toward proxies.

**PR4 — Author in one undivided pass; add a loop only when the task needs environmental
observation.** Wiki operations are gather-then-write; they fit one pass. The two things
that fragment it — a harness-imposed multi-call pipeline and an interpretive finish-gate on
a step budget — are both absent by construction. A genuine agentic loop is for tasks whose
next action depends on the consequences of the last; wiki authoring is not one.

**PR5 — Verify objective invariants outside the authoring pass; never gate on interpretive
form.** Work-ids, verbatim quotes, links, page types, provenance: deterministic, checked
after, corrected and re-checked. Integration depth, relation fluency, citation density:
subjective, improved at design time, never gated at run time.

**PR6 — The no-op is a first-class output; selectivity compounds.** A wiki that grows only
when justified compounds; one that grows on every operation pollutes itself. Trust the
model to refuse, and require it to say what would change the refusal.

**PR7 — The wiki is its own future context; every page added changes every future
operation.** The output becomes the input. A clean, selective wiki produces clean
operations; a polluted one degrades every later read.

**PR8 — Expose operations; keep the scripts to the floor.** The surface is the
contracts; each is gather-by-reading, write, verify. The scripts do the deterministic work
and do not orchestrate the agent or retrieve for it. Subjective quality is tuned at design
time, not run time.

**PR9 — The human leaves the generation critical path but stays in the research agenda.**
The human does not review each page or decide each boundary; the human decides what to
ingest and what to ask. Objective invariants are automatic; selectivity is automatic via
the no-op.

**PR10 — Verification is where investment compounds; orchestration is where it decays.**
Build verification thick (objective, deterministic, grounded in the world) and orchestration
thin (the least that delivers the agent to the floor). If scaffolding grows faster on the
orchestration side than the verification side, the system is being built backward.

---

## 12. How Patchouli answers its own principles

A self-audit — the same checklist the design is meant to pass:

- One undivided authoring pass per contract, the agent reading the filesystem for context
  (PR4, PR3)? Yes — `AGENTS.md` makes each contract a read-decide-write pass.
- Objective invariants verified outside the pass, advisory on the rest, never gating on
  form (PR5, PR10)? Yes — `check_wiki.py` binds, `lint.py` advises.
- The no-op first-class, the model trusted to refuse (PR6)? Yes — every contract carries a
  no-op clause; ingest never auto-creates durable pages.
- A selective wiki, not auto-promotion (PR6, PR7)? Durable pages come only from organize,
  which is expected to decline most candidates.
- The human in sourcing and asking, out of the generation path (PR9)? Yes — the human
  talks; the agent writes and verifies.
- Logistics thin on orchestration, thick on objective verification (PR10)? The scripts are
  extraction, discovery, the floor, and indexes — there is no orchestration layer.

A "no" on any line is a named reason to reconsider, not a vague worry.

---

## Sources

- [1] Karpathy, Andrej, "LLM Wiki" (2026). <https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f>. The reframe: wiki as compounding artifact; Obsidian as IDE, LLM as programmer, wiki as codebase; the three operations; the human as product owner.
- [2] Anthropic engineering, "Building Effective Agents," "Effective Context Engineering for AI Agents," "Writing Tools for AI Agents," and "Building Agents with the Claude Agent SDK"; with Vaswani et al. on transformer attention and the latent-reasoning literature. The forward-pass account of a single call, the cost of fragmenting reasoning across turns, and "capability lives in the model."
- [3] Sutton, Richard, "The Bitter Lesson" (2019). <http://www.incompleteideas.net/IncIdeas/BitterLesson.html>. General methods that scale with compute defeat hand-engineered domain knowledge.
- [4] Lincoln, Logan, "The Bitter Lesson Kills Your Orchestration Layer" (2025). <https://loganlincoln.com/blog/bitter-lesson-kills-your-orchestration-layer>. Orchestration as depreciating capital with a months-long shelf life.
- [5] Anthropic, "Harness design for long-running application development" (2026). <https://www.anthropic.com/engineering/harness-design-long-running-apps>. The generator-evaluator pattern; turning subjective judgment into gradable criteria at design time.
- [6] yAI, "The Verification Paradox: Why Agents Cannot Automatically Validate Themselves." <https://yaihq.com/research/verification-paradox-agents-cannot-validate-themselves>. Why subjective quality cannot be self-certified by the agent at run time.
- [7] Agent Hypervisor, "The Bitter Lesson of Agentic Coding." <https://agent-hypervisor.ai/posts/bitter-lesson-of-agentic-coding/>. "Thin on orchestration and thick on verification and memory."
- [8] Anthropic, "Effective Context Engineering for AI Agents" (2025). <https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents>. Context as a finite attention budget; context rot; curating the smallest high-signal set.

The principles are a synthesis from these sources and from the A/P-series arm evidence in
the LLM Wiki Iterate eval project; the comparative analysis that produced them lives there,
not in this product. They are the foundation for iteration, to be revised when evidence
contradicts them.

### Notes on confidence

The structural argument — wiki as asset, logistics as depreciating capital, one undivided
pass with objective verification outside it, selectivity compounds — is well-supported by
the cited sources and the arm evidence together.

The claim that wiki operations almost never need a genuine agentic loop (Section 4) is
grounded in the structure of the operations, not a measured survey. It is stated as a
default with an explicit escape clause — an operation whose next action genuinely depends
on observing the last would narrow it — not as a law.
