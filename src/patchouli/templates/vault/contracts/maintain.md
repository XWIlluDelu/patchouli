# Maintain — keep the wiki true and well organized

**Objective.** Keep the knowledge base correct, current and easy to navigate: fix what is
wrong, carry changes in sources through to what builds on them, and reshape the
organization when it no longer fits the knowledge.

**Resources.** `patchouli check` (errors and advice), `query`, `search`, `extract`,
the graph, all pages. For a named problem ("this page is wrong"), that problem is the scope.

**Deliverables.**
- Errors from `check` fixed. Advice acted on where it points at something real.
- For every substantively changed source or page: dependents (flagged by `sync`, or found with
  `query`) re-checked against the changed basis. A dependent you revise gets a dated line under
  `## Revision notes` (what changed, on what basis); one that still holds gets
  `reviewed: <date>` in its frontmatter instead, so confirming it doesn't flag the pages
  built on it.
- What scripts can't see, when asked for a real clean-up: contradictions between pages,
  claims superseded by newer sources, near-duplicate concepts, overloaded pages that should
  split, missing syntheses, summaries or certainty that drifted from the evidence.
- Restructurings (merge, split, rename) that keep every inbound link and citation valid —
  `patchouli rename` (and `--merge`) does the reference updates. Propose sweeping
  reorganizations to the human before doing them.
- `patchouli sync --op maintain -m "<scope>\n<summary>"` and a report of what changed and
  what needs the human's judgment.

**Quality bar.** Correct a source page only against its reading text; correct other pages
against the pages and sources they rest on. Disagreement between sources is kept and
explained, not "fixed". Leave justified pages alone — churn is not maintenance.
