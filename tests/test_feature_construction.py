"""A feature is constructed in ONE place, and ownership is never acquired late.

`graph_builder` hands `notes_dir` to the entry node alone — "it owns the run's
hypothesis + milestone ledgers". That decision used to be undone silently:
`_absorb_state`, which runs at the start of every turn, rebuilt the hypothesis
ledger whenever it found one missing, knowing nothing about why the constructor
had left it None.

Three failures came out of the second construction site, and each is pinned
below:

1. Any orchestrating node that is not the entry node acquired a ledger on its
   first turn.
2. Only the hypothesis ledger was re-pointed when the run's notes dir differed
   from the constructor's; the milestone ledger and telemetry kept writing to
   the stale path.
3. The science monitor was built once in the constructor and never rebuilt, so
   a node whose ledger was resurrected ran with the ledger ON and the monitor
   OFF — the exact inverse of a "disable the hypothesis ledger" arm.
"""
from __future__ import annotations

from pathlib import Path

from .test_route_aware_termination import (
    StubAdapter,
    _make_state,
    _minimal_spec,
)


def _node(tmp_path, *, notes_dir=None, delegation_log=None):
    from adda._src.nodes import Node

    return Node(
        StubAdapter(response="unused"),
        name="strategizer", outgoing=["implementer"], spec=_minimal_spec(),
        notes_dir=notes_dir, delegation_log=delegation_log,
    )


def _dlog(tmp_path):
    from adda._src.infra.delegation_log import DelegationLog

    return DelegationLog(tmp_path / "delegation_log.jsonl")


def test_a_node_without_notes_dir_never_acquires_a_ledger(tmp_path):
    """graph_builder gives notes_dir to the entry node alone. A turn must not
    hand one to anybody else."""
    node = _node(tmp_path, notes_dir=None)
    assert node._ledger is None

    run_dir = tmp_path / "study" / "runs" / "T"
    (run_dir / "debug").mkdir(parents=True)
    state = _make_state(study_dir=tmp_path / "study")
    state["run_dir"] = str(run_dir)
    node._absorb_state(state)

    assert node._ledger is None, "ownership was acquired mid-run"
    assert node._milestones is None
    assert node._science_monitor is None


def test_a_non_owner_still_tracks_the_runs_notes_dir(tmp_path):
    """It reads run files through _current_notes_dir (the critic gate does),
    so the path must still update — it just must not confer ownership."""
    node = _node(tmp_path, notes_dir=None)
    run_dir = tmp_path / "study" / "runs" / "T"
    (run_dir / "debug").mkdir(parents=True)
    state = _make_state(study_dir=tmp_path / "study")
    state["run_dir"] = str(run_dir)
    node._absorb_state(state)

    assert node._current_notes_dir == run_dir / "debug" / "strategizer_notes"
    assert node._ledger is None


def test_every_ledger_follows_a_corrected_notes_dir(tmp_path):
    """Not just the hypothesis ledger. The milestone ledger and telemetry used
    to keep writing to the constructor's path."""
    stale = tmp_path / "stale_notes"
    stale.mkdir()
    node = _node(tmp_path, notes_dir=stale, delegation_log=_dlog(tmp_path))

    run_dir = tmp_path / "study" / "runs" / "T"
    (run_dir / "debug").mkdir(parents=True)
    state = _make_state(study_dir=tmp_path / "study")
    state["run_dir"] = str(run_dir)
    node._absorb_state(state)

    live = run_dir / "debug" / "strategizer_notes"
    assert node._ledger is not None
    assert node._ledger._notes_dir == live
    assert node._milestones is not None
    assert Path(node._milestones._path).parent == live
    # telemetry lives one level up, under debug/telemetry/
    assert node._telemetry is not None
    assert Path(node._telemetry._path).parent == live.parent / "telemetry"


def test_the_science_monitor_survives_a_notes_dir_correction(tmp_path):
    """It was built once in the constructor and never rebuilt, so a node whose
    ledger got resurrected ran ledger-ON / monitor-OFF."""
    stale = tmp_path / "stale_notes"
    stale.mkdir()
    node = _node(tmp_path, notes_dir=stale, delegation_log=_dlog(tmp_path))

    run_dir = tmp_path / "study" / "runs" / "T"
    (run_dir / "debug").mkdir(parents=True)
    state = _make_state(study_dir=tmp_path / "study")
    state["run_dir"] = str(run_dir)
    node._absorb_state(state)

    assert node._science_monitor is not None
    assert node._ledger is not None


def test_the_science_monitor_does_not_depend_on_the_hypothesis_ledger(tmp_path):
    """Its live rules read the delegation log and the store. It took a ledger
    argument it stored and never read, and the construction site gated on it —
    so turning the hypothesis ledger off turned drift detection off too."""
    from adda._src.epistemics.science_monitor import ScienceMonitor

    mon = ScienceMonitor(_dlog(tmp_path))

    assert not hasattr(mon, "_ledger")
