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
    cancelled or otherwise disturbed, and Wait/Done/deliverable
    tools stay open so the run can still close. DISABLED when <= 0 (knob:
    delegate_cutoff_multiple, default 1.5)."""
    return get_float("delegate_cutoff_multiple", 1.5)


def delegate_cutoff_enabled() -> bool:
    """True when the new-delegation time cutoff is active (multiple > 0)."""
    return delegate_cutoff_multiple() > 0


# ── Escalating wrap-up ladder — shared by EVERY node, not just orchestrating
# ones (CLAUDE.md "all nodes are equal": a worker's time-budget signal must
# not depend on its position in the graph). One node crosses 10%-of-budget
# bands at 100, 110, 120, …; ``budget_band_due`` marks the crossing (once)
# and ``budget_wrapup_message`` renders the text for it. Kept here, not on
# a mixin, so orchestration.py, leaf.py AND delegation.py's worker-broadcast
# can all call the same implementation without an import cycle.


def budget_band_due(elapsed: float, budget: float, fired: set[int]) -> bool:
    """True the first time ``elapsed``/``budget`` crosses a NEW 10% band at
    or past 100% (100, 110, 120, …); marks it fired in ``fired`` (mutated in
    place — pass the caller's own per-node tracking set). False, with no
    mutation, below 100% or on a band already fired."""
    if budget <= 0:
        return False
    pct100 = (elapsed / budget) * 100
    if pct100 < 100:
        return False
    band = int(pct100 // 10) * 10
    if band in fired:
        return False
    fired.add(band)
    return True


def budget_wrapup_message(
    elapsed: float, budget: float, *, can_call_done: bool
) -> str:
    """The wrap-up text for a node past its time budget, at whatever band it
    just crossed — carries the actual percentage so each firing reads as a
    new, escalating signal rather than a repeated one.

    The instructed action must be one the node can actually perform: a
    strategizer (``can_call_done=True``) is told to wrap up and call Done();
    a worker cannot call Done(), so it is told to finish the step it is on,
    report what it has, and return instead. The delegate-cutoff mention is
    strategizer-only (workers never call Delegate) and only appears once it
    is actually true, so it reads as informative rather than a standing
    threat.
    """
    pct = round(100 * elapsed / budget)
    action = (
        "Wrap up and call Done() soon" if can_call_done
        else "Finish the step you are on, report what you have, and return"
    )
    cutoff_txt = ""
    if can_call_done and delegate_cutoff_enabled():
        _cut = delegate_cutoff_multiple()
        if elapsed > budget * _cut:
            cutoff_txt = (
                f" New delegations are now refused (past {_cut:g}x budget)."
            )
    return (
        f"Time budget at {pct}% ({elapsed:.0f}s / {budget:.0f}s). "
        f"{action}.{cutoff_txt} Do not cancel a delegation/step that is "
        "still progressing to save time — its ledgered evals persist "
        "regardless, so cancelling only throws away its report."
    )
