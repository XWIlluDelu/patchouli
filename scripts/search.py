"""Discover candidate sources for a research direction, via Exa.

    python3 scripts/search.py "attention as explanation" [--n 8]

Exa is a neural search engine: it takes a natural-language research direction and
returns relevant web pages (papers, blogs, docs). This does NOT ingest and does NOT
touch the wiki — it writes a candidate list to ``searches/<slug>.md`` for the
user to review, then pick which entries to ``ingest`` by URL or arxiv id.

Search is the same shape of deterministic fetch-and-format as extract.py, so it is a
script for the same reason: any agent runtime gets it identically, keys come from
.env via env_loader, and discovery stays separate from ingestion.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import urllib.error
import urllib.request
from pathlib import Path

from env_loader import with_key_retry, KeyRetry, KeyPoolExhausted
from file_state import atomic_write_text
from text_helpers import parse_arxiv_ref, slugify
from workspace_paths import Workspace

EXA_SEARCH = "https://api.exa.ai/search"
SNIPPET_CHARS = 300


def _exa_search(query: str, n: int, env_path: Path, *, timeout: int = 60) -> dict:
    body = json.dumps({
        "query": query,
        "numResults": n,
        "type": "neural",
        "contents": {"text": {"maxCharacters": SNIPPET_CHARS}},
        "autoprompt": True,
    }).encode("utf-8")

    def _try(api_key: str) -> dict:
        req = urllib.request.Request(
            EXA_SEARCH,
            data=body,
            headers={"x-api-key": api_key, "Content-Type": "application/json", "User-Agent": "patchouli-search/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # 401/403 = bad key, 429 = rate-limited, 5xx = server: try another key.
            # Other 4xx are real request failures.
            if exc.code in (401, 403, 429) or 500 <= exc.code < 600:
                raise KeyRetry(f"exa key failed ({exc.code}): {exc.read().decode('utf-8', 'replace')[:200]}")
            raise SystemExit(f"exa request failed ({exc.code}): {exc.read().decode('utf-8', 'replace')[:400]}")
        except urllib.error.URLError as exc:
            # Connection-level failure (timeout, DNS, refused): not a key problem,
            # so do not rotate keys — fail cleanly and let the caller re-run.
            raise SystemExit(f"could not reach Exa ({exc.reason}); transient network or endpoint down, retry")

    try:
        return with_key_retry(env_path, "EXA_API_KEY", _try)
    except KeyPoolExhausted as exc:
        raise SystemExit("search needs EXA_API_KEY and all keys failed; add one to .env (see .env.example). Last error: " + str(exc))


def _arxiv_id_from(url: str) -> str | None:
    ref = parse_arxiv_ref(url)
    return ref.fetch_id if ref else None


def search(query: str, *, n: int, workspace: Workspace) -> dict:
    """Run an Exa search and write a candidate list to searches/<slug>.md.

    Returns a summary dict (query, path, count, candidates)."""

    result = _exa_search(query, n, workspace.root / ".env")
    candidates: list[dict] = []
    for item in result.get("results") or []:
        url = item.get("url") or ""
        text = (item.get("text") or "").strip().replace("\n", " ")
        snippet = text[:SNIPPET_CHARS] + ("…" if len(text) > SNIPPET_CHARS else "")
        candidates.append({
            "title": item.get("title") or "(untitled)",
            "url": url,
            "arxiv_id": _arxiv_id_from(url),
            "snippet": snippet,
            "published_date": item.get("publishedDate"),
        })

    slug = slugify(query, fallback="search")
    out_path = workspace.searches / f"{slug}.md"
    lines = [
        f"# Search: {query}",
        "",
        f"_Candidate list from Exa, {_dt.date.today().isoformat()}. Review and `ingest` the",
        "ones worth keeping, by URL or arxiv id. This file is a scratch record, not wiki",
        "evidence, and is not checked by the binding verifier._",
        "",
        f"**{len(candidates)} candidate(s).**",
        "",
    ]
    for i, c in enumerate(candidates, start=1):
        arxiv_line = f" · arxiv: `{c['arxiv_id']}`" if c["arxiv_id"] else ""
        date_line = f" · {c['published_date']}" if c.get("published_date") else ""
        lines += [
            f"## {i}. {c['title']}",
            "",
            f"- link: {c['url']}{arxiv_line}{date_line}",
            f"- to ingest: `ingest {c['arxiv_id'] or c['url']}`",
            "",
            f"> {c['snippet']}",
            "",
        ]
    atomic_write_text(out_path, "\n".join(lines) + "\n")

    return {"query": query, "path": workspace.relpath(out_path), "count": len(candidates), "candidates": candidates}


def main() -> int:
    ap = argparse.ArgumentParser(description="Discover candidate sources via Exa; writes searches/<slug>.md.")
    ap.add_argument("query", help="a natural-language research direction")
    ap.add_argument("--n", type=int, default=8, help="number of candidates (default 8)")
    args = ap.parse_args()
    summary = search(args.query, n=args.n, workspace=Workspace.from_path(None))
    print(json.dumps(
        {"query": summary["query"], "path": summary["path"], "count": summary["count"],
         "candidates": [{"title": c["title"], "url": c["url"], "arxiv_id": c["arxiv_id"]} for c in summary["candidates"]]},
        ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
