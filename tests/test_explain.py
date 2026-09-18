"""The user-facing lookup: it must answer, and it must not lie about scope.

These are not retrieval-quality tests — quality is measured over 128 labelled
queries by ``internal/tools/source_index_baseline.py``, and a handful of
eyeballed examples is exactly how a ranker rots unnoticed. What is pinned here
is the contract: the thing indexes adda, it says so, it stays bounded, and its
four unit kinds are all actually present.
"""
from __future__ import annotations

import pytest

from adda import explain as E


@pytest.fixture(scope="module")
def api():
    return E._api()


def test_it_indexes_adda_and_says_so(api):
    """A reply that named f3dasm while searching adda shipped once. The
    renderer was written for one package and hardcoded its name in seven
    user-facing strings."""
    out = E.explain("run")
    assert "in adda" in out
    assert "f3dasm " not in out.split("match(es)")[0]


def test_all_four_unit_kinds_are_in_the_index(api):
    """Symbols alone LOSE to ripgrep on this package; the other three are why
    it wins. If one silently stopped being indexed, quality would drop and
    every functional test here would still pass."""
    kinds = {e.kind for e in api._index.values()}
    for required in ("module", "constant", "markdown"):
        assert required in kinds, f"{required} entries are missing"
    assert kinds & {"class", "function", "method"}, "no symbols indexed"


def test_a_constant_carries_its_modules_docstring(api):
    """``BACKSTOP_USD = 'backstop_usd'`` teaches nothing on its own. Attaching
    the module docstring is what makes it reachable by the concept, and it is
    worth +0.03 r@1 over 128 queries — the single best-measured change here."""
    e = api._index["adda._src.runtime.terminal.BACKSTOP_USD"]
    assert "backstop_usd" in e.doc
    assert len(e.doc) > 200, "the module's docstring is not attached"


def test_an_exact_name_returns_its_entry_with_the_public_import(api):
    out = E.explain("AgenticRun")
    assert "from adda import AgenticRun" in out, (
        "an agent handed adda._src.runtime.agent_runtime writes a private "
        "import that breaks on the next release")


def test_a_knowledge_base_rule_is_reachable(api):
    """The rules live in markdown shipped inside the package. They are the one
    thing no walk over module attributes can reach."""
    md = [k for k, e in api._index.items() if e.kind == "markdown"]
    assert any("entries/0001" in k for k in md), (
        "the evaluate-through-get-evaluator rule is not indexed")


def test_a_reply_is_bounded(api):
    """The tool exists to keep adda OUT of the context window."""
    for q in ("run", "adda", "store", "how do I configure a run"):
        assert len(E.explain(q)) <= 6500, q


def test_a_miss_is_honest_about_what_it_searched(api):
    """The query has to be something adda genuinely has no word for. The first
    version of this test used "abaqus contact stabilisation", lifted from the
    f3dasm suite where it IS a miss -- here it correctly returns adda's Abaqus
    integration, so the test was wrong and the tool was right."""
    out = E.explain("zzqx wqjm vbrt")
    assert "INSTALLED adda only" in out
    assert "not that it does not exist" in out
    assert "zzqx" in out, "it must echo what was searched"


def test_it_almost_never_admits_ignorance_RECORDED_NOT_ASSERTED(api):
    """A property of the ranker, recorded so it is a decision rather than a
    surprise.

    There is no score floor: the top ``limit`` hits are returned whatever they
    scored. "kubernetes helm chart" returns the falsification charter, because
    "chart" folds to "charter". For an agent, a confidently wrong answer costs
    more than a miss -- it acts on it.

    This is NOT asserted as desirable. It is pinned because the fix (a
    minimum-score floor) cannot be judged by recall@k, which a floor can only
    lower: it needs a set of questions adda genuinely cannot answer, scored on
    how often it says so. That set does not exist yet.
    """
    out = E.explain("kubernetes helm chart")
    assert "match(es)" in out, (
        "if this now reports a miss, a score floor was added -- delete this "
        "test and measure the floor against a negative-query set")


def test_the_cli_runs_and_reports_status():
    assert E.main(["AgenticRun"]) == 0
    assert E.main(["--overview"]) == 0
    assert E.main([]) == 2, "no query should be a usage error, not a crash"
