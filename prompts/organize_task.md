# Task: organize

Sweep the wiki and create or update durable pages (concept / entity / synthesis) only
where a boundary genuinely deserves one.

Read a broad snapshot: the `wiki/sources/` pages and the existing durable pages. The
snapshot is evidence, not a candidate list — discover durable boundaries yourself.
Create or update a page only when the boundary is genuinely durable, clearly scoped,
and supported by at least two works or a clear cross-work need (a synthesis needs two
resolved works — the floor binds this). Declining most
candidates is the expected outcome; a one-off, noisy, or stopword boundary gets no
page. Prefer updating an existing page over creating a near-duplicate. Follow the
relevant template in `system/page_templates.md`.

Let `tastes/active.md` shape which boundary type you notice, but never let taste
override evidence or the support bar above.

Then run the binding floor (`check_wiki.py` → fix → `indexes.py`; `lint.py` advisory).
Return `NO_OP: <reason>` if no boundary justifies a page.
