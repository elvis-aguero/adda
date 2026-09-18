"""The query set must keep pointing at files that exist.

A labelled set whose labels have rotted scores whatever it scores and means
nothing. Renaming a module is normal; leaving this set behind is the failure
these tests exist to make loud.
"""
from __future__ import annotations

import collections
from pathlib import Path

import pytest

from . import adda_source_queries as Q

_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("qid", "gold"), [(qid, g) for _, qid, _, gold in Q.ALL for g in gold])
def test_every_gold_target_still_exists(qid, gold):
    assert (_ROOT / gold).exists(), (
        f"query {qid} is labelled with {gold}, which no longer exists. "
        f"Repoint the label at the file that answers the question now — do "
        f"NOT delete the query, and do not repoint it at whatever a "
        f"retriever happens to return.")


def test_query_ids_are_unique():
    dupes = [i for i, c in collections.Counter(q[1] for q in Q.ALL).items()
             if c > 1]
    assert not dupes, f"duplicate query ids: {dupes}"


def test_the_held_out_split_is_frozen_and_real():
    """A held-out id that matches no query is a split that silently shrank."""
    ids = {q[1] for q in Q.ALL}
    assert Q.HELD_OUT_IDS <= ids, sorted(Q.HELD_OUT_IDS - ids)
    assert len(Q.DEVELOPMENT) + len(Q.HELD_OUT) == len(Q.ALL)
    assert Q.HELD_OUT, "the held-out split is empty"


def test_every_tier_is_represented_in_both_splits():
    """Stratification is the point of the split: a tier held out entirely, or
    not at all, makes the held-out score unreadable for that tier."""
    for split, rows in (("development", Q.DEVELOPMENT), ("held out", Q.HELD_OUT)):
        tiers = {r[0] for r in rows}
        assert tiers == set(Q.TIERS), (
            f"{split} split is missing tiers: {set(Q.TIERS) - tiers}")


def test_every_declared_knob_is_reachable_by_some_query():
    """A knob no question can find is a knob nobody can find.

    Not a retrieval assertion — it asserts the QUERY SET covers the declared
    feature surface, so a new feature knob arrives with a way to ask for it.
    """
    from adda._src.runtime import features

    declared = {f.key for f in features.FEATURES}
    uncovered = declared - set(Q.KNOB_COVERAGE)
    assert not uncovered, (
        f"these feature knobs have no query: {sorted(uncovered)}. Add a "
        f"question someone would really ask for each, and map it in "
        f"KNOB_COVERAGE.")

    stale = set(Q.KNOB_COVERAGE) - declared
    assert not stale, f"KNOB_COVERAGE names knobs that no longer exist: {sorted(stale)}"

    ids = {q[1] for q in Q.ALL}
    dangling = {k: v for k, v in Q.KNOB_COVERAGE.items() if v not in ids}
    assert not dangling, f"KNOB_COVERAGE points at missing queries: {dangling}"
