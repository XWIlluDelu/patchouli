"""Unified source extraction for Patchouli.

Dispatches by input type and writes the reading surface the agent compiles into a
source page:

    python3 scripts/extract.py <input> [--work-id ID] [--refresh]

Inputs:
  - arxiv id or arxiv URL: arxiv API metadata + ar5iv body, no key
  - http(s) URL: Firecrawl, using FIRECRAWL_API_KEY
  - local .pdf/.html/.htm/.md/.txt file: local extraction

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
import filecmp
import hashlib
import io
import json
import os
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
SUPPORTED_LOCAL_SUFFIXES = {".pdf", ".html", ".htm", ".md", ".txt"}
DOCLING_LAYOUT_REVISION = "8f39ad3c0b4c58e9c2d2c84a38465abf757272d8"
DOCLING_FORMULA_REVISION = "ecedbe111d15c2dc60bfd4a823cbe80127b58af4"


@dataclass(frozen=True)
class Extraction:
    work_id: str
    source: str
    text: str
    raw_files: tuple[tuple[str, bytes], ...]


def _clean_markdown(markdown: str) -> str:
    return markdown.strip() + "\n" if markdown.strip() else ""


def html_to_markdown(html: str) -> str:
    """Convert captured HTML into structured Markdown without executing it."""

    try:
        from bs4 import BeautifulSoup
        from markdownify import markdownify
    except ImportError as exc:
        raise SystemExit(
            "HTML extraction needs Beautiful Soup and markdownify: "
            "`uv pip install -r requirements.txt`"
        ) from exc

    soup = BeautifulSoup(html, "html.parser")
    for element in soup.select("script, style, head, nav, footer"):
        element.decompose()
    root = soup.find("article") or soup.body or soup
    markdown = _clean_markdown(markdownify(str(root), heading_style="ATX", bullets="-"))
    if not markdown:
        raise SystemExit("HTML conversion produced no readable content")
    return markdown


def _pdf_pipeline_options():
    from docling.datamodel.accelerator_options import (
        AcceleratorDevice,
        AcceleratorOptions,
    )
    from docling.datamodel.layout_model_specs import DOCLING_LAYOUT_HERON
    from docling.datamodel.pipeline_options import (
        CodeFormulaVlmOptions,
        HeadingHierarchyOptions,
        LayoutOptions,
        PdfPipelineOptions,
        RapidOcrOptions,
    )

    layout_spec = DOCLING_LAYOUT_HERON.model_copy(
        update={"revision": DOCLING_LAYOUT_REVISION}
    )
    code_formula = CodeFormulaVlmOptions.from_preset("codeformulav2")
    code_formula = code_formula.model_copy(
        update={
            "model_spec": code_formula.model_spec.model_copy(
                update={"revision": DOCLING_FORMULA_REVISION}
            )
        }
    )
    return PdfPipelineOptions(
        accelerator_options=AcceleratorOptions(
            device=AcceleratorDevice.AUTO,
            num_threads=min(8, os.cpu_count() or 1),
        ),
        do_ocr=True,
        ocr_options=RapidOcrOptions(backend="onnxruntime", lang=["chinese"]),
        do_table_structure=True,
        do_formula_enrichment=True,
        layout_options=LayoutOptions(model_spec=layout_spec),
        code_formula_options=code_formula,
        heading_hierarchy_options=HeadingHierarchyOptions(
            enabled=True,
            use_bookmarks=True,
            use_numbering=True,
            use_style=False,
        ),
        enable_remote_services=False,
    )


def pdf_to_markdown(data: bytes, name: str) -> str:
    """Convert one captured PDF with the benchmarked local Docling pipeline."""

    try:
        from docling.datamodel.base_models import DocumentStream, InputFormat
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.exceptions import ConversionError
    except ImportError as exc:
        raise SystemExit(
            "ingesting a local .pdf needs Docling: `uv pip install -r requirements.txt`"
        ) from exc

    try:
        options = _pdf_pipeline_options()
        converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
        )
        stream = DocumentStream(name=name, stream=io.BytesIO(data))
        result = converter.convert(stream, raises_on_error=True)
        markdown = _clean_markdown(
            result.document.export_to_markdown(compact_tables=False)
        )
    except (ConversionError, OSError, RuntimeError) as exc:
        raise SystemExit(f"could not convert PDF to Markdown: {exc}") from exc
    if not any(character.isalnum() for character in markdown):
        raise SystemExit(
            "PDF conversion produced no readable text; the document may be blank, "
            "encrypted, damaged, or beyond the OCR pipeline"
        )
    return markdown


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", flags=re.MULTILINE)


def _heading_text(markdown_heading: str) -> str:
    return re.sub(r"[*_`]+", "", markdown_heading).strip()


def _markdown_title(markdown: str, fallback: str, *, structured: bool = False) -> str:
    first = _HEADING_RE.search(markdown)
    if first is None:
        return fallback
    title = _heading_text(first.group(2))
    if first.group(1) == "#" and not markdown[: first.start()].strip():
        return title or fallback
    if structured and slugify(title) == slugify(fallback):
        return title or fallback
    return fallback


def _drop_title_heading(
    markdown: str, title: str, *, authoritative: bool = False
) -> str:
    first = _HEADING_RE.search(markdown)
    if first is None or _heading_text(first.group(2)).casefold() != title.casefold():
        return markdown
    leading_title = first.group(1) == "#" and not markdown[: first.start()].strip()
    if not leading_title and not authoritative:
        return markdown
    return _clean_markdown(markdown[: first.start()] + markdown[first.end() :])


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


def _local_identity(
    path: Path, workspace: Workspace, work_id: str | None
) -> tuple[Path, str, str, str]:
    path = path.resolve()
    ext = path.suffix.lower()
    if ext not in SUPPORTED_LOCAL_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_LOCAL_SUFFIXES))
        raise SystemExit(
            f"unsupported local file type {ext or '<none>'!r}; supported types: {supported}"
        )
    source = _local_source(path, workspace)
    identity = _validate_work_id(work_id) if work_id else _locator_work_id(path.stem, source)
    return path, ext, source, identity


def _reusable_local_extraction(
    path: Path, workspace: Workspace, work_id: str | None
) -> Extraction | None:
    path, _, source, identity = _local_identity(path, workspace, work_id)
    try:
        raw = workspace.confined(workspace.raw, identity, path.name)
        surface = workspace.confined(workspace.extracted, identity, "text.md")
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if not raw.is_file() or not surface.is_file():
        return None
    if raw.stat().st_size != path.stat().st_size or not filecmp.cmp(
        path, raw, shallow=False
    ):
        return None
    text = surface.read_text(encoding="utf-8")
    source_match = re.search(r"^- Source:\s*(.+?)\s*$", text, flags=re.MULTILINE)
    if source_match is None or source_match.group(1) != source:
        return None
    return Extraction(identity, source, text, ())


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
        body = html_to_markdown(html_bytes.decode("utf-8", "replace"))
        body = _drop_title_heading(body, title, authoritative=True)
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
    markdown = _drop_title_heading(markdown, title, authoritative=True)
    if work_id is None:
        parts = urlsplit(source)
        work_id = _locator_work_id(f"{parts.netloc}{parts.path}", source)
    raw = json.dumps(result, indent=2, ensure_ascii=False).encode("utf-8")
    text = f"# {title}\n\n- Source: {source}\n\n{markdown}\n"
    return Extraction(work_id, source, text, (("firecrawl.json", raw),))


def extract_file(path: Path, workspace: Workspace, work_id: str | None) -> Extraction:
    path, ext, source, work_id = _local_identity(path, workspace, work_id)
    raw_bytes = path.read_bytes()
    if ext == ".pdf":
        body = pdf_to_markdown(raw_bytes, path.name)
    else:
        try:
            decoded = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SystemExit(f"local {ext} input is not valid UTF-8: {path}") from exc
        body = html_to_markdown(decoded) if ext in {".html", ".htm"} else decoded
    structured = ext in {".pdf", ".html", ".htm"}
    title = _markdown_title(body, path.stem, structured=structured)
    first_heading = _HEADING_RE.search(body)
    inferred_from_name = bool(
        structured
        and first_heading
        and slugify(_heading_text(first_heading.group(2))) == slugify(path.stem)
    )
    body = _drop_title_heading(body, title, authoritative=inferred_from_name)
    text = f"# {title}\n\n- Source: {source}\n\n{body.rstrip()}\n"
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
    reused = False
    if arxiv_ref:
        if explicit_work_id and explicit_work_id != arxiv_ref.work_id:
            raise SystemExit("arxiv work_id is its stable base id; --work-id cannot override it")
        extraction = extract_arxiv(arxiv_ref)
    elif value.startswith(("http://", "https://")):
        extraction = extract_url(value, workspace, explicit_work_id)
    elif Path(value).is_file():
        local_path = Path(value)
        extraction = None
        if not args.refresh:
            extraction = _reusable_local_extraction(
                local_path, workspace, explicit_work_id
            )
            reused = extraction is not None
        if extraction is None:
            extraction = extract_file(local_path, workspace, explicit_work_id)
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

    if not reused:
        try:
            _publish(extraction, workspace, surface)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    title = _markdown_title(extraction.text, work_id)
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
