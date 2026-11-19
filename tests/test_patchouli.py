"""Tests for Markdown and source evidence."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from patchouli import extract, frontmatter, markup, quotes, relocate
from patchouli import state as statemod

SID = "doe2024-widgets"
CLAIM = "Widgets improve throughput by 12% on the W benchmark."


def cite(n, m=None, sid=SID):
    return markup.cite_link(sid, n, m or n)


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


if __name__ == "__main__":
    unittest.main()
