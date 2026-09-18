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


def test_unconfigured_says_unconfigured_not_undocumented(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    tool = build_abaqus_docs_closures()["ConsultAbaqusDocs"]
    out = tool("*FREQUENCY")
    assert ENV_VAR in out
    assert "not set" in out
    # the whole point: it must not read as "the keyword does not exist"
    assert "undocumented" in out


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
