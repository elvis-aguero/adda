"""Tests for adda._src.runtime.constraint_snapshot — the single source of truth
for a run's budget/time-remaining state, shared by every delegation
boundary (human->strategizer, strategizer->worker, strategizer->critic in
both GATE and FEEDBACK mode)."""
from __future__ import annotations

from adda._src.runtime.constraint_snapshot import (
    ConstraintSnapshot,
    compute_constraint_snapshot,
)


def test_no_budgets_set_renders_as_unspecified():
    s = compute_constraint_snapshot(
        eval_budget=None, budget_seconds=None, run_start=None,
        experiment_data_dir=None,
    )
    assert s.evals_remaining is None
    assert s.wall_remaining_s is None
    assert not s.eval_exhausted
    assert not s.wall_exhausted
    text = s.as_text()
    assert "unspecified" in text
    assert "<constraints>" in text and "</constraints>" in text


def test_eval_budget_remaining_and_exhausted():
    s = ConstraintSnapshot(
        eval_budget=100, evals_used=80,
        wall_budget_s=None, wall_elapsed_s=None,
    )
    assert s.evals_remaining == 20
    assert not s.eval_exhausted
    exhausted = ConstraintSnapshot(
        eval_budget=100, evals_used=140,
        wall_budget_s=None, wall_elapsed_s=None,
    )
    assert exhausted.evals_remaining == 0, "remaining floors at 0, never negative"
    assert exhausted.eval_exhausted


def test_wall_budget_remaining_and_exhausted():
    s = ConstraintSnapshot(
        eval_budget=None, evals_used=0,
        wall_budget_s=3600.0, wall_elapsed_s=900.0,
    )
    assert s.wall_remaining_s == 2700.0
    assert not s.wall_exhausted
    exhausted = ConstraintSnapshot(
        eval_budget=None, evals_used=0,
        wall_budget_s=3600.0, wall_elapsed_s=5000.0,
    )
    assert exhausted.wall_remaining_s == 0.0
    assert exhausted.wall_exhausted


def test_as_text_reports_both_budgets_together():
    s = ConstraintSnapshot(
        eval_budget=200, evals_used=150,
        wall_budget_s=3600.0, wall_elapsed_s=1800.0,
    )
    text = s.as_text()
    assert "150/200 evals used" in text
    assert "30.0min/60.0min used (50%)" in text
    assert "EXHAUSTED" not in text


def test_as_text_flags_exhaustion_explicitly():
    s = ConstraintSnapshot(
        eval_budget=200, evals_used=200,
        wall_budget_s=None, wall_elapsed_s=None,
    )
    assert "(EXHAUSTED)" in s.as_text()


def test_as_dict_matches_as_text_numbers():
    """Single source of truth: the structured fields persisted to
    DelegationLog and the text injected into an agent's context must come
    from the same computation, never drift independently."""
    s = ConstraintSnapshot(
        eval_budget=50, evals_used=10,
        wall_budget_s=100.0, wall_elapsed_s=25.0,
    )
    d = s.as_dict()
    assert d["eval_budget"] == 50
    assert d["evals_used"] == 10
    assert d["evals_remaining"] == 40
    assert d["wall_budget_s"] == 100.0
    assert d["wall_elapsed_s"] == 25.0
    assert d["wall_remaining_s"] == 75.0


def test_compute_constraint_snapshot_falls_back_gracefully_on_bad_path(tmp_path):
    """A nonexistent/empty experiment_data_dir must never raise — evals_used
    falls back to 0, matching a fresh run before any evaluations exist."""
    s = compute_constraint_snapshot(
        eval_budget=10, budget_seconds=None, run_start=None,
        experiment_data_dir=tmp_path / "does_not_exist",
    )
    assert s.evals_used == 0


# ---------------------------------------------------------------------------
# The orchestrator's clock must advance
#
# agent_runtime rendered one snapshot at run start and concatenated it onto
# the problem statement -- the standing first user turn, re-sent verbatim
# every turn. Four consecutive strategizer turns across 23.5 minutes of run
# 20260917T141603 all read "2.7min/60.0min used (5%)" while the true figure
# had reached 44%. Every worker path re-snapshots at use; this was the one
# call site that cached, on the node that decides how much more to attempt.
# ---------------------------------------------------------------------------

class _FakeNode:
    """Just enough of a node for snapshot_for_node and _constraint_refresh."""

    _eval_budget = None
    _budget_seconds = 3600.0
    _current_notes_dir = None
    _delegation_log = None

    def __init__(self, run_start):
        self._run_start = run_start


def test_the_orchestrators_snapshot_advances_between_turns():
    import time

    from adda._src.nodes.node import Node
    from adda._src.runtime.constraint_snapshot import snapshot_for_node

    node = _FakeNode(run_start=time.time() - 120.0)
    first = snapshot_for_node(node).wall_elapsed_s

    node._run_start -= 1500.0          # 25 more minutes of wall clock
    second = snapshot_for_node(node).wall_elapsed_s

    assert second > first + 1400, (
        "the snapshot is not recomputed; this is the frozen-clock bug"
    )
    assert callable(Node._constraint_refresh)


def test_the_turn_composer_injects_a_fresh_block():
    """The block must arrive per TURN, not once into the standing message."""
    import time

    from adda._src.nodes.node import Node

    node = _FakeNode(run_start=time.time() - 60.0)
    early = Node._constraint_refresh(node)
    assert early and "Wall-clock" in early[0]["content"]

    node._run_start -= 1800.0
    later = Node._constraint_refresh(node)

    assert later[0]["content"] != early[0]["content"], (
        "two turns half an hour apart rendered byte-identical constraints"
    )


def test_a_broken_snapshot_never_fails_the_turn():
    from adda._src.nodes.node import Node

    class _Exploding:
        @property
        def _run_start(self):
            raise RuntimeError("boom")

    assert Node._constraint_refresh(_Exploding()) == []


def test_the_problem_statement_no_longer_carries_a_baked_snapshot():
    """Regression pin: rendering it into the standing message is what froze
    it. A future edit that re-concatenates it must fail here."""
    import inspect

    from adda._src.runtime import agent_runtime

    src = inspect.getsource(agent_runtime)
    assert "_initial_snapshot.as_text()" not in src
    assert "compute_constraint_snapshot(" not in src
