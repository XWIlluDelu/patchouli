# Task: maintain

Keep the wiki healthy. Run `python3 scripts/lint.py` and read its advisory
findings (citation clutter, orphans, duplicate titles); the binding floor
already blocks broken links, missing markers or `## Supporting works`, and
single-work syntheses. Your scan is for what no script can judge: pages
superseded by later ingests, near-duplicate concepts under different names,
tensions a newer work has resolved, and thin pages not worth keeping.

Revise only findings that are a real, fixable problem. No-op-keep a page when
the finding is a false positive or the page is still justified as-is, and say
why. A clean wiki compounds; churn for its own sake does not.

Then run the binding floor (`check_wiki.py` → fix → `indexes.py`). Return
`NO_OP: <reason>` if no page warrants revision.
