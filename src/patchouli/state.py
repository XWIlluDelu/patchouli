"""Automatic change tracking for wiki pages (script-owned bookkeeping).

The agent never maintains dates or hashes by hand. On each `patchouli sync` the
content hash of every page is compared with the recorded one:

* `changed` — when the page last changed in any way;
* `revised` — when its `## Revision notes` last changed. A new revision note is
  how a page declares a *substantive* change (a correction, a re-reading); routine
  edits such as adding links don't count, so they don't make other pages "stale";
* `basis` — when the page last answered to what it rests on: created, revised, or
  marked `reviewed: <date>` in its frontmatter. Editing a tag or adding a link is not
  a review, so it doesn't clear a re-check flag;
* `text_sha` (source pages) — the reading-text version the page was last checked
  against (moves with `basis`, so citation relocation alone doesn't hide a changed text).

From this the checker derives which pages may need re-checking.
"""
from __future__ import annotations

import hashlib
import json
import re

from .vault import Vault, now

FILE = "pages.json"
_NOTES_RE = re.compile(r"^##\s+Revision notes\s*$(.*?)(?=^##\s|\Z)", re.M | re.S | re.I)


def load(v: Vault) -> dict:
    p = v.state_dir / FILE
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save(v: Vault, state: dict) -> None:
    v.state_dir.mkdir(exist_ok=True)
    (v.state_dir / FILE).write_text(json.dumps(state, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                                    encoding="utf-8")


def notes_hash(text: str) -> str:
    """Hash of the revision entries themselves — not of footnote definitions that follow them."""
    m = _NOTES_RE.search(text)
    kept, in_fn = [], False
    for line in (m.group(1).split("\n") if m else []):
        if re.match(r"^\[\^[^\]\s]+\]:", line):
            in_fn = True
        elif in_fn and (not line.strip() or line.startswith(("    ", "\t"))):
            pass
        else:
            in_fn = False
            kept.append(line)
    body = "\n".join(kept).strip()
    return hashlib.sha256(body.encode()).hexdigest()[:16] if body else ""


def current(v: Vault, g):
    """Return (state, changed_slugs, removed_slugs). Unsynced edits count as changed now."""
    old = load(v)
    ts = now()
    state, changed = {}, []
    for slug, page in sorted(g.pages.items()):
        raw = page.path.read_bytes()
        h = hashlib.sha256(raw).hexdigest()
        prev = old.get(slug)
        if prev and prev.get("sha") == h:
            state[slug] = prev
            continue
        notes = notes_hash(raw.decode("utf-8", "replace"))
        reviewed = str(page.meta.get("reviewed") or "")
        entry = {"sha": h, "changed": ts, "notes": notes, "reviewed": reviewed}
        if prev is None:
            entry["revised"] = ts if notes else ""
            checked = True
        else:
            revised = prev["notes"] != notes
            entry["revised"] = ts if revised else prev.get("revised", "")
            # only a new revision note or a new `reviewed:` value counts; other edits are not a review
            checked = revised or bool(reviewed and reviewed != prev.get("reviewed", ""))
        entry["basis"] = ts if checked else prev["basis"]
        if page.type == "source":
            entry["text_sha"] = v.text_sha(slug) if checked else prev.get("text_sha") or v.text_sha(slug)
        state[slug] = entry
        changed.append(slug)
    removed = sorted(s for s in old if s not in g.pages)
    return state, changed, removed


def rename(v: Vault, old: str, new: str, merged: bool) -> None:
    """Carry a page's history over to its new slug, or drop it when merged into another page."""
    st = load(v)
    if old in st:
        entry = st.pop(old)
        if not merged:
            st[new] = entry
        save(v, st)
