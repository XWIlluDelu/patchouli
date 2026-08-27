# Task: maintain

Keep the wiki healthy. If the user names a wrong page or claim, make it the
active object and do not broaden the correction into a general sweep. Correct a
source page's account of its own work only against its bound reading surface;
check a cross-work `## Tensions` correction against the related compiled source
pages. Correct an answer or durable page only against its compiled supporting
pages. New evidence is ingested separately, and disagreement remains a tension
rather than rewriting an older work to agree.

For a general maintenance sweep, run both advisory scans:

- `python3 scripts/lint.py` for citation clutter, workflow residue, orphans, and
  duplicate titles;
- `python3 scripts/stale.py` for committed knowledge pages whose compiled source
  dependencies have changed since the page's last revision. This includes
  source pages with cross-work `## Tensions`, not only answers and durable pages.

A stale finding is a review candidate, not a defect. Re-read the current
supporting source pages and revise only when the source change affects the page;
otherwise no-op-keep it and say why. The binding floor already blocks broken
links, missing schema or support, and single-work syntheses. Also scan for what
no script can judge: pages superseded by later ingests, near-duplicate concepts
under different names, tensions a newer work has resolved, and thin pages not
worth keeping.

Revise only a real, fixable problem. No-op-keep a page when a finding is a false
positive or the page is still justified as-is, and say why. A clean wiki
compounds; churn for its own sake does not.

Then run the binding floor (`check_wiki.py` → fix → `indexes.py`). Return
`NO_OP: <reason>` if no page warrants revision.
