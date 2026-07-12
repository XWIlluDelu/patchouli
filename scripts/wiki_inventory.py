from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import posixpath
import re
from urllib.parse import unquote, urlsplit

from workspace_paths import Workspace

PAGE_DIRS = {
    "sources": "source",
    "answers": "answer",
    "concepts": "concept",
    "entities": "entity",
    "syntheses": "synthesis",
    "hubs": "hub",
    "indexes": "index",
}
PAGE_TYPES = set(PAGE_DIRS.values())
DURABLE_TYPES = {"concept", "entity", "synthesis"}

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
WORK_MARKER_RE = re.compile(r"\((?:synthesis across\s+)?Works?:\s*([^)]+)\)")
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
MD_LINK_RE = re.compile(
    r"\]\(\s*(?:<([^>\n]+)>|([^\s)]+))"
    r"(?:\s+(?:\"[^\"\n]*\"|'[^'\n]*'|\([^()\n]*\)))?\s*\)"
)


@dataclass(frozen=True)
class LinkRef:
    kind: str
    target: str


@dataclass(frozen=True)
class PageRecord:
    path: str
    wiki_path: str
    page_type: str
    title: str
    aliases: tuple[str, ...]
    work_ids: tuple[str, ...]
    frontmatter: dict[str, str]
    body: str
    links: tuple[LinkRef, ...]


@dataclass(frozen=True)
class WikiInventory:
    pages: tuple[PageRecord, ...]
    problems: tuple[str, ...] = field(default_factory=tuple)

    def by_path(self) -> dict[str, PageRecord]:
        return {page.path: page for page in self.pages}

    def by_type(self, page_type: str) -> list[PageRecord]:
        return [page for page in self.pages if page.page_type == page_type]


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse scalar, inline-list, and block-list YAML frontmatter; return (metadata, body).

    Block lists are normalized to inline form ("[a, b]") so values round-trip
    through parse_inline_list and frontmatter re-serialization.
    """

    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    metadata: dict[str, str] = {}
    block_key: str | None = None
    block_items: list[str] = []

    def close_block() -> None:
        nonlocal block_key, block_items
        if block_key is not None and block_items:
            metadata[block_key] = "[" + ", ".join(block_items) + "]"
        block_key, block_items = None, []

    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if block_key is not None and line.startswith("- "):
            block_items.append(line[2:].strip().strip("\"'`"))
            continue
        close_block()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip().strip("\"'")
        metadata[key.strip()] = value
        if not value:
            block_key = key.strip()
    close_block()
    return metadata, text[match.end() :]


def parse_inline_list(value: str) -> tuple[str, ...]:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1]
        return tuple(
            item.strip().strip("\"'`") for item in inner.split(",") if item.strip()
        )
    return (value.strip().strip("\"'`"),) if value else ()


def work_ids_from_text(body: str) -> tuple[str, ...]:
    found: list[str] = []
    for match in WORK_MARKER_RE.finditer(body):
        for token in match.group(1).split(","):
            token = token.strip().strip("`")
            if token and token not in found:
                found.append(token)
    return tuple(found)


def _is_latex_double_bracket(body: str, match: re.Match[str]) -> bool:
    """Return whether a ``[[...]]`` match is glued-on LaTeX notation."""

    start = match.start()
    if start == 0:
        return False
    prev = body[start - 1]
    return not prev.isspace() and prev not in {
        "(",
        "[",
        "{",
        "-",
        ">",
        ",",
        ";",
        ":",
    }


def links_from_text(body: str) -> tuple[LinkRef, ...]:
    links: list[LinkRef] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, target: str) -> None:
        key = (kind, target)
        if target and key not in seen:
            seen.add(key)
            links.append(LinkRef(kind, target))

    for match in WIKILINK_RE.finditer(body):
        if not _is_latex_double_bracket(body, match):
            add("wikilink", match.group(1).strip())
    for match in MD_LINK_RE.finditer(body):
        target = (match.group(1) or match.group(2)).strip()
        parsed = urlsplit(target)
        if (
            not parsed.scheme
            and not parsed.netloc
            and unquote(parsed.path).endswith(".md")
        ):
            add("markdown", target)
    return tuple(links)


def link_key(target: str) -> str:
    """Normalize one bare wiki name for title/alias/stem lookup."""

    value = target.removesuffix(".md")
    return re.sub(r"\s+", " ", value.strip()).casefold()


def link_target_map(inventory: WikiInventory) -> dict[str, tuple[str, ...]]:
    """Map each bare name to every page that claims it."""

    targets: dict[str, set[str]] = {}
    for page in inventory.pages:
        values = [Path(page.path).stem, page.title, *page.aliases]
        if page.page_type == "source":
            values.extend(page.work_ids)
        for value in values:
            key = link_key(value)
            if key:
                targets.setdefault(key, set()).add(page.path)
    return {key: tuple(sorted(paths)) for key, paths in targets.items()}


def _wiki_root_path(target: str) -> str | None:
    raw = unquote(target.split("#", 1)[0])
    if not raw or raw.startswith("/") or "\\" in raw:
        return None
    if not raw.endswith(".md"):
        raw += ".md"
    normalized = posixpath.normpath(posixpath.join("wiki", raw))
    return normalized if normalized.startswith("wiki/") else None


def _markdown_path(page: PageRecord, target: str) -> str | None:
    parsed = urlsplit(target)
    raw = unquote(parsed.path)
    if not raw or raw.startswith("/") or "\\" in raw:
        return None
    normalized = posixpath.normpath(posixpath.join(posixpath.dirname(page.path), raw))
    return normalized if normalized.startswith("wiki/") else None


@dataclass(frozen=True)
class LinkResolver:
    paths: frozenset[str]
    names: dict[str, tuple[str, ...]]

    @classmethod
    def from_inventory(cls, inventory: WikiInventory) -> "LinkResolver":
        return cls(frozenset(inventory.by_path()), link_target_map(inventory))

    def resolve(self, page: PageRecord, link: LinkRef) -> tuple[str, ...]:
        """Resolve one link without discarding explicit paths or ambiguity."""

        if link.kind == "markdown":
            target = _markdown_path(page, link.target)
            return (target,) if target in self.paths else ()
        if "/" in link.target:
            target = _wiki_root_path(link.target)
            return (target,) if target in self.paths else ()
        return self.names.get(link_key(link.target), ())


def page_type_for(workspace: Workspace, path: Path) -> str:
    rel = workspace.relpath(path)
    if rel == "wiki/index.md" or rel == "wiki/recent.md":
        return "index"
    parts = Path(rel).parts
    if len(parts) >= 3 and parts[0] == "wiki":
        return PAGE_DIRS.get(parts[1], "unknown")
    return "unknown"


def scan_wiki(workspace: Workspace) -> WikiInventory:
    pages: list[PageRecord] = []
    problems: list[str] = []
    if not workspace.wiki.exists():
        return WikiInventory(pages=())
    for path in sorted(workspace.wiki.rglob("*.md")):
        rel = workspace.relpath(path)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            problems.append(f"{rel}: unreadable ({exc})")
            continue
        metadata, body = parse_frontmatter(text)
        page_type = metadata.get("page_type") or page_type_for(workspace, path)
        title = metadata.get("title") or next(
            (line[2:].strip() for line in body.splitlines() if line.startswith("# ")),
            path.stem,
        )
        work_ids = parse_inline_list(metadata.get("work_ids", ""))
        if not work_ids:
            work_ids = work_ids_from_text(body)
        pages.append(
            PageRecord(
                path=rel,
                wiki_path=rel.removeprefix("wiki/"),
                page_type=page_type,
                title=title,
                aliases=parse_inline_list(metadata.get("aliases", "")),
                work_ids=work_ids,
                frontmatter=metadata,
                body=body,
                links=links_from_text(body),
            )
        )
    return WikiInventory(pages=tuple(pages), problems=tuple(problems))
