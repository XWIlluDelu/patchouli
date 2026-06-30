from __future__ import annotations

import re


def slugify(value: str, *, fallback: str = "untitled", max_length: int = 96) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip("-._")
    slug = re.sub(r"-+", "-", slug)
    return (slug or fallback)[:max_length]
