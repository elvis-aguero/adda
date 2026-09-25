"""SearchPapers, CitationGraph and PaperDetails over fake providers.

What the merge must keep from the tools it replaced: a provider failing is
visible (it was a separate tool the agent could see had failed), searches run
concurrently (the async pool's job), and the same paper found twice is one
entry (which the agent used to do by hand).
"""
from __future__ import annotations

import json
import threading
import time

import adda._src.agents.literature_tools.discovery as disc
from adda._src.agents.literature_tools.discovery import (
    build_discovery_closures,
    merge_records,
)


def _papers(out: str) -> list[dict]:
    return json.loads(out.split("\n", 1)[1])


def _providers(**over):
    base = {
        "arxiv_search": lambda q, n: [
            {"title": "Attention is all you need, a long title", "year": 2017,
             "arxiv": "1706.03762v5", "pdf_url": "https://arxiv.org/pdf/1706.03762"}],
        "search_openalex": lambda q, n: json.dumps([
            {"id": "https://openalex.org/W1", "title": "Attention is all you need, a long title",
             "year": 2017, "doi": "10.48550/arXiv.1706.03762", "cited_by_count": 900},
            {"id": "https://openalex.org/W2", "title": "A journal paper arXiv never saw",
             "year": 2020, "doi": "10.1016/j.x.2020.1"}]),
        "search_semantic_scholar": lambda q, n: (
            "ERROR: Semantic Scholar access forbidden (403) — retrying will not help."),
    }
    base.update(over)
    return base


def test_the_same_paper_from_two_providers_is_one_entry():
    out = build_discovery_closures(_providers())["SearchPapers"]("attention")
    papers = _papers(out)
    assert len(papers) == 2
    first = papers[0]
    assert first["paper_id"] == "1706.03762"
    assert sorted(first["found_in"]) == ["arxiv", "openalex"]
    assert first["citations"] == 900
    assert first["pdf_url"] == "https://arxiv.org/pdf/1706.03762"


def test_the_first_line_says_how_each_provider_did():
    out = build_discovery_closures(_providers())["SearchPapers"]("attention")
    header = out.split("\n", 1)[0]
    assert "arxiv 1 results" in header
    assert "openalex 2 results" in header
    assert "semantic_scholar failed — Semantic Scholar access forbidden (403)" in header


def test_providers_are_asked_concurrently():
    """Three one-second providers answer in about one second, not three."""
    def slow(result):
        def fn(q, n):
            time.sleep(1.0)
            return result
        return fn
    tools = build_discovery_closures(_providers(
        arxiv_search=slow([]), search_openalex=slow("[]"),
        search_semantic_scholar=slow("[]")))
    t0 = time.monotonic()
    tools["SearchPapers"]("q")
    assert time.monotonic() - t0 < 2.0


def test_a_provider_past_the_timeout_is_reported_and_the_rest_returned(monkeypatch):
    monkeypatch.setattr(disc, "PROVIDER_TIMEOUT_S", 0.2)
    release = threading.Event()

    def hang(q, n):
        release.wait(5)
        return "[]"
    out = build_discovery_closures(_providers(search_openalex=hang))["SearchPapers"]("q")
    release.set()
    assert "openalex timed out" in out.split("\n", 1)[0]
    assert _papers(out)[0]["found_in"] == ["arxiv"]


def test_sources_restricts_and_an_unknown_one_is_refused():
    tools = build_discovery_closures(_providers())
    out = tools["SearchPapers"]("q", sources="openalex")
    assert out.split("\n", 1)[0] == "Searched: openalex 2 results"
    assert tools["SearchPapers"]("q", sources="scopus").startswith("ERROR")


def test_merge_orders_by_best_rank_then_agreement():
    merged = merge_records({
        "a": [{"title": "Only in a, a sufficiently long title"},
              {"title": "In both, a sufficiently long title"}],
        "b": [{"title": "In both, a sufficiently long title"}],
    })
    assert [m["title"] for m in merged] == [
        "In both, a sufficiently long title", "Only in a, a sufficiently long title"]


def test_citation_graph_uses_openalex_first():
    calls = []
    tools = build_discovery_closures({
        "resolve_openalex_id": lambda pid: calls.append(pid) or "W1",
        "get_openalex_citations": lambda wid, n: json.dumps(
            [{"id": "https://openalex.org/W9", "title": "A citing paper", "doi": "10.1/c"}]),
    })
    out = tools["CitationGraph"]("1706.03762")
    assert out.startswith("Source: openalex\n")
    assert calls == ["1706.03762"]
    assert _papers(out)[0]["paper_id"] == "10.1/c"


def test_citation_graph_falls_back_and_says_why():
    tools = build_discovery_closures({
        "resolve_openalex_id": lambda pid: "ERROR: OpenAlex has no work for 'x'",
        "get_openalex_references": lambda wid: "[]",
        "get_semantic_scholar_citations_and_references": lambda pid: json.dumps(
            {"references": [{"paperId": "s2a", "title": "A reference"}], "citations": []}),
    })
    out = tools["CitationGraph"]("x", direction="references")
    assert out.startswith("Source: semantic_scholar (openalex failed — OpenAlex has no work")
    assert _papers(out)[0]["title"] == "A reference"


def test_citation_graph_refuses_an_unknown_direction():
    out = build_discovery_closures({})["CitationGraph"]("x", direction="sideways")
    assert out.startswith("ERROR: direction must be")


def test_paper_details_falls_back_to_openalex():
    tools = build_discovery_closures({
        "get_semantic_scholar_paper_details": lambda pid: "ERROR: timed out after 30s.",
        "get_openalex_work": lambda pid: '{"title": "T"}',
    })
    out = tools["PaperDetails"]("1706.03762")
    assert out.startswith("Source: openalex (semantic_scholar failed — timed out")
    assert out.endswith('{"title": "T"}')


def test_no_provider_is_an_error_not_an_empty_answer():
    out = build_discovery_closures({})["PaperDetails"]("x")
    assert out.startswith("ERROR: no provider could answer")
