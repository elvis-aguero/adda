"""Offline Abaqus documentation corpus: structure-aware ingest + hybrid search.

WHY THIS EXISTS
    The datagenerator writes Abaqus input decks and Abaqus-Python scripts against
    a solver whose reference documentation it cannot consult. This indexes the
    SIMULIA 2024 documentation locally so it can.

WHAT MAKES THE PREPROCESSING NON-NAIVE
    A measured survey of 1,200 pages found 99% carry tables, 52% MathML, 37%
    <pre> code blocks, and parameter documentation lives in <dl>/<dt>/<dd>
    definition lists. Flattening a page to text destroys exactly the content a
    reference lookup needs -- a parameter table becomes word soup, and a
    keyword's syntax block gets shredded. So each of those is handled
    explicitly:

      <pre>      kept verbatim and ATOMIC (never split across chunks)
      <table>    rendered as a markdown table, row/column binding preserved
      <dl>       rendered as "term -- definition" pairs
      MathML     rendered to readable inline text rather than dropped
      chrome     .DocHeader*, <script>, <style>, <link>, nav stripped by selector

    Boilerplate removal matters more than it sounds: text repeated on every
    page carries zero discriminative power but inflates every BM25 score.

CHUNKING
    Semantic-boundary-first: split on the page's own <section> structure, and
    only window an oversized section. Every chunk is prefixed with its
    breadcrumb ("Analysis Reference > Riks method > ...") so a retrieved chunk
    is self-describing and the lexical index can match on section titles.

RETRIEVAL
    Lexical-dominant hybrid. For reference documentation the query is often a
    literal token (*STATIC, RIKS / ALLSD / B31) where BM25 is exactly right and
    dense similarity actively hurts by pulling in "conceptually related" prose.
    Default blend is BM25:dense = 2:1; dense is optional and the corpus works
    without it.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
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
# --------------------------------------------------------------------------
def chunk_page(page: Page, target_words: int = 220,
               overlap_words: int = 60) -> list[dict]:
    """Split on the page's own '## heading' structure; window oversized parts.

    Code fences are atomic: a chunk boundary is never placed inside one.
    Every chunk is prefixed with its breadcrumb so it stands alone.
    """
    breadcrumb = f"{page.book_name} > {page.title}".strip(" >")
    blocks = re.split(r"\n## ", page.text)
    sections: list[tuple[str, str]] = []
    for i, blk in enumerate(blocks):
        if not blk.strip():
            continue
        if i == 0:
            sections.append(("", blk.strip()))
        else:
            head, _, rest = blk.partition("\n")
            sections.append((head.strip(), rest.strip()))

    chunks: list[dict] = []
    for head, content in sections:
        if not content:
            continue
        crumb = breadcrumb + (f" > {head}" if head else "")
        # split into atomic units: fenced code stays whole
        units = re.split(r"(```.*?```)", content, flags=re.DOTALL)
        buf: list[str] = []
        count = 0

        def flush():
            nonlocal buf, count
            if not buf:
                return
            body = " ".join(buf).strip()
            if body:
                chunks.append({
                    "page_id": page.page_id, "book": page.book,
                    "book_name": page.book_name, "title": page.title,
                    "section": head, "breadcrumb": crumb,
                    "text": f"[{crumb}]\n{body}",
                })
            buf, count = [], 0

        for unit in units:
            if not unit or not unit.strip():
                continue
            if unit.startswith("```"):
                buf.append(unit)
                count += len(unit.split())
                if count >= target_words:
                    flush()
                continue
            words = unit.split()
            idx = 0
            while idx < len(words):
                room = max(target_words - count, 1)
                take = words[idx:idx + room]
                buf.append(" ".join(take))
                count += len(take)
                idx += len(take)
                if count >= target_words:
                    tail = " ".join(" ".join(buf).split()[-overlap_words:])
                    flush()
                    if tail:
                        buf, count = [tail], len(tail.split())
        flush()
    return chunks


# --------------------------------------------------------------------------
# corpus
# --------------------------------------------------------------------------
def _tokenize(s: str) -> list[str]:
    """Tokenizer that PRESERVES Abaqus syntax tokens.

    '*STATIC, RIKS' must survive as searchable units; a naive \\w+ split throws
    away the leading '*' that distinguishes a keyword from prose, and splits
    'E11' or 'B31' cleanly but loses '*step'. Keeps both a starred and bare
    form so either query style hits.
    """
    s = s.lower()
    toks = re.findall(r"\*?[a-z_][a-z0-9_]*|\d+[a-z]+\d*|[a-z]+\d+", s)
    out = []
    for t in toks:
        out.append(t)
        if t.startswith("*"):
            out.append(t[1:])
    return out


class AbaqusDocCorpus:
    """Build once, then search. State lives in one SQLite file plus an
    optional embeddings .npy next to it."""

    def __init__(self, corpus_dir):
        self.dir = Path(corpus_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.dir / "corpus.sqlite"
        self.vec_path = self.dir / "chunk_vectors.npy"
        self._bm25 = None
        self._chunks = None
        self._vectors = None

    # -- build -------------------------------------------------------------
    def build(self, pages_dir, log=print) -> dict:
        pages_dir = Path(pages_dir)
        files = sorted(pages_dir.rglob("*.htm"))
        log(f"  pages found: {len(files):,}")

        db = sqlite3.connect(self.db_path)
        db.executescript("""
            drop table if exists pages;
            drop table if exists chunks;
            create table pages(
                page_id text, title text, book text, book_name text,
                rel_path text primary key, text text,
                n_pre int, n_table int, n_math int, n_dl int, keywords text);
            create table chunks(
                chunk_id integer primary key, page_id text, rel_path text,
                book text, book_name text, title text, section text,
                breadcrumb text, text text);
        """)

        stats = {"pages": 0, "parse_fail": 0, "empty": 0, "chunks": 0,
                 "pre": 0, "table": 0, "math": 0, "dl": 0, "chars": 0}
        thin = []
        cid = 0
        for f in files:
            page = extract_page(f, pages_dir)
            if page is None:
                stats["parse_fail"] += 1
                continue
            if len(page.text) < 200:
                stats["empty"] += 1
                thin.append((f.relative_to(pages_dir).as_posix(),
                             len(page.text)))
            db.execute(
                "insert or replace into pages values (?,?,?,?,?,?,?,?,?,?,?)",
                (page.page_id, page.title, page.book, page.book_name,
                 page.rel_path, page.text, page.n_pre, page.n_table,
                 page.n_math, page.n_dl, json.dumps(page.keywords)))
            stats["pages"] += 1
            stats["pre"] += page.n_pre
            stats["table"] += page.n_table
            stats["math"] += page.n_math
            stats["dl"] += page.n_dl
            stats["chars"] += len(page.text)
            for ch in chunk_page(page):
                db.execute(
                    "insert into chunks values (?,?,?,?,?,?,?,?,?)",
                    (cid, ch["page_id"], page.rel_path, ch["book"],
                     ch["book_name"], ch["title"], ch["section"],
                     ch["breadcrumb"], ch["text"]))
                cid += 1
                stats["chunks"] += 1
        db.commit()
        db.close()

        # extraction QA: pages that yielded almost nothing are a selector bug,
        # not a fact about the document. Surface them instead of hiding them.
        (self.dir / "thin_pages.txt").write_text(
            "\n".join(f"{n}\t{c}" for n, c in sorted(thin, key=lambda x: x[1])))
        stats["thin_report"] = str(self.dir / "thin_pages.txt")
        return stats

    # -- load --------------------------------------------------------------
    def _load(self):
        if self._chunks is not None:
            return
        db = sqlite3.connect(self.db_path)
        self._chunks = [
            {"chunk_id": r[0], "page_id": r[1], "rel_path": r[2], "book": r[3],
             "book_name": r[4], "title": r[5], "section": r[6],
             "breadcrumb": r[7], "text": r[8]}
            for r in db.execute(
                "select chunk_id,page_id,rel_path,book,book_name,title,"
                "section,breadcrumb,text from chunks order by chunk_id")
        ]
        db.close()
        from rank_bm25 import BM25Okapi
        self._bm25 = BM25Okapi([_tokenize(c["text"]) for c in self._chunks])
        if self.vec_path.exists():
            import numpy as np
            self._vectors = np.load(self.vec_path)

    # -- search ------------------------------------------------------------
    def search(self, query: str, top_k: int = 8, book: str | None = None,
               lexical_weight: float = 2.0, use_dense: bool = False) -> str:
        """Search; returns a formatted passage list.

        ``use_dense`` defaults to FALSE deliberately. Embedding the query goes
        through a3dasm's out-of-process worker, which costs ~26 s per call
        (measured warm) -- unusable for an interactive agent tool that is
        supposed to be consulted freely. Lexical-only answers the full golden
        set (36/36), so the fast path is also the accurate one for reference
        lookups, where queries are literal Abaqus tokens. Pass use_dense=True
        for a paraphrase-style question carrying no exact token, and accept
        the latency.
        """
        self._load()
        if not self._chunks:
            return "ERROR: corpus is empty — run build() first."

        scores = self._bm25.get_scores(_tokenize(query))
        import numpy as np
        scores = np.asarray(scores, dtype=float)
        if scores.max() > 0:
            lex = scores / scores.max()
        else:
            lex = scores

        combined = lexical_weight * lex
        if use_dense and self._vectors is not None:
            qv = self._embed([query])
            if qv is not None:
                import numpy as np
                q = np.asarray(qv[0], dtype=float)
                q /= (np.linalg.norm(q) + 1e-9)
                V = self._vectors
                dense = V @ q
                if dense.max() > 0:
                    dense = dense / dense.max()
                combined = combined + 1.0 * dense

        order = list(range(len(self._chunks)))
        if book:
            b = book.lower()
            order = [i for i in order
                     if b in self._chunks[i]["book"].lower()
                     or b in self._chunks[i]["book_name"].lower()]
            if not order:
                return f"ERROR: no book matching {book!r}."
        order.sort(key=lambda i: combined[i], reverse=True)
        hits = order[:max(1, int(top_k))]
        if not hits or combined[hits[0]] <= 0:
            return f"No passages matched {query!r}."

        out = []
        for rank, i in enumerate(hits, 1):
            c = self._chunks[i]
            body = c["text"]
            if len(body) > 1400:
                body = body[:1400] + " …"
            out.append(
                f"[{rank}] score={combined[i]:.3f}  page_id={c['page_id']}\n"
                f"    {c['breadcrumb']}\n    ({c['rel_path']})\n{body}\n")
        return "\n".join(out)

    def get_page(self, page_id: str) -> str:
        db = sqlite3.connect(self.db_path)
        row = db.execute(
            "select title, book_name, rel_path, text from pages "
            "where page_id=? or rel_path=?", (page_id, page_id)).fetchone()
        db.close()
        if not row:
            return f"ERROR: no page {page_id!r}."
        title, book, rel, text = row
        return f"# {title}\n({book} — {rel})\n\n{text}"

    def list_books(self) -> str:
        db = sqlite3.connect(self.db_path)
        rows = db.execute(
            "select book_name, book, count(*) from pages "
            "group by book order by count(*) desc").fetchall()
        db.close()
        return "\n".join(f"  {n:6,}  {bn}  [{b}]" for bn, b, n in rows)

    # -- embeddings (optional) --------------------------------------------
    def _embed(self, texts, timeout: float = 1800.0):
        """Embed via a3dasm's out-of-process worker.

        Each call pays ~18 s of fixed subprocess + model-load overhead, so
        batches want to be large -- but the worker's own default timeout is
        600 s, and a 512-batch of real 2,000-char chunks exceeds it (measured:
        failed at 616 s). Hence an explicit, generous timeout here.
        """
        try:
            from adda._src.literature_corpus import _SubprocessEmbedder
        except Exception:
            return None
        try:
            return _SubprocessEmbedder(timeout=timeout).embed(texts)
        except Exception:
            return None

    def embed_chunks(self, batch: int = 128, log=print,
                     timeout: float = 1800.0) -> bool:
        """Optional dense index. Corpus works without it (BM25-dominant).

        Resumable: partial progress is saved after every batch, so an
        interrupted run continues instead of restarting.
        """
        import numpy as np
        self._load()
        part_path = self.dir / "chunk_vectors.partial.npy"
        vecs = []
        if part_path.exists():
            vecs = [v for v in np.load(part_path)]
            log(f"  resuming from {len(vecs):,} embedded chunks")
        for i in range(len(vecs), len(self._chunks), batch):
            part = [c["text"][:2000] for c in self._chunks[i:i + batch]]
            got = self._embed(part, timeout=timeout)
            if got is None:
                log("  embeddings unavailable — staying lexical-only")
                return False
            vecs.extend(got)
            np.save(part_path, np.asarray(vecs, dtype="float32"))
            log(f"  embedded {min(i + batch, len(self._chunks)):,}"
                f"/{len(self._chunks):,}")
        V = np.asarray(vecs, dtype="float32")
        V /= (np.linalg.norm(V, axis=1, keepdims=True) + 1e-9)
        np.save(self.vec_path, V)
        part_path.unlink(missing_ok=True)
        self._vectors = V
        return True
