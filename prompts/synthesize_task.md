# Task: synthesize

Discover a genuine cross-work pattern, tension, or mechanism in the compiled
wiki and write it to `wiki/syntheses/<slug>.md`. The topic the user names is a
hint, not a mandate — let the real relation emerge from the source and synthesis
bodies you read.

No-op if fewer than two works genuinely relate. When synthesis is justified,
follow the synthesis template in `system/page_templates.md`: one contestable
thesis, the strongest counter-evidence, and a delta sentence. Weave the works
into one argument — do not catalogue contributions side by side. Compare what
each work assumes, measures, and concludes; where they differ, name the
methodological or theoretical reason. Carry `(Works: …)` markers and end with
`## Supporting works`. Use the optional Evidence/Claim-status blocks only when
they make grounding scannable.

Let `tastes/active.md` shape which cross-work pattern you foreground, not the
structure.

Then run the binding floor (`check_wiki.py` → fix → `indexes.py`; `lint.py`
advisory). Return `NO_OP: <reason>` naming what to ingest or how to narrow the
topic if no genuine synthesis holds.
