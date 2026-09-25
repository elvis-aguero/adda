"""Runtime tool closures for the literature reviewer.

The reviewer holds six tools: the corpus (ConsultLiterature, CorpusAdd),
discovery over the literature databases (SearchPapers, CitationGraph,
PaperDetails, see ``discovery.py``), and arxiv_read_paper. The per-provider
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
from .throttle import _cap_result


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

    # Reading one arXiv paper's text without indexing it.
    from ...backends.ollama import _build_arxiv_closures
    read = _build_arxiv_closures().get("arxiv_read_paper")
    if read is not None:
        def _capped(paper_id: str) -> str:
            return _cap_result(read(paper_id))
        _capped.__doc__ = read.__doc__
        _capped._tool_examples = list(getattr(read, "_tool_examples", []))
        _capped.__wrapped__ = read
        tools["arxiv_read_paper"] = _capped
    return tools
