from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from urllib.parse import urlsplit

ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")
ARXIV_ROUTE_RE = re.compile(r"/(?:abs|pdf|html)/(\d{4}\.\d{4,5})(v\d+)?(?:\.pdf)?/?")
AR5IV_ROUTE_RE = re.compile(r"/html/(\d{4}\.\d{4,5})(v\d+)?/?")
WORK_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


@dataclass(frozen=True)
class ArxivRef:
    work_id: str
    fetch_id: str


def parse_arxiv_ref(value: str) -> ArxivRef | None:
    stripped = value.strip()
    match = ARXIV_ID_RE.fullmatch(stripped)
    if match is None:
        parts = urlsplit(stripped)
        host = (parts.hostname or "").lower()
        if host in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
            match = ARXIV_ROUTE_RE.fullmatch(parts.path)
        elif host == "ar5iv.labs.arxiv.org":
            match = AR5IV_ROUTE_RE.fullmatch(parts.path)
        else:
            return None
    if match is None:
        return None
    work_id = match.group(1)
    return ArxivRef(work_id=work_id, fetch_id=work_id + (match.group(2) or ""))


def is_valid_work_id(value: str) -> bool:
    return bool(WORK_ID_RE.fullmatch(value)) and value not in {".", ".."}


def slugify(value: str, *, fallback: str = "untitled", max_length: int = 96) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip("-._")
    slug = re.sub(r"-+", "-", slug)
    return (slug or fallback)[:max_length]


def content_version_id(data: bytes | str) -> str:
    """Return the version identifier used to bind a page to its reading surface."""

    if isinstance(data, str):
        data = data.encode("utf-8")
    return "sha256-" + hashlib.sha256(data).hexdigest()[:16]
