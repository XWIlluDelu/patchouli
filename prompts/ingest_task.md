# Task: ingest

Compile one source into a single page under `wiki/sources/`.

1. If the source is not yet extracted, run `python3 scripts/extract.py <input>`
   (arxiv id/URL, http(s) URL, or local file). It writes `extracted/<work_id>/text.md`
   and prints the `source_page` path to write, plus the `work_id`, `version_id`, and
   `reading_surface` for the frontmatter. The filename is a deterministic function of
   the work, so re-ingesting the same source lands on the same file — write to the path
   it prints; do not hand-derive it.
2. Read the reading surface in full. Read related wiki pages (search
   `wiki/sources/`, `wiki/concepts/`, `wiki/syntheses/` for the topic) so you can
   place the source and surface any tension.
3. Write the source page in your own words, following the source template in
   `system/page_templates.md`.

A full reading is what lets you honor the template's harder levers: claims specific
enough to check (numbers, parameters, dataset, metric, assumption), method as
connected prose rather than a bullet dump, and scientific `## Limits` kept separate
from `## Extraction caveats`. Cover the source's distinct claims — a rich paper
yields several; a thin one is not padded to look rich. The GOOD/BAD pairs in the
template show each shape.

Quote verbatim in `> blockquotes` only when the wording carries evidence; one or two
is plenty. Record genuine conflicts under `## Tensions`. Let `tastes/active.md` shape
what you foreground, not the structure. Do not create concept/entity/synthesis pages
here — those come from organize.

Then run the binding floor (`check_wiki.py` → fix any failures → `indexes.py`; `lint.py`
is advisory). Return `NO_OP: <reason>` if the same version is already covered at equal
or greater depth.
