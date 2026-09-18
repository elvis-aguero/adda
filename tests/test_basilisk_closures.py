import os
from pathlib import Path

import pytest

from adda._src.knowledge.basilisk import build_basilisk_docs_closures

_ROOT = os.environ.get("ADDA_BASILISK_SRC", "")
SRC = Path(_ROOT) if _ROOT else None
corpus = pytest.mark.corpus


def test_unconfigured_returns_no_tool_at_all(monkeypatch):
    """A dead tool produces ERROR_RETURNs, the one KPI whose target is zero."""
    monkeypatch.delenv("ADDA_BASILISK_SRC", raising=False)
    assert build_basilisk_docs_closures() == {}


def test_a_configured_but_unreadable_corpus_also_withholds(tmp_path):
    assert build_basilisk_docs_closures(tmp_path) == {}


@corpus
def test_configured_exposes_exactly_one_tool():
    assert list(build_basilisk_docs_closures(SRC)) == ["ConsultBasiliskDocs"]


@corpus
def test_the_tool_answers_a_name_and_a_description():
    tool = build_basilisk_docs_closures(SRC)["ConsultBasiliskDocs"]
    assert "Two-phase" in tool("two-phase.h")
    assert "tension.h" in tool("add surface tension between two fluids")


@corpus
def test_the_docstring_is_the_agents_only_documentation():
    """The runtime renders this into the generated <tools> catalog."""
    tool = build_basilisk_docs_closures(SRC)["ConsultBasiliskDocs"]
    assert tool.__doc__ and len(tool.__doc__) > 400
    assert "NEVER STACKED" in tool.__doc__ or "never" in tool.__doc__.lower()
