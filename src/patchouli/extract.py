"""Raw material -> reading text.

Reading text is line-addressable Markdown that pages cite by line
(`../../text/<id>.md#L5-L9`). Extraction is deterministic; nobody edits it by hand.
A better conversion made elsewhere can be imported with `patchouli extract ID --from`.
"""
from __future__ import annotations

import html
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

TEXT_EXTS = {".md", ".markdown", ".txt", ".text", ".rst", ".org", ".tex", ".csv", ".json", ".yaml", ".yml"}
HTML_EXTS = {".html", ".htm", ".xhtml"}
PDF_EXTS = {".pdf"}


class ExtractError(Exception):
    pass


def tidy(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    lines = [l.rstrip() for l in text.split("\n")]
    out, blank = [], 0
    for l in lines:
        blank = blank + 1 if not l else 0
        if blank <= 1:
            out.append(l)
    while out and not out[0]:
        out.pop(0)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- HTML
class _HTMLToMarkdown(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "form", "button", "iframe", "template", "aside"}
    BLOCK = {"p", "div", "section", "article", "main", "header", "ul", "ol", "dl", "table", "tr", "blockquote",
             "figure", "figcaption", "dt", "dd", "hr", "details", "summary"}

    def __init__(self, restrict: bool = False):
        super().__init__(convert_charrefs=True)
        self.restrict = restrict  # page marks its main content: keep only <main>/<article>
        self.main = 0
        self.out: list[str] = []
        self.skip = 0
        self.pre = 0
        self.title = ""
        self._in_title = False
        self.list_depth = 0
        self._scripts: list = []

    def _nl(self, n=1):
        if not self.out:
            return
        tail = "".join(self.out[-4:]).rstrip(" ")
        have = len(tail) - len(tail.rstrip("\n"))
        if have < n:
            self.out.append("\n" * (n - have))

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
            return
        if tag in ("main", "article"):
            self.main += 1
        if self.skip or (self.restrict and not self.main and tag != "title"):
            return
        if tag == "title":
            self._in_title = True
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._nl(2)
            self.out.append("#" * int(tag[1]) + " ")
        elif tag == "li":
            self._nl(1)
            self.out.append("  " * max(self.list_depth - 1, 0) + "- ")
        elif tag in ("ul", "ol"):
            self.list_depth += 1
            self._nl(1)
        elif tag == "pre":
            self.pre += 1
            self._nl(2)
            self.out.append("```\n")
        elif tag == "br":
            self.out.append("\n")
        elif tag in ("sup", "sub"):
            self._scripts.append((tag, len(self.out)))
        elif tag in ("td", "th"):
            self.out.append(" | ")
        elif tag == "img":
            alt = dict(attrs).get("alt")
            if alt:
                self.out.append(f"[image: {alt}]")
        elif tag in self.BLOCK:
            self._nl(2)

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip or (self.restrict and not self.main and tag != "title"):
            return
        if tag in ("main", "article"):
            self.main = max(0, self.main - 1)
            self._nl(2)
        elif tag == "title":
            self._in_title = False
        elif tag in ("sup", "sub") and self._scripts:
            kind, i = self._scripts.pop()
            content = "".join(self.out[i:]).strip()
            del self.out[i:]
            if content:  # 10<sup>3</sup> → 10^3, 10<sup>-12</sup> → 10^-12, H<sub>2</sub>O → H_2O
                simple = re.fullmatch(r"[-+−]?\w+", content)
                self.out.append(("^" if kind == "sup" else "_") + (content if simple else f"({content})"))
        elif tag in ("ul", "ol"):
            self.list_depth = max(0, self.list_depth - 1)
            self._nl(2)
        elif tag == "pre":
            self.pre = max(0, self.pre - 1)
            self._nl(1)
            self.out.append("```")
            self._nl(2)
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6") or tag in self.BLOCK:
            self._nl(2)

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        if self.skip or (self.restrict and not self.main):
            return
        if self.pre:
            self.out.append(data)
        else:
            text = re.sub(r"\s+", " ", data)
            if self.out and self.out[-1].endswith(("\n", "- ", "# ")):
                text = text.lstrip()
            if text:
                self.out.append(text)


def html_to_markdown(src: str) -> tuple[str, str]:
    p = _HTMLToMarkdown(restrict=bool(re.search(r"<(main|article)\b", src, re.I)))
    p.feed(src)
    p.close()
    lines = [re.sub(r"[ \t]+$", "", l) for l in "".join(p.out).split("\n")]
    return tidy("\n".join(lines)), html.unescape(p.title.strip())


def _decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):  # UTF-16 only with a byte-order mark: almost any
        return data.decode("utf-16")                    # byte string "decodes" as UTF-16 otherwise
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    m = re.search(rb'charset=["\']?([\w\-]+)', data[:4000])
    if m:
        try:
            return data.decode(m.group(1).decode())
        except (LookupError, UnicodeDecodeError):
            pass
    return data.decode("latin-1")


# ---------------------------------------------------------------- PDF
def docling_available() -> bool:
    try:
        import docling  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False


def docling_to_text(path: Path) -> tuple[str, str]:
    """High-quality profile: layout model, OCR, table structure, formulas; local only, one
    `<!-- page N -->` marker per page so locators can be related to printed pages."""
    import os
    from importlib.metadata import version

    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions  # type: ignore
    from docling.datamodel.base_models import InputFormat  # type: ignore
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions  # type: ignore
    from docling.document_converter import DocumentConverter, PdfFormatOption  # type: ignore

    options = PdfPipelineOptions(
        do_ocr=True, do_table_structure=True, do_formula_enrichment=True, enable_remote_services=False,
        ocr_options=RapidOcrOptions(backend="onnxruntime", lang=["ch"]),  # its Chinese model also reads English
        accelerator_options=AcceleratorOptions(device=AcceleratorDevice.AUTO, num_threads=min(8, os.cpu_count() or 1)))
    conv = DocumentConverter(allowed_formats=[InputFormat.PDF],
                             format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
    doc = conv.convert(str(path), raises_on_error=True).document
    text = "\n".join(f"<!-- page {n} -->\n{doc.export_to_markdown(page_no=n, compact_tables=False).strip()}\n"
                     for n in sorted(doc.pages))
    if not any(ch.isalnum() for ch in text):
        raise ExtractError("Docling produced no readable text (blank, encrypted or damaged PDF?)")
    return tidy(text), f"docling=={version('docling')}"


def _pdf_pages(path: Path) -> tuple[list[str], str]:
    try:
        import pypdf  # type: ignore

        reader = pypdf.PdfReader(str(path))
        return [pg.extract_text() or "" for pg in reader.pages], "pypdf"
    except ImportError:
        pass
    exe = shutil.which("pdftotext")
    if exe:
        res = subprocess.run([exe, "-enc", "UTF-8", str(path), "-"], capture_output=True)
        if res.returncode != 0:
            raise ExtractError(f"pdftotext failed: {res.stderr.decode(errors='replace').strip()}")
        pages = res.stdout.decode("utf-8", errors="replace").split("\f")
        if pages and not pages[-1].strip():
            pages.pop()
        return pages, "pdftotext"
    raise ExtractError("no PDF extractor: install the pdf-quality extra (Docling), `pypdf`, or poppler's "
                       "`pdftotext` — or convert externally and use `patchouli extract ID --from FILE.md`")


def _heading(text: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return m.group(1).strip() if m else ""


def _first_line(text: str) -> str:
    """The first line that reads like a title (PDFs often carry no title metadata)."""
    for line in text.split("\n")[:40]:
        line = line.strip().lstrip("#").strip()
        if 8 <= len(line) <= 200 and not line.startswith(("<!--", "arXiv:")) and re.search(r"[^\W\d]{3}", line):
            return line
    return ""


def pdf_title(path: Path) -> str:
    exe = shutil.which("pdfinfo")
    if not exe:
        return ""
    res = subprocess.run([exe, "-enc", "UTF-8", str(path)], capture_output=True)
    m = re.search(r"^Title:[ \t]*(\S.*)$", res.stdout.decode("utf-8", "replace"), re.M)
    title = m.group(1).strip() if m else ""
    bad = title.lower() in ("untitled", "") or title.lower().endswith((".dvi", ".doc", ".docx", ".tex"))
    return "" if bad else title


def pdf_to_text(path: Path, mode: str = "auto") -> tuple[str, str, str]:
    """Return (text, extractor, quality). mode: auto | docling | basic."""
    if mode == "docling" or (mode == "auto" and docling_available()):
        if not docling_available():
            raise ExtractError("pdf_extractor is 'docling' but Docling is not installed "
                               "(pip install 'patchouli[pdf-quality]')")
        try:
            text, tool = docling_to_text(path)
        except Exception as e:  # Docling raises many types; report, don't crash
            raise e if isinstance(e, ExtractError) else ExtractError(f"Docling failed on {path.name}: {e}") from e
        return text, tool, "high"
    pages, tool = _pdf_pages(path)
    parts = [f"<!-- page {i} -->\n{tidy(page).rstrip()}\n" for i, page in enumerate(pages, 1)]
    return tidy("\n".join(parts)), tool, "basic"


# ---------------------------------------------------------------- dispatch
def extract(path: Path, pdf_mode: str = "auto") -> tuple[str, str, str, str]:
    """Return (reading_text, extractor_name, quality, detected_title)."""
    ext = path.suffix.lower()
    if ext in PDF_EXTS:
        text, tool, quality = pdf_to_text(path, pdf_mode)
        return text, tool, quality, pdf_title(path) or _first_line(text)
    data = path.read_bytes()
    if ext in HTML_EXTS or (ext == "" and b"<html" in data[:2000].lower()):
        text, title = html_to_markdown(_decode(data))
        return text, "html", "good", _heading(text) or title  # <title> often carries the site name
    if ext in TEXT_EXTS or ext == "":
        text = tidy(_decode(data))
        return text, "plain", "exact", _heading(text)
    raise ExtractError(f"don't know how to extract '{ext}' files; convert externally and use "
                       "`patchouli extract ID --from FILE.md`")
