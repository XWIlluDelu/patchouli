# Task: ask

Answer a research question from the compiled wiki and file the answer under
`wiki/answers/`.

Search the compiled wiki for support — `wiki/sources/`, `wiki/syntheses/`,
`wiki/concepts/`, `wiki/entities/`, and prior `wiki/answers/`. Derived pages
surface relations and prior judgment; `## Evidence` grounds in source pages, and
a prior answer is never new evidence. Hubs may guide navigation but carry no
evidence. Do not read `raw/`/`extracted/`: ask answers from the compiled wiki,
the asset, not by re-deriving from sources. If the compiled layer cannot support
the answer, that gap is itself the finding.

Before choosing an output path, look for an existing answer with the same
question or materially the same scope. Update that page when the compiled wiki
now supports a real improvement; do not create a differently worded duplicate.
If the existing page already answers the question at equal or greater depth,
return a no-op and point to it. Otherwise create `wiki/answers/<slug>.md`.
Author or revise no knowledge page except that answer; the mandatory index
script may regenerate derived navigation.

Answer the question the wiki can actually support — narrow or reframe it
explicitly when the support sits beside the user's phrasing — and never fill a
gap from outside knowledge. Follow the answer template in
`system/page_templates.md`: a `## Short answer` that stands on its own, dense
per-source `## Evidence` (each bullet its own specifics and caveat), then a
`## Synthesis`. With multiple works, name the non-obvious relation; with one
work, develop its implication and boundary without inventing a cross-work
connection. Carry `(Work: …)` markers. If support is partial, say so plainly and
name what source or evidence would change the answer.

Then run the binding floor (`check_wiki.py` → fix → `indexes.py`; `lint.py`
advisory). Return `NO_OP: <reason>` when the compiled wiki cannot support an
answer or an existing answer already covers it at equal or greater depth.
