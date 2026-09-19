"""The control adda's literature retrieval has to beat -- ripgrep and the
substring floor -- and the question the whole design rests on: does hybrid
(RRF over BM25 + dense/fastembed) earn its place over BM25 alone.

Modelled closely on ``internal/tools/source_index_baseline.py``, which did
this for code search (pre-registered queries, a ripgrep control, a held-out
split, blind-authored expansion, McNemar significance -- see commits
7cddc13, d6239f9, 9754d91, 6c5ec81, 1e9d0e8). This is the same discipline,
applied to literature retrieval, where 3,632 lines of literature tests
contain zero r@k/MRR/recall/gold assertions before this file existed.

THIS FILE IS THE INSTRUMENT ONLY. It ships with NO query set -- a separate,
blind author writes the labelled queries later, against the manifest at
``scratchpad/litcorpus_manifest.md`` (paper_id/title/description, no
queries, no gold labels). Nothing in this module may be edited to
accommodate a retriever, and nothing here may originate a query or a gold
label.

FOUR ARMS, all scored identically on the same queries, all against the same
frozen corpus fixture:

    rg          ripgrep over the corpus's extracted text (``papers/*/paper.md``).
                The EXTERNAL floor. Two variants are scored -- raw match
                counts, and matches-per-kilobyte -- and the HIGHER is the bar,
                exactly as source_index_baseline.py does (raw counts favour
                long files; per-kb favours short, dense ones).
    substring   retrieval_mode="substring": no ranking at all. The internal
                floor -- what CorpusSearch does with zero retrieval logic.
    bm25        retrieval_mode="bm25": lexical only. THE CONTROL.
    hybrid      retrieval_mode="hybrid": RRF over BM25 + dense (fastembed,
                possibly out-of-process via uv -- see embedder.py). THE ARM
                UNDER TEST. The decisive comparison is hybrid vs bm25: does
                fastembed earn its place. rg and substring are floors, not
                the bar.

Every mode is requested EXPLICITLY (never "auto", which silently degrades).
``LiteratureCorpus.resolved_mode`` records what a search actually ran as,
and is asserted against the requested arm after every single query -- an
arm that silently ran as something else is a mislabelled condition, not a
detail, and this harness refuses to score one. If the dense embedder
cannot run in this environment (no ``uv`` on PATH, or the out-of-process
probe fails), that is reported PLAINLY and three arms are scored, not four
-- never a silent fallback.

METRICS -- a literature reviewer's cost asymmetry is the opposite of code
search's: a missed relevant paper silently narrows a whole run, while a
wrong top hit only costs one read. So:

    PRIMARY    recall@5, recall@10, recall@20, and Lost Evidence (1 - recall@k)
    SECONDARY  r@1, MRR
    ALSO       wall-clock per query per arm, and for the dense arm the
               embedder subprocess overhead (measured as the hybrid-vs-bm25
               per-query wall-time delta, since every query pays a fresh
               ``uv run`` subprocess spawn when the out-of-process embedder
               route is active -- see embedder.py's ``_SubprocessEmbedder``,
               which has no persistent server). Report cost-per-hit: a win
               that costs 100x is not a win.

Gold labels are paper_ids, not chunk ids -- a chunk-level gold is too
brittle. Retrieved chunks are collapsed to their paper_id before scoring,
the way ``_score_index`` in source_index_baseline.py collapses entries to
their file: rank ``--raw-k`` (default 60) raw chunks, take the first
occurrence of each paper_id in that order, then slice at 5/10/20.

STATISTICS -- learned from the source index's first mistake at n=34
(source_index_baseline.py's docstring, and 1e9d0e8's honest shrinkage
report): every paired arm comparison gets an EXACT McNemar test (stdlib
binomial, no scipy -- scipy is not a declared adda dependency) and a
bootstrap 95% CI on the difference, plus a power note (the n the observed
effect would need for 80% power). These are FUNCTIONS here, not something
left to whoever reads the table, so every future run reports them
automatically.

Usage::

    uv run python internal/tools/literature_retrieval_baseline.py \\
        --corpus /path/to/frozen/litcorpus --queries tests/some_query_set.py

``--corpus`` is any LiteratureCorpus-shaped directory (``corpus.csv``,
``chunks.jsonl``, ``papers/<paper_id>/{paper.md,chunks.npy}``). A frozen
fixture copied from elsewhere carries STALE absolute paths in its
``corpus.csv`` (``local_md_path`` baked in from wherever it was built) --
this harness self-heals that into a disposable temp working copy at
startup; it never mutates the source ``--corpus`` directory.

``--queries`` is a Python file exposing ``QUERIES: list[tuple[str, str,
list[str]]]`` of ``(qid, query_text, gold_paper_ids)`` triples (a 4th,
trailing ``tier`` element is also accepted, for a stratified query set). No
default is shipped, and pointing at a missing/malformed one fails loudly
rather than silently scoring zero queries.

``--held-out`` scores the frozen split instead of DEVELOPMENT. Do not pass
it until the design is frozen; that is what makes the split worth having --
mirrors ``source_index_baseline.py``'s ``--held-out``. The query module may
declare ``HELD_OUT_IDS: frozenset[str]``, a set of ``qid`` values listed
LITERALLY (never computed -- a hash-based split silently reshuffles the
moment a query is added and the held-out set stops being held out; see
``tests/adda_source_queries.py``). Every id it names must exist in
``QUERIES``, checked on load. Without a declared ``HELD_OUT_IDS`` the
module still loads (backward compatible), all queries are DEVELOPMENT, and
a warning is printed that no held-out split exists; passing ``--held-out``
against such a module is a loud error, not a silent empty scoring run.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import random
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

#: Same generic, domain-agnostic stoplist source_index_baseline.py uses for
#: the ripgrep control. Kept small and generic on purpose -- see that file's
#: docstring: a stoplist tuned against these very queries would make the
#: control look worse and the harness look better, which is backwards for a
#: control.
STOP = frozenset(
    "how do i the a an of to in is it and or what where when which for does "
    "can my me on at that this with from without so be are was there here "
    "into out up off no not has have if its".split())

ARMS = ("rg", "substring", "bm25", "hybrid")

#: Paper-level collapsing strategies for the internal (bm25/hybrid) arms --
#: see `aggregate_chunk_scores`. "first" is the pre-existing behaviour
#: (first-seen chunk wins, no pooling of a paper's other chunks) and is the
#: baseline every other strategy is measured against.
AGGREGATIONS = ("first", "sum", "max", "mean", "sum_norm")

#: How many raw chunks to rank before collapsing to distinct paper_ids and
#: slicing at 5/10/20 -- mirrors _score_index's k=60 in source_index_baseline.py.
DEFAULT_RAW_K = 60


# ---------------------------------------------------------------------------
# Query set loading -- fails loudly, ships with nothing
# ---------------------------------------------------------------------------

@dataclass
class Query:
    qid: str
    text: str
    gold: frozenset[str]
    tier: str | None = None


def load_queries(spec: str, *, held_out: bool = False) -> list[Query]:
    """Load ``QUERIES`` (and an optional frozen ``HELD_OUT_IDS`` split) from
    *spec*, and return the DEVELOPMENT queries or the HELD_OUT ones.

    *spec* is a path to a ``.py`` file. There is no default query set and no
    silent empty-list fallback: a missing or malformed module is a hard
    error, because a harness that quietly scored zero queries would look
    identical to one that never ran.

    ``QUERIES`` entries are ``(qid, query_text, gold_paper_ids)`` triples, or
    ``(qid, query_text, gold_paper_ids, tier)`` 4-tuples -- both are
    accepted so a query set can grow a tier field without breaking the
    existing 3-tuple contract.

    An optional module-level ``HELD_OUT_IDS: frozenset[str]`` names a
    frozen held-out split by ``qid``, listed LITERALLY rather than computed
    -- a hash-based split silently reshuffles the moment a query is added
    and the held-out set stops being held out (the same discipline
    ``tests/adda_source_queries.py`` documents and
    ``source_index_baseline.py`` mirrors with its own ``--held-out``).
    Every id ``HELD_OUT_IDS`` names must exist in ``QUERIES`` -- checked
    here, loudly, rather than silently scoring a typo'd id as "development".

    *held_out* selects which split this call returns: ``False`` (default)
    returns DEVELOPMENT (every query NOT in ``HELD_OUT_IDS``); ``True``
    returns the frozen HELD_OUT split. A module with only ``QUERIES`` (no
    ``HELD_OUT_IDS``) still loads -- every query is treated as
    DEVELOPMENT, and a warning is printed that no held-out split is
    declared -- but passing ``held_out=True`` against such a module is a
    hard error: there is no frozen split to score, and returning an empty
    list would look identical to a harness that silently scored nothing.
    """
    path = Path(spec)
    if not path.exists():
        raise SystemExit(
            f"ERROR: --queries {spec!r} does not exist. This harness ships "
            "with NO query set on purpose (see the module docstring) -- "
            "point --queries at a file exposing QUERIES: "
            "list[tuple[qid, query_text, gold_paper_ids]]."
        )
    module_name = "adda_literature_queries_" + re.sub(r"\W", "_", path.stem)
    module_spec = importlib.util.spec_from_file_location(module_name, path)
    if module_spec is None or module_spec.loader is None:
        raise SystemExit(f"ERROR: could not load {spec!r} as a Python module.")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    raw = getattr(module, "QUERIES", None)
    if raw is None:
        raise SystemExit(
            f"ERROR: {spec!r} has no QUERIES list. Expected "
            "list[tuple[qid, query_text, gold_paper_ids]]."
        )
    out: list[Query] = []
    for i, row in enumerate(raw):
        if len(row) == 3:
            qid, text, gold = row
            tier = None
        elif len(row) == 4:
            qid, text, gold, tier = row
        else:
            raise SystemExit(
                f"ERROR: {spec!r} QUERIES[{i}] = {row!r} is not a "
                "(qid, query_text, gold_paper_ids) triple or "
                "(qid, query_text, gold_paper_ids, tier) 4-tuple."
            )
        out.append(Query(qid=str(qid), text=str(text), gold=frozenset(gold),
                          tier=str(tier) if tier is not None else None))
    if not out:
        raise SystemExit(f"ERROR: {spec!r} QUERIES is empty.")

    all_ids = {q.qid for q in out}
    raw_held_out_ids = getattr(module, "HELD_OUT_IDS", None)
    if raw_held_out_ids is not None:
        held_out_ids = frozenset(str(x) for x in raw_held_out_ids)
        unknown = held_out_ids - all_ids
        if unknown:
            raise SystemExit(
                f"ERROR: {spec!r} HELD_OUT_IDS names id(s) not present in "
                f"QUERIES: {sorted(unknown)!r}. HELD_OUT_IDS must list "
                "qids LITERALLY against ids that actually exist in "
                "QUERIES -- a hash-based or computed split silently "
                "reshuffles the moment a query is added and the held-out "
                "set stops being held out (see "
                "tests/adda_source_queries.py)."
            )
    else:
        held_out_ids = None
        if held_out:
            raise SystemExit(
                f"ERROR: --held-out was passed but {spec!r} declares no "
                "HELD_OUT_IDS -- there is no frozen split to score. Add "
                "HELD_OUT_IDS = frozenset({...}) with ids listed "
                "literally, or drop --held-out to score all queries as "
                "DEVELOPMENT."
            )
        print(f"  WARNING: {spec!r} declares no HELD_OUT_IDS -- scoring "
              "ALL queries as DEVELOPMENT. No held-out split exists for "
              "this query set.")

    dev = [q for q in out if held_out_ids is None or q.qid not in held_out_ids]
    ho = [q for q in out if held_out_ids is not None and q.qid in held_out_ids]

    tiers = sorted({q.tier for q in out if q.tier is not None})
    print(f"  {len(out)} total queries: {len(dev)} development, "
          f"{len(ho)} held-out"
          + (f", tiers: {', '.join(tiers)}" if tiers else ""))
    if tiers:
        for split_name, rows in (("development", dev), ("held-out", ho)):
            if not rows:
                continue
            counts: dict[str, int] = {}
            for q in rows:
                counts[q.tier] = counts.get(q.tier, 0) + 1
            breakdown = ", ".join(f"{t}={counts.get(t, 0)}" for t in tiers)
            print(f"    {split_name} by tier: {breakdown}")

    selected = ho if held_out else dev
    if not selected:
        raise SystemExit(
            f"ERROR: the {'held-out' if held_out else 'development'} split "
            f"of {spec!r} is empty -- nothing to score."
        )
    return selected


def validate_gold_reachability(queries: list[Query], corpus_dir: Path) -> None:
    """Warn (not fail) about gold paper_ids that no arm can ever hit.

    The frozen fixture has papers that are NOT reachable through
    ``LiteratureCorpus.search()`` at all: an orphan directory with no
    ``corpus.csv`` row (excluded from ``full_text_ids``, see
    literature_corpus.py's ``search()``), and paper_ids that simply do not
    exist on disk (a typo in the query set). Either makes recall for that
    query structurally 0 on substring/bm25/hybrid regardless of ranking
    quality -- worth surfacing loudly before scoring, not discovering after.
    """
    csv_path = corpus_dir / "corpus.csv"
    registered: set[str] = set()
    if csv_path.exists():
        with csv_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("full_text", "false").lower() == "true":
                    registered.add(row["paper_id"])
    on_disk = {p.name for p in (corpus_dir / "papers").iterdir() if p.is_dir()}
    for q in queries:
        for pid in q.gold:
            if pid not in on_disk:
                print(f"  WARNING [{q.qid}] gold {pid!r} is not a paper "
                      f"directory under {corpus_dir}/papers -- likely a typo.")
            elif pid not in registered:
                print(f"  WARNING [{q.qid}] gold {pid!r} exists but is not "
                      "registered full_text=true in corpus.csv -- "
                      "unreachable by substring/bm25/hybrid; only rg can "
                      "ever hit it.")


# ---------------------------------------------------------------------------
# Corpus materialization: a frozen fixture's corpus.csv carries stale
# absolute local_md_path/local_pdf_path columns baked in from wherever it
# was built. _search_substring() and get_paper() read those paths directly
# and silently skip a row whose path does not exist -- so left unfixed, the
# substring arm would score a false, silent floor of zero everywhere.
# ---------------------------------------------------------------------------

def materialize_corpus(src: Path, workdir: Path) -> Path:
    """Return a disposable corpus dir with corpus.csv paths rehomed to *src*.

    ``papers/`` and ``chunks.jsonl`` are symlinked (not copied -- the fixture
    is ~40MB and re-copying it per run buys nothing); only ``corpus.csv`` is
    rewritten, into the temp dir, so the frozen *src* copy is never mutated
    and stays byte-identical for the content hash that versions it.
    """
    dst = workdir / "corpus"
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "papers").symlink_to((src / "papers").resolve())
    (dst / "chunks.jsonl").symlink_to((src / "chunks.jsonl").resolve())

    src_csv = src / "corpus.csv"
    if not src_csv.exists():
        raise SystemExit(f"ERROR: {src_csv} does not exist -- not a "
                          "LiteratureCorpus-shaped directory.")
    with src_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    for row in rows:
        pid = row["paper_id"]
        md = dst / "papers" / pid / "paper.md"
        if md.exists():
            row["local_md_path"] = str(md)
        pdf = dst / "papers" / pid / "paper.pdf"
        row["local_pdf_path"] = str(pdf) if pdf.exists() else ""
    with (dst / "corpus.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return dst


# ---------------------------------------------------------------------------
# Arm 1: rg -- the external floor
# ---------------------------------------------------------------------------

def _rg_rank(query: str, papers_dir: Path, k: int, *, per_kb: bool) -> list[str]:
    toks = [t for t in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]+", query.lower())
            if t not in STOP]
    if not toks:
        return []
    pat = "|".join(re.escape(t) for t in toks)
    try:
        out = subprocess.run(
            ["rg", "-i", "-L", "--count-matches", "-e", pat, str(papers_dir),
             "-g", "paper.md"],
            capture_output=True, text=True, timeout=120, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    scores: dict[str, float] = {}
    for line in out.splitlines():
        if ":" not in line:
            continue
        path, n = line.rsplit(":", 1)
        try:
            hits = int(n)
        except ValueError:
            continue
        pid = Path(path).parent.name  # papers/<paper_id>/paper.md
        if per_kb:
            hits = hits * 1000 / max(Path(path).stat().st_size, 1)
        scores[pid] = scores.get(pid, 0) + hits
    ranked = [p for p, _ in sorted(scores.items(), key=lambda kv: -kv[1])]
    return ranked[:k]


# ---------------------------------------------------------------------------
# Arms 2-4: substring / bm25 / hybrid via the real LiteratureCorpus.search()
# ---------------------------------------------------------------------------

_HEADER_RE = re.compile(r"^--- (.+?) \([^)]*\), p\.\S+ ---$", re.MULTILINE)


def build_title_index(corpus_dir: Path) -> dict[str, str]:
    """title -> paper_id, from the same corpus.csv search() itself reads.

    search() only ever prints a paper's OWN title (from this same csv row)
    in its output header, so reversing that mapping is self-consistent even
    where a csv title is itself wrong (see the manifest's noted metadata bug
    for adma201904845_sup_0001_suppmat__1) -- the round trip still lands on
    the right paper_id because both sides read the same field.
    """
    idx: dict[str, str] = {}
    dupes: list[str] = []
    with (corpus_dir / "corpus.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            title = row.get("title", "").strip()
            if not title:
                continue
            if title in idx and idx[title] != row["paper_id"]:
                dupes.append(title)
            idx[title] = row["paper_id"]
    if dupes:
        print(f"  WARNING: {len(dupes)} duplicate title(s) in corpus.csv -- "
              "title->paper_id mapping used the LAST row for each; "
              "affected searches may misattribute chunks.")
    return idx


def parse_search_output(text: str, title_to_pid: dict[str, str]) -> list[str]:
    """Ranked, deduped (first occurrence wins) list of paper_ids."""
    if text in ("No results found.",) or text.startswith("ERROR"):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for title in _HEADER_RE.findall(text):
        pid = title_to_pid.get(title)
        if pid is None or pid in seen:
            continue
        seen.add(pid)
        out.append(pid)
    return out


def load_chunk_counts(corpus_dir: Path) -> dict[str, int]:
    """paper_id -> total number of chunks in ``chunks.jsonl``.

    This is the WHOLE-CORPUS chunk count for a paper (how many chunks it
    was split into when added), not how many of its chunks a given query
    happens to retrieve. It exists to test the length confound on the
    ``sum`` aggregation: a paper split into many chunks has more chances
    for a chunk to weakly match and enter the top ``raw_k`` window, which
    can inflate a naive sum independently of relevance. ``sum_norm``
    divides a paper's summed chunk score by this count.
    """
    counts: dict[str, int] = {}
    path = corpus_dir / "chunks.jsonl"
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            pid = row.get("paper_id")
            if pid:
                counts[pid] = counts.get(pid, 0) + 1
    return counts


def aggregate_chunk_scores(
    scored: list[tuple[str, str]], agg: str,
    chunk_counts: dict[str, int] | None = None,
) -> list[str]:
    """Collapse ``(paper_id, score)`` chunk-level pairs -- already in rank
    order, exactly as ``LiteratureCorpus.search_chunk_scores`` returns them
    -- to a ranked list of DISTINCT paper_ids, under aggregation *agg*:

    ``first``     first-seen chunk wins (the pre-existing behaviour of
                  ``parse_search_output``, reimplemented here on top of
                  real per-chunk scores instead of re-parsing formatted
                  text -- a paper's score doesn't matter, only whether one
                  of its chunks was the first of that paper_id seen).
    ``sum``       sum a paper's retrieved chunk scores; ranked by the sum,
                  descending. Rewards a paper with many weakly-matching
                  chunks as much as one with fewer strong ones -- and is
                  confounded by how many chunks a paper WAS SPLIT INTO in
                  the first place (see ``sum_norm`` / ``load_chunk_counts``).
    ``max``       a paper's single highest-scoring chunk; ranked
                  descending. Rewards one strong hit; ignores corroborating
                  evidence spread across the rest of the paper.
    ``mean``      a paper's mean retrieved-chunk score; ranked descending.
                  Normalizes by how many of THIS query's raw_k retrieved
                  chunks belonged to the paper (not by the paper's total
                  corpus-wide chunk count -- see ``sum_norm`` for that).
    ``sum_norm``  ``sum`` divided by the paper's TOTAL chunk count in the
                  whole corpus (*chunk_counts*, required for this mode) --
                  the length-normalised control for the ``sum`` confound.

    Ties are broken by first-seen rank (stable and deterministic) so two
    runs of the same arm never reorder a tie differently.
    """
    if agg == "first":
        seen_set: set[str] = set()
        out: list[str] = []
        for pid, _score in scored:
            if pid not in seen_set:
                seen_set.add(pid)
                out.append(pid)
        return out

    per_paper: dict[str, list[float]] = {}
    first_rank: dict[str, int] = {}
    for rank, (pid, score) in enumerate(scored):
        per_paper.setdefault(pid, []).append(score)
        first_rank.setdefault(pid, rank)

    if agg == "sum":
        agg_score = {pid: sum(vals) for pid, vals in per_paper.items()}
    elif agg == "max":
        agg_score = {pid: max(vals) for pid, vals in per_paper.items()}
    elif agg == "mean":
        agg_score = {pid: statistics.fmean(vals) for pid, vals in per_paper.items()}
    elif agg == "sum_norm":
        if chunk_counts is None:
            raise ValueError("agg='sum_norm' requires chunk_counts")
        agg_score = {
            pid: sum(vals) / max(chunk_counts.get(pid, len(vals)), 1)
            for pid, vals in per_paper.items()
        }
    else:
        raise ValueError(f"unknown aggregation {agg!r}; valid: {AGGREGATIONS}")

    return sorted(per_paper, key=lambda pid: (-agg_score[pid], first_rank[pid]))


def assert_resolved(corpus, expected: str, qid: str) -> None:
    """The whole point of ``resolved_mode``: catch a mislabelled arm loudly.

    Never caught silently -- a run that scored 'hybrid' while
    ``resolved_mode`` says 'bm25' is not a graceful degradation, it is a
    labelling bug in the harness or the tool, and belongs in the report.
    """
    got = corpus.resolved_mode
    if got != expected:
        raise AssertionError(
            f"MISLABELLED ARM on query {qid!r}: requested retrieval_mode="
            f"{expected!r} but corpus.resolved_mode={got!r}. Refusing to "
            "score this as the requested arm."
        )


def probe_dense_embedder(corpus) -> tuple[bool, str]:
    """Try the embedder once, before spending a whole arm's queries on it.

    Two independent things can make the hybrid arm unavailable, and both are
    checked here so the caller gets one plain reason instead of a crash mid-
    arm:

    1. The MODEL itself: no ``uv`` on PATH, or the out-of-process probe
       fails. Reaches into the corpus's private ``_get_embedding_model`` the
       same way source_index_baseline.py reaches into ``PackageApi._rank``
       -- there is no public probe method, and the module's own docstring
       names this exact resolution order.
    2. The CORPUS's embeddings: ``_load_all_embeddings()`` returns
       ``(chunks, None, None)`` only when NOT ONE chunk anywhere in the
       corpus has a usable embedding.

       Prior to the ``literature_corpus.py`` fix for partial embedding
       coverage, a matrix build aborted CORPUS-WIDE the instant any single
       paper's chunks.jsonl entries had no matching chunks.npy -- found on
       the frozen fixture itself: the orphan
       ``hussein2015_thesis_curved_beams_multistable_microrobots`` (has
       chunks in chunks.jsonl, no chunks.npy, no corpus.csv row) poisoned
       dense ranking for all 131 registered papers, silently downgrading
       ``retrieval_mode="hybrid"``/``"auto"`` to BM25-only. That is now
       fixed in ``literature_corpus.py``: a paper missing embeddings (or
       with fewer embedding rows than chunks) only drops out of DENSE
       ranking for ITS OWN chunks -- every other paper's embeddings still
       run. This probe reports that partial coverage via
       ``LiteratureCorpus.dense_coverage`` (set per-query by ``search()``)
       instead of treating it as corpus-wide unavailability.

    Returns (available, route_or_reason).
    """
    if shutil.which("uv") is None:
        note = "no 'uv' on PATH (needed for the out-of-process embedder route)"
    else:
        note = "'uv' present"
    model = corpus._get_embedding_model()
    if model is None:
        return False, f"embedder unavailable ({note}); in-process fastembed " \
            "import failed and the uv subprocess probe also failed"
    _chunks, emb_matrix, has_emb = corpus._load_all_embeddings()
    if emb_matrix is None:
        return False, (
            "embedder model IS available, but corpus._load_all_embeddings() "
            "found no usable embedding anywhere in the corpus (no paper "
            "has a matching chunks.npy)."
        )
    route = "subprocess uv" if type(model).__name__ == "_SubprocessEmbedder" \
        else "in-process fastembed"
    if not bool(has_emb.all()):
        missing = int(len(has_emb) - has_emb.sum())
        route += (
            f"; PARTIAL coverage: {missing}/{len(has_emb)} chunks "
            f"({100.0 * missing / len(has_emb):.1f}%) have no usable "
            "embedding and are excluded from dense ranking only -- see "
            "LiteratureCorpus.dense_coverage per-query"
        )
    return True, route


@dataclass
class PerQuery:
    qid: str
    ranked: list[str]
    wall_s: float
    #: Side-channel for a second ranking of the SAME query (only the rg arm
    #: uses this, to carry its per-kb variant alongside the raw-count one).
    per_kb_ranked: list[str] | None = None


@dataclass
class ArmResult:
    name: str
    per_query: list[PerQuery] = field(default_factory=list)
    unavailable_reason: str | None = None


def run_internal_arm(corpus, mode: str, queries: list[Query],
                      title_to_pid: dict[str, str], raw_k: int) -> ArmResult:
    from adda._src.runtime import settings as _settings

    result = ArmResult(name=mode)
    _settings.configure({"retrieval_mode": mode})
    for q in queries:
        t0 = time.perf_counter()
        text = corpus.search(q.text, top_k=raw_k)
        wall = time.perf_counter() - t0
        if isinstance(text, str) and text.startswith("ERROR"):
            raise RuntimeError(
                f"retrieval_mode={mode!r} errored on query {q.qid!r}: {text}"
            )
        assert_resolved(corpus, mode, q.qid)
        ranked = parse_search_output(text, title_to_pid)
        result.per_query.append(PerQuery(q.qid, ranked, wall))
    return result


def run_internal_arm_scored(
    corpus, mode: str, queries: list[Query], raw_k: int, agg: str,
    chunk_counts: dict[str, int] | None = None,
) -> ArmResult:
    """Like ``run_internal_arm``, but collapses to paper_ids via
    ``LiteratureCorpus.search_chunk_scores`` + ``aggregate_chunk_scores``
    instead of re-parsing ``search()``'s formatted text -- the only way to
    run any *agg* other than "first" (sum/max/mean/sum_norm need real
    per-chunk scores, which do not survive the round trip through text).

    Not valid for ``mode="substring"`` -- that arm has no per-chunk score
    (see ``search_chunk_scores``'s docstring); use ``run_internal_arm`` for
    it, unconditionally, regardless of *agg*.
    """
    from adda._src.runtime import settings as _settings

    result = ArmResult(name=f"{mode}:{agg}")
    _settings.configure({"retrieval_mode": mode})
    for q in queries:
        t0 = time.perf_counter()
        scored = corpus.search_chunk_scores(q.text, top_k=raw_k)
        wall = time.perf_counter() - t0
        if isinstance(scored, str):
            raise RuntimeError(
                f"retrieval_mode={mode!r} search_chunk_scores errored on "
                f"query {q.qid!r}: {scored}"
            )
        assert_resolved(corpus, mode, q.qid)
        ranked = aggregate_chunk_scores(scored, agg, chunk_counts=chunk_counts)
        result.per_query.append(PerQuery(q.qid, ranked, wall))
    return result


def run_rg_arm(queries: list[Query], papers_dir: Path, raw_k: int) -> ArmResult:
    result = ArmResult(name="rg")
    for q in queries:
        t0 = time.perf_counter()
        a = _rg_rank(q.text, papers_dir, raw_k, per_kb=False)
        b = _rg_rank(q.text, papers_dir, raw_k, per_kb=True)
        wall = time.perf_counter() - t0
        # Whichever variant scores higher IS the bar (source_index_baseline's
        # rule) -- both are kept per query so the reporting step can score
        # each independently and pick the winner by MRR.
        result.per_query.append(PerQuery(q.qid, a, wall, per_kb_ranked=b))
    return result


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def recall_at_k(ranked: list[str], gold: frozenset[str], k: int) -> float | None:
    if not gold:
        return None
    found = len(set(ranked[:k]) & gold)
    return found / len(gold)


def hit_at_k(ranked: list[str], gold: frozenset[str], k: int) -> int:
    return 1 if set(ranked[:k]) & gold else 0


def reciprocal_rank(ranked: list[str], gold: frozenset[str]) -> float:
    for i, p in enumerate(ranked, 1):
        if p in gold:
            return 1.0 / i
    return 0.0


def summarize(arm: ArmResult, queries: list[Query], k_values=(5, 10, 20)):
    by_qid = {q.qid: q for q in queries}
    n = len(arm.per_query)
    out = {"n": n, "wall_mean_s": statistics.fmean(
        pq.wall_s for pq in arm.per_query) if n else 0.0}
    for k in k_values:
        vals = [recall_at_k(pq.ranked, by_qid[pq.qid].gold, k)
                for pq in arm.per_query]
        vals = [v for v in vals if v is not None]
        out[f"recall@{k}"] = statistics.fmean(vals) if vals else 0.0
        out[f"lost_evidence@{k}"] = 1 - out[f"recall@{k}"]
        out[f"hit@{k}"] = statistics.fmean(
            hit_at_k(pq.ranked, by_qid[pq.qid].gold, k)
            for pq in arm.per_query) if n else 0.0
    out["r@1"] = statistics.fmean(
        hit_at_k(pq.ranked, by_qid[pq.qid].gold, 1)
        for pq in arm.per_query) if n else 0.0
    out["mrr"] = statistics.fmean(
        reciprocal_rank(pq.ranked, by_qid[pq.qid].gold)
        for pq in arm.per_query) if n else 0.0
    hits10 = out["hit@10"] * n
    out["cost_per_hit_s"] = (out["wall_mean_s"] * n / hits10) if hits10 else float("inf")
    return out


# ---------------------------------------------------------------------------
# Statistics: exact McNemar, bootstrap 95% CI, power note. Functions, so
# every future run reports these automatically rather than by hand.
# ---------------------------------------------------------------------------

def _binom_cdf(k: int, n: int, p: float = 0.5) -> float:
    return sum(math.comb(n, i) * p**i * (1 - p)**(n - i) for i in range(k + 1))


def exact_mcnemar(hits_a: list[int], hits_b: list[int]) -> dict:
    """Exact (binomial-based) McNemar test on paired binary hit/miss arrays.

    b = A hit & B miss, c = A miss & B hit (the discordant pairs -- concordant
    pairs carry no information about a DIFFERENCE and are excluded, which is
    the entire premise of McNemar's test). Two-sided exact p via the
    binomial CDF, matching the "exact McNemar" figures reported in commit
    1e9d0e8 (p = 0.0385 at n=128, 40 discordant).
    """
    assert len(hits_a) == len(hits_b)
    b = sum(1 for a, bb in zip(hits_a, hits_b, strict=True) if a == 1 and bb == 0)
    c = sum(1 for a, bb in zip(hits_a, hits_b, strict=True) if a == 0 and bb == 1)
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "n_discordant": 0, "p": 1.0}
    k = min(b, c)
    p = min(1.0, 2 * _binom_cdf(k, n, 0.5))
    return {"b": b, "c": c, "n_discordant": n, "p": p}


def bootstrap_ci(hits_a: list[int], hits_b: list[int], *, n_resamples: int = 5000,
                  seed: int = 1234) -> tuple[float, float, float]:
    """Bootstrap 95% CI on mean(hits_a) - mean(hits_b), paired by query.

    Resamples QUERY INDICES with replacement (not the individual arm
    outcomes independently) -- the pairing per query is what makes this a
    paired comparison rather than two unrelated samples.
    """
    assert len(hits_a) == len(hits_b)
    n = len(hits_a)
    rng = random.Random(seed)
    point = statistics.fmean(hits_a) - statistics.fmean(hits_b)
    if n == 0:
        return point, point, point
    diffs = []
    idx_range = range(n)
    for _ in range(n_resamples):
        idx = [rng.choice(idx_range) for _ in range(n)]
        ra = sum(hits_a[i] for i in idx) / n
        rb = sum(hits_b[i] for i in idx) / n
        diffs.append(ra - rb)
    diffs.sort()
    lo = diffs[int(0.025 * n_resamples)]
    hi = diffs[min(int(0.975 * n_resamples), n_resamples - 1)]
    return point, lo, hi


def power_note(mcnemar: dict, n_total: int, *, power: float = 0.8,
               alpha: float = 0.05) -> str:
    """Approximate n needed for *power* to detect the OBSERVED discordance.

    Closed-form McNemar sample-size approximation (not a simulation):
    n_needed = (z_a + z_b)^2 * (p_b + p_c) / (p_b - p_c)^2
    with p_b, p_c the observed discordant proportions. This is the same
    question source_index_baseline's own docstring names ("the sample size
    the power simulation called for", commit 1e9d0e8) -- here computed
    analytically so it ships with every run instead of a one-off script.
    """
    b, c = mcnemar["b"], mcnemar["c"]
    if n_total == 0 or b == c:
        return ("no discordant asymmetry observed (b == c) -- this harness "
                "cannot project a required n for an effect of zero")
    p_b, p_c = b / n_total, c / n_total
    delta = abs(p_b - p_c)
    z_alpha = 1.959963985  # two-sided, alpha=0.05
    z_beta = 0.841621234   # power=0.80
    n_needed = ((z_alpha + z_beta) ** 2) * (p_b + p_c) / (delta ** 2)
    return (f"observed b={b}, c={c} at n={n_total} (delta={delta:.3f}) would "
            f"need n~={math.ceil(n_needed)} for {power:.0%} power at "
            f"alpha={alpha} (closed-form approximation, not a simulation)")


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Plain-stdlib Pearson correlation (no scipy/numpy -- not a declared
    dependency of this harness, same discipline as exact_mcnemar/bootstrap_ci).
    None when undefined (n<2 or a zero-variance series).
    """
    n = len(xs)
    if n < 2 or len(ys) != n:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    denx = sum((x - mx) ** 2 for x in xs) ** 0.5
    deny = sum((y - my) ** 2 for y in ys) ** 0.5
    if denx == 0 or deny == 0:
        return None
    return num / (denx * deny)


def report_pairwise_stats(hits_by_arm: dict[str, list[int]], k: int) -> None:
    names = list(hits_by_arm)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a_name, b_name = names[i], names[j]
            ha, hb = hits_by_arm[a_name], hits_by_arm[b_name]
            n = len(ha)
            mc = exact_mcnemar(ha, hb)
            point, lo, hi = bootstrap_ci(ha, hb)
            marker = " <-- hybrid vs bm25 (the decisive comparison)" if \
                {a_name, b_name} == {"hybrid", "bm25"} else ""
            print(f"  hit@{k}: {a_name} vs {b_name}  n={n}  "
                  f"McNemar b={mc['b']} c={mc['c']} p={mc['p']:.4f}  "
                  f"diff={point:+.3f} 95%CI[{lo:+.3f},{hi:+.3f}]{marker}")
            print(f"    power note: {power_note(mc, n)}")


# ---------------------------------------------------------------------------
# --compare-agg: study mode for the paper-level aggregation strategies
# ---------------------------------------------------------------------------

def run_aggregation_comparison(
    corpus, queries: list[Query], raw_k: int, corpus_dir: Path,
) -> None:
    """Run bm25 and hybrid under EVERY aggregation in ``AGGREGATIONS``,
    report per-variant recall@k/MRR, full pairwise significance between the
    variants (exact McNemar + bootstrap 95% CI + power note -- the same
    functions every arm-vs-arm comparison uses, per this harness's own
    STATISTICS contract), and the sum-vs-paper-length confound check.
    """
    chunk_counts = load_chunk_counts(corpus_dir)
    by_qid_gold = {q.qid: q.gold for q in queries}

    modes_to_compare = ["bm25"]
    print("\n--- probing dense embedder for hybrid ---")
    available, route = probe_dense_embedder(corpus)
    if available:
        print(f"  embedder route: {route}")
        modes_to_compare.append("hybrid")
    else:
        print(f"  DENSE ARM UNAVAILABLE: {route} -- comparing bm25 only.")

    variant_results: dict[str, ArmResult] = {}
    variant_summaries: dict[str, dict] = {}
    for mode in modes_to_compare:
        for agg in AGGREGATIONS:
            print(f"--- running {mode}:{agg} ---")
            cc = chunk_counts if agg == "sum_norm" else None
            result = run_internal_arm_scored(
                corpus, mode, queries, raw_k, agg, chunk_counts=cc
            )
            name = f"{mode}:{agg}"
            variant_results[name] = result
            variant_summaries[name] = summarize(result, queries)

    print("\n=== aggregation comparison: per-variant metrics"
          f" (development split, n={len(queries)}) ===")
    print(f"{'variant':16s} {'n':>4s} {'r@1':>6s} {'r@5':>7s} {'r@10':>7s} "
          f"{'r@20':>7s} {'MRR':>6s} {'wall_s':>8s}")
    for mode in modes_to_compare:
        for agg in AGGREGATIONS:
            s = variant_summaries[f"{mode}:{agg}"]
            print(f"{mode + ':' + agg:16s} {s['n']:>4d} {s['r@1']:>6.2f} "
                  f"{s['recall@5']:>7.2f} {s['recall@10']:>7.2f} "
                  f"{s['recall@20']:>7.2f} {s['mrr']:>6.2f} "
                  f"{s['wall_mean_s']:>8.4f}")

    print("\n=== aggregation comparison: pairwise significance per arm"
          " (exact McNemar + bootstrap 95% CI) ===")
    for mode in modes_to_compare:
        for k in (5, 10, 20):
            print(f"\n-- {mode}, k={k} --")
            hits_by_variant = {
                agg: [
                    hit_at_k(pq.ranked, by_qid_gold[pq.qid], k)
                    for pq in variant_results[f"{mode}:{agg}"].per_query
                ]
                for agg in AGGREGATIONS
            }
            report_pairwise_stats(hits_by_variant, k)

    # ---- sum-vs-length confound ----
    print("\n=== sum-vs-length confound ===")
    print(f"  corpus: {len(chunk_counts)} papers with chunks; per-paper "
          f"chunk-count range [{min(chunk_counts.values())}, "
          f"{max(chunk_counts.values())}], mean="
          f"{statistics.fmean(chunk_counts.values()):.1f}, "
          f"stdev={statistics.pstdev(chunk_counts.values()):.1f}")

    from adda._src.runtime import settings as _settings
    for mode in modes_to_compare:
        s_sum = variant_summaries[f"{mode}:sum"]
        s_norm = variant_summaries[f"{mode}:sum_norm"]
        for k in (5, 10, 20):
            print(f"  {mode}: sum r@{k}={s_sum[f'recall@{k}']:.3f}  vs "
                  f"sum_norm (/corpus chunk count) r@{k}="
                  f"{s_norm[f'recall@{k}']:.3f}")

        # Top-1 disagreements between sum (has a length term) and max (no
        # length term at all): when they disagree, whose pick has MORE
        # total corpus chunks? A pattern skewed toward sum's pick being
        # the longer paper is direct evidence sum is partly rewarding
        # length rather than relevance.
        by_qid_sum = {
            pq.qid: pq.ranked for pq in variant_results[f"{mode}:sum"].per_query
        }
        by_qid_max = {
            pq.qid: pq.ranked for pq in variant_results[f"{mode}:max"].per_query
        }
        agree = sum_longer = max_longer = tie = compared = 0
        for q in queries:
            top_sum = by_qid_sum.get(q.qid) or [None]
            top_max = by_qid_max.get(q.qid) or [None]
            top_sum, top_max = top_sum[0], top_max[0]
            if top_sum is None or top_max is None:
                continue
            compared += 1
            if top_sum == top_max:
                agree += 1
                continue
            len_sum, len_max = chunk_counts.get(top_sum, 0), chunk_counts.get(top_max, 0)
            if len_sum > len_max:
                sum_longer += 1
            elif len_max > len_sum:
                max_longer += 1
            else:
                tie += 1
        disagree = compared - agree
        print(f"  {mode}: top-1 pick sum vs max -- agree {agree}/{compared}; "
              f"of {disagree} disagreements, sum's pick has MORE total "
              f"corpus chunks than max's in {sum_longer}, FEWER in "
              f"{max_longer}, tied in {tie}")

        # Pearson r(paper's total corpus chunk_count, that paper's summed
        # chunk score) pooled over every (query, paper) pair the sum
        # aggregation actually scored -- the direct test of whether `sum`
        # tracks paper length.
        _settings.configure({"retrieval_mode": mode})
        xs: list[float] = []
        ys: list[float] = []
        for q in queries:
            scored = corpus.search_chunk_scores(q.text, top_k=raw_k)
            if isinstance(scored, str):
                continue
            per_paper: dict[str, float] = {}
            for pid, sc in scored:
                per_paper[pid] = per_paper.get(pid, 0.0) + sc
            for pid, sc in per_paper.items():
                xs.append(float(chunk_counts.get(pid, 0)))
                ys.append(sc)
        r = _pearson(xs, ys)
        r_str = f"{r:+.3f}" if r is not None else "undefined (n<2 or zero variance)"
        print(f"  {mode}: Pearson r(paper chunk_count, summed chunk score) "
              f"over {len(xs)} (query,paper) pairs = {r_str}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", required=True, type=Path,
                     help="LiteratureCorpus-shaped dir (corpus.csv, "
                          "chunks.jsonl, papers/<id>/{paper.md,chunks.npy})")
    ap.add_argument("--queries", required=True,
                     help="path to a .py file exposing QUERIES: "
                          "list[tuple[qid, query_text, gold_paper_ids]]. "
                          "No default is shipped.")
    ap.add_argument("--raw-k", type=int, default=DEFAULT_RAW_K,
                     help=f"raw chunks ranked before collapsing to distinct "
                          f"paper_ids (default {DEFAULT_RAW_K})")
    ap.add_argument("--no-hybrid", action="store_true",
                     help="skip the dense arm even if the embedder is available")
    ap.add_argument("--held-out", action="store_true",
                     help="score the frozen HELD_OUT_IDS split instead of "
                          "DEVELOPMENT. Do not pass it until the design is "
                          "frozen; that is what makes the split worth having.")
    ap.add_argument("--agg", choices=AGGREGATIONS, default="first",
                     help="paper-level collapsing strategy for the bm25/"
                          "hybrid arms (default 'first', the pre-existing "
                          "behaviour). substring has no per-chunk score and "
                          "always collapses by first-seen regardless of "
                          "this flag. See aggregate_chunk_scores().")
    ap.add_argument("--compare-agg", action="store_true",
                     help="instead of the normal 4-arm report, run bm25 and "
                          "hybrid under EVERY aggregation in AGGREGATIONS "
                          "and report full pairwise stats between them, "
                          "plus a sum-vs-paper-length confound check. "
                          "Ignores --agg. Exits without the standard report.")
    args = ap.parse_args()

    corpus_src = args.corpus.resolve()
    if not corpus_src.exists():
        raise SystemExit(f"ERROR: --corpus {corpus_src} does not exist.")

    split = "HELD OUT" if args.held_out else "DEVELOPMENT"
    queries = load_queries(args.queries, held_out=args.held_out)
    print(f"=== {len(queries)} queries ({split} split) from {args.queries} ===")
    validate_gold_reachability(queries, corpus_src)

    with tempfile.TemporaryDirectory(prefix="adda_lit_baseline_") as tmp:
        workdir = Path(tmp)
        corpus_dir = materialize_corpus(corpus_src, workdir)

        from adda._src.literature.literature_corpus import LiteratureCorpus
        corpus = LiteratureCorpus(corpus_dir)
        title_to_pid = build_title_index(corpus_dir)

        if args.compare_agg:
            run_aggregation_comparison(corpus, queries, args.raw_k, corpus_dir)
            return 0

        results: dict[str, ArmResult] = {}

        # --- Arm 1: rg (two variants; the metrics step below reports both) ---
        print("\n--- running rg (external floor: raw counts + per-kb) ---")
        results["rg"] = run_rg_arm(queries, corpus_src / "papers", args.raw_k)

        # --- Arm 2: substring (internal floor) -- no per-chunk score exists
        # for this mode (see search_chunk_scores docstring), so --agg never
        # applies to it: it always collapses by first-seen.
        print("--- running substring ---")
        results["substring"] = run_internal_arm(
            corpus, "substring", queries, title_to_pid, args.raw_k)

        # --- Arm 3: bm25 (the control) ---
        print(f"--- running bm25 (agg={args.agg}) ---")
        if args.agg == "first":
            results["bm25"] = run_internal_arm(
                corpus, "bm25", queries, title_to_pid, args.raw_k)
        else:
            cc = load_chunk_counts(corpus_dir) if args.agg == "sum_norm" else None
            results["bm25"] = run_internal_arm_scored(
                corpus, "bm25", queries, args.raw_k, args.agg, chunk_counts=cc)

        # --- Arm 4: hybrid (the arm under test) ---
        if args.no_hybrid:
            print("--- hybrid SKIPPED (--no-hybrid) ---")
        else:
            print("--- probing dense embedder for hybrid ---")
            available, route = probe_dense_embedder(corpus)
            if not available:
                print(f"  DENSE ARM UNAVAILABLE: {route}")
                print("  Scoring THREE arms, not four. Not a silent fallback "
                      "-- reported plainly, per the design contract.")
            else:
                print(f"  embedder route: {route}")
                print(f"--- running hybrid (agg={args.agg}) ---")
                if args.agg == "first":
                    results["hybrid"] = run_internal_arm(
                        corpus, "hybrid", queries, title_to_pid, args.raw_k)
                else:
                    cc = load_chunk_counts(corpus_dir) if args.agg == "sum_norm" else None
                    results["hybrid"] = run_internal_arm_scored(
                        corpus, "hybrid", queries, args.raw_k, args.agg,
                        chunk_counts=cc)

    # ---------------- reporting ----------------
    print("\n=== per-arm metrics ===")
    print(f"{'arm':12s} {'n':>4s} {'r@1':>6s} {'r@5':>7s} {'r@10':>7s} "
          f"{'r@20':>7s} {'MRR':>6s} {'wall_s':>8s} {'cost/hit':>9s}")
    summaries: dict[str, dict] = {}
    for name in ARMS:
        if name not in results:
            continue
        arm = results[name]
        if name == "rg":
            # Score both variants; report whichever is higher per source_index_baseline's rule.
            raw_arm = ArmResult("rg_raw", [PerQuery(pq.qid, pq.ranked, pq.wall_s)
                                            for pq in arm.per_query])
            perkb_arm = ArmResult("rg_per_kb", [
                PerQuery(pq.qid, pq.per_kb_ranked or [], pq.wall_s)
                for pq in arm.per_query])
            s_raw = summarize(raw_arm, queries)
            s_kb = summarize(perkb_arm, queries)
            best = s_raw if s_raw["mrr"] >= s_kb["mrr"] else s_kb
            best_variant = "raw" if best is s_raw else "per_kb"
            print(f"{'rg (raw)':12s} {s_raw['n']:>4d} {s_raw['r@1']:>6.2f} "
                  f"{s_raw['recall@5']:>7.2f} {s_raw['recall@10']:>7.2f} "
                  f"{s_raw['recall@20']:>7.2f} {s_raw['mrr']:>6.2f} "
                  f"{s_raw['wall_mean_s']:>8.4f} {s_raw['cost_per_hit_s']:>9.4f}")
            print(f"{'rg (per_kb)':12s} {s_kb['n']:>4d} {s_kb['r@1']:>6.2f} "
                  f"{s_kb['recall@5']:>7.2f} {s_kb['recall@10']:>7.2f} "
                  f"{s_kb['recall@20']:>7.2f} {s_kb['mrr']:>6.2f} "
                  f"{s_kb['wall_mean_s']:>8.4f} {s_kb['cost_per_hit_s']:>9.4f}")
            print(f"  -> the bar to beat is rg ({best_variant}), MRR={best['mrr']:.2f}")
            summaries["rg"] = best
            results["rg"] = raw_arm if best_variant == "raw" else perkb_arm
        else:
            s = summarize(arm, queries)
            summaries[name] = s
            print(f"{name:12s} {s['n']:>4d} {s['r@1']:>6.2f} "
                  f"{s['recall@5']:>7.2f} {s['recall@10']:>7.2f} "
                  f"{s['recall@20']:>7.2f} {s['mrr']:>6.2f} "
                  f"{s['wall_mean_s']:>8.4f} {s['cost_per_hit_s']:>9.4f}")

    print("\n=== Lost Evidence (1 - recall@k) ===")
    for name, s in summaries.items():
        print(f"  {name:12s} LE@5={s['lost_evidence@5']:.2f}  "
              f"LE@10={s['lost_evidence@10']:.2f}  LE@20={s['lost_evidence@20']:.2f}")

    if "hybrid" in summaries and "bm25" in summaries:
        delta_wall = summaries["hybrid"]["wall_mean_s"] - summaries["bm25"]["wall_mean_s"]
        print("\n=== dense/embedder overhead (hybrid wall - bm25 wall, per query) ===")
        print(f"  {delta_wall:+.4f}s/query "
              "(includes any out-of-process embedder subprocess spawn)")

    print("\n=== pairwise significance (exact McNemar + bootstrap 95% CI) ===")
    by_qid_gold = {q.qid: q.gold for q in queries}
    for k in (5, 10, 20):
        print(f"\n-- k={k} --")
        hits_by_arm = {
            name: [hit_at_k(pq.ranked, by_qid_gold[pq.qid], k)
                   for pq in results[name].per_query]
            for name in results
        }
        report_pairwise_stats(hits_by_arm, k)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
