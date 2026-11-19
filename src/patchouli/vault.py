"""Vault layout, source registry and page loading."""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from . import frontmatter as fm

STATE_DIR = ".patchouli"
PAGE_DIRS = {"source": "sources", "concept": "concepts", "synthesis": "syntheses",
             "answer": "answers", "hub": "hubs"}
PAGE_TYPES = ("source", "concept", "synthesis", "answer", "hub")
INTEGRATED_TYPES = ("concept", "synthesis", "answer")
DEFAULT_CONFIG = {"language": "auto", "taste": "mechanism", "pdf_extractor": "auto"}
SPECIAL_FILES = ("index.md", "log.md")


class VaultNotFound(Exception):
    pass


def now() -> str:
    """Local time, ISO seconds (PATCHOULI_NOW pins it, for tests)."""
    return os.environ.get("PATCHOULI_NOW") or datetime.datetime.now().isoformat(timespec="seconds")


def today() -> str:
    return now()[:10]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def stat_of(path: Path) -> tuple[int, int]:
    """(size, mtime) — unchanged means the file wasn't touched, so it needn't be re-hashed."""
    st = path.stat()
    return st.st_size, st.st_mtime_ns


def slugify(text: str, max_len: int = 60) -> str:
    text = unicodedata.normalize("NFKC", text).strip().lower()
    text = re.sub(r"[^\w\s\-.]", " ", text)
    text = re.sub(r"[\s_.]+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    if len(text) > max_len:
        text = text[:max_len].rsplit("-", 1)[0] or text[:max_len]
    return text or "untitled"


@dataclass
class Page:
    slug: str
    path: Path
    rel: str
    meta: dict
    body: str
    body_start: int
    has_frontmatter: bool

    @property
    def type(self) -> str:
        return str(self.meta.get("type", "") or "")

    @property
    def title(self) -> str:
        return str(self.meta.get("title") or self.slug)

    @property
    def summary(self) -> str:
        return str(self.meta.get("summary") or "")

    @property
    def dir(self) -> str:
        """Directory of the page, relative to the vault root (for resolving links)."""
        return self.rel.rsplit("/", 1)[0] if "/" in self.rel else ""


class Vault:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.state_dir = self.root / STATE_DIR
        self.raw_dir, self.text_dir = self.root / "raw", self.root / "text"
        self.wiki_dir, self.inbox_dir = self.root / "wiki", self.root / "inbox"
        self.index_path, self.log_path = self.wiki_dir / "index.md", self.wiki_dir / "log.md"
        self.registry_path = self.state_dir / "sources.json"
        self._registry = None

    @classmethod
    def find(cls) -> "Vault":
        cur = Path.cwd()
        for d in (cur, *cur.parents):
            if (d / STATE_DIR).is_dir():
                return cls(d)
        raise VaultNotFound("not inside a Patchouli vault (no .patchouli/ found); run `patchouli init <dir>`")

    def text_path(self, sid: str) -> Path:
        return self.text_dir / f"{sid}.md"

    def page_dir(self, ptype: str) -> Path:
        sub = PAGE_DIRS.get(ptype)
        return self.wiki_dir / sub if sub else self.wiki_dir

    def rel(self, p: Path) -> str:
        try:
            return Path(p).resolve().relative_to(self.root).as_posix()
        except ValueError:
            return str(p)

    # ---------- registry ----------
    @property
    def registry(self) -> dict:
        if self._registry is None:
            if self.registry_path.exists():
                self._registry = json.loads(self.registry_path.read_text(encoding="utf-8") or "{}")
            else:
                self._registry = {}
        return self._registry

    def save_registry(self, *sids: str) -> None:
        """Write the given entries (deleting those no longer present here) into the registry on
        disk. Re-reads the file under a lock and replaces it atomically, so two `add`s running
        at once can't erase each other's entries."""
        self.state_dir.mkdir(exist_ok=True)
        mine = self.registry
        with open(self.state_dir / "sources.lock", "a") as lock:
            try:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX)
            except ImportError:  # no flock (Windows): still atomic, just not serialized
                pass
            disk = json.loads(self.registry_path.read_text(encoding="utf-8") or "{}") \
                if self.registry_path.exists() else {}
            for sid in sids:
                if sid in mine:
                    disk[sid] = mine[sid]
                else:
                    disk.pop(sid, None)
            tmp = self.registry_path.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(dict(sorted(disk.items())), indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
            os.replace(tmp, self.registry_path)
            self._registry = disk

    def text_lines(self, sid: str) -> list[str] | None:
        p = self.text_path(sid)
        if not p.exists():
            return None
        lines = p.read_text(encoding="utf-8").split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        return lines

    def text_sha(self, sid: str) -> str | None:
        p = self.text_path(sid)
        return sha256_file(p) if p.exists() else None

    # ---------- pages ----------
    def iter_pages(self):
        if not self.wiki_dir.exists():
            return
        for p in sorted(self.wiki_dir.rglob("*.md")):
            if p.parent == self.wiki_dir and p.name in SPECIAL_FILES:
                continue
            if any(part.startswith(".") for part in p.relative_to(self.wiki_dir).parts):
                continue
            yield self.load_page(p)

    def load_page(self, p: Path) -> Page:
        text = p.read_text(encoding="utf-8")
        meta, body, start, has = fm.parse(text)
        return Page(p.stem, p, self.rel(p), meta, body, start, has)

    def find_page(self, slug: str) -> Page | None:
        for page in self.iter_pages():
            if page.slug == slug:
                return page
        return None

    def config(self) -> dict:
        p = self.state_dir / "config.json"
        cfg = dict(DEFAULT_CONFIG)
        if p.exists():
            cfg.update(json.loads(p.read_text(encoding="utf-8")))
        return cfg
