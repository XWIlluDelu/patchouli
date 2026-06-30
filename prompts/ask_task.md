# Task: ask

Answer a research question from the compiled wiki, and file the answer at
`wiki/answers/<slug>.md`.

Search the compiled wiki for support — `wiki/sources/`, `wiki/syntheses/`,
`wiki/concepts/`, prior `wiki/answers/`. Do not read `raw/`/`extracted/`: ask answers
from the compiled wiki, the asset, not by re-deriving from sources — if the compiled
layer cannot support the answer, that gap is itself the finding. Do not mutate any wiki
page except the answer you write. Answer the question the wiki can actually support —
narrow or reframe it explicitly when the support sits beside the user's phrasing — and
never fill a gap from outside knowledge.

Follow the answer template in `system/page_templates.md`: a `## Short answer` that
stands on its own, dense per-source `## Evidence` (each bullet its own specifics and
caveat), then a `## Synthesis` that names the non-obvious connection. Carry `(Work: …)`
markers. If support is missing or partial, say so plainly and name what source or
evidence would change the answer.

Then run the binding floor (`check_wiki.py` → fix → `indexes.py`; `lint.py` advisory).
Return `NO_OP: <reason>` if the compiled wiki cannot support an answer.
