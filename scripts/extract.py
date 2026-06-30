"""Unified ingest extraction for Patchouli.

Dispatches by input type and writes a clean reading surface the agent then
compiles into a source page:

    python3 scripts/extract.py <input> [--work-id ID]

    <input> is one of
      - an arxiv id or arxiv URL  -> arxiv API (metadata) + ar5iv (body), no key
      - an http(s) URL            -> Firecrawl (needs FIRECRAWL_API_KEY in .env)
      - a local file (.pdf/.html/.md/.txt) -> local extraction

Outputs
      raw/<work_id>/...            original downloaded material (provenance)
      extracted/<work_id>/text.md  the reading surface check_wiki binds quotes to

and prints work_id / version_id / reading_surface for the source frontmatter.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

from env_loader import with_key_retry, KeyRetry, KeyPoolExhausted
from file_state import atomic_write_bytes, atomic_write_text
from text_helpers import slugify
from workspace_paths import Workspace

USER_AGENT = "Patchouli/1.0 (research wiki ingest)"
TIMEOUT = 30
ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")
ARXIV_API = "https://export.arxiv.org/api/query?id_list={id}&max_results=1"
AR5IV = "https://ar5iv.labs.arxiv.org/html/{id}"
FIRECRAWL_ENDPOINT = "https://api.firecrawl.dev/v1/scrape"
ATOM = {"a": "http://www.w3.org/2005/Atom"}
# Tags whose start/end is a textual block boundary in the reading surface.
_BLOCK_TAGS = {"p", "div", "section", "article", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "td", "th"}
_DROP_TAGS = {"script", "style", "head", "nav", "footer"}


class _TextExtractor(HTMLParser):
    """Collapse HTML to readable text. If the document has an <article> (ar5iv
    wraps the paper in one), only its text is kept, dropping site chrome."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._all: list[str] = []
        self._article: list[str] = []
        self._drop_depth = 0
        self._article_depth = 0
        self._has_article = False

    def _emit(self, chunk: str) -> None:
        if self._drop_depth:
            return
        self._all.append(chunk)
        if self._article_depth > 0:
            self._article.append(chunk)

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _DROP_TAGS:
            self._drop_depth += 1
        if tag == "article":
            self._has_article = True
            self._article_depth += 1
        if tag in _BLOCK_TAGS:
            self._emit("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS:
            self._emit("\n")
        if tag in _DROP_TAGS and self._drop_depth:
            self._drop_depth -= 1
        if tag == "article" and self._article_depth:
            self._article_depth -= 1

    def handle_data(self, data: str) -> None:
        self._emit(data)

    def text(self) -> str:
        raw = "".join(self._article if self._has_article else self._all)
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw.splitlines()]
        out: list[str] = []
        blank = False
        for ln in lines:
            if ln:
                out.append(ln)
                blank = False
            elif not blank:
                out.append("")
                blank = True
        return "\n".join(out).strip() + "\n"


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def _post_json(url: str, payload: dict, headers: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read())


def _arxiv_id(value: str) -> str | None:
    match = ARXIV_ID_RE.search(value)
    if match and ("arxiv" in value.lower() or value.strip() == match.group(0)):
        return match.group(1)
    return None


def extract_arxiv(arxiv_id: str, ws: Workspace) -> tuple[str, str]:
    work_id = arxiv_id
    try:
        meta_xml = _get(ARXIV_API.format(id=arxiv_id))
    except urllib.error.URLError as exc:
        raise SystemExit(f"could not reach the arxiv API ({exc.reason}); network issue, retry")
    atomic_write_bytes(ws.abspath(ws.raw / work_id / "arxiv-metadata.xml"), meta_xml)
    entry = ET.fromstring(meta_xml).find("a:entry", ATOM)
    if entry is None:
        raise SystemExit(f"arxiv: no metadata entry for {arxiv_id}")
    title = " ".join(entry.find("a:title", ATOM).text.split())
    authors = ", ".join(a.find("a:name", ATOM).text for a in entry.findall("a:author", ATOM))
    published = (entry.find("a:published", ATOM).text or "")[:10]
    year = published[:4]
    abstract = " ".join((entry.find("a:summary", ATOM).text or "").split())

    body = ""
    try:
        html = _get(AR5IV.format(id=arxiv_id)).decode("utf-8", "replace")
        atomic_write_bytes(ws.abspath(ws.raw / work_id / "ar5iv.html"), html.encode("utf-8"))
        body = html_to_text(html)
    except (urllib.error.URLError, OSError) as exc:
        body = f"[ar5iv body unavailable: {exc}; reading surface holds the abstract only]"

    header = (
        f"# {title}\n\n"
        f"- Authors: {authors}\n"
        f"- Year: {year}\n"
        f"- arXiv: {arxiv_id}\n"
        f"- Abstract page: https://arxiv.org/abs/{arxiv_id}\n"
        f"- Body source: {AR5IV.format(id=arxiv_id)}\n"
    )
    text = f"{header}\n## Abstract\n\n{abstract}\n\n## Body\n\n{body}\n"
    return work_id, text


def extract_url(url: str, ws: Workspace, work_id: str | None) -> tuple[str, str]:
    def _try(key: str) -> dict:
        try:
            return _post_json(FIRECRAWL_ENDPOINT, {"url": url, "formats": ["markdown"]}, {"Authorization": f"Bearer {key}"})
        except urllib.error.HTTPError as exc:
            # 401/403 = bad key; 429 = rate-limited; 5xx = server. All retryable
            # across another key. Other 4xx are real failures.
            if exc.code in (401, 403, 429) or 500 <= exc.code < 600:
                raise KeyRetry(f"firecrawl key failed ({exc.code}): {exc.read().decode('utf-8', 'replace')[:200]}")
            raise SystemExit(f"firecrawl request failed ({exc.code}): {exc.read().decode('utf-8', 'replace')[:300]}")
        except urllib.error.URLError as exc:
            # Connection-level failure (timeout, DNS, refused): not a key problem,
            # so do not rotate keys — fail cleanly and let the caller re-run.
            raise SystemExit(f"could not reach Firecrawl ({exc.reason}); transient network or endpoint down, retry")

    try:
        result = with_key_retry(ws.root / ".env", "FIRECRAWL_API_KEY", _try)
    except KeyPoolExhausted as exc:
        raise SystemExit(f"web ingest needs FIRECRAWL_API_KEY and all keys failed; set one in .env (see .env.example), or ingest an arxiv id / local file instead. Last error: {exc}")
    data = result.get("data") or {}
    markdown = data.get("markdown") or ""
    if not markdown:
        raise SystemExit(f"firecrawl returned no markdown for {url}: {json.dumps(result)[:300]}")
    title = (data.get("metadata") or {}).get("title") or url
    work_id = work_id or slugify(title, fallback=slugify(re.sub(r"^https?://", "", url)))
    atomic_write_bytes(ws.abspath(ws.raw / work_id / "firecrawl.json"), json.dumps(result, indent=2).encode("utf-8"))
    text = f"# {title}\n\n- Source: {url}\n\n{markdown}\n"
    return work_id, text


def extract_file(path: Path, ws: Workspace, work_id: str | None) -> tuple[str, str]:
    work_id = work_id or slugify(path.stem)
    ext = path.suffix.lower()
    if ext == ".pdf":
        try:
            import pypdf
        except ImportError:
            raise SystemExit("ingesting a local .pdf needs pypdf: `uv pip install -r requirements.txt` (in the project venv), or host the PDF and ingest its URL")
        reader = pypdf.PdfReader(str(path))
        body = "\n\n".join((page.extract_text() or "") for page in reader.pages)
    elif ext in {".html", ".htm"}:
        body = html_to_text(path.read_text(encoding="utf-8", errors="replace"))
    else:
        body = path.read_text(encoding="utf-8", errors="replace")
    raw_copy = ws.abspath(ws.raw / work_id / path.name)
    raw_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(path, raw_copy)
    text = f"# {path.stem}\n\n- Source file: {path.name}\n\n{body}\n"
    return work_id, text


def _source_page(work_id: str, title: str, *, is_arxiv: bool) -> str:
    """Deterministic source-page path for a work, so a re-ingest lands on the same file.
    An opaque arxiv id gets the first three title words appended for legibility; a
    title-derived work_id (web, file) is already legible and stands alone."""
    if is_arxiv:
        suffix = slugify(" ".join(title.split()[:3]), fallback=work_id)
        return f"wiki/sources/{work_id}-{suffix}.md"
    return f"wiki/sources/{work_id}.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract a source into extracted/<work_id>/text.md")
    parser.add_argument("input", help="arxiv id/URL, http(s) URL, or local file path")
    parser.add_argument("--work-id", default=None, help="override the derived work_id")
    args = parser.parse_args(argv)
    ws = Workspace.from_path(None)

    value = args.input.strip()
    arxiv_id = _arxiv_id(value)
    if arxiv_id:
        work_id, text = extract_arxiv(arxiv_id, ws)
    elif value.startswith(("http://", "https://")):
        work_id, text = extract_url(value, ws, args.work_id)
    elif Path(value).is_file():
        work_id, text = extract_file(Path(value), ws, args.work_id)
    else:
        raise SystemExit(f"unrecognized input: {value!r} (not an arxiv id, an http(s) URL, or an existing file)")

    out = ws.abspath(ws.extracted / work_id / "text.md")
    atomic_write_text(out, text)
    version_id = "sha256-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    title = next((ln[2:].strip() for ln in text.splitlines() if ln.startswith("# ")), work_id)
    source_page = _source_page(work_id, title, is_arxiv=arxiv_id is not None)
    print(f"extracted. write the source page to:\n  {source_page}")
    print("put these in its frontmatter:")
    print(f"  work_id: {work_id}")
    print(f"  version_id: {version_id}")
    print(f"  reading_surface: {ws.relpath(out)}")
    print(f"  title: {title}")
    print(f"  (reading surface is {len(text):,} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
