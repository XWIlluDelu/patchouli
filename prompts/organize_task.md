# Task: organize

Sweep the wiki and create or update durable pages (concept / entity / synthesis)
or navigation hubs only where a boundary or reading path genuinely deserves one.

Read a broad snapshot: `wiki/sources/`, existing durable pages and hubs, and
the generated indexes.
The snapshot is evidence, not a candidate list — discover durable boundaries
yourself. Create or update a claim-bearing page only when the boundary is
genuinely durable, clearly scoped, and supported by at least two works or a
clear cross-work need (a synthesis needs two resolved works — the floor binds
this). Create a claim-free hub only when an existing cluster needs a reading
path that generated indexes do not provide. Declining most candidates is the
expected outcome; a one-off, noisy, or stopword boundary gets no page. Prefer
updating an existing page over creating a near-duplicate. Follow the relevant
template in `system/page_templates.md`.

Let `tastes/active.md` shape which boundary type you notice, but never let taste
override evidence or the support bar above.

Then run the binding floor (`check_wiki.py` → fix → `indexes.py`; `lint.py`
advisory). Return `NO_OP: <reason>` if no boundary or reading path justifies a
page.
