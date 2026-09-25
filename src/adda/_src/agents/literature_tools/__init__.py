"""Runtime tool closures for the literature reviewer.

The reviewer holds five tools: the corpus (ConsultLiterature, CorpusAdd) and
discovery over the literature databases (SearchPapers, CitationGraph,
PaperDetails, see ``discovery.py``). The per-provider
calls those are built from -- one module per provider -- are returned by
``build_literature_providers`` and are not tools themselves.
"""

from __future__ import annotations

from pathlib import Path

from .corpus import build_corpus_closures
from .discovery import arxiv_search, build_discovery_closures
from .openalex import build_openalex_closures
from .semantic_scholar import (
    build_recommendations_closure,
    build_semantic_scholar_closures,
)


def _corpus(study_dir, lit_reviewer_notes_dir):
    from ...literature.literature_corpus import LiteratureCorpus

    corpus_dir = (
        Path(lit_reviewer_notes_dir)
        if lit_reviewer_notes_dir is not None
        else Path(study_dir) / "runs" / "lit_reviewer_notes"
    )
    return LiteratureCorpus(corpus_dir)


def _providers(cache_dir) -> dict:
    providers: dict = {}
    providers.update(build_semantic_scholar_closures())
    providers.update(build_openalex_closures(cache_dir))
    providers.update(build_recommendations_closure())
    try:
        import arxiv  # noqa: F401
        providers["arxiv_search"] = arxiv_search
    except ImportError:
        pass
    return providers


def build_literature_providers(study_dir, lit_reviewer_notes_dir=None) -> dict:
    """Every per-provider call, by name. {} if the literature stack is not
    installed. A provider whose library is missing is absent."""
    try:
        corpus = _corpus(study_dir, lit_reviewer_notes_dir)
    except ImportError:
        return {}
    return _providers(corpus._http_cache_dir)


def build_literature_tools(study_dir, lit_reviewer_notes_dir=None) -> dict:
    """Corpus + discovery tools as runtime closures; {} if the optional
    literature stack is not installed."""
    try:
        corpus = _corpus(study_dir, lit_reviewer_notes_dir)
    except ImportError:
        return {}

    corpus_tools = build_corpus_closures(corpus, corpus._http_cache_dir)
    tools = {k: corpus_tools[k] for k in ("CorpusAdd", "ConsultLiterature")}
    tools.update(build_discovery_closures(_providers(corpus._http_cache_dir)))
    # No tool reads a paper outside the corpus: only corpus full text may be
    # quoted, and the reviewer has no Write tool to add such text anyway.
    # CorpusAdd(pdf_url) then ConsultLiterature(paper_id) is how it reads one.
    return tools
