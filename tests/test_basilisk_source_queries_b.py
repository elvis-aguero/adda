"""Assertions on query set B, and its consistency with set A.

Mirrors `test_basilisk_source_queries.py`. The one addition is the
cross-file duplicate-query check: set B must not silently re-ask a question
set A already asks.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from .basilisk_source_queries import ALL as ALL_A
from .basilisk_source_queries_b import (
    ALL_B,
    DEVELOPMENT_B,
    HELD_OUT_B,
    HELD_OUT_IDS_B,
    TIERS_B,
)

_ROOT = os.environ.get("ADDA_BASILISK_SRC", "")
#: Guarded on the ENV VAR, never on whether a path happens to exist -- see
#: the identical comment in test_basilisk_source_queries.py for why.
SRC = Path(_ROOT) / "src" if _ROOT else None


@pytest.mark.corpus
@pytest.mark.parametrize("qid,query,gold", ALL_B)
def test_every_gold_target_still_exists(qid, query, gold):
    """A rename upstream must break this set loudly, not silently pass."""
    for path in gold:
        assert (SRC / path).exists(), f"{qid}: missing gold {path}"


def test_query_ids_are_unique():
    ids = [q[0] for q in ALL_B]
    assert len(ids) == len(set(ids))


def test_query_ids_do_not_collide_with_set_a():
    """Set B's id prefixes (nb/cb/sb/rb/eb/kb) exist precisely so a stray
    id typo can't silently alias a set A id."""
    ids_a = {q[0] for q in ALL_A}
    ids_b = {q[0] for q in ALL_B}
    assert not (ids_a & ids_b)


def test_every_gold_list_is_non_empty():
    """A query with no gold answer scores nothing and measures nothing."""
    for qid, _, gold in ALL_B:
        assert gold, f"{qid} has no gold answer"


def test_no_duplicate_query_strings_within_set_b():
    queries = [q[1] for q in ALL_B]
    assert len(queries) == len(set(queries))


def test_no_duplicate_query_strings_across_set_a_and_set_b():
    """Set B is an EXTENSION of set A's approach -- it must not silently
    re-ask a question set A already asks under a new id."""
    queries_a = {q[1] for q in ALL_A}
    queries_b = {q[1] for q in ALL_B}
    overlap = queries_a & queries_b
    assert not overlap, f"duplicate query text across set A and B: {overlap}"


def test_every_held_out_id_matches_a_real_query():
    """A held-out id matching nothing is a split that silently shrank."""
    assert HELD_OUT_IDS_B <= {q[0] for q in ALL_B}
    assert len(HELD_OUT_B) == len(HELD_OUT_IDS_B)


def test_the_splits_partition_the_set():
    assert len(DEVELOPMENT_B) + len(HELD_OUT_B) == len(ALL_B)
    assert not ({q[0] for q in DEVELOPMENT_B} & {q[0] for q in HELD_OUT_B})


def test_every_tier_is_represented_in_both_splits():
    tier_prefixes = tuple(TIERS_B)
    for name, split in (("development", DEVELOPMENT_B),
                        ("held_out", HELD_OUT_B)):
        prefixes = {next(p for p in tier_prefixes if q[0].startswith(p))
                    for q in split}
        assert prefixes == set(TIERS_B), \
            f"{name} missing tiers: {set(TIERS_B) - prefixes}"
