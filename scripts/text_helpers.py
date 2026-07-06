from __future__ import annotations

import hashlib
import re


def slugify(value: str, *, fallback: str = "untitled", max_length: int = 96) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip("-._")
    slug = re.sub(r"-+", "-", slug)
    return (slug or fallback)[:max_length]


def content_version_id(data: bytes | str) -> str:
    """Content hash of a reading surface. extract.py mints it as the source
    version_id; check_wiki verifies the page still matches the surface it claims."""

    if isinstance(data, str):
        data = data.encode("utf-8")
    return "sha256-" + hashlib.sha256(data).hexdigest()[:16]
