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
- `python3 scripts/stale.py` for committed answers and durable pages whose
  compiled source-page blobs have changed since the page's last revision or
  explicit no-change review.

A stale finding is a review candidate, not a defect. Re-read the current
supporting source pages and revise only when the source change affects the page.
If it remains valid, record that review instead of rewriting knowledge:

```sh
python3 scripts/stale.py --acknowledge wiki/<type>/<page>.md
# optionally restrict the acknowledgement
python3 scripts/stale.py --acknowledge wiki/<type>/<page>.md --work-id <id>
```

The command updates tracked `wiki/.stale-reviews.json`, binding the review to the
current committed source-page blob. Include that exact sidecar in the scoped
maintenance commit. Report `REVIEWED_KEEP: <reason>` for this case, not `NO_OP`,
because maintenance state changed. A later source change reopens the candidate.
Never acknowledge an uncommitted source or derived page.

The binding floor already blocks broken links, missing schema or support, and
single-work syntheses. Also scan for what no script can judge: pages superseded
by later ingests, near-duplicate concepts under different names, tensions a newer
work has resolved, and thin pages not worth keeping.

Revise only a real, fixable problem. A clean wiki compounds; churn for its own
sake does not. Return `NO_OP: <reason>` only when no knowledge page and no review
acknowledgement warrants a tracked change.

Then run the binding floor (`check_wiki.py` → fix → `indexes.py`).
