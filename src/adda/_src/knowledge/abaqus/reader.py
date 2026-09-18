"""Abaqus documentation, indexed around its own table of contents.

WHAT CHANGED FROM v1
    v1 flattened every page into 19k text chunks and searched them with BM25.
    That threw away the structure the publisher ships: each book carries a
    `structure.xml` -- a real table of contents, 31,041 nested entries with
    canonical titles and section anchors. v2 makes that tree the spine.

    Three things follow from it:
      * a hit is a LOCATION (book > chapter > section + page_id), not an
        anonymous passage, so the agent sees where it landed;
      * the tree also lists pages we do NOT hold, so a miss can say "this
        exists, we don't have it" instead of silently returning nothing --
        this media is a HotFix delta, holding ~45% of the pages the TOC
        describes, so silent misses would otherwise be common and misleading;
      * breadcrumbs are authoritative rather than inferred from headings.

THE TOOL SURFACE
    One entry point, two behaviours, disambiguated without a mode flag:

        consult("ALLSDTOL")          -> TOC-style hits
        consult("simakey-r-static")  -> that whole page

    A page_id is distinctive (`simakey-r-static`), never something typed as a
    query, and search results hand back the exact string -- so "argument is a
    known page_id" is a safe switch.

SIZES (measured)
    Median page is ~600 tokens, 90th percentile ~2,100, so returning whole
    pages is cheap. The only giant pages were Legal Notices (1.6M chars),
    sitemaps and the keyword-browser table -- boilerplate, dropped at ingest.
"""
from __future__ import annotations

import html as _html
import re
import sqlite3
from pathlib import Path

# ---------------------------------------------------------------------------
# what we index
# ---------------------------------------------------------------------------
# Books a datagenerator writing input decks and Abaqus-Python actually uses.
# The GUI manuals (Abaqus/CAE, Getting Started, GUI Toolkit), the Isight guides
# (Ihr*) and the Webtop/Frontmatter material are dropped: they document menus
# and unrelated products, and they contributed the largest noise pages.
KEEP_BOOKS = {
    "SIMACAEANLRefMap": "Analysis",
    "SIMACAEKEYRefMap": "Keywords",
    "SIMACAEELMRefMap": "Elements",
    "SIMACAEMATRefMap": "Materials",
    "SIMACAEITNRefMap": "Interactions",
    "SIMACAEOUTRefMap": "Output",
    "SIMACAETHERefMap": "Theory",
    "SIMACAESUBRefMap": "User Subroutines",
    "SIMACAEKERRefMap": "Scripting Reference",
    "SIMACAECMDRefMap": "Scripting",
    "SIMACAEEXCRefMap": "Execution",
    "SIMACAEEXARefMap": "Example Problems",
    "SIMACAEVERRefMap": "Verification",
    "SIMACAEBMKRefMap": "Benchmarks",
    "SIMACAECSTRefMap": "Constraints",
    "SIMACAEPRCRefMap": "Prescribed Conditions",
    "SIMACAEMODRefMap": "Introduction & Spatial Modeling",
    "SIMACAERNGRefMap": "Release Notes",
}

# Boilerplate pages: no documentation value, and the size outliers.
DROP_TITLE_RE = re.compile(r"^(legal notices|sitemap|abaqus keyword browser table)$", re.I)


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------
SCHEMA = """
drop table if exists nodes;
drop table if exists pages;
drop table if exists fts;
drop table if exists gaps;
drop table if exists vocab;

-- the table of contents, verbatim from each book's structure.xml
create table nodes(
    node_id     integer primary key,
    parent_id   integer,
    book        text,      -- directory, e.g. SIMACAEKEYRefMap
    book_name   text,      -- human, e.g. Keywords
    depth       integer,
    ord         integer,   -- order among siblings
    title       text,      -- the TOC entry's own title
    href        text,      -- page file it points at
    fragment    text,      -- #anchor within that page, if any
    page_id     text,      -- DC.identifier, when we hold the page
    have        integer    -- 1 = we hold the page, 0 = declared but absent
);
create index nodes_parent on nodes(parent_id);
create index nodes_href   on nodes(book, href);
create index nodes_page   on nodes(page_id);
create index nodes_have   on nodes(have);

create table pages(
    page_id   text primary key,
    book      text,
    book_name text,
    rel_path  text,
    title     text,
    title_norm text,    -- title lowercased with '*' stripped, for exact lookup
    dc_type   text,     -- reference | concept | task | topic
    abstract  text,     -- the publisher's own one-line summary
    text      text,
    n_pre integer, n_table integer, n_math integer, n_dl integer
);

-- one row per page; title/abstract weighted by being repeated at query time
create index pages_titlenorm on pages(title_norm);

-- distinct titles the table of contents DECLARES but this corpus lacks.
-- Materialised at build: deriving it per query (select distinct ... where
-- have=0) cost ~400 ms of every search.
create table gaps(book_name text, title text, title_low text);
create index gaps_low on gaps(title_low);

-- vocabulary for "did you mean": every page title and every TOC entry title,
-- normalised. A lone mistyped token ("*SATIC", "imperfetion") produces zero
-- FTS hits, because FTS matches tokens exactly; approximate matching over this
-- table is the fallback.
create table vocab(term text, term_norm text, page_id text, book_name text, kind text);
create index vocab_norm on vocab(term_norm);

create virtual table fts using fts5(
    page_id UNINDEXED, title, abstract, body, tokenize='porter unicode61'
);
"""


def _norm_title(t: str) -> str:
    """Title reduced for exact matching: no '*', lowercased, single-spaced.

    Precomputed and INDEXED at build time. Doing this inline in the query
    (lower(replace(replace(title,...)))) defeats the index and costs ~1s per
    search on 3.5k pages -- measured.
    """
    return " ".join(_html.unescape(t or "").replace("*", " ").lower().split())


def _clean(t: str) -> str:
    """TOC titles carry XML entities (&#xA;, &amp;) and stray whitespace."""
    if not t:
        return ""
    return " ".join(_html.unescape(t).split())


def _toc_title_chain(db, node_id):
    """book > chapter > ... > this node"""
    parts = []
    cur = node_id
    while cur is not None:
        row = db.execute(
            "select parent_id, title, book_name from nodes where node_id=?",
            (cur,)).fetchone()
        if not row:
            break
        parts.append(_clean(row[1]))
        cur = row[0]
        if cur is None:
            parts.append(_clean(row[2]))
    return " > ".join(reversed([p for p in parts if p]))


class AbaqusDocs:
    def __init__(self, corpus_dir):
        self.dir = Path(corpus_dir)
        self.db_path = self.dir / "abaqus_docs.sqlite"

    # -- build ------------------------------------------------------------
    def build(self, pages_root, log=print) -> dict:
        from lxml import etree

        # The extractor lives in builder.py, this package's own module. It was
        # imported as `abaqus_doc_corpus` -- the name the file had as a
        # standalone script -- which no longer resolves anywhere, so build()
        # could never run.
        from .builder import extract_page

        pages_root = Path(pages_root)
        db = sqlite3.connect(self.db_path)
        db.executescript(SCHEMA)

        stats = {"books": 0, "toc_nodes": 0, "pages": 0, "declared": 0,
                 "have": 0, "dropped_boilerplate": 0, "parse_fail": 0}

        # --- 1. pages we physically hold, per kept book
        page_by_rel: dict[tuple[str, str], dict] = {}
        for book in sorted(KEEP_BOOKS):
            bdir = pages_root / "English" / book
            if not bdir.is_dir():
                continue
            for f in sorted(bdir.glob("*.htm")):
                page = extract_page(f, pages_root)
                if page is None:
                    stats["parse_fail"] += 1
                    continue
                if DROP_TITLE_RE.match((page.title or "").strip()):
                    stats["dropped_boilerplate"] += 1
                    continue
                meta_type, abstract = _page_meta(f, etree)
                rec = dict(page_id=page.page_id, book=book,
                           book_name=KEEP_BOOKS[book], rel_path=page.rel_path,
                           title=page.title,
                           title_norm=_norm_title(page.title),
                           dc_type=meta_type,
                           abstract=abstract, text=page.text,
                           n_pre=page.n_pre, n_table=page.n_table,
                           n_math=page.n_math, n_dl=page.n_dl)
                page_by_rel[(book, f.name)] = rec
        for rec in page_by_rel.values():
            db.execute(
                "insert or replace into pages values (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                tuple(rec[k] for k in ("page_id", "book", "book_name",
                                       "rel_path", "title", "title_norm",
                                       "dc_type",
                                       "abstract", "text", "n_pre", "n_table",
                                       "n_math", "n_dl")))
            db.execute("insert into fts values (?,?,?,?)",
                       (rec["page_id"], rec["title"] or "",
                        rec["abstract"] or "", rec["text"] or ""))
        stats["pages"] = len(page_by_rel)

        # --- 2. the table of contents, as a tree
        nid = 0
        for book in sorted(KEEP_BOOKS):
            sx = pages_root / "English" / book / "structure.xml"
            if not sx.exists():
                continue
            stats["books"] += 1
            root = etree.parse(str(sx), etree.XMLParser(recover=True)).getroot()

            # `book` is bound as a default for the same reason flush() does
            # it in builder.py: walk() recurses inside a per-book loop, and a
            # late-bound reference would file this book's TOC nodes under
            # whichever book the loop had reached.
            def walk(el, parent_id, depth, book=book):
                nonlocal nid
                for order, it in enumerate(el.findall("ITEM")):
                    href_raw = it.get("href") or ""
                    href, _, frag = href_raw.partition("#")
                    rec = page_by_rel.get((book, href)) if href else None
                    nid += 1
                    me = nid
                    db.execute(
                        "insert into nodes values (?,?,?,?,?,?,?,?,?,?,?)",
                        (me, parent_id, book, KEEP_BOOKS[book], depth, order,
                         _clean(it.get("title")), href, frag or None,
                         rec["page_id"] if rec else None, 1 if rec else 0))
                    stats["toc_nodes"] += 1
                    if href:
                        stats["declared"] += 1
                        stats["have"] += 1 if rec else 0
                    walk(it, me, depth + 1)

            walk(root, None, 0)

        db.execute(
            "insert into gaps select distinct book_name, title, lower(title) "
            "from nodes where have=0 and title is not null and title<>''")
        db.execute(
            "insert into vocab select distinct title, title_norm, page_id, "
            "book_name, 'page' from pages where title is not null and title<>''")
        db.execute(
            "insert into vocab select distinct n.title, "
            "lower(replace(n.title,'*','')), n.page_id, n.book_name, 'toc' "
            "from nodes n where n.title is not null and n.title<>'' "
            "and n.have=1")
        db.commit()
        db.close()
        return stats

    # -- query ------------------------------------------------------------
    def consult(self, query: str, limit: int = 8) -> str:
        """Search, or return a page when `query` is a known page_id."""
        db = sqlite3.connect(self.db_path)
        q = (query or "").strip()
        if not q:
            return "ERROR: empty query."
        hit = db.execute("select page_id from pages where page_id=?", (q,)).fetchone()
        if hit:
            return self._render_page(db, q)
        return self._search(db, q, limit)

    # A page read has to fit in the agent's context alongside everything else
    # it is carrying. Overflowing a context is not a soft failure on every
    # backend: ollama truncates server-side and then rejects the request for
    # having no user turn left (see tests/oracle_bench/ollama_userless_repro.py),
    # which surfaces as an opaque 500 mid-run. 24k chars is ~6k tokens.
    PAGE_CHAR_CAP = 24_000

    def _render_page(self, db, page_id: str, cap: int | None = None) -> str:
        t, bn, rp, dct, ab, txt = db.execute(
            "select title, book_name, rel_path, dc_type, abstract, text "
            "from pages where page_id=?", (page_id,)).fetchone()
        node = db.execute(
            "select node_id from nodes where page_id=? and fragment is null "
            "order by depth limit 1", (page_id,)).fetchone()
        crumb = _toc_title_chain(db, node[0]) if node else bn
        secs = db.execute(
            "select title from nodes where page_id=? and fragment is not null "
            "order by node_id", (page_id,)).fetchall()
        head = [f"# {t}", f"{crumb}", f"page_id: {page_id}  ({dct or 'topic'})"]
        if ab:
            head.append(f"\n{ab}")
        if secs:
            head.append("\nSections: " + " | ".join(_clean(s[0]) for s in secs[:25]))
        cap = self.PAGE_CHAR_CAP if cap is None else cap
        if cap and len(txt) > cap:
            # Cut on a section boundary so the agent gets whole sections, and
            # name the sections it did not get -- a silent truncation would
            # read as "the documentation does not cover this".
            cut = txt.rfind("\n## ", 0, cap)
            if cut < cap // 2:
                cut = cap
            dropped = [ln[3:].strip() for ln in txt[cut:].splitlines()
                       if ln.startswith("## ")]
            txt = txt[:cut].rstrip() + (
                f"\n\n[page truncated at {cut:,} of {len(txt):,} chars]"
                + (f"\nSections not shown: {' | '.join(dropped[:20])}"
                   if dropped else ""))
        return "\n".join(head) + "\n\n" + txt

    def _search(self, db, query: str, limit: int) -> str:
        # FTS5 reserves a leading '*' (and ^ : " - NEAR etc.) as query syntax.
        # EVERY Abaqus keyword starts with '*', so a raw query like "*STATIC"
        # raises "unknown special query". Tokenize and quote instead.
        terms = re.findall(r"[A-Za-z0-9_]+", query)
        if not terms:
            return f"No documentation matched {query!r}."
        expr = " OR ".join(f'"{t}"' for t in terms)

        rows = db.execute(
            "select page_id, bm25(fts, 0.0, 8.0, 4.0, 1.0) as s "
            "from fts where fts match ? order by s limit ?",
            (expr, limit * 4)).fetchall()
        ranked = [r[0] for r in rows]

        # Nothing matched: the query is very likely misspelled or names
        # something that does not exist. Offer the closest real titles rather
        # than an empty answer -- a lone bad token ("*SATIC") is otherwise a
        # dead end, since FTS matches tokens exactly.
        suggestions = []
        if not ranked:
            suggestions = self._did_you_mean(db, query, terms)

        # Exact keyword-title hit ranks first. Keywords Reference pages are
        # titled "*STATIC", "*CONTACT PAIR" etc., so a query naming a keyword
        # should land on its own page rather than on a passage that mentions
        # it -- BM25 alone cannot know that, because the tokenizer has already
        # discarded the '*'.
        norm = " ".join(terms).lower()
        exact = [r[0] for r in db.execute(
            "select page_id from pages where title_norm = ?", (norm,))]

        # A query written as a keyword ("*NON-EQUILIBRIUM") asserts that such a
        # keyword exists. If no Keywords page carries that title, say so first:
        # otherwise stemming happily returns pages that merely mention a word
        # from it, and the agent may take that as confirmation the keyword is
        # real. This is the dominant query shape, so it is worth special-casing.
        kw_note = ""
        first = query.strip().split()[0] if query.strip() else ""
        if first.startswith("*") and len(first) > 1:
            # Check the LEADING KEYWORD alone, not the whole query. Checking the
            # whole query was wrong: "*STEP BUCKLE EIGENSOLVER SUBSPACE" has no
            # page titled that, so the tool told an agent "*STEP does not exist"
            # -- misinforming it about a keyword that plainly does. A note that
            # can fire on a real keyword is worse than no note at all.
            kw = _norm_title(first)
            hit = db.execute(
                "select 1 from pages where book='SIMACAEKEYRefMap' "
                "and title_norm=? limit 1", (kw,)).fetchone()
            if not hit:
                import difflib
                kws = {r[0]: r[1] for r in db.execute(
                    "select title_norm, title from pages "
                    "where book='SIMACAEKEYRefMap'")}
                close = difflib.get_close_matches(kw, list(kws), n=4, cutoff=0.6)
                kw_note = (f"NOTE: no Abaqus keyword named {first} appears in "
                           f"this documentation.")
                if close:
                    kw_note += ("  Closest: " + ", ".join(kws[c] for c in close) + ".")
                kw_note += "\n\n"

        ordered = exact + [p for p in ranked if p not in exact]

        out = []
        for page_id in ordered[:limit]:
            r = db.execute(
                "select title, book_name, dc_type, abstract from pages "
                "where page_id=?", (page_id,)).fetchone()
            if not r:
                continue
            title, bn, dct, ab = r
            node = db.execute(
                "select node_id from nodes where page_id=? and fragment is null "
                "order by depth limit 1", (page_id,)).fetchone()
            crumb = _toc_title_chain(db, node[0]) if node else bn
            line = f"  {crumb}\n    page_id: {page_id}  [{dct or 'topic'}]"
            if ab:
                line += f"\n    {_clean(ab)[:180]}"
            out.append(line)

        gaps = []
        if len(terms) >= 2:
            sql = "select book_name, title from gaps where " + \
                  " and ".join(["title_low like ?"] * len(terms)) + " limit 5"
            gaps = db.execute(sql, [f"%{t.lower()}%" for t in terms]).fetchall()

        if not out and not gaps and suggestions:
            body = "\n".join(
                f"  {t}  ->  page_id: {pid}   [{bn}]" for t, pid, bn in suggestions)
            return (f"No documentation matched {query!r}. "
                    f"Closest titles in the documentation:\n{body}\n\n"
                    "Re-run with one of these, or with a page_id, to read it.")
        if not out and not gaps:
            return (f"No documentation matched {query!r}.\n"
                    "This corpus holds ~45% of the pages the Abaqus table of "
                    "contents declares (a HotFix delta), so absence here is "
                    "not proof the topic is undocumented.")
        head = (kw_note + f"{len(out)} page(s) matching {query!r} — "
                f"pass a page_id back to read the full page:\n")
        body = "\n".join(out) if out else "  (no held page matched)"
        tail = ""
        if gaps:
            tail = ("\n\nDeclared in the documentation but NOT in this corpus:\n"
                    + "\n".join(f"  {b} > {_clean(t)}" for b, t in gaps))
        return head + body + tail

    @staticmethod
    def _did_you_mean(db, query: str, terms: list, k: int = 5) -> list:
        """Closest real titles to a query that matched nothing.

        difflib over ~4k normalised titles: no dependency, few ms, and it
        handles the realistic failure ("*SATIC" -> "*STATIC", "imperfetion" ->
        "*IMPERFECTION") which exact-token FTS cannot.
        """
        import difflib
        rows = db.execute(
            "select term, term_norm, page_id, book_name from vocab "
            "where page_id is not null").fetchall()
        norm = " ".join(t.lower() for t in terms)
        index = {}
        for term, tnorm, pid, bn in rows:
            if tnorm and tnorm not in index:
                index[tnorm] = (term, pid, bn)
        close = difflib.get_close_matches(norm, list(index), n=k, cutoff=0.6)
        # also try each token alone, which catches a typo inside a phrase
        if len(terms) > 1:
            for t in terms:
                for m in difflib.get_close_matches(t.lower(), list(index),
                                                   n=2, cutoff=0.75):
                    if m not in close:
                        close.append(m)
        return [index[m] for m in close[:k]]

    # -- introspection -----------------------------------------------------
    def books(self) -> str:
        db = sqlite3.connect(self.db_path)
        rows = db.execute(
            "select book_name, count(distinct case when have=1 then href end), "
            "count(distinct href) from nodes group by book_name "
            "order by 2 desc").fetchall()
        db.close()
        out = ["  held  declared  book"]
        for bn, have, tot in rows:
            out.append(f"  {have or 0:4}  {tot or 0:8}  {bn}")
        return "\n".join(out)


def _page_meta(path, etree):
    """DC.type and the publisher's abstract, straight from the page."""
    try:
        t = etree.fromstring(Path(path).read_bytes(),
                             etree.HTMLParser(recover=True))
    except Exception:
        return None, None
    dct = ab = None
    for m in t.xpath("//meta"):
        n, c = m.get("name"), m.get("content")
        if n == "DC.type":
            dct = c
        elif n in ("abstract", "description") and not ab:
            ab = c
    return dct, ab
