"""Unified source extraction for Patchouli.

Dispatches by input type and writes the reading surface the agent compiles into a
source page:

    python3 scripts/extract.py <input> [--work-id ID] [--refresh]

Inputs:
  - arxiv id or arxiv URL: arxiv API metadata + ar5iv body, no key
  - http(s) URL: Firecrawl, using FIRECRAWL_API_KEY
  - local .pdf/.html/.md/.txt file: local extraction

Outputs:
  raw/<work_id>/...            replaceable current capture, gitignored
  extracted/<work_id>/text.md  tracked reading surface that binds source quotes

A changed reading surface is rejected before either layer is written unless the
caller passes --refresh. A refresh replaces the current capture and surface; the
source page and surface are then committed together, so Git retains the prior
version.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import shutil
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from env_loader import KeyPoolExhausted, KeyRetry, with_key_retry
from file_state import atomic_write_bytes, atomic_write_text
from text_helpers import ArxivRef, content_version_id, is_valid_work_id, parse_arxiv_ref, slugify
from workspace_paths import Workspace

USER_AGENT = "Patchouli/1.0 (research wiki ingest)"
TIMEOUT = 30
ARXIV_API = "https://export.arxiv.org/api/query?id_list={id}&max_results=1"
AR5IV = "https://ar5iv.labs.arxiv.org/html/{id}"
FIRECRAWL_ENDPOINT = "https://api.firecrawl.dev/v1/scrape"
ATOM = {"a": "http://www.w3.org/2005/Atom"}
_BLOCK_TAGS = {
    "p", "div", "section", "article", "li", "tr", "br", "h1", "h2",
    "h3", "h4", "h5", "h6", "blockquote", "pre", "td", "th",
}
_DROP_TAGS = {"script", "style", "head", "nav", "footer"}


@dataclass(frozen=True)
class Extraction:
    work_id: str
    source: str
    text: str
    raw_files: tuple[tuple[str, bytes], ...]


class _TextExtractor(HTMLParser):
    """Collapse HTML to text, preferring an article element when present."""

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
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw.splitlines()]
        out: list[str] = []
        blank = False
        for line in lines:
            if line:
                out.append(line)
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
    req = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", **headers},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read())


def _validate_work_id(value: str) -> str:
    if not is_valid_work_id(value):
        raise SystemExit(
            f"invalid work_id {value!r}; use one path-safe segment containing only "
            "letters, digits, dot, underscore, or hyphen"
        )
    return value


def _normalize_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        raise SystemExit(f"invalid web URL: {url!r}")
    if parts.username is not None or parts.password is not None:
        raise SystemExit("credential-bearing URLs are not accepted; use a public source URL")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))


def _locator_work_id(label: str, locator: str) -> str:
    base = slugify(label, fallback="source", max_length=80)
    digest = hashlib.sha256(locator.encode("utf-8")).hexdigest()[:10]
    return _validate_work_id(f"{base}-{digest}")


def _local_source(path: Path, workspace: Workspace) -> str:
    try:
        return workspace.relpath(path)
    except ValueError:
        return path.as_uri()


def extract_arxiv(ref: ArxivRef) -> Extraction:
    try:
        meta_xml = _get(ARXIV_API.format(id=ref.fetch_id))
    except urllib.error.URLError as exc:
        raise SystemExit(f"could not reach the arxiv API ({exc.reason}); network issue, retry")

    entry = ET.fromstring(meta_xml).find("a:entry", ATOM)
    if entry is None:
        raise SystemExit(f"arxiv: no metadata entry for {ref.fetch_id}")
    title = " ".join((entry.findtext("a:title", default="", namespaces=ATOM)).split())
    authors = ", ".join(
        name
        for author in entry.findall("a:author", ATOM)
        if (name := author.findtext("a:name", default="", namespaces=ATOM))
    )
    published = entry.findtext("a:published", default="", namespaces=ATOM)[:10]
    abstract = " ".join(entry.findtext("a:summary", default="", namespaces=ATOM).split())

    raw_files: list[tuple[str, bytes]] = [("arxiv-metadata.xml", meta_xml)]
    try:
        html_bytes = _get(AR5IV.format(id=ref.fetch_id))
        raw_files.append(("ar5iv.html", html_bytes))
        body = html_to_text(html_bytes.decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError) as exc:
        body = f"[ar5iv body unavailable: {exc}; reading surface holds the abstract only]"

    source = f"https://arxiv.org/abs/{ref.fetch_id}"
    text = (
        f"# {title}\n\n"
        f"- Source: {source}\n"
        f"- Authors: {authors}\n"
        f"- Year: {published[:4]}\n"
        f"- arXiv: {ref.fetch_id}\n"
        f"- Body source: {AR5IV.format(id=ref.fetch_id)}\n\n"
        f"## Abstract\n\n{abstract}\n\n## Body\n\n{body}\n"
    )
    return Extraction(ref.work_id, source, text, tuple(raw_files))


def extract_url(url: str, workspace: Workspace, work_id: str | None) -> Extraction:
    source = _normalize_url(url)

    def _try(key: str) -> dict:
        try:
            return _post_json(
                FIRECRAWL_ENDPOINT,
                {"url": source, "formats": ["markdown"]},
                {"Authorization": f"Bearer {key}"},
            )
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 429) or 500 <= exc.code < 600:
                detail = exc.read().decode("utf-8", "replace")[:200]
                raise KeyRetry(f"firecrawl key failed ({exc.code}): {detail}")
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise SystemExit(f"firecrawl request failed ({exc.code}): {detail}")
        except urllib.error.URLError as exc:
            raise SystemExit(
                f"could not reach Firecrawl ({exc.reason}); transient network or endpoint down, retry"
            )

    try:
        result = with_key_retry(workspace.root / ".env", "FIRECRAWL_API_KEY", _try)
    except KeyPoolExhausted as exc:
        raise SystemExit(
            "web ingest needs FIRECRAWL_API_KEY and all keys failed; set one in .env "
            f"(see .env.example), or ingest an arxiv id / local file instead. Last error: {exc}"
        )
    data = result.get("data") or {}
    markdown = data.get("markdown") or ""
    if not markdown:
        raise SystemExit(f"firecrawl returned no markdown for {source}: {json.dumps(result)[:300]}")
    title = (data.get("metadata") or {}).get("title") or source
    if work_id is None:
        parts = urlsplit(source)
        work_id = _locator_work_id(f"{parts.netloc}{parts.path}", source)
    raw = json.dumps(result, indent=2, ensure_ascii=False).encode("utf-8")
    text = f"# {title}\n\n- Source: {source}\n\n{markdown}\n"
    return Extraction(work_id, source, text, (("firecrawl.json", raw),))


def extract_file(path: Path, workspace: Workspace, work_id: str | None) -> Extraction:
    path = path.resolve()
    raw_bytes = path.read_bytes()
    source = _local_source(path, workspace)
    if work_id is None:
        work_id = _locator_work_id(path.stem, source)
    ext = path.suffix.lower()
    if ext == ".pdf":
        try:
            import pypdf
        except ImportError:
            raise SystemExit(
                "ingesting a local .pdf needs pypdf: `uv pip install -r requirements.txt` "
                "(in the project venv), or host the PDF and ingest its URL"
            )
        reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
        body = "\n\n".join((page.extract_text() or "") for page in reader.pages)
    elif ext in {".html", ".htm"}:
        body = html_to_text(raw_bytes.decode("utf-8", "replace"))
    else:
        body = raw_bytes.decode("utf-8", "replace")
    text = f"# {path.stem}\n\n- Source: {source}\n\n{body}\n"
    return Extraction(work_id, source, text, ((path.name, raw_bytes),))


def _source_page(work_id: str) -> str:
    return f"wiki/sources/{work_id}.md"


def _publish(extraction: Extraction, workspace: Workspace, surface: Path) -> None:
    raw_dir = workspace.confined(workspace.raw, extraction.work_id)
    expected: set[str] = set()
    for name, content in extraction.raw_files:
        if Path(name).name != name:
            raise ValueError(f"raw artifact name must be one path segment: {name!r}")
        expected.add(name)
        target = workspace.confined(workspace.raw, extraction.work_id, name)
        if not target.exists() or target.read_bytes() != content:
            atomic_write_bytes(target, content)
    if raw_dir.exists():
        for stale in raw_dir.iterdir():
            if stale.name in expected:
                continue
            if stale.is_dir() and not stale.is_symlink():
                shutil.rmtree(stale)
            else:
                stale.unlink()
    surface_bytes = extraction.text.encode("utf-8")
    if not surface.exists() or surface.read_bytes() != surface_bytes:
        atomic_write_text(surface, extraction.text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract a source into extracted/<work_id>/text.md")
    parser.add_argument("input", help="arxiv id/URL, http(s) URL, or local file path")
    parser.add_argument("--work-id", default=None, help="stable path-safe identity override for a web or local source")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="replace a changed current capture/surface; update and commit its source page in the same ingest",
    )
    args = parser.parse_args(argv)
    workspace = Workspace.from_path(None)
    explicit_work_id = _validate_work_id(args.work_id) if args.work_id else None

    value = args.input.strip()
    arxiv_ref = parse_arxiv_ref(value)
    if arxiv_ref:
        if explicit_work_id and explicit_work_id != arxiv_ref.work_id:
            raise SystemExit("arxiv work_id is its stable base id; --work-id cannot override it")
        extraction = extract_arxiv(arxiv_ref)
    elif value.startswith(("http://", "https://")):
        extraction = extract_url(value, workspace, explicit_work_id)
    elif Path(value).is_file():
        extraction = extract_file(Path(value), workspace, explicit_work_id)
    else:
        raise SystemExit(
            f"unrecognized input: {value!r} (not an arxiv id, an http(s) URL, or an existing file)"
        )

    work_id = _validate_work_id(extraction.work_id)
    try:
        surface = workspace.confined(workspace.extracted, work_id, "text.md")
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    version_id = content_version_id(extraction.text)
    if surface.exists() and not args.refresh:
        existing = content_version_id(surface.read_bytes())
        if existing != version_id:
            raise SystemExit(
                f"{workspace.relpath(surface)} already exists with different content "
                f"(existing {existing}, new {version_id}); no artifact was changed. "
                "If this is a new version of the same work, re-run with --refresh, then "
                "re-read and update the source page in the same commit. If it is a distinct "
                "web/local work, re-run with a stable explicit --work-id."
            )

    try:
        _publish(extraction, workspace, surface)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    title = next(
        (line[2:].strip() for line in extraction.text.splitlines() if line.startswith("# ")),
        work_id,
    )
    print(f"extracted. write the source page to:\n  {_source_page(work_id)}")
    print("put these in its frontmatter:")
    print(f"  title: {json.dumps(title, ensure_ascii=False)}")
    print("  page_type: source")
    print(f"  work_id: {work_id}")
    print(f"  version_id: {version_id}")
    print(f"  reading_surface: {workspace.relpath(surface)}")
    print(f"  source: {json.dumps(extraction.source, ensure_ascii=False)}")
    print(f"  (reading surface is {len(extraction.text):,} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
