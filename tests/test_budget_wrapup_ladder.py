"""Tests for the shared time-budget wrap-up ladder (nodes/_constants.py:
budget_band_due / budget_wrapup_message).

CLAUDE.md "all nodes are equal": a dispatched worker (WorkerSession, in
nodes/tools/routing/delegation.py) must get the same escalating past-budget
signal an orchestrating node's own turn gets, worded for what IT can
actually do (no Done()). Each 10% band (100, 110, 120, …) fires once, not
every turn, and the 1.5x band agrees with the Delegate() refusal introduced
alongside it.

A standalone leaf node (no outgoing edges, driven directly through
Node.__call__ rather than dispatched) used to get this same signal through
its own single-turn `_respond` path — deleted along with `_respond` (STEP 3
of the leaf/orchestration merge): every node now runs the same
delegate-or-close loop, whose own wrap-up ladder is `_budget_warnings`
below, worded with `can_call_done=True` since that loop is exactly what
lets a node call Done(). The real "worker, no Done()" wording is exercised
below only via the actual dispatched-worker mechanism
(test_budget_broadcast_worker_message_never_mentions_done).
"""
from __future__ import annotations

import time

from adda._src.backends.base import Agent, Edge, Graph
from adda._src.nodes import Node
from adda._src.nodes._constants import budget_band_due, budget_wrapup_message
from adda._src.runtime import settings


def teardown_function(_fn) -> None:
    settings.configure(None)


# ---------------------------------------------------------------------------
# Pure ladder helpers
# ---------------------------------------------------------------------------


def test_band_not_due_below_budget():
    fired: set[int] = set()
    assert budget_band_due(50.0, 100.0, fired) is False
    assert fired == set()


def test_band_fires_once_per_new_band():
    fired: set[int] = set()
    assert budget_band_due(100.0, 100.0, fired) is True   # 100% band
    assert budget_band_due(105.0, 100.0, fired) is False  # same band, no re-fire
    assert budget_band_due(115.0, 100.0, fired) is True   # 110% band, new
    assert fired == {100, 110}


def test_message_mentions_delegate_refusal_only_past_cutoff_and_only_for_strategizer():
    # Below cutoff (default 1.5x): no refusal mention.
    below = budget_wrapup_message(140.0, 100.0, can_call_done=True)
    assert "refused" not in below

    # At/past cutoff: strategizer message mentions it...
    past = budget_wrapup_message(151.0, 100.0, can_call_done=True)
    assert "refused" in past
    assert "1.5x" in past

    # ...but a worker's message (can_call_done=False) never does, and never
    # mentions Done() — a worker has no such tool.
    worker_past = budget_wrapup_message(151.0, 100.0, can_call_done=False)
    assert "refused" not in worker_past
    assert "Done()" not in worker_past
    assert "Done()" in past


def test_disabled_cutoff_knob_drops_refusal_mention():
    settings.configure({"delegate_cutoff_multiple": 0})
    msg = budget_wrapup_message(1000.0, 100.0, can_call_done=True)
    assert "refused" not in msg


# ---------------------------------------------------------------------------
# Orchestrating node: bands fire once per turn's worth of elapsed time
# ---------------------------------------------------------------------------


def _strategizer_node():
    class A(Agent):
        role = "strategizer"
        tools = frozenset({"Done", "Delegate"})
        description = "strategizer"

    class B(Agent):
        role = "implementer"
        description = "implementer"

    spec = Graph(
        nodes={"strategizer": A(), "implementer": B()},
        edges=(Edge("strategizer", "implementer"),),
        entry="strategizer",
    )
    return Node(
        _StubAdapter(), name="strategizer", outgoing=["implementer"], spec=spec,
    )


class _StubAdapter:
    def __init__(self) -> None:
        self.closure_tools: dict = {}
        self.last_usage: dict = {}
        self.model = "m"

    def invoke(self, messages):
        return ""


def test_orchestrating_node_band_fires_once_not_every_turn():
    n = _strategizer_node()
    n._budget_seconds = 100.0
    n._run_start = time.time() - 105.0  # 105% -> band 100

    w1 = n._budget_warnings({"eval_budget": None, "evals_used": 0})
    assert any("Time budget at" in x["content"] for x in w1)

    # Same band, called again immediately (elapsed barely changes) -> no
    # repeat.
    w2 = n._budget_warnings({"eval_budget": None, "evals_used": 0})
    assert not any("Time budget at" in x["content"] for x in w2)


def test_orchestrating_node_band_escalates_at_1_5x():
    n = _strategizer_node()
    n._budget_seconds = 100.0
    n._run_start = time.time() - 151.0  # 151% -> band 150, past 1.5x cutoff

    w = n._budget_warnings({"eval_budget": None, "evals_used": 0})
    msgs = [x["content"] for x in w if "Time budget at" in x["content"]]
    assert msgs, w
    assert "refused" in msgs[0]


# ---------------------------------------------------------------------------
# A standalone leaf node's own wrap-up signal used to be tested here, driven
# through the now-deleted `_respond` (test_leaf_worker_gets_wrapup_message_
# past_budget, test_leaf_worker_band_fires_once, test_leaf_worker_no_budget_
# configured_no_crash — the last of these lived further down this file).
# Every node now runs the unified `_orchestrate` loop (STEP 3 of the
# leaf/orchestration merge), whose own budget ladder is exactly
# test_orchestrating_node_band_fires_once_not_every_turn /
# test_orchestrating_node_band_escalates_at_1_5x above — there is no
# separate "leaf's own turn" signal left to test. The real worker-facing
# wording (no Done() mention) is covered below via the actual
# dispatched-worker mechanism, delegation.py's own broadcast.
# ---------------------------------------------------------------------------
# delegation.py's own worker-broadcast: strategizer text vs worker text
# ---------------------------------------------------------------------------


def test_budget_broadcast_worker_message_never_mentions_done():
    """The strategizer's own status text (about the polled delegation) may
    say 'call Done()' — this is exactly what the strategizer polling
    GetStatus can do. The OTHER active delegations queued behind it are
    workers with no Done() tool, so their queued message must not say it."""
    from adda._src.nodes.tools.routing.delegation import DelegationTools

    n = _strategizer_node()
    n._budget_seconds = 100.0
    n._run_start = time.time() - 151.0  # 151% -> band 150, past 1.5x cutoff
    with n._registry_lock:
        n._registry["D001"] = {"status": "Working"}
        n._registry["D002"] = {"status": "Working"}

    tools = DelegationTools(n)
    strategizer_text = tools._budget_broadcast("D001")
    assert strategizer_text
    assert "Done()" in strategizer_text[0]

    worker_text = n._pending_worker_msgs["D002"]
    assert worker_text
    assert "Done()" not in worker_text[0]
    assert "Finish the step you are on" in worker_text[0]
