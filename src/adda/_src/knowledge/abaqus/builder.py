"""Abaqus documentation HTML -> structured page text.

WHY THIS EXISTS
    The datagenerator writes Abaqus input decks against a solver whose
    reference documentation it cannot consult. ``reader.AbaqusDocs.build``
    calls ``extract_page`` here on each documentation file and indexes the
    result; this module is that extractor and nothing else.

WHAT MAKES THE EXTRACTION NON-NAIVE
    A measured survey of 1,200 pages found 99% carry tables, 52% MathML, 37%
    <pre> code blocks, and parameter documentation lives in <dl>/<dt>/<dd>
    definition lists. Flattening a page to text destroys exactly the content a
    reference lookup needs -- a parameter table becomes word soup, and a
    keyword's syntax block gets shredded. So each is handled explicitly:

      <pre>      kept verbatim and atomic
      <table>    rendered as a markdown table, row/column binding preserved
      <dl>       rendered as "term -- definition" pairs
      MathML     rendered to readable inline text rather than dropped
      chrome     .DocHeader*, <script>, <style>, <link>, nav stripped by selector

    Boilerplate removal matters more than it sounds: text repeated on every
    page carries zero discriminative power but inflates every search score.

WHAT THIS MODULE NO LONGER CARRIES, AND WHY
    It also held ``AbaqusDocCorpus``: a second, complete retrieval stack --
    semantic chunking, BM25, an optional dense blend at 2:1 -- referenced by
    nothing. The tool that ships runs sqlite FTS in ``reader.py``, so the
    docstring here advertised a design that never executed, and 315 lines of
    it sat untested behind an undeclared rank_bm25/numpy/embedder path. Two
    retrieval implementations where one runs is the "which one is actually
    answering?" problem this package exists to avoid. It is in git history if
    the chunking approach is ever measured against the FTS one.

DEPENDENCY
    lxml, for the HTML parse. Declared as the optional ``abaqus`` extra --
    READING a built corpus needs only the stdlib.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Books whose directory prefix maps to a human-readable manual name.
BOOK_NAMES = {
    "SIMACAEANLRefMap": "Analysis User's Guide",
    "SIMACAEKEYRefMap": "Keywords Reference",
    "SIMACAEELMRefMap": "Element Reference",
    "SIMACAEMATRefMap": "Materials Reference",
    "SIMACAEITNRefMap": "Interaction/Contact",
    "SIMACAEOUTRefMap": "Output Variables",
    "SIMACAETHERefMap": "Theory Guide",
    "SIMACAESUBRefMap": "User Subroutines",
    "SIMACAECAERefMap": "Abaqus/CAE User's Guide",
    "SIMACAEKERRefMap": "Scripting Reference (Kernel)",
    "SIMACAEEXCRefMap": "Execution/Procedures",
    "SIMACAEEXARefMap": "Example Problems",
    "SIMACAEVERRefMap": "Verification",
    "SIMACAEBMKRefMap": "Benchmarks",
    "SIMACAECSTRefMap": "Constraints",
    "SIMACAEGSARefMap": "Getting Started",
    "SIMACAEPRCRefMap": "Analysis Procedures",
    "SIMAINPRefResources": "Example Input Files",
}

CHROME_CLASS_RE = re.compile(r"DocHeader|breadcrumb|navheader|navfooter|related-links")
DROP_TAGS = {"script", "style", "link", "noscript", "head"}


# --------------------------------------------------------------------------
# extraction
# --------------------------------------------------------------------------
@dataclass
class Page:
    page_id: str
    title: str
    book: str
    book_name: str
    rel_path: str
    text: str
    n_pre: int = 0
    n_table: int = 0
    n_math: int = 0
    n_dl: int = 0
    keywords: list = field(default_factory=list)


def _local(tag) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].lower()


def _mathml_to_text(el) -> str:
    """Flatten a MathML subtree into readable inline text.

    Not LaTeX: the goal is that an equation contributes its symbols to the
    index and reads sanely in a retrieved passage, not that it re-renders.
    """
    parts = []
    for node in el.iter():
        name = _local(node.tag)
        if name in ("mi", "mn", "mo", "mtext"):
            if node.text:
                parts.append(node.text.strip())
    out = " ".join(p for p in parts if p)
    return f" {out} " if out else " "


def _render_flow(el, counters) -> str:
    """Render an element's contents IN DOCUMENT ORDER, keeping prose and
    structured blocks (code, definition lists, math, nested tables) together.

    This is the same traversal the page body uses. It exists as a function
    because the cell renderer needs it too: SIMULIA lays pages out with
    tables, so a single cell routinely holds a section's whole prose next to
    its syntax block or parameter list.
    """
    out: list[str] = []

    def rec(node):
        name = _local(node.tag)
        cls = node.get("class") or ""
        if name in DROP_TAGS or CHROME_CLASS_RE.search(cls):
            return
        if name == "pre":
            counters["pre"] += 1
            code = "".join(node.itertext()).rstrip()
            if code.strip():
                out.append("\n```\n" + code + "\n```\n")
            return
        if name == "dl":
            counters["dl"] += 1
            dl = _dl_to_text(node)
            if dl:
                out.append("\n" + dl + "\n")
            return
        if name == "math":
            counters["math"] += 1
            out.append(_mathml_to_text(node))
            return
        if name == "table":
            md = _table_to_markdown(node, counters)
            if md:
                out.append("\n" + md + "\n")
            return
        if name in ("h1", "h2", "h3", "h4", "h5", "h6") or "sectiontitle" in cls:
            heading = " ".join("".join(node.itertext()).split())
            if heading:
                out.append(f"\n## {heading}\n")
            return
        if node.text and node.text.strip():
            out.append(node.text)
        for child in node:
            rec(child)
            if child.tail and child.tail.strip():
                out.append(child.tail)

    if el.text and el.text.strip():
        out.append(el.text)
    for child in el:
        rec(child)
        if child.tail and child.tail.strip():
            out.append(child.tail)
    txt = " ".join(out)
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r"\n\s*\n\s*\n+", "\n\n", txt)
    return txt.strip()


def _render_cell(el, counters) -> str:
    """Render one table cell, preserving code / definition lists / math AND
    the prose around them.

    SIMULIA uses tables as the LAYOUT mechanism: a measured 100% of <pre>,
    <dl> and MathML in this corpus sit inside a table cell. An earlier version
    collected only those blocks and returned them alone whenever any were
    present, falling back to plain text only for cells that had none -- so on
    every page where a section's prose shared a cell with its own syntax block
    or file list, the prose was dropped. Measured cost: 28.4% of pages kept
    under half their source prose, 355 kept under a quarter. The NAFEMS
    lateral-torsional-buckling benchmark, for instance, retained its list of
    input-file names and lost its problem description, geometry, boundary
    conditions and reference solution.
    """
    return _render_flow(el, counters)


def _table_to_markdown(el, counters) -> str:
    """Render a table. Layout tables (single cell / single column) are emitted
    inline; genuine data tables keep their row/column binding as markdown."""
    rows = []
    for tr in el.iter():
        if _local(tr.tag) not in ("row", "tr"):
            continue
        cells = [_render_cell(td, counters) for td in tr
                 if _local(td.tag) in ("entry", "td", "th")]
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    # Layout table, not data: emit contents inline so code/lists read normally.
    if width == 1 or len(rows) == 1:
        return "\n".join(c for r in rows for c in r if c)
    counters["table"] += 1
    rows = [r + [""] * (width - len(r)) for r in rows]
    flat = [[c.replace("\n", " ").strip() for c in r] for r in rows]
    out = ["| " + " | ".join(flat[0]) + " |",
           "|" + "|".join([" --- "] * width) + "|"]
    for r in flat[1:]:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def _dl_to_text(el) -> str:
    """Definition lists carry parameter documentation: keep term->definition."""
    out, term = [], None
    for child in el.iter():
        name = _local(child.tag)
        if name in ("dt", "dlterm"):
            term = " ".join("".join(child.itertext()).split())
        elif name in ("dd", "dldef") and term is not None:
            definition = " ".join("".join(child.itertext()).split())
            if definition:
                out.append(f"- {term} -- {definition}")
            term = None
    return "\n".join(out)


def extract_page(path: Path, root: Path) -> Page | None:
    """Parse one documentation page into structured plain text."""
    from lxml import etree

    try:
        tree = etree.fromstring(path.read_bytes(),
                                etree.HTMLParser(recover=True))
    except Exception:
        return None
    if tree is None:
        return None

    meta = {}
    for m in tree.xpath("//meta"):
        n, c = m.get("name"), m.get("content")
        if n and c:
            meta[n] = c

    title_el = tree.xpath("//title")
    title = " ".join("".join(title_el[0].itertext()).split()) if title_el else ""
    if not title:
        h = tree.xpath('//*[contains(@class,"title")]')
        if h:
            title = " ".join("".join(h[0].itertext()).split())

    rel = path.relative_to(root).as_posix()
    parts = rel.split("/")
    book = parts[1] if len(parts) > 1 else parts[0]
    page_id = meta.get("DC.identifier") or path.stem

    # Body container. DITA class names are NOT reliable here: on many pages
    # .conbody/.body sit on an EMPTY placeholder while the real content lives
    # directly under <body> (measured: 2,494 of 4,020 pages extracted to <200
    # chars when trusting the class). So score every candidate by how much text
    # it actually holds and take the richest, falling back to <body>.
    candidates = []
    for cls in ("conbody", "refbody", "taskbody", "body"):
        candidates.extend(tree.xpath(f'//*[contains(@class,"{cls}")]'))
    candidates.extend(tree.xpath("//body"))
    body = None
    best = -1
    for cand in candidates:
        size = len("".join(cand.itertext()))
        if size > best:
            best, body = size, cand
    if body is None:
        body = tree

    counters = {"pre": 0, "table": 0, "math": 0, "dl": 0}
    pieces: list[str] = []

    def walk(el):
        name = _local(el.tag)
        cls = el.get("class") or ""
        if name in DROP_TAGS or CHROME_CLASS_RE.search(cls):
            return
        if name == "pre":
            counters["pre"] += 1
            code = "".join(el.itertext()).rstrip()
            if code.strip():
                pieces.append("\n```\n" + code + "\n```\n")
            return
        if name == "table":
            md = _table_to_markdown(el, counters)
            if md:
                pieces.append("\n" + md + "\n")
            return
        if name == "dl":
            counters["dl"] += 1
            dl = _dl_to_text(el)
            if dl:
                pieces.append("\n" + dl + "\n")
            return
        if name == "math":
            counters["math"] += 1
            pieces.append(_mathml_to_text(el))
            return
        if name in ("h1", "h2", "h3", "h4", "h5", "h6") or "sectiontitle" in cls:
            heading = " ".join("".join(el.itertext()).split())
            if heading:
                pieces.append(f"\n## {heading}\n")
            return
        if el.text and el.text.strip():
            pieces.append(el.text)
        for child in el:
            walk(child)
            if child.tail and child.tail.strip():
                pieces.append(child.tail)

    walk(body)

    text = "".join(pieces)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    keywords = sorted({
        " ".join("".join(k.itertext()).split())
        for k in tree.xpath('//*[contains(@class,"keyword")]'
                            '|//*[contains(@class,"abqelement")]')
        if "".join(k.itertext()).strip()
    })[:25]

    return Page(
        page_id=page_id, title=title, book=book,
        book_name=BOOK_NAMES.get(book, book), rel_path=rel, text=text,
        n_pre=counters["pre"], n_table=counters["table"],
        n_math=counters["math"], n_dl=counters["dl"],
        keywords=keywords,
    )


# --------------------------------------------------------------------------
# chunking
