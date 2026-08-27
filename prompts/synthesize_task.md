# Task: synthesize

Discover a genuine cross-work pattern, tension, or mechanism in the compiled
wiki and write it under `wiki/syntheses/`. The topic the user names fixes the
scope; let the precise thesis emerge from the source and synthesis bodies you
read within that scope. If no genuine relation holds there, return a no-op
rather than substituting a different topic.

Before choosing an output path, inspect existing syntheses for the same thesis
or materially the same boundary. Update the existing synthesis when new compiled
evidence changes or deepens it; do not create a near-duplicate under a new slug.
If the relation is already captured at equal or greater depth, return a no-op and
point to that page. Otherwise create `wiki/syntheses/<slug>.md`. Author or revise
no other knowledge page in this contract.

No-op if fewer than two works genuinely relate. When synthesis is justified,
follow the synthesis template in `system/page_templates.md`: one contestable
thesis, the strongest counter-evidence, and a delta sentence. Weave the works
into one argument — do not catalogue contributions side by side. Compare what
each work assumes, measures, and concludes; where they differ, name the
methodological or theoretical reason. Mark cross-work inferences as
`(synthesis across Works: …)` and end with `## Supporting works`. Use the
optional Evidence/Claim-status blocks only when they make grounding scannable.

Let `tastes/active.md` shape which cross-work pattern you foreground, not the
structure.

Then run the binding floor (`check_wiki.py` → fix → `indexes.py`; `lint.py`
advisory). Return `NO_OP: <reason>` naming what to ingest or how to narrow the
topic when no genuine synthesis holds, or naming the existing synthesis when no
new page or revision is justified.
