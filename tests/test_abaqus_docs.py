"""The Abaqus docs tool, and specifically what it says when it CANNOT help.

The unconfigured/broken paths matter more than the happy path: an agent that
reads "no corpus" as "this keyword is undocumented" will confidently write a
deck around a keyword that does exist. Both messages therefore state which
kind of failure occurred, and these tests pin that wording.

The happy path is exercised only when a corpus is configured, because the
corpus is licensed Abaqus documentation and cannot ship with adda.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from adda._src.knowledge.abaqus import ENV_VAR, build_abaqus_docs_closures


def test_unconfigured_withholds_the_tool_entirely(monkeypatch):
    """It used to declare the tool and have it explain that it had no corpus.
    But "no corpus" can only be misread as "not documented" by an agent that
    HAS the tool; withheld, the agent is simply one without an Abaqus manual.
    features.py states the rule: a dead tool left registered produces an agent
    that keeps calling something that errors, and those land as ERROR_RETURN."""
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert build_abaqus_docs_closures() == {}


def test_an_agent_without_a_corpus_matches_its_base_class(monkeypatch, tmp_path):
    """The consequence worth asserting: no catalog tokens, no phantom tool."""
    monkeypatch.delenv(ENV_VAR, raising=False)
    from adda import AbaqusDataGeneratorAgent, DataGeneratorAgent

    assert (set(AbaqusDataGeneratorAgent().build_closure_tools(tmp_path))
            == set(DataGeneratorAgent().build_closure_tools(tmp_path)))


def test_unreadable_corpus_degrades_without_raising(tmp_path):
    tool = build_abaqus_docs_closures(tmp_path / "nope")["ConsultAbaqusDocs"]
    out = tool("*FREQUENCY")
    assert "unavailable" in out
    assert "NOT that the keyword is undocumented" in out


def test_env_var_is_honoured(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_VAR, str(tmp_path))
    from adda._src.knowledge.abaqus import corpus_dir
    assert corpus_dir() == Path(tmp_path)


@pytest.mark.skipif(not os.environ.get(ENV_VAR),
                    reason="needs a locally built Abaqus corpus")
def test_search_and_page_fetch_round_trip():
    tool = build_abaqus_docs_closures()["ConsultAbaqusDocs"]
    hits = tool("*FREQUENCY")
    assert "page_id:" in hits
    page = tool("simakey-r-frequency")
    assert page.lstrip().startswith("#")


# ---------------------------------------------------------------------------
# The corpus round trip, on a SYNTHETIC corpus
#
# The licensed documentation cannot ship, but the code under test is ours, not
# Dassault's: the HTML extractor, the sqlite schema, the search, the page
# renderer and the keyword correction. A handful of fake pages exercises all
# of it, and without this the two largest modules in the feature ran at 0% and
# 9% — which is how both of their imports came to be broken:
#
#   * reader.build() imported `extract_page` from `abaqus_doc_corpus`, the
#     name builder.py had as a standalone script. It resolves nowhere, so the
#     build path could never run at all.
#   * builder.py imported `adda._src.literature_corpus`, which moved to
#     `adda._src.literature.literature_corpus` — swallowed by a bare
#     `except Exception: return None`, so it degraded silently.
#
# Neither is subtle. Both survived because nothing executed these lines.
# ---------------------------------------------------------------------------

_PAGES = {
    "SIMACAEKEYRefMap": {
        "simakey-r-frequency.htm": (
            "*FREQUENCY",
            "<p>Extract eigenvalues and eigenmodes of the model.</p>"
            "<pre>*FREQUENCY, EIGENSOLVER=LANCZOS\n10,,,</pre>",
        ),
        "simakey-r-boundary.htm": (
            "*BOUNDARY",
            "<p>Prescribe boundary conditions at nodes.</p>",
        ),
        "simakey-r-beamsection.htm": (
            "*BEAM SECTION",
            "<p>Specify section properties for beam elements.</p>"
            "<table><tr><th>Parameter</th><th>Meaning</th></tr>"
            "<tr><td>SECTION</td><td>cross-section library name</td></tr></table>",
        ),
    },
    "SIMACAEELMRefMap": {
        "simaelm-c-beamcrosssectlib.htm": (
            "Beam cross-section library",
            "<p>The CIRC section defines a solid circular beam.</p>"
            "<dl><dt>CIRC</dt><dd>solid circular section, one radius</dd></dl>",
        ),
    },
}


@pytest.fixture
def corpus(tmp_path):
    """A built corpus from synthetic pages — the real builder, real schema."""
    pytest.importorskip("lxml", reason="the HTML extractor needs lxml")
    from adda._src.knowledge.abaqus.reader import AbaqusDocs

    pages = tmp_path / "pages"
    for book, files in _PAGES.items():
        d = pages / "English" / book
        d.mkdir(parents=True)
        for name, (title, body) in files.items():
            (d / name).write_text(
                f'<html><head><title>{title}</title>'
                f'<meta name="DC.Type" content="reference"/></head>'
                f"<body><h1>{title}</h1>{body}</body></html>",
                encoding="utf-8")

    out = tmp_path / "corpus"
    out.mkdir()
    docs = AbaqusDocs(out)
    stats = docs.build(pages, log=lambda *a, **k: None)
    assert stats["pages"] == 4, stats
    return out


def test_the_build_path_runs_at_all(corpus):
    """It could not. reader.build() imported a module that does not exist."""
    assert (corpus / "abaqus_docs.sqlite").is_file()


def test_a_keyword_search_finds_its_page(corpus):
    tool = build_abaqus_docs_closures(corpus)["ConsultAbaqusDocs"]
    out = tool("*FREQUENCY")
    assert "simakey-r-frequency" in out


def test_a_page_id_returns_the_whole_page(corpus):
    """The second of the tool's two behaviours: search hands back a page_id,
    and passing it returns the document rather than another hit list."""
    tool = build_abaqus_docs_closures(corpus)["ConsultAbaqusDocs"]
    page = tool("simakey-r-frequency")
    assert "EIGENSOLVER=LANCZOS" in page, page[:300]


def test_a_wrong_keyword_is_corrected_rather_than_refused(corpus):
    """The behaviour the PR credits as the tool's most valuable, and the one
    that had no test: 8 of 24 consultations in the measured run named a
    keyword that does not exist, and every one came back with a usable
    correction."""
    tool = build_abaqus_docs_closures(corpus)["ConsultAbaqusDocs"]
    out = tool("*FREQ")
    assert "*FREQUENCY" in out, out[:300]


def test_structure_survives_extraction(corpus):
    """Flattening a page to text is what the extractor exists to avoid: a
    parameter table becomes word soup and a syntax block gets shredded."""
    tool = build_abaqus_docs_closures(corpus)["ConsultAbaqusDocs"]
    assert "cross-section library name" in tool("simakey-r-beamsection")
    assert "solid circular section" in tool("simaelm-c-beamcrosssectlib")
