"""Tests for the deterministic layer. Run: python -m unittest discover -s tests"""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from patchouli import check, db, extract, frontmatter, graph, markup, quotes, relocate, search  # noqa: E402
from patchouli import state as statemod  # noqa: E402
from patchouli.cli import main  # noqa: E402
from patchouli.vault import Vault  # noqa: E402

SID = "doe2024-widgets"
CLAIM = "Widgets improve throughput by 12% on the W benchmark."


def run(*args):
    out = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        try:
            main(list(args))
        except SystemExit as e:
            code = e.code or 0
    return code, out.getvalue()


def cite(n, m=None, sid=SID):
    return markup.cite_link(sid, n, m or n)


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


class MarkupTests(unittest.TestCase):
    def test_links_relations_citations_claims(self):
        body = ("- Defines: [B](../concepts/b.md) and also [C](../concepts/c.md)\n"
                "- **Contradicts:** [D](../concepts/d.md)\n- 反驳：[E](../concepts/e.md)\n"
                f"- Inline {cite(3, 9)} and [web](https://x.org)\n\n"
                f"A holds.[^1] B follows from it.[^2][^3]\n\n[^1]: {cite(1)}\n"
                f"[^2]: Judgment (low) — from [A](../sources/a.md); {cite(4)}\n[^3]: {cite(3)}\n")
        m = markup.parse(body, 1, "wiki/concepts")
        self.assertEqual([(l.target, l.rel) for l in m.links],
                         [("b", "defines"), ("c", "link"), ("d", "contradicts"), ("e", "反驳"), ("a", "link")])
        self.assertIn((SID, 3, 9, None), [(c.source, c.start, c.end, c.footnote) for c in m.cites])
        self.assertEqual([(c.label, c.kind, c.text) for c in m.claims],
                         [(None, "stated", f"Inline {cite(3, 9)} and [web](https://x.org)"),
                          ("1", "stated", "A holds."), ("2", "judgment", "B follows from it."),
                          ("3", "stated", "B follows from it.")])
        zh = markup.parse(f"模型A更快[^1]。模型B更省[^2]。\n\n[^1]: {cite(1)}\n[^2]: {cite(2)}\n", 1, "wiki/concepts")
        self.assertEqual([c.text for c in zh.claims], ["模型A更快", "模型B更省"])
        # quote attributions attach to the quote (next line, Chinese lead-in/punctuation, trailing note)
        qbody = (f"> Exact quote\n— {cite(1)}\n\n> 中文引文\n\n—— 来源：{cite(2)}（正文）\n\n"
                 f"> 另一句\n\n— {cite(3)}。\n")
        qm = markup.parse(qbody, 1, "wiki/concepts")
        self.assertEqual([c.text for c in qm.claims], ["Exact quote", "中文引文", "另一句"])
        self.assertEqual([q.start for q in quotes.extract_quotes(qbody, 1, None, "wiki/concepts", {})], [1, 2, 3])

    def test_footnote_kinds(self):
        body = (f"x[^a] y[^b] z[^c]\n\n[^a]: {cite(1)}\n[^b]: Interpretation (moderate) — {cite(2)}\n"
                "[^c]: just a remark\n")
        fn = markup.parse(body, 1, "wiki/sources").footnotes
        self.assertEqual([(fn[k].kind, fn[k].certainty) for k in "abc"],
                         [("stated", None), ("interpretation", "moderate"), ("note", None)])

    def test_masking_and_paths(self):
        m = markup.parse("`[x](../concepts/x.md)`\n<!-- [y](../concepts/y.md) -->\n[z](concepts/z.md)", 1,
                         "wiki/concepts")
        self.assertEqual([(l.target, l.path) for l in m.links], [("z", "wiki/concepts/concepts/z.md")])
        c = markup.classify("wiki/concepts", "../text/a.md#L5?", 1)
        self.assertEqual((c.source, c.path_ok, c.unsure), ("a", False, True))

    def test_frontmatter(self):
        t = "---\ntitle: \"A: b\"\ntags: [x, \"y z\"]\nauthors:\n  - Ann\n  - Bob\nsummary:\n---\nbody"
        meta, body, start, has = frontmatter.parse(t)
        self.assertEqual((meta["title"], meta["tags"], meta["authors"], meta["summary"]),
                         ("A: b", ["x", "y z"], ["Ann", "Bob"], ""))
        self.assertEqual((body, start, has), ("body", 9, True))

    def test_footnotes_under_revision_notes_are_not_revisions(self):
        a = "## Revision notes\n\n- 2026-01-01: re-read\n\n[^1]: [x L1](../../text/x.md#L1)\n"
        self.assertEqual(statemod.notes_hash(a), statemod.notes_hash(a.replace("#L1", "#L2")))
        self.assertNotEqual(statemod.notes_hash(a), statemod.notes_hash(a.replace("re-read", "corrected")))


class EvidenceTests(unittest.TestCase):
    TEXT = ["Intro line.", "We find that *attention* weights", "correlate weakly — with gradients.", "End.",
            "Toxicity occurs at concentrations < 10 mg/L; a field of 1e-6 volts."]

    def test_quote_verification(self):
        idx = quotes.TextIndex(self.TEXT + [""] * 20 + ["Far away sentence here."])
        q = quotes.Quote("attention weights correlate weakly - with gradients", 1, "a", 2, 3)
        self.assertEqual(quotes.verify(q, idx), (True, ""))  # typography and emphasis fold, words don't
        ok, msg = quotes.verify(quotes.Quote("far away sentence here", 1, "a", 1, 2), idx)
        self.assertFalse(ok)
        self.assertIn("L26", msg)
        for wrong in ("attention weights correlate strongly", "concentrations > 10 mg/L", "a field of 1e6 volts"):
            self.assertFalse(idx.find_all(quotes.tokens(wrong)), wrong)  # signs and exponents count
        self.assertTrue(idx.find_all(quotes.tokens("concentrations < 10 mg/L")))

    def test_what_counts_as_a_quote(self):
        body = ("> We find that attention\n> weights correlate\n\n— [a L2–3](../../text/a.md#L2-L3)\n\n"
                "> [!note] callout\n\n> unattributed\n- Interpretation: see the text\n\n"
                'Builds on "A Totally Different Paper Title Here".[^1]\n\n'
                f'They write "a field of one microvolt was used" ({markup.cite_link("a", 5, 5)}).\n')
        qs = quotes.extract_quotes(body, 1, None, "wiki/concepts", {})
        self.assertEqual([(q.source, q.start) for q in qs], [("a", 2), ("a", 5)])

    def test_html_keeps_superscripts(self):
        text, _ = extract.html_to_markdown("<p>Protocol A: 10<sup>3</sup> iterations; B: 103; H<sub>2</sub>O.</p>")
        self.assertIn("A: 10^3 iterations; B: 103; H_2O.", text)

    def test_relocation_flags_changed_numbers(self):
        tail = "on the widget benchmark compared with the standard pipeline used in earlier work."
        old = ["Intro.", f"Throughput changed by 12 percent {tail}", "End."]
        self.assertEqual(relocate.Aligner(old, ["Preface.", "", *old]).map_span(2, 2), (4, 4))  # reflow moves
        for changed in (f"Throughput changed by −12 percent {tail}", f"Throughput changed by 12 percent in 3 {tail}",
                        f"Throughput changed {tail}"):
            self.assertIsNone(relocate.Aligner(old, ["Intro.", changed, "End."]).map_span(2, 2), changed)


class VaultFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "v"
        self.cwd = os.getcwd()
        self.assertEqual(run("init", str(self.root), "--no-git")[0], 0)
        os.chdir(self.root)
        src = Path(self.tmp.name) / "paper.html"
        src.write_text("<html><head><title>On Widgets</title></head><body><h1>On Widgets</h1>"
                       f"<p>{CLAIM}</p><p>Only tested at small scale.</p></body></html>")
        self.assertEqual(run("add", str(src), "--id", SID)[0], 0)
        self.n = Vault(self.root).text_lines(SID).index(CLAIM) + 1

    def tearDown(self):
        os.chdir(self.cwd)
        os.environ.pop("PATCHOULI_NOW", None)
        self.tmp.cleanup()

    def codes(self, level=None):
        return {i.code for i in check.run(Vault(self.root)) if level in (None, i.level)}

    def write_pages(self, quote="Widgets improve throughput by 12%"):
        run("new", "source", SID)
        run("new", "concept", "Widget throughput")
        sp = self.root / f"wiki/sources/{SID}.md"
        sp.write_text(sp.read_text().replace('summary: ""', "summary: widgets paper").replace(
            "## Key claims\n", f"## Key claims\n\n- Throughput +12% on W.[^1]\n\n> {quote}\n\n").replace(
            "## Connections\n", "## Connections\n\n- [Widget throughput](../concepts/widget-throughput.md)\n")
            + f"\n[^1]: {cite(self.n)}\n")
        cp = self.root / "wiki/concepts/widget-throughput.md"
        cp.write_text(cp.read_text().replace('summary: ""', "summary: throughput of widgets").replace(
            "## Evidence and limits\n", "## Evidence and limits\n\n- Gains may not hold at scale.[^1]\n").replace(
            "## Relations\n", f"## Relations\n\n- Extends: [the widgets paper](../sources/{SID}.md)\n")
            + f"\n[^1]: Judgment (low) — {cite(self.n, self.n + 2)}; only small scale was tested.\n")
        return sp, cp

    def page(self, kind, name, extra):
        run("new", kind, name)
        p = next((self.root / "wiki").rglob(f"{name.lower().replace(' ', '-')}.md"))
        p.write_text(p.read_text().replace('summary: ""', "summary: s") + extra)
        return p

    def test_clean_cycle_tracking_and_db(self):
        self.assertEqual(Vault(self.root).registry[SID]["title"], "On Widgets")  # title from the HTML
        sp, cp = self.write_pages()
        os.environ["PATCHOULI_NOW"] = "2026-01-01T10:00:00"
        code, out = run("sync", "--op", "ingest", "-m", "On Widgets")
        self.assertEqual(code, 0, out)
        self.assertFalse(self.codes() & {"LNK002", "STL001", "QUO001", "SRC005", "FN001"})
        self.assertIn("ingest | On Widgets", (self.root / "wiki/log.md").read_text())
        self.assertIn("](concepts/widget-throughput.md)", (self.root / "wiki/index.md").read_text())

        g = graph.build(Vault(self.root))
        self.assertEqual(g.dependencies("widget-throughput"), {SID: "extends"})
        hits = search.search(Vault(self.root), "throughput benchmark", scope="text")
        self.assertTrue(hits and hits[0].cite().startswith(f"[{SID} L"))
        rows = db.refresh(Vault(self.root)).execute("SELECT page, certainty FROM claims WHERE kind='judgment'")
        self.assertEqual(rows.fetchall(), [("widget-throughput", "low")])
        self.assertNotEqual(run("query", "DELETE FROM pages")[0], 0)  # read-only

        # a routine edit (a new link) flags nothing
        os.environ["PATCHOULI_NOW"] = "2026-01-15T10:00:00"
        sp.write_text(sp.read_text().replace("## Connections\n", "## Connections\n\n- See [index](../index.md)\n"))
        run("sync")
        self.assertNotIn("STL001", self.codes())
        # a revision note (substantive change) flags what builds on it; only a review clears that
        os.environ["PATCHOULI_NOW"] = "2026-02-01T10:00:00"
        sp.write_text(sp.read_text() + "\n## Revision notes\n\n- 2026-02-01: re-read\n")
        run("sync")
        self.assertIn("STL001", self.codes())
        os.environ["PATCHOULI_NOW"] = "2026-02-02T10:00:00"
        cp.write_text(cp.read_text().replace("tags: []", "tags: [widgets]"))  # editing a tag is no review
        run("sync")
        self.assertIn("STL001", self.codes())
        cp.write_text(cp.read_text().replace("tags: [widgets]", "tags: [widgets]\nreviewed: 2026-02-02"))
        run("sync")
        self.assertNotIn("STL001", self.codes())
        self.assertEqual(statemod.load(Vault(self.root))["widget-throughput"]["revised"], "")  # not passed on
        os.environ["PATCHOULI_NOW"] = "2026-02-02T16:00:00"  # revised again the same day
        sp.write_text(sp.read_text() + "- 2026-02-02: corrected the scale\n")
        run("sync")
        self.assertIn("STL001", self.codes())

    def test_failed_sync_records_nothing_and_snapshots_are_scoped(self):
        git(self.root, "init", "-q")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "t")
        (self.root / "notes" / "private.md").write_text("mine\n")
        sp, cp = self.write_pages(quote="Widgets never improve anything at all")
        log = (self.root / "wiki/log.md").read_text()
        self.assertEqual(run("sync", "--op", "ingest", "-m", "On Widgets")[0], 1)  # quote not verbatim
        self.assertEqual(log, (self.root / "wiki/log.md").read_text())
        self.assertNotEqual(git(self.root, "log").returncode, 0)  # nothing committed
        sp.write_text(sp.read_text().replace("Widgets never improve anything at all", "Widgets improve throughput by 12%"))
        self.assertEqual(run("sync", "--op", "ingest", "-m", "On Widgets")[0], 0)
        log = (self.root / "wiki/log.md").read_text()
        self.assertIn(f"wiki/sources/{SID}.md", log)
        self.assertIn("wiki/concepts/widget-throughput.md", log)  # not lost to the failed first try
        files = git(self.root, "ls-files").stdout
        self.assertIn(f"wiki/sources/{SID}.md", files)
        self.assertNotIn("notes/private.md", files)
        self.assertNotIn("index.db", files)

    def test_objective_vs_advice(self):
        p = self.page("concept", "Bad", "\n- a[^1]\n- b[^2]\n- c[^9]\n"
                      f"- range {cite(999)}\n- who {cite(1, sid='ghost')}\n- see [nowhere](../concepts/nowhere.md)\n"
                      "\n[^1]: Judgment — with no basis\n[^2]: Interpretation (high) — [Bad](../concepts/bad.md)\n"
                      f"[^3]: unused\n[^2]: {cite(1)}\n")
        levels = {i.code: i.level for i in check.run(Vault(self.root))}
        for c in ("CIT002", "CIT001", "FN001", "FN003"):
            self.assertEqual(levels.get(c), "error", c)
        for c in ("EVD002", "EVD004", "LNK001", "FN002"):
            self.assertEqual(levels.get(c), "advice", c)
        self.assertIn("`nowhere`", graph.render_index(graph.build(Vault(self.root))))
        self.assertTrue(p.exists())

    def test_sync_fixes_paths_but_not_code(self):
        sp, cp = self.write_pages()
        cp.write_text(cp.read_text().replace(f"../sources/{SID}.md", f"{SID}.md").replace(
            f"../../text/{SID}.md", f"../text/{SID}.md") + f"\nSee `[x]({SID}.md)` and [p]({SID}.md).\n")
        self.assertIn("corrected", run("sync")[1])
        out = cp.read_text()
        self.assertIn(f"](../sources/{SID}.md)", out)
        self.assertIn(f"](../../text/{SID}.md#L", out)
        self.assertIn(f"`[x]({SID}.md)`", out)  # code untouched

    def test_raw_immutability_duplicates_and_inbox(self):
        raw = self.root / Vault(self.root).registry[SID]["raw"]
        self.assertIn("already registered", run("add", str(raw))[1])
        raw.write_text(raw.read_text() + "<!-- tampered -->")
        self.assertIn("SRC002", self.codes())
        note = self.root / "notes" / "idea.md"
        note.write_text("# My idea\n\nWidgets might saturate.\n")
        run("add", str(note))
        self.assertTrue(note.exists())  # notes are copied
        (self.root / "inbox" / "drop.txt").write_text("dropped text\n")
        run("add")
        self.assertFalse((self.root / "inbox" / "drop.txt").exists())  # the inbox is moved
        self.assertIn("drop", Vault(self.root).registry)

    def test_registry_survives_overlapping_adds(self):
        a, b = Vault(self.root), Vault(self.root)
        a.registry  # process A has loaded the registry and is busy extracting
        b.registry["other2024"] = {"raw": "raw/other2024.txt", "title": "Other"}
        b.save_registry("other2024")
        a.registry[SID]["title"] = "On Widgets (extracted)"
        a.save_registry(SID)
        reg = Vault(self.root).registry
        self.assertEqual((reg["other2024"]["title"], reg[SID]["title"]), ("Other", "On Widgets (extracted)"))

    def test_source_ids_are_reserved_and_ingested_means_a_source_page(self):
        self.assertNotEqual(run("new", "concept", SID)[0], 0)
        (self.root / f"wiki/concepts/{SID}.md").write_text("---\ntype: concept\ntitle: X\n---\n")
        found = {i.code: i.level for i in check.run(Vault(self.root))}
        self.assertEqual(found.get("FM006"), "error")
        self.assertIn("SRC004", found)  # still awaiting ingestion
        self.assertIn("1 awaiting ingestion", run("status")[1])

    def test_relocation_on_reextraction(self):
        sp, cp = self.write_pages()
        run("sync")
        better = Path(self.tmp.name) / "better.md"
        better.write_text(f"# On Widgets\n\nPreface one.\n\nPreface two.\n\n{CLAIM}\n\nOnly tested at small scale.\n")
        run("extract", SID, "--from", str(better))
        new_n = Vault(self.root).text_lines(SID).index(CLAIM) + 1
        self.assertNotEqual(self.n, new_n)
        self.assertIn(cite(new_n), sp.read_text())  # anchor and visible range both moved
        self.assertFalse(self.codes() & {"QUO001", "CIT002", "CIT004"})
        run("sync")
        self.assertIn("SRC005", self.codes())  # moving citations is not re-reading the text
        gone = Path(self.tmp.name) / "gone.md"
        gone.write_text("# On Widgets\n\nSomething else entirely, nothing about it.\n")
        run("extract", SID, "--from", str(gone))
        self.assertIn("?)", sp.read_text())
        self.assertIn("CIT004", self.codes())

    def test_rename_source_and_merge_pages(self):
        sp, cp = self.write_pages()
        sp.write_text(sp.read_text() + f"\nUse `{SID}` to load it; mirror: [csv](https://example.org/raw/{SID}.csv)\n"
                      "My view: [note](../../notes/widget-throughput.md)\n")
        (self.root / "notes/widget-throughput.md").write_text("my note\n")
        run("sync")
        new = "widgets-paper"
        self.assertEqual(run("rename", SID, new)[0], 0)
        sp = self.root / f"wiki/sources/{new}.md"
        out = sp.read_text()
        self.assertIn(f"_Source `{new}`", out)  # the header follows
        self.assertIn(f"](../../raw/{new}.", out)
        self.assertIn(f"[text/{new}.md](../../text/{new}.md)", out)
        self.assertIn(f"Use `{SID}` to load it", out)  # prose and outside URLs don't
        self.assertIn(f"https://example.org/raw/{SID}.csv", out)
        self.assertIn(f"[{new} L", cp.read_text())
        self.assertIn(f"](../sources/{new}.md)", cp.read_text())
        self.assertFalse(self.codes("error"))

        tp = self.page("concept", "Throughput", "\n- Refines: [widget throughput](widget-throughput.md)\n")
        self.assertNotEqual(run("rename", "widget-throughput", "no-such-page", "--merge")[0], 0)
        self.assertEqual(run("rename", "widget-throughput", "throughput", "--merge")[0], 0)
        self.assertFalse(cp.exists())
        self.assertTrue(list((self.root / ".patchouli/trash").glob("widget-throughput.*.md")))  # safety copy
        self.assertIn("](../concepts/throughput.md)", sp.read_text())
        self.assertIn("- Refines: widget throughput\n", tp.read_text())  # no self-link
        self.assertIn("[note](../../notes/widget-throughput.md)", sp.read_text())  # a same-named note stays

    def test_provenance_and_tensions(self):
        self.write_pages()
        raw = Vault(self.root).registry[SID]["raw"]
        (self.root / f"notes/{SID}.md").write_text("my note\n")
        self.page("synthesis", "Widget debate",
                  f"\nAlso see [the paper](../sources/{SID}.md).\n\nWidgets win, mostly.[^1] The curve bends.[^2] "
                  f"A hunch.[^3]\n\n[^1]: Judgment (low) — from [the paper](../sources/{SID}.md); one study.\n"
                  f"[^2]: [{SID} fig. 1](../../{raw}#page=3)\n[^3]: Judgment (low) — from [my note](../../notes/{SID}.md)\n"
                  "\n- **Caveat:** [r](../concepts/widget-throughput.md)\n"
                  "- Contradicts: [Widget throughput](../concepts/widget-throughput.md)\n")
        run("sync")
        g = graph.build(Vault(self.root))
        self.assertEqual(g.sources_of("widget-debate"), [SID])  # footnotes count; "see also" and notes don't
        self.assertEqual(g.dependencies("widget-debate")[SID], "evidence")
        con = db.refresh(Vault(self.root))
        rows = con.execute("SELECT c.footnote, c.kind, s.source FROM claims c LEFT JOIN claim_sources s "
                           "ON s.claim = c.id WHERE c.page = 'widget-debate' ORDER BY c.footnote").fetchall()
        self.assertEqual(rows, [("1", "judgment", SID), ("2", "stated", SID), ("3", "judgment", None)])
        index = (self.root / "wiki/index.md").read_text()
        self.assertIn("1 source", index.split("Widget debate")[1].split("\n")[0])
        self.assertIn("## Tensions", index)  # a stray label doesn't hide the contradiction
        self.assertIn("SYN001", self.codes())
        self.assertFalse(self.codes("error"))


if __name__ == "__main__":
    unittest.main()
