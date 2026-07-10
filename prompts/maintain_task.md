# Task: maintain

Keep the wiki healthy. If the user names a wrong page or claim, make it the
active object and do not broaden the correction into a general sweep. Correct a
source page's account of its own work only against its bound reading surface;
check a cross-work `## Tensions` correction against the related compiled source
pages. Correct an answer or durable page only against its compiled supporting
pages. New evidence is ingested separately, and disagreement remains a tension
rather than rewriting an older work to agree.

For a general maintenance sweep, run `python3 scripts/lint.py` and read its
advisory findings (citation clutter, workflow residue, orphans, duplicate
titles); the binding floor already blocks broken links, missing schema or
support, and single-work syntheses. Scan for what no script can judge: pages
superseded by later ingests, near-duplicate concepts under different names,
tensions a newer work has resolved, and thin pages not worth keeping.

Revise only a real, fixable problem. No-op-keep a page when a finding is a false
positive or the page is still justified as-is, and say why. A clean wiki
compounds; churn for its own sake does not.

Then run the binding floor (`check_wiki.py` → fix → `indexes.py`). Return
`NO_OP: <reason>` if no page warrants revision.
