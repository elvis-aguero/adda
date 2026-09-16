"""The ranking strategy is DECLARED, not inferred from which packages import.

`search()` decided between RRF-over-BM25+dense, BM25-only and substring by
whether `rank_bm25` and `fastembed` happened to import and whether a
subprocess embedder probe succeeded — cached in a module global, falling back
silently. Nobody could state what a given run actually did, so an arm labelled
"hybrid" could have been BM25-only and the comparison would read as a null
result for dense retrieval.

`auto` keeps the historical degrade-on-missing-dependency behaviour and is the
default. An explicitly requested mode that cannot be satisfied is an error.
"""
from __future__ import annotations

import pytest

from adda._src.literature.literature_corpus import (
    _RETRIEVAL_MODES,
    LiteratureCorpus,
)
from adda._src.runtime import settings


@pytest.fixture(autouse=True)
def _clean():
    settings.configure(None)
    yield
    settings.configure(None)


def _corpus(tmp_path):
    """A corpus with one full-text paper. `.md` input makes it full_text."""
    src = tmp_path / "paper.md"
    # Must exceed _FULL_TEXT_MD_THRESHOLD (5000 chars) or the corpus records
    # it as abstract-only and search() refuses before reaching any ranking.
    body = ("The critical buckling stress depends on the moment of inertia "
            "and the effective length of the slender elastic rod. ") * 80
    src.write_text(f"# Buckling\n\n{body}\n", encoding="utf-8")
    c = LiteratureCorpus(tmp_path / "corp")
    c.add(str(src), title="Buckling of slender rods", authors="A",
          year="2020", venue="J", citation_count=10,
          abstract="critical buckling stress of slender elastic rods")
    return c


def test_the_modes_are_a_closed_set():
    assert _RETRIEVAL_MODES == {"auto", "hybrid", "bm25", "substring"}


def test_an_unknown_mode_is_refused(tmp_path):
    settings.configure({"retrieval_mode": "vibes"})
    out = _corpus(tmp_path).search("buckling")
    assert out.startswith("ERROR:")
    assert "vibes" in out


def test_substring_mode_is_honoured_and_recorded(tmp_path):
    settings.configure({"retrieval_mode": "substring"})
    c = _corpus(tmp_path)

    c.search("buckling")

    assert c.resolved_mode == "substring"


def test_auto_records_whatever_it_settled_on(tmp_path):
    """The point of recording: an arm can be verified rather than assumed."""
    settings.configure({"retrieval_mode": "auto"})
    c = _corpus(tmp_path)

    c.search("buckling")

    assert c.resolved_mode in _RETRIEVAL_MODES
    assert c.resolved_mode != "auto", "auto must resolve to a concrete mode"


def test_hybrid_errors_rather_than_quietly_becoming_bm25(tmp_path, monkeypatch):
    """The whole point of item 7. Silently dropping to lexical ranking is how
    a 'hybrid' arm becomes a mislabelled condition."""
    c = _corpus(tmp_path)
    monkeypatch.setattr(c, "_get_embedding_model", lambda: None)
    settings.configure({"retrieval_mode": "hybrid"})

    out = c.search("buckling")

    assert out.startswith("ERROR:")
    assert "hybrid" in out
    assert c.resolved_mode != "hybrid"


def test_auto_still_degrades_where_hybrid_refuses(tmp_path, monkeypatch):
    """Backwards compatible: an install without an embedder keeps working."""
    c = _corpus(tmp_path)
    monkeypatch.setattr(c, "_get_embedding_model", lambda: None)
    settings.configure({"retrieval_mode": "auto"})

    out = c.search("buckling")

    assert not out.startswith("ERROR:")
    assert c.resolved_mode == "bm25"


def test_citation_weighting_is_switchable(tmp_path):
    """A popularity prior multiplied into the lexical scores before fusion.
    It may help; nobody has measured it, so it has to be switchable."""
    settings.configure({"citation_weighting": False})
    c = _corpus(tmp_path)

    out = c.search("buckling")

    assert not out.startswith("ERROR:")
