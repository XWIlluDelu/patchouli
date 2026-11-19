"""`patchouli` command line: the deterministic half of the agent/tool division of labor.

The agent does the reading, writing and judging; these commands do the parts a
script does better: extraction, line-addressed reading, search, the graph and
index, change tracking, checks, the log and version snapshots.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import shutil
import sqlite3
import subprocess
import sys
import urllib.parse
import urllib.request
from importlib import resources
from pathlib import Path

from . import __version__
from . import check as checkmod
from . import db
from . import extract as ex
from . import frontmatter as fm
from . import graph as graphmod
from . import markup
from . import relocate
from . import search as searchmod
from . import state as statemod
from .vault import DEFAULT_CONFIG, PAGE_TYPES, STATE_DIR, Vault, VaultNotFound, now, sha256_file, slugify, stat_of, today


def die(msg: str, code: int = 2):
    print(f"patchouli: {msg}", file=sys.stderr)
    sys.exit(code)


def _template_root():
    return resources.files("patchouli") / "templates" / "vault"


# ====================================================================== init
def _copy_tree(src, dst: Path, created: list[str], root: Path):
    for item in src.iterdir():
        name = item.name
        if name == "__pycache__":
            continue
        if name.startswith("dot_"):
            name = "." + name[4:]
        target = dst / name
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            _copy_tree(item, target, created, root)
        elif not target.exists():
            target.write_bytes(item.read_bytes())
            created.append(target.relative_to(root).as_posix())


def cmd_init(a):
    root = Path(a.dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    _copy_tree(_template_root(), root, created, root)
    state = root / STATE_DIR
    state.mkdir(exist_ok=True)
    cfg = state / "config.json"
    if not cfg.exists():
        data = {**DEFAULT_CONFIG, "language": a.language, "created": today(), "patchouli": __version__}
        cfg.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    if not (state / "sources.json").exists():
        (state / "sources.json").write_text("{}\n")
    v = Vault(root)
    g = graphmod.build(v)
    st, _, _ = statemod.current(v, g)
    statemod.save(v, st)
    graphmod.write_index(v, g, st)
    if not a.no_git and not (root / ".git").exists() and shutil.which("git"):
        subprocess.run(["git", "init", "-q", str(root)], check=False)
    print(f"Patchouli vault ready at {root} ({len(created)} files)")
    print("Next: start your agent in this folder and tell it what you are researching; give it "
          "papers as paths or URLs, or drop them into inbox/. It drafts your research goals in "
          "wiki/hubs/overview.md from what you ask; correct them there or in conversation.")


# ====================================================================== add / extract
_URL_RE = re.compile(r"^https?://", re.I)


def _unique_id(v: Vault, base: str) -> str:
    sid, i = base, 2
    slugs = {p.slug for p in v.iter_pages()}
    while sid in v.registry or sid in slugs:
        sid, i = f"{base}-{i}", i + 1
    return sid


def _fetch(url: str) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": f"Mozilla/5.0 (compatible; Patchouli/{__version__})"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
        ctype = r.headers.get_content_type() or ""
    path_ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if "pdf" in ctype or path_ext == ".pdf":
        ext = ".pdf"
    elif "html" in ctype or "xml" in ctype:
        ext = ".html"
    elif ctype.startswith("text/"):
        ext = ".md" if path_ext in (".md", ".markdown") else ".txt"
    else:
        ext = path_ext or ".bin"
    return data, ext  # the title comes from extraction, as for files


def register(v: Vault, target: str, a) -> str | None:
    v.raw_dir.mkdir(exist_ok=True)
    if _URL_RE.match(target):
        data, ext = _fetch(target)
        u = urllib.parse.urlparse(target)
        name = re.sub(r"\.(pdf|html?)$", "", Path(u.path).name, flags=re.I)  # not .stem: 1902.10186
        stem, origin, src = urllib.parse.unquote(name) or u.netloc, target, None
    else:
        src = Path(target).expanduser().resolve()
        if not src.is_file():
            print(f"skip: {target} is not a file")
            return None
        data, ext, stem, origin = None, src.suffix.lower(), src.stem, v.rel(src)
    digest = hashlib.sha256(data if data is not None else src.read_bytes()).hexdigest()
    for sid, e in v.registry.items():
        if e.get("raw_sha256") == digest:
            print(f"skip: {target} is already registered as `{sid}`")
            return None
    if a.id and (a.id in v.registry):
        die(f"source id `{a.id}` already exists")
    sid = a.id or _unique_id(v, slugify(a.title or stem, 50))
    dest = v.raw_dir / f"{sid}{ext}"
    if data is not None:
        dest.write_bytes(data)
    elif v.inbox_dir in src.parents:  # inbox is a drop zone: move. Anything else (incl. notes/): copy.
        shutil.move(str(src), dest)
    else:
        shutil.copy2(src, dest)
    v.registry[sid] = {
        "title": a.title or stem,
        "title_auto": not a.title,
        "raw": v.rel(dest),
        "origin": origin,
        "added": today(),
        "raw_sha256": digest,
        "raw_stat": list(stat_of(dest)),
        "text": None,
        "text_sha256": None,
        "lines": 0,
        "extractor": None,
    }
    v.save_registry(sid)
    print(f"registered `{sid}` ← {origin}")
    return sid


def do_extract(v: Vault, sid: str, from_file: str | None = None, force: bool = False) -> bool:
    e = v.registry.get(sid)
    if e is None:
        die(f"unknown source `{sid}`")
    tp = v.text_path(sid)
    old = sha256_file(tp) if tp.exists() else None
    if old and not force and not from_file and old == e.get("text_sha256"):
        print(f"`{sid}`: reading text up to date ({e.get('lines')} lines)")
        return True
    try:
        if from_file:
            text = ex.tidy(Path(from_file).read_text(encoding="utf-8"))
            tool, quality, title = f"import:{Path(from_file).name}", "imported", ""
        else:
            text, tool, quality, title = ex.extract(v.root / e["raw"], v.config().get("pdf_extractor", "auto"))
    except ex.ExtractError as err:
        print(f"`{sid}`: {err}", file=sys.stderr)
        return False
    old_lines = v.text_lines(sid) if old else None
    v.text_dir.mkdir(exist_ok=True)
    tp.write_text(text, encoding="utf-8")
    new = sha256_file(tp)
    new_lines = v.text_lines(sid) or []
    n = len(new_lines)
    e.update(text=v.rel(tp), text_sha256=new, lines=n, extractor=tool, quality=quality, extracted=today())
    if title and e.pop("title_auto", False):
        e["title"] = title
    v.save_registry(sid)
    print(f"`{sid}`: {n} lines of reading text via {tool} → {v.rel(tp)}")
    if old_lines is not None and old != new:
        r = relocate.relocate(v, sid, old_lines, new_lines)
        if r["pages"]:
            print(f"  citations carried over to the new text: {r['moved']} moved in {len(r['pages'])} page(s)"
                  + (f"; {r['unresolved']} could not be located and are marked `#L…?` — find those passages "
                     "again" if r["unresolved"] else ""))
        if v.find_page(sid):
            print(f"  ! reading text changed: re-read source page `{sid}` against it")
    if quality == "basic":
        print("  ! basic PDF extraction — tables/formulas may be damaged; install the pdf-quality extra for "
              "Docling, or import a better conversion with --from")
    if n < 5:
        print("  ! very little text — scanned or image-only? Convert externally and use --from FILE.md")
    return True


def cmd_add(a):
    v = Vault.find()
    targets = a.targets
    if not targets:
        targets = [str(p) for p in sorted(v.inbox_dir.iterdir()) if p.is_file() and not p.name.startswith(".")] \
            if v.inbox_dir.exists() else []
        if not targets:
            print("inbox/ is empty")
            return
    if (a.id or a.title) and len(targets) > 1:
        die("--id/--title apply to a single target")
    ok = True
    for t in targets:
        try:
            sid = register(v, t, a)
        except OSError as err:
            print(f"failed: {t}: {err}", file=sys.stderr)
            ok = False
            continue
        if sid and not a.no_extract:
            ok = do_extract(v, sid) and ok
    sys.exit(0 if ok else 1)


def cmd_extract(a):
    v = Vault.find()
    ids = list(v.registry) if a.all else a.ids
    if not ids:
        die("give source ids or --all")
    if a.from_file and len(ids) != 1:
        die("--from needs exactly one source id")
    ok = all([do_extract(v, sid, a.from_file, a.force) for sid in ids])
    sys.exit(0 if ok else 1)


# ====================================================================== read
def _parse_range(s: str) -> tuple[int, int]:
    m = re.match(r"^L?(\d+)(?:-L?(\d+))?$", s.strip())
    if not m:
        die(f"bad range `{s}` (use 120-180 or L120-L180)")
    return int(m.group(1)), int(m.group(2) or m.group(1))


def cmd_read(a):
    v = Vault.find()
    target, loc = a.id.strip("()<>[] "), None
    if "text/" in target:  # a citation link target such as ../../text/jain2019.md#L88-L95
        target = target.split("text/", 1)[1]
    target, _, loc = target.partition("#")
    target = target.lstrip("@").removesuffix(".md")
    loc = loc.rstrip("?") or None
    lines = v.text_lines(target)
    if lines is None:
        die(f"no reading text for `{target}`" + ("" if target in v.registry else " (unknown source)"))
    n, width = len(lines), len(str(len(lines)))
    if a.grep:
        pat = re.compile(a.grep, re.I)
        hits = [i for i, l in enumerate(lines) if pat.search(l)]
        shown = sorted({j for i in hits for j in range(max(0, i - a.context), min(n, i + a.context + 1))})
        prev = None
        for j in shown:
            if prev is not None and j != prev + 1:
                print(" " + "·" * width)
            print(f"{'>' if j in hits else ' '}{j + 1:>{width}}│ {lines[j]}")
            prev = j
        print(f"-- {len(hits)} matching lines in {target} ({n} lines)", file=sys.stderr)
        return
    rng = a.lines or loc
    if rng:
        s, e = _parse_range(rng)
        s, e = max(1, s - a.context), min(n, e + a.context)
    else:
        s, e = 1, min(n, a.max)
    for i in range(s - 1, e):
        print(f"{i + 1:>{width}}│ {lines[i]}")
    if rng:
        print(f"-- cite from any wiki page: {markup.cite_link(target, *_parse_range(rng))}", file=sys.stderr)
    if not rng and e < n:
        print(f"-- showing 1-{e} of {n} lines; use -l A-B for more", file=sys.stderr)


# ====================================================================== new
def _render(template: str, values: dict) -> str:
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(values.get(m.group(1), "")), template)


def _load_template(v: Vault, ptype: str) -> str:
    p = v.root / "templates" / f"{ptype}.md"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return (_template_root() / "templates" / f"{ptype}.md").read_text(encoding="utf-8")


def cmd_new(a):
    v = Vault.find()
    values = {"date": today()}
    if a.type == "source":
        sid = a.name
        e = v.registry.get(sid)
        if e is None:
            die(f"`{sid}` is not a registered source; run `patchouli add` first")
        slug, origin = sid, e.get("origin", "")
        title = a.title or e.get("title") or sid
        values.update(source_id=sid, raw=e.get("raw", ""),
                      url=fm.dump_scalar(origin) if _URL_RE.match(origin) else '""')
    else:
        title = a.title or a.name
        slug = a.slug or slugify(a.name)
        if slug in v.registry:
            die(f"`{slug}` is a source id; give the {a.type} page another name (--slug)")
    values.update(title=fm.dump_scalar(title), title_plain=title, slug=slug)
    existing = v.find_page(slug)
    if existing is not None:
        die(f"a page with slug `{slug}` already exists: {existing.rel}")
    dest = v.page_dir(a.type) / f"{slug}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_render(_load_template(v, a.type), values), encoding="utf-8")
    print(v.rel(dest))


# ====================================================================== sync / check
def _print_issues(issues, show_advice: bool, focus: set[str] | None = None, limit: int = 40):
    """Errors always; advice only for `focus` paths (plus re-check notices) when a focus is given."""
    errors = [i for i in issues if i.level == "error"]
    advice = [i for i in issues if i.level == "advice"]
    if focus is not None:
        shown = [i for i in advice if i.path in focus or i.code == "STL001"]
    else:
        shown = advice
    for i in errors:
        print(i.format())
    if show_advice:
        for i in shown[:limit]:
            print(i.format())
        if len(shown) > limit:
            print(f"  … {len(shown) - limit} more")
    rest = len(advice) - (len(shown) if show_advice else 0)
    label = " on this change" if focus is not None else ""
    print(f"-- {len(errors)} error(s) to fix" + (f", {len(shown)} advice{label}" if show_advice else "")
          + (f"; {rest} other advice item(s) in the vault (`patchouli check`)" if rest > 0 else ""))


def _git_commit(v: Vault, message: str) -> str:
    """Commit only Patchouli-owned paths, never the human's notes/ or inbox/."""
    if not (v.root / ".git").exists():
        return ""
    owned = [p for p in ("wiki", "raw", "text", f"{STATE_DIR}/sources.json", f"{STATE_DIR}/pages.json",
                         f"{STATE_DIR}/config.json") if (v.root / p).exists()]
    git = ["git", "-C", str(v.root)]
    subprocess.run(git + ["add", "-A", "--"] + owned, check=True)
    if subprocess.run(git + ["diff", "--cached", "--quiet", "--"] + owned).returncode == 0:
        return ""
    r = subprocess.run(git + ["commit", "-q", "-m", message, "--"] + owned, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip() or "git commit failed")
    return subprocess.run(git + ["log", "-1", "--format=%h"], capture_output=True, text=True).stdout.strip()


def fix_paths(v: Vault, g) -> int:
    """Correct relative paths of links whose target is known (a page slug or a source id)."""
    fixed = 0
    for slug, page in g.pages.items():
        text = page.path.read_text(encoding="utf-8")

        def repl(m, page=page):
            nonlocal fixed
            if m.group(1) == "!":
                return m.group(0)
            target = m.group(3)
            frag = "#" + target.split("#", 1)[1] if "#" in target else ""
            item = markup.classify(page.dir, target, 0)
            if isinstance(item, markup.Citation) and not item.path_ok and item.source in v.registry:
                new = posixpath.relpath(f"text/{item.source}.md", page.dir) + frag
            elif (isinstance(item, markup.Link) and item.target in g.pages and item.path != g.pages[item.target].rel
                  and not (v.root / item.path).exists()):
                new = posixpath.relpath(g.pages[item.target].rel, page.dir) + frag
            else:
                return m.group(0)
            fixed += 1
            return f"[{m.group(2)}]({new})"

        new_text = markup.sub_links(text, repl)
        if new_text != text:
            page.path.write_text(new_text, encoding="utf-8")
    return fixed


def cmd_sync(a):
    """Finish a piece of work: track changes, rebuild index+graph, check, log, snapshot."""
    v = Vault.find()
    g = graphmod.build(v)
    fixed = fix_paths(v, g)
    if fixed:
        g = graphmod.build(v)
    st, changed, removed = statemod.current(v, g)
    graphmod.write_index(v, g, st)
    db.refresh(v, g, st).close()
    issues = checkmod.run(v, g, st)
    errors = [i for i in issues if i.level == "error"]
    if not errors:  # until clean, the same pages count as changed on every retry
        statemod.save(v, st)
    if a.message and not errors:
        title, _, body = a.message.partition("\n")
        entry = f"\n## [{today()}] {a.op} | {title.strip()}\n"
        touched = [g.pages[s].rel for s in changed] + [f"(removed) {s}" for s in removed]
        details = body.strip()
        if touched:
            details += ("\n\n" if details else "") + "Pages: " + ", ".join(touched)
        if details:
            entry += f"\n{details}\n"
        if not v.log_path.exists():
            v.log_path.write_text("# Log\n", encoding="utf-8")
        with open(v.log_path, "a", encoding="utf-8") as f:
            f.write(entry)
    print(f"synced: {len(changed)} changed, {len(removed)} removed page(s); index rebuilt"
          + (f"; {fixed} link path(s) corrected" if fixed else ""))
    snapshot_failed = False
    if a.message and not errors:
        try:
            sha = _git_commit(v, f"{a.op}: {a.message.splitlines()[0]}")
            if sha:
                print(f"snapshot {sha}")
        except (RuntimeError, OSError, subprocess.CalledProcessError) as e:
            snapshot_failed = True
            print(f"snapshot FAILED (the work is saved and logged, but not committed): {e}")
    elif a.message:
        print("not logged or snapshotted yet: fix the errors below and run the same sync again")
    # advice on what this sync touched: changed pages, and the sources behind changed source pages
    focus = {g.pages[s].rel for s in changed}
    focus |= {v.registry[s].get("raw", "") for s in changed if s in v.registry}
    _print_issues(issues, show_advice=not a.quiet, focus=focus)
    sys.exit(1 if errors or snapshot_failed else 0)


def cmd_check(a):
    v = Vault.find()
    issues = checkmod.run(v)
    _print_issues(issues, show_advice=not a.errors, limit=10_000)
    sys.exit(1 if any(i.level == "error" for i in issues) else 0)


# ====================================================================== search
def cmd_search(a):
    v = Vault.find()
    hits = searchmod.search(v, " ".join(a.query), a.scope, a.k)
    if not hits:
        print("no results")
    for n, h in enumerate(hits, 1):
        print(f"{n:>2}. {h.cite()}  {'' if h.kind == 'page' else h.title}  ({h.path}:{h.best_line})")
        print(f"      {h.snippet}")
    if hits:
        print("-- link/citation forms are valid from any wiki page", file=sys.stderr)


# ====================================================================== rename
def _rewrite_refs(text: str, page_dir: str, old: str, new: str, new_page: str | None = None,
                  unlink: bool = False, old_rel: str | None = None, root: Path | None = None) -> tuple[str, int]:
    """Point links and citations at `new` instead of `old` (code is left alone).

    `unlink`: this page *is* the merge target, so its links to `old` become plain text
    rather than links to itself."""
    count = 0

    def repl(m):
        nonlocal count
        if m.group(1) == "!":
            return m.group(0)
        target = m.group(3)
        path, sep, frag = target.partition("#")
        item = markup.classify(page_dir, target, 0)
        if isinstance(item, markup.Citation) and item.source == old:
            base, ext = posixpath.splitext(path)
            newpath = base[: -len(old)] + new + ext  # text/old.md or raw/old.pdf
        elif (isinstance(item, markup.Link) and item.target == old
              and (item.path == old_rel  # the page itself; or a broken wiki link that named it
                   or (item.path.startswith("wiki/") and not (root and (root / item.path).exists())))):
            if unlink:
                count += 1
                return m.group(2)
            newpath = posixpath.relpath(new_page, page_dir) if new_page else path[: -len(f"{old}.md")] + f"{new}.md"
        else:
            return m.group(0)
        count += 1
        label = m.group(2)
        if label == old or label.startswith(old + " "):
            label = new + label[len(old):]
        label = re.sub(rf"(^|/)(raw|text)/{re.escape(old)}(\.\w+)$", rf"\g<1>\g<2>/{new}\g<3>", label)
        return f"[{label}]({newpath}{sep}{frag})"

    return markup.sub_links(text, repl), count


def cmd_rename(a):
    v = Vault.find()
    old, new = a.old, a.new
    if not re.fullmatch(r"[\w][\w.\-]*", new) or new == old:
        die("the new name must be a different simple slug (letters, digits, - . _)")
    page, target = v.find_page(old), v.find_page(new)
    old_rel = page.rel if page else None
    reg = v.registry
    if old in reg:
        if a.merge:
            die("--merge is for pages; two sources stay two sources (link them instead)")
        if new in reg or target:
            die(f"`{new}` already exists")
        e = reg.pop(old)
        raw = v.root / e["raw"]
        if raw.exists():
            dest = raw.with_name(new + raw.suffix)
            raw.rename(dest)
            e["raw"] = v.rel(dest)
        if v.text_path(old).exists():
            v.text_path(old).rename(v.text_path(new))
            e["text"] = v.rel(v.text_path(new))
        if e.get("title_auto") or e.get("title") == old:
            e["title"] = new
        reg[new] = e
        v.save_registry(old, new)
        if page:
            dest = page.path.with_name(f"{new}.md")
            page.path.rename(dest)
            # the header line names the id and files in code spans: `old`, `raw/old.pdf`, `text/old.md`
            body = dest.read_text(encoding="utf-8")
            body = re.sub(r"^_Source .*$", lambda hm: re.sub(rf"`((?:raw|text)/)?{re.escape(old)}((?:\.\w+)?)`",
                                                           rf"`\g<1>{new}\g<2>`", hm.group(0)), body, count=1,
                          flags=re.M)
            dest.write_text(body, encoding="utf-8")
    elif page:
        if new in reg:
            die(f"`{new}` is a source id")
        if a.merge and not target:
            die(f"nothing to merge into: `{new}` does not exist (to rename, drop --merge)")
        if target and not a.merge:
            die(f"`{new}` exists; fold the content of `{old}` into it, then rerun with --merge")
        if not target:
            page.path.rename(page.path.with_name(f"{new}.md"))
    else:
        die(f"no source or page `{old}`")
    statemod.rename(v, old, new, merged=bool(a.merge))
    new_page = target.rel if (a.merge and target) else None
    refs = pages = 0
    for p in v.iter_pages():
        if a.merge and p.slug == old:
            continue
        text = p.path.read_text(encoding="utf-8")
        updated, k = _rewrite_refs(text, p.dir, old, new, new_page, unlink=bool(new_page) and p.slug == new,
                                   old_rel=old_rel, root=v.root)
        if k:
            p.path.write_text(updated, encoding="utf-8")
            refs, pages = refs + k, pages + 1
    kept = ""
    if a.merge and page and page.path.exists():
        trash = v.state_dir / "trash"  # not versioned; a safety copy in case content wasn't folded in
        trash.mkdir(exist_ok=True)
        kept = trash / f"{old}.{now().replace(':', '')}.md"
        shutil.move(str(page.path), kept)
        kept = f"; the old page is kept at {v.rel(kept)}"
    print(f"{'merged' if a.merge else 'renamed'} `{old}` → `{new}`; {refs} reference(s) updated in {pages} page(s)"
          + kept)


# ====================================================================== query
def cmd_query(a):
    v = Vault.find()
    if not a.sql:
        print(db.DOC)
        return
    db.refresh(v).close()
    con = db.connect(v, readonly=True)
    try:
        cur = con.execute(a.sql)
        rows = cur.fetchmany(a.limit)
    except sqlite3.Error as e:
        die(f"query failed: {e}  (run `patchouli query` for the schema)")
    cols = [d[0] for d in cur.description or []]
    if a.json:
        print(json.dumps([dict(zip(cols, r)) for r in rows], indent=1, ensure_ascii=False))
        return
    if cols:
        print(" | ".join(cols))
    for r in rows:
        print(" | ".join("" if x is None else (str(x) if len(str(x)) <= 120 else str(x)[:117] + "...") for x in r))
    print(f"-- {len(rows)} row(s){' (limit reached)' if len(rows) == a.limit else ''}", file=sys.stderr)


# ====================================================================== status
def cmd_status(a):
    v = Vault.find()
    g = graphmod.build(v)
    st, changed, _ = statemod.current(v, g)
    cfg = v.config()
    counts = {t: 0 for t in PAGE_TYPES}
    for p in g.pages.values():
        counts[p.type] = counts.get(p.type, 0) + 1
    reg = v.registry
    pending = [s for s in reg if not g.has_source_page(s)]
    inbox = sorted(p.name for p in v.inbox_dir.iterdir() if p.is_file() and not p.name.startswith(".")) \
        if v.inbox_dir.exists() else []
    issues = checkmod.run(v, g, st)
    errors = sum(1 for i in issues if i.level == "error")
    stale = sorted({i.path for i in issues if i.code in ("STL001", "SRC005")})
    print(f"vault: {v.root}   taste: {cfg.get('taste')}   language: {cfg.get('language')}")
    print("pages: " + ", ".join(f"{n} {t}" for t, n in counts.items()))
    print(f"sources: {len(reg)} registered, {len(pending)} awaiting ingestion")
    if inbox:
        print(f"inbox: {len(inbox)} file(s): {', '.join(inbox[:6])}{' …' if len(inbox) > 6 else ''}")
    if pending:
        print(f"awaiting ingestion: {', '.join(pending[:8])}{' …' if len(pending) > 8 else ''}")
    if changed:
        print(f"unsynced edits: {', '.join(changed[:8])}{' …' if len(changed) > 8 else ''}")
    if stale:
        print(f"may need re-checking: {', '.join(stale)}")
    print(f"check: {errors} error(s), {len(issues) - errors} advice")
    if v.log_path.exists():
        heads = [l[3:] for l in v.log_path.read_text(encoding="utf-8").split("\n") if l.startswith("## [")]
        if heads:
            print("recent: " + " · ".join(heads[-3:]))


# ====================================================================== parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="patchouli", description="Deterministic tools for a Patchouli research wiki.")
    p.add_argument("--version", action="version", version=f"patchouli {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create a vault")
    s.add_argument("dir", nargs="?", default=".")
    s.add_argument("--language", default="auto", help="wiki language (default: follow the user)")
    s.add_argument("--no-git", action="store_true")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("status", help="where things stand: pages, pending sources, inbox, stale pages")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("add", help="register materials (paths, URLs, or all of inbox/) and extract reading text")
    s.add_argument("targets", nargs="*")
    s.add_argument("--id", help="source id, e.g. vaswani2017-attention (default: from title/filename)")
    s.add_argument("--title")
    s.add_argument("--no-extract", action="store_true")
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("extract", help="(re)build reading text")
    s.add_argument("ids", nargs="*")
    s.add_argument("--all", action="store_true")
    s.add_argument("--force", action="store_true")
    s.add_argument("--from", dest="from_file", help="import an externally converted Markdown file")
    s.set_defaults(func=cmd_extract)

    s = sub.add_parser("read", help="reading text with line numbers")
    s.add_argument("id", help="source id, or a citation target such as ../../text/id.md#L10-L40")
    s.add_argument("-l", "--lines", help="range, e.g. 120-180")
    s.add_argument("-g", "--grep", help="regex; show matching lines")
    s.add_argument("-C", "--context", type=int, default=0)
    s.add_argument("--max", type=int, default=400, help="max lines without a range")
    s.set_defaults(func=cmd_read)

    s = sub.add_parser("search", help="BM25 over wiki pages and reading text")
    s.add_argument("query", nargs="+")
    s.add_argument("--scope", choices=["all", "wiki", "text"], default="all")
    s.add_argument("-k", type=int, default=10)
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("new", help="start a page from its template")
    s.add_argument("type", choices=list(PAGE_TYPES))
    s.add_argument("name", help="source id (source pages) or page title")
    s.add_argument("--title")
    s.add_argument("--slug")
    s.set_defaults(func=cmd_new)

    s = sub.add_parser("sync", help="finish work: track changes, rebuild index, check, log, snapshot")
    s.add_argument("-m", "--message", help="log entry: first line is the title, the rest is the body")
    s.add_argument("--op", default="edit", help="ingest | ask | synthesize | explore | maintain | distill | edit")
    s.add_argument("-q", "--quiet", action="store_true", help="only show errors")
    s.set_defaults(func=cmd_sync)

    s = sub.add_parser("check", help="all checks: errors (binding) and advice")
    s.add_argument("--errors", action="store_true", help="errors only")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("query", help="read-only SQL over pages, links, citations and claims (no args: schema)")
    s.add_argument("sql", nargs="?")
    s.add_argument("--limit", type=int, default=200)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_query)

    s = sub.add_parser("rename", help="rename a source id or page slug and update every link and citation")
    s.add_argument("old")
    s.add_argument("new")
    s.add_argument("--merge", action="store_true",
                   help="NEW is an existing page you merged OLD into: redirect references, remove OLD")
    s.set_defaults(func=cmd_rename)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except VaultNotFound as e:
        die(str(e))
    except BrokenPipeError:
        pass


if __name__ == "__main__":
    main()
