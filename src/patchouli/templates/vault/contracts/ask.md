# Ask — answer a question from the wiki

**Objective.** Answer the human's question with evidence they can trace and certainty
they can trust, and keep the answer if it has lasting value. "What do we have on X?" is a
question too: answer it with pointers (pages, exact passages) ranked by relevance, and say
how solid the coverage is and which registered sources would help but aren't ingested yet.

**Resources.** The whole knowledge base. Start from what is already understood (answers,
syntheses, concepts), go to source pages for methods, evidence and conditions,
and trace back to reading text — or the raw file — whenever the answer hinges on details,
numbers or exact conditions. Use the active taste for emphasis.

**Deliverables.**
- The answer in chat: the direct answer first, then the reasoning with citations, then
  what limits it. Tables or other formats when they serve the question.
- Lasting understanding kept where future readers will look for it. Often that is an
  existing concept or synthesis page — a paragraph there beats a new page. An answer page
  (`wiki/answers/`) is for a question likely to be asked again that has no better home;
  an unanswerable but important question can be kept with `status: open`. Link to it from
  other pages only where their readers would want it.
- Anything learned while tracing back (a missed condition, an error, a better locator)
  written into the page where it belongs.
- If the wiki changed: `patchouli sync --op ask -m "<question>"`. A pure lookup changes nothing.

**Quality bar.** Source findings, your interpretations and cross-source judgments
stay distinguishable (footnotes, see STYLE.md); certainty matches evidence; conditions under which
the answer would flip are stated. A question that compares sources ("do A and B agree?")
gets the comparison `contracts/synthesize.md` asks for: why they differ, and whether they are
independent — not a list per source. If the wiki cannot support an answer, say so plainly,
name what is missing, and don't fill the gap from general knowledge without flagging it.
