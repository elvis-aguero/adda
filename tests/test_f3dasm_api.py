"""The f3dasm API index: never stale, and sharp enough to be worth a tool slot.

Three things are asserted here, in increasing order of what they protect.

1. THE INDEX MATCHES THE INSTALLED f3dasm. It is built by introspection, so it
   cannot drift on its own — but a hand-edit or a cached artifact could. These
   tests re-introspect and compare, the same discipline
   ``tests/test_f3dasm_idioms.py`` applies to the snippet block.

2. THE PUBLIC IMPORT PATH IS RIGHT. ``__module__`` reports
   ``f3dasm._src.experimentdata`` for ``ExperimentData``; the import an agent
   must write is ``from f3dasm import ExperimentData``. Handing over the
   private path would make the tool worse than nothing, so it is pinned.

3. RETRIEVAL ACTUALLY FINDS THINGS — a golden set of queries an agent would
   plausibly type, each with the symbol it must surface. Ranking is the part
   that silently rots, and eyeballing a few queries is how you ship a tool that
   looks fine and answers badly.
"""
from __future__ import annotations

import pytest

f3dasm = pytest.importorskip("f3dasm")

from adda._src.knowledge.f3dasm_api import (  # noqa: E402
    F3dasmApi,
    build_index,
)


@pytest.fixture(scope="module")
def api():
    return F3dasmApi()


# --- 1. never stale ---------------------------------------------------------

def test_the_index_is_built_from_the_installed_package(api):
    """Not from a checkout. On a cluster there may be no source tree, and a
    checked-out version can differ from the one that will actually run."""
    import inspect
    import pathlib

    pkg = pathlib.Path(f3dasm.__file__).parent
    e = api._index["f3dasm.ExperimentData"]
    live = pathlib.Path(inspect.getsourcefile(f3dasm.ExperimentData))
    assert live.is_relative_to(pkg)
    assert e.where.startswith("f3dasm/")


def test_every_entry_still_matches_live_introspection(api):
    """The whole index, re-derived and compared. Catches a stale artifact."""
    fresh = build_index()
    assert set(fresh) == set(api._index)
    for key, e in fresh.items():
        assert e.signature == api._index[key].signature, key


def test_a_symbol_that_moved_would_be_noticed():
    """Sanity: the index is keyed on real symbols, not a frozen list."""
    idx = build_index()
    assert "f3dasm.ExperimentData" in idx
    assert "f3dasm.create_sampler" in idx
    assert len(idx) > 200


# --- 2. the public path, which is the whole point ---------------------------

@pytest.mark.parametrize("key,expected_import", [
    ("f3dasm.ExperimentData", "from f3dasm import ExperimentData"),
    ("f3dasm.DataGenerator", "from f3dasm import DataGenerator"),
    ("f3dasm.create_sampler", "from f3dasm import create_sampler"),
    ("f3dasm.design.Domain", "from f3dasm.design import Domain"),
])
def test_the_entry_gives_the_public_import_not_the_private_one(
        api, key, expected_import):
    e = api._index[key]
    assert e.import_line == expected_import
    assert "_src" not in (e.import_line or ""), (
        "handing an agent a private import path is worse than no tool")


def test_the_private_definition_path_is_never_the_key(api):
    """`__module__` says f3dasm._src.experimentdata. The key must not."""
    assert f3dasm.ExperimentData.__module__.startswith("f3dasm._src")
    assert "f3dasm.ExperimentData" in api._index
    assert "f3dasm._src.experimentdata.ExperimentData" not in api._index


def test_a_private_symbol_is_answerable_but_flagged(api):
    """An agent reading a traceback needs to look internals up; it must not
    mistake that for permission to import them."""
    priv = [k for k, e in api._index.items() if e.private]
    assert priv, "f3dasm has internals; the index should know about them"
    e = api._index[priv[0]]
    assert e.import_line is None
    out = api.consult(e.key)
    assert "PRIVATE" in out and "not import" in out.lower()


# --- 3. retrieval: the golden set -------------------------------------------

# (query, one-or-more acceptable answers). A concept query often has several
# correct answers, and pinning one would tune the ranker toward a WORSE result:
# "sample the design space" legitimately returns grid/sobol/latin before
# create_sampler, and "run a pipeline on slurm" returns Pipeline.run before
# SlurmCluster. Both are better answers than the ones first written here.
# Queries are phrased the way an agent phrases them, including without f3dasm's
# own vocabulary.
GOLDEN = [
    # exact names
    ("ExperimentData", {"f3dasm.ExperimentData"}),
    ("create_sampler", {"f3dasm.create_sampler"}),
    ("Domain", {"f3dasm.design.Domain"}),
    ("DataGenerator", {"f3dasm.DataGenerator"}),
    # dotted / method names
    ("ExperimentData.store", {"f3dasm.ExperimentData.store"}),
    ("Domain.add_float", {"f3dasm.design.Domain.add_float"}),
    # the name as it appears in a traceback
    ("f3dasm._src.experimentdata.ExperimentData", {"f3dasm.ExperimentData"}),
    # concept queries — the vocabulary-mismatch case
    ("how do I sample the design space",
     {"f3dasm.create_sampler", "f3dasm.design.grid", "f3dasm.design.sobol",
      "f3dasm.design.latin"}),
    ("sampler", {"f3dasm.create_sampler"}),
    ("store data to disk", {"f3dasm.ExperimentData.store"}),
    # Domain.add_parameter / .add are better answers than the class itself, and
    # were what the ranker actually returned all along — the old substring
    # assertion passed because "f3dasm.design.Domain" is a prefix of them.
    ("define input parameters",
     {"f3dasm.design.Domain", "f3dasm.design.Domain.add_parameter",
      "f3dasm.design.Domain.add", "f3dasm.design.Domain.add_float"}),
    ("run a pipeline on slurm",
     {"f3dasm.SlurmCluster", "f3dasm.SlurmResources", "f3dasm.Pipeline",
      "f3dasm.Pipeline.run"}),
]


@pytest.mark.parametrize("query,accept", GOLDEN, ids=[q for q, _ in GOLDEN])
def test_golden_query_surfaces_an_acceptable_symbol(api, query, accept):
    """Top FIVE, not top eight. A hit the agent must scroll to is a hit it will
    not take, and "somewhere in the list" is how a ranker rots unnoticed."""
    # Keys are compared EXACTLY, not as substrings of the rendered page.
    # `"f3dasm.ExperimentData" in out` is true when the page contains
    # `f3dasm.ExperimentData.set_project_dir`, and that false pass hid a real
    # failure: the traceback query returned three ExperimentData METHODS and
    # never the class. tests/test_f3dasm_api_retrieval.py found it.
    got = [h.key for h in api._rank(query, 5)]
    assert any(a in got for a in accept), (
        f"{query!r} surfaced none of {sorted(accept)} in the top 5."
        f"\n--- got ---\n{got}")


def test_a_concept_query_prefers_public_symbols(api):
    """f3dasm has 78 private symbols against 47 public. Without a penalty they
    crowd every concept search, and the agent is steered into internals."""
    hits = api._rank("sample the domain", 6)
    assert not hits[0].private
    assert sum(1 for h in hits if h.private) <= len(hits) // 2


def test_a_miss_says_what_it_searched(api):
    """A bare 'no results' invites the agent to conclude the thing does not
    exist, when it may simply live elsewhere."""
    out = api.consult("abaqus contact stabilisation")
    assert "No f3dasm symbol" in out
    assert "INSTALLED f3dasm only" in out


# --- output discipline ------------------------------------------------------

def test_a_reply_is_bounded(api):
    """The tool exists to keep f3dasm OUT of the context window."""
    for q in ("ExperimentData", "store", "sample", "f3dasm"):
        assert len(api.consult(q)) <= 6500, q


def test_search_results_are_terse(api):
    """A search is a menu, not the meal: one line per hit so the agent can
    choose without paying for eight full entries."""
    out = api.consult("sample", limit=8)
    body = out.split("\n\n", 1)[1]
    assert len(body) < 1400


def test_a_method_signature_omits_self(api):
    """The agent writes data.store(...), never store(data, ...)."""
    assert not api._index["f3dasm.ExperimentData.store"].signature.startswith(
        "(self")


def test_source_is_a_separate_request(api):
    """The 99k-token tier must never arrive unasked."""
    entry = api.consult("f3dasm.create_sampler")
    src = api.consult("f3dasm.create_sampler", source=True)
    assert "def create_sampler" not in entry
    assert "def create_sampler" in src


def test_source_of_an_unknown_symbol_refuses_clearly(api):
    out = api.consult("NotARealSymbol", source=True)
    assert out.startswith("ERROR:") and "search" in out.lower()


# --- the finding this tool exists to surface --------------------------------

def test_a_runtime_patched_method_says_so(api):
    """adda monkeypatches two ExperimentData methods at import time, so what
    runs is NOT what f3dasm documents. That is behaviour no f3dasm docstring
    describes, and it is the single highest-signal thing the index knows."""
    patched = {k for k, e in api._index.items() if e.patched_by}
    assert patched == {
        "f3dasm.ExperimentData.store",
        "f3dasm.ExperimentData.to_numpy",
    }, patched
    out = api.consult("ExperimentData.to_numpy")
    assert "REPLACED AT RUNTIME BY adda" in out


def test_overview_is_the_map_not_the_territory(api):
    """Orientation must stay cheap enough to be worth reading."""
    out = api.overview()
    assert "f3dasm.ExperimentData" in out
    assert len(out) <= 6500
    assert "_src" not in out, "the map must not name private paths"


def test_operator_dunders_are_indexed(api):
    """The one API a lexical index is otherwise blind to.

    An agent cannot search for `>>`, and no symbol list hints that `a >> b`
    builds a ChainedBlock or that `data + other` merges two ExperimentData.
    Drop these and the operator is unreachable — findable only by reading the
    owning class's docstring and hoping it mentions it.
    """
    assert "f3dasm.Block.__rshift__" in api._index
    assert "f3dasm.ExperimentData.__add__" in api._index

    out = api.consult("f3dasm.ExperimentData.__add__")
    assert "ExperimentData" in out

    # protocol noise stays out
    noise = [k for k in api._index
             if k.rsplit(".", 1)[-1] in ("__repr__", "__eq__", "__reduce__",
                                         "__hash__", "__str__")]
    assert not noise, noise
