# Task: ingest

Compile one source into a single page under `wiki/sources/`.

1. Run `python3 scripts/extract.py <input>` when the source is not yet extracted
   or when checking a requested update. It writes
   `extracted/<work_id>/text.md` and prints the exact `source_page`, `work_id`,
   `version_id`, `reading_surface`, and `source` frontmatter. Web/local defaults
   are collision-resistant functions of the source locator; `--work-id` is the
   stable identity override. Write only to the printed source-page path. If a
   changed surface is the same work and the user requested an update, re-run
   with `--refresh`, then update the source page and commit both tracked files
   together. Never use refresh to resolve a collision between distinct works.
2. Read the reading surface in full. Read related wiki pages (search
   `wiki/sources/`, `wiki/concepts/`, `wiki/syntheses/` for the topic) so you
   can place the source and surface any tension.
3. Write the source page in your own words, following the source template in
   `system/page_templates.md`.

A full reading is what lets you honor the template's harder levers: claims
specific enough to check (numbers, parameters, dataset, metric, assumption),
method as connected prose rather than a bullet dump, and scientific `## Limits`
kept separate from `## Extraction caveats`. Cover the source's distinct claims —
a rich paper yields several; a thin one is not padded to look rich. The GOOD/BAD
pairs in the template show each shape.

Quote verbatim in `> blockquotes` only when the wording carries evidence; one or
two is plenty. Record genuine conflicts under `## Tensions`. Let
`tastes/active.md` shape what you foreground, not the structure. Do not create
any durable page here: targeted synthesis belongs to `synthesize`; discovered
concept, entity, synthesis, and hub boundaries belong to `organize`.

Then run the binding floor (`check_wiki.py` → fix any failures → `indexes.py`;
`lint.py` is advisory). Return `NO_OP: <reason>` if the same version is already
covered at equal or greater depth. A user selection containing several sources
is several complete ingest operations, never one multi-source page.
