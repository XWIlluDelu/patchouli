# Task: search

Discover candidate sources for a research direction the user has only loosely
specified. Search produces a candidate list for the user to review; nothing under
`wiki/` is touched.

1. Run `python3 scripts/search.py "<the user's direction>"` (default 8 candidates;
   pass `--n` if the user asked for more or fewer). It calls Exa and writes
   `searches/<slug>.md` — a Markdown list of candidates with title, link,
   arxiv id (when one is in the URL), a short snippet, and the exact `ingest` line
   the user can give back for each one.
2. Tell the user the path of the candidate file and a one-line summary of what was
   found (count, and the top two or three titles); note when the list is mostly
   secondary commentary rather than primary sources. Do not paste the whole list
   into chat unless asked — the file is the record.
3. Stop. Do not ingest anything. The user decides which candidates to ingest and
   will say so in a follow-up (e.g. "ingest the first two", or "ingest 1706.03762").

If Exa returns nothing useful, reformulate the query once yourself — broader if the
direction was narrow, more specific if it was flooded — and re-run before suggesting
the user sharpen the direction or give a URL/arxiv id to ingest directly.
