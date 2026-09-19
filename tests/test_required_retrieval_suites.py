"""The retrieval suites that may never be optional.

WHY THIS FILE EXISTS
    Three of the four knowledge tools are guarded on a corpus. Abaqus needs
    Dassault's licensed documentation and Basilisk needs a checkout, so both
    are marked ``corpus`` and deselected in CI -- deliberately, because a
    corpus nobody can ship cannot gate a push.

    f3dasm and adda are different: f3dasm is a declared dependency and adda is
    the package under test, so both are always available and both MUST be
    measured on every push. The danger is that they stop being measured
    quietly. ``tests/test_f3dasm_api.py`` used to open with ``importorskip``,
    which would have turned a missing dependency into a green skip instead of
    a loud collection failure; and a marker applied a little too broadly
    would deselect the adda suite with no failure anywhere.

    This session has already seen both failure modes for real: a contract test
    silently reduced to checking one of seven feature defaults and reporting
    passing skips, and 48 of 54 Basilisk tests skipping while their figures
    were quoted as measured. A skip is not a failure, which is exactly what
    makes it dangerous.
"""
from __future__ import annotations


def test_f3dasm_is_importable_so_its_suite_cannot_skip():
    """f3dasm is a hard dependency (``pyproject.toml``'s
    ``project.dependencies``), never an optional extra, so its suites must
    import it plainly and let a missing install fail collection loudly
    instead of skipping green."""
    import f3dasm  # noqa: F401


def test_the_f3dasm_index_builds_and_is_not_empty():
    from adda._src.knowledge.f3dasm_api import F3dasmApi

    api = F3dasmApi()
    assert len(api._index) > 200, "the f3dasm index collapsed"
    assert api._rank("ExperimentData", 5), "the f3dasm ranker returns nothing"


def test_the_adda_index_builds_over_all_four_units():
    """adda indexes itself over symbols, modules, constants and markdown.
    Measured on 128 labelled queries, symbols alone lose to ripgrep; the mix
    is the result, so losing a unit silently is a quality regression that no
    functional test would catch."""
    from adda._src.knowledge.f3dasm_api import AddaApi

    api = AddaApi()
    kinds = {e.kind for e in api._index.values()}
    for required in ("module", "constant", "markdown"):
        assert required in kinds, f"the adda index lost its {required} entries"
    assert kinds & {"class", "function", "method"}


def test_both_required_query_sets_are_present_and_sized():
    """The sets are the instrument. If one shrinks, every figure quoted from
    it changes meaning without any test failing."""
    from .adda_source_queries import ALL as ADDA_A
    from .adda_source_queries_b import ALL as ADDA_B
    from .f3dasm_query_set import QUERIES as F3_A
    from .f3dasm_query_set_b import QUERIES as F3_B

    assert len(ADDA_A) + len(ADDA_B) >= 128, "the adda query set shrank"
    assert len(F3_A) + len(F3_B) >= 126, "the f3dasm query set shrank"
