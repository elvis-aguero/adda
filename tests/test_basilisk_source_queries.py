"""Assertions on the query set itself, so it cannot rot into silently passing."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from .basilisk_source_queries import (ALL, DEVELOPMENT, HELD_OUT,
                                      HELD_OUT_IDS, TIERS)

SRC = Path(os.environ.get(
    "ADDA_BASILISK_SRC",
    "/oscar/data/dharri15/eaguerov/basilisk-2025-04")) / "src"


@pytest.mark.parametrize("qid,query,gold", ALL)
def test_every_gold_target_still_exists(qid, query, gold):
    """A rename upstream must break this set loudly, not silently pass."""
    if not SRC.is_dir():
        pytest.skip("Basilisk corpus not available")
    for path in gold:
        assert (SRC / path).exists(), f"{qid}: missing gold {path}"


def test_query_ids_are_unique():
    ids = [q[0] for q in ALL]
    assert len(ids) == len(set(ids))


def test_every_gold_list_is_non_empty():
    """A query with no gold answer scores nothing and measures nothing."""
    for qid, _, gold in ALL:
        assert gold, f"{qid} has no gold answer"


def test_every_held_out_id_matches_a_real_query():
    """A held-out id matching nothing is a split that silently shrank."""
    assert HELD_OUT_IDS <= {q[0] for q in ALL}
    assert len(HELD_OUT) == len(HELD_OUT_IDS)


def test_the_splits_partition_the_set():
    assert len(DEVELOPMENT) + len(HELD_OUT) == len(ALL)
    assert not ({q[0] for q in DEVELOPMENT} & {q[0] for q in HELD_OUT})


def test_every_tier_is_represented_in_both_splits():
    for name, split in (("development", DEVELOPMENT), ("held_out", HELD_OUT)):
        tiers = {q[0][0] for q in split}
        assert tiers == set(TIERS), f"{name} missing tiers: {set(TIERS) - tiers}"
