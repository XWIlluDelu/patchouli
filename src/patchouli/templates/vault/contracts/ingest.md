# Ingest — compile materials into the wiki

**Objective.** Turn new material into knowledge the wiki can use: a source page that
faithfully captures what the material claims, how it knows, and where it stops — and
the integration of that knowledge into the rest of the wiki, so it is connected rather
than appended.

**Resources.** The material (inbox/, a path, a URL, a note in notes/, or a registered
source awaiting ingestion); `patchouli add`, `read`, `search`, `new`; the research goals
and frontier in `wiki/hubs/overview.md`; the active taste; existing pages.

**Deliverables.**
- `wiki/sources/<id>.md` (see STYLE.md → Source page). Give the source a meaningful id
  (`author2024-keyword`): `--id` when adding, or `patchouli rename` afterwards.
- The wiki updated wherever the material matters: new evidence, variants, conditions or
  counterexamples on concept pages; agreement or conflict made explicit on
  syntheses; answers whose conclusions it changes; new pages where it introduces a
  concept or question of lasting value that has no home yet.
- Any new open questions or leads on the overview's frontier.
- `patchouli sync --op ingest -m "<title>\n<one-line gist>"`, then a short report to the
  human: what the material contributes, where it landed, what it contradicts or leaves
  open, what might be worth reading next.

**Quality bar.** Read the reading text fully (for very long works, the parts that matter
for the goals — and say what you skipped). Claims are specific and conditioned, with
real locators. Extraction damage (garbled formulas, missing tables) is noted under
Extraction caveats, and claims depending on it are verified against the raw file and
cite it directly (`[id fig. 2](../../raw/id.pdf#page=4)`). Several
materials are several source pages, integrated together.

**Decline** to (re)write if the same version is already covered as well or better; say so.
