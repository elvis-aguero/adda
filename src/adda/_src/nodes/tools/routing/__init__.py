"""The tool closures an orchestrating node is handed (Delegate/Parallel/GetStatus/Done/FollowUp/
WriteNote/ReadNote/WriteDeliverable/RecallStore/QueryStore/AskForFeedback +
hypothesis tools). Built per-node; the node is passed in so closures reach its
state. Built by an orchestrating node via Node._build_routing_closures.

This package assembles the final tool dict from the family-specific builders
in its sibling modules — delegation.py, notes.py, notebook.py, feedback.py,
store.py — in the exact same order and under the exact same declaration gates
as the original single-file implementation, so tool_catalog.py's rendered
``<tools>`` prompt section is unaffected by the split.
"""
from __future__ import annotations

from .delegation import (
    build_delegation_closures,
    build_recall_history,
    build_report_evals,
    build_sandboxed_write,
    resolve_target,
)
from .feedback import (
    _EXIT_INTERVIEW,
    _FAILED_RETROSPECTIVE,
    build_feedback_closures,
)
from .ledger import build_ledger_closures
from .notebook import (
    _strip_leading_md_header,
    build_notebook_closures,
)
from .notes import build_notes_closures
from .store import _select_best_index, build_declared_shared_closures

__all__ = [
    "build_declared_shared_closures",
    "build_routing_tools",
    # Re-exported for tests and internal callers that reached these directly
    # off the old flat routing.py module (kept so nothing outside this
    # package needs to know which family file now defines them).
    "_EXIT_INTERVIEW",
    "_FAILED_RETROSPECTIVE",
    "resolve_target",
    "_select_best_index",
    "_strip_leading_md_header",
    # One implementation per tool, not one per call site — these are the
    # shared builders both nodes/node.py (every node's own capabilities) and
    # nodes/tools/routing/delegation.py (a dispatched worker's) call.
    "build_recall_history",
    "build_report_evals",
    "build_sandboxed_write",
]


def build_routing_tools(node) -> dict:
    _dele = build_delegation_closures(node)

    # Topology-injected tools: granted to every orchestrating node because the
    # ability to delegate/recall derives from having outgoing edges — the only
    # structural fact about a node (see nodes/node.py). Capability tools (RecallStore/QueryStore/
    # Hypothesis*/Milestone*/...) are declaration-gated below, NOT here.
    closures: dict = {
        "Delegate": _dele["Delegate"],
        "Wait": _dele["Wait"],
        "Reply": _dele["Reply"],
        "FollowUp": _dele["FollowUp"],
    }

    if node._delegation_log is not None:
        closures["RecallHistory"] = _dele["RecallHistory"]

    # Agent-declared closure tools: inject only what the subclass opted in to.
    # Done / WriteNote / ReadNote are declared in StrategizerAgent.tools;
    # an ImplementerAgent or DebuggerAgent that gains outgoing edges does not
    # declare them and therefore does not receive them.
    _agent_tools: frozenset = frozenset()
    if node._spec is not None:
        _ag = node._spec.nodes.get(node._name)
        if _ag is not None:
            _agent_tools = _ag.tools
    # A disabled feature takes its tools with it. Leaving them registered does
    # not produce an agent without the feature -- it produces an agent that
    # keeps calling a tool which returns "ERROR: ... not available in this
    # run.", and every such return is counted as an ERROR_RETURN diagnostic.
    # This generalises the hand-rolled pipeline_deliverable strip (BACKLOG
    # #30), which was the only feature that did it: the strategizer otherwise
    # saw a toolset saturated with pipeline.ipynb capability regardless of what
    # the study's own PROBLEM_STATEMENT.md said, and used it. Done is never
    # owned by a feature -- a run must always be able to close.
    from ....runtime import features as _features
    _agent_tools = _agent_tools - _features.disabled_tool_names()

    _fb = build_feedback_closures(node)
    _nb = build_notebook_closures(node)
    _notes = build_notes_closures(node)

    if "Done" in _agent_tools:
        closures["Done"] = _fb["Done"]
    if "EditPipelineCell" in _agent_tools:
        closures["EditPipelineCell"] = _nb["EditPipelineCell"]
    if "DeletePipelineCell" in _agent_tools:
        closures["DeletePipelineCell"] = _nb["DeletePipelineCell"]
    if "ShowNotebook" in _agent_tools:
        closures["ShowNotebook"] = _nb["ShowNotebook"]
    if "RunScratch" in _agent_tools:
        closures["RunScratch"] = _nb["RunScratch"]
    if "LedgerBreakdown" in _agent_tools:
        closures["LedgerBreakdown"] = _nb["LedgerBreakdown"]
    if "RunPipelineCell" in _agent_tools:
        closures["RunPipelineCell"] = _nb["RunPipelineCell"]
    if "WriteNote" in _agent_tools:
        closures["WriteNote"] = _notes["WriteNote"]
    if "ReadNote" in _agent_tools:
        closures["ReadNote"] = _notes["ReadNote"]
    if "WriteDeliverable" in _agent_tools:
        closures["WriteDeliverable"] = _nb["WriteDeliverable"]
    if "CheckDeliverable" in _agent_tools:
        closures["CheckDeliverable"] = _nb["CheckDeliverable"]
    if "AddPipelineCell" in _agent_tools:
        closures["AddPipelineCell"] = _nb["AddPipelineCell"]
    if "AddPipelineMarkdownCell" in _agent_tools:
        closures["AddPipelineMarkdownCell"] = _nb["AddPipelineMarkdownCell"]
    if "Confer" in _agent_tools:
        closures["Confer"] = _dele["Confer"]
    # GetStatus / CancelDelegation are now OPT-IN (plug-and-play), not always-on.
    # Their defs above are intact; they are simply not granted unless an agent
    # lists them in its `tools`. PRODUCTION agents do not, so:
    #   - GetStatus is dropped: completions are PUSHED via _notifications each
    #     turn + Confer supersedes polling.
    #   - CancelDelegation is dropped (drop-but-don't-delete) pending the
    #     cooperative-stop decision; restore by adding the name to an agent's
    #     `tools` (one line), exactly like the debugger agent is plug-and-play.
    if "GetStatus" in _agent_tools:
        closures["GetStatus"] = _dele["GetStatus"]
    if "CancelDelegation" in _agent_tools:
        closures["CancelDelegation"] = _dele["CancelDelegation"]
    # ConsultHandbook is injected universally at adapter construction
    # (agent_runtime._make_adapter) — no per-node duplication here.

    # Capability closures are DECLARATION-GATED (single source of truth = the
    # Agent's `tools`), exactly like the notebook/Done/notes tools above.
    # Every ledger tool MUTATES — hypothesis (epistemics) or milestone
    # (process policy) — so they go only to agents that declare them; a
    # stateless leaf must never mutate a shared ledger. The read-only
    # HypothesisList/HypothesisGet come from the shared builder below instead.
    for _t, _fn in build_ledger_closures(node).items():
        if _t in _agent_tools:
            closures[_t] = _fn
    # Read-only ledger/store tools — declaration-gated and shared verbatim
    # across every node (Node._init_capabilities calls the same builder), so
    # the exposure surface is identical regardless of a node's outgoing edges.
    closures.update(build_declared_shared_closures(node, _agent_tools))

    # AskForFeedback is only injected when a critic node is
    # connected AND this is the entry node (only the entry node
    # gates Done).
    if "AskForFeedback" in _fb:
        closures["AskForFeedback"] = _fb["AskForFeedback"]

    # Wrap every closure so ERROR returns and exceptions are counted.
    _node_name = node._name
    return {k: node._wrap_closure(v, _node_name) for k, v in closures.items()}
