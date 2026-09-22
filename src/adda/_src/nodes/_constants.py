"""Shared run-knob accessors for the nodes package — kept here (not in
strategizer.py) so strategizer.py, lifecycle.py and routing.py can import them
without an import cycle.

Read at CALL time (not import) so they reflect config.yaml, which AgenticRun
installs after these modules import. config.yaml's runtime block is the source
of truth; F3DASM_RUN_BACKSTOP_MULTIPLE overrides."""
from ..runtime.settings import get_float


def run_backstop_multiple() -> float:
    """Run-level cost backstop multiple: a run halts once it exceeds this ×
    the (soft) time budget, bounding runaway cost. Wall-clock is a poor cost
    proxy when one oracle eval can take days, so the cap is configurable and
    DISABLED when <= 0 (knob: run_backstop_multiple, default 2.0)."""
    return get_float("run_backstop_multiple", 2.0)


def backstop_enabled() -> bool:
    """True when the run-level time backstop is active (multiple > 0)."""
    return run_backstop_multiple() > 0


def delegate_cutoff_multiple() -> float:
    """Multiple of the (soft) time budget past which NEW delegations are
    refused. Fits one rung below :func:`run_backstop_multiple`: the 1.0x soft
    warning already asks the agent to stop starting new delegations and is
    routinely ignored, so this enforces that request instead of merely asking
    for it. Only NEW delegations are affected — an in-flight one is never
    cancelled or otherwise disturbed, and Wait/GetStatus/Done/deliverable
    tools stay open so the run can still close. DISABLED when <= 0 (knob:
    delegate_cutoff_multiple, default 1.5)."""
    return get_float("delegate_cutoff_multiple", 1.5)


def delegate_cutoff_enabled() -> bool:
    """True when the new-delegation time cutoff is active (multiple > 0)."""
    return delegate_cutoff_multiple() > 0
