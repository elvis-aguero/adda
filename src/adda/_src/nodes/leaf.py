"""The behaviour of a node with NO outgoing edges: it answers.

The other of the two behaviours :class:`~.node.Node` dispatches between. A
leaf receives one task, answers it, and returns to whoever sent it — there
is nowhere for it to delegate to, which is the whole of the difference. It
is the behaviour of every non-delegating agent alike (implementer, critic,
literature reviewer); the node's NAME in the graph is what distinguishes
them, never its type.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..runtime.graph_state import AgenticState

from ..infra.delegation_log import DelegationLog  # noqa: F401 (type hint)
from ._constants import budget_band_due, budget_wrapup_message
from .parsing import _classify_response, _to_adapter_messages


class LeafMixin:
    """Single-turn answering behaviour, used when a node has no outgoing edges."""

    def _init_leaf(
        self,
        *,
        study_dir: Any = None,
        workspace_dir: Any = None,
        delegation_log: DelegationLog | None = None,
        name: str = "worker",
        report_sections: tuple[str, ...] | None = None,
        agent_tools: frozenset[str] | None = None,
    ) -> None:
        """Set up this leaf's sandboxed Write and its declared read-only tools."""
        self._name = name
        # Accepted but previously never stored: build_declared_shared_closures
        # (called below) resolves ReadProblemStatement's path through
        # node._study_dir the same way an orchestrating node does — every leaf
        # that declares the tool crashed with AttributeError the moment it
        # was called (the leaf had no such attribute at all).
        self._study_dir = study_dir
        # The agent's declared tools — the single source of truth for which
        # capability closures this leaf worker is granted (read-only ledger/
        # store tools). Kept as a frozenset for membership checks.
        self._agent_tools: frozenset[str] = frozenset(agent_tools or ())
        # This agent's declared report sections (e.g. the critic's
        # Findings/Verdict, not the implementer's Conclusions/Files touched).
        # Used to validate the worker's report against ITS OWN contract instead
        # of the implementer-shaped default — otherwise a correct critic or
        # literature report is wrongly flagged malformed (audit BF-10/O40).
        self._report_sections = report_sections
        self._delegation_log = delegation_log
        self._evals_reported: dict = {}
        self._workspace_dir = Path(workspace_dir) if workspace_dir else None
        self._setup_sandboxed_write()
        self.adapter.closure_tools.update(self._build_eval_closures())
        if delegation_log is not None:
            from .tools.routing import build_recall_history
            self.adapter.closure_tools["RecallHistory"] = build_recall_history(self)
        # Declaration-gated read-only ledger/store tools — the SAME builder the
        # orchestrating nodes use, so a leaf worker (e.g. the critic) gets an
        # identical, working RecallStore/QueryStore/HypothesisList/Get surface
        # whenever it declares them. Resolves the run via the shared
        # Node._resolve_run_dir (delegation-log path).
        from .tools.routing import build_declared_shared_closures
        self.adapter.closure_tools.update(
            build_declared_shared_closures(self, self._agent_tools))

    def _setup_sandboxed_write(self) -> None:
        """Replace native Write with a workspace-sandboxed closure.

        Removes 'Write' from native_tools so the SDK doesn't expose it,
        then installs the same builder an orchestrating node's dispatched
        worker gets (:func:`build_sandboxed_write`), scoped to this leaf's
        whole workspace instead of one delegation's subfolder — a leaf
        reached via real graph routing (see module docstring) has no
        delegation_id of its own to scope tighter than that.

        Bash is kept native but cwd is already set to study_dir by the adapter;
        the prompt further constrains it to the workspace.
        """
        if self._workspace_dir is None:
            return  # no sandboxing if study_dir unknown (e.g. tests)

        # Remove native Write so the SDK doesn't expose an unrestricted version
        if hasattr(self.adapter, "native_tools") and "Write" in self.adapter.native_tools:
            self.adapter.native_tools = [
                t for t in self.adapter.native_tools if t != "Write"
            ]

        from .tools.routing import build_sandboxed_write

        # Bound to a plain name (not inlined into the assignment) so
        # internal/tools/promptmap.py's injected_tool_docs() scanner — which
        # resolves a closure_tools["Write"] = <name> rebind to the function
        # <name> refers to — can still find this tool's docstring after the
        # move into the shared builder.
        Write = build_sandboxed_write(self._workspace_dir)
        self.adapter.closure_tools["Write"] = Write

    def _build_eval_closures(self) -> dict:
        from .tools.routing import build_report_evals

        evals = self._evals_reported
        return {
            "ReportEvals": build_report_evals(
                record=lambda n: evals.__setitem__("count", n)
            )
        }

    def _budget_wrapup_message(self, state: AgenticState) -> str | None:
        """The same escalating wrap-up ladder an orchestrating node's own
        turn gets (nodes/_constants.py), for a leaf worker. Read straight
        from ``state`` — a leaf never runs :meth:`_absorb_state`, so it has
        no ``_budget_seconds``/``_run_start`` of its own, but the state it is
        handed carries the run's budget/start time regardless of which node
        is answering (CLAUDE.md "all nodes are equal").

        A worker cannot call Done(), so the text asks for what it CAN do:
        finish the step in flight, report what it has, and return.
        """
        budget, start = state.get("budget_seconds"), state.get("start_time")
        if budget is None or start is None:
            return None
        import time
        elapsed = time.time() - start
        if not budget_band_due(elapsed, budget, self._budget_bands_fired):
            return None
        return budget_wrapup_message(elapsed, budget, can_call_done=False)

    def _respond(self, state: AgenticState) -> Any:
        """One task, one answer, handed back to whoever delegated it."""
        from langchain_core.messages import AIMessage
        from langgraph.types import Command

        from ..prompts.agent_prompts import build_report_retry_prompt

        self._evals_reported.clear()
        messages = _to_adapter_messages(state["messages"])
        wrapup = self._budget_wrapup_message(state)
        if wrapup is not None:
            messages = [*messages, {"role": "user", "content": wrapup}]
        text = self.adapter.invoke(messages)

        _req_sections = (
            list(self._report_sections) if self._report_sections else None
        )
        diagnosis = _classify_response(text, _req_sections)
        if diagnosis is not None:
            # One retry — the correction prompt is built from THIS agent's own
            # report_sections so it can't command a structure that omits a
            # section the parser requires (e.g. the implementer's Retrospective).
            retry_messages = messages + [
                {"role": "ai", "content": text},
                {
                    "role": "user",
                    "content": (
                        f"{build_report_retry_prompt(_req_sections)}"
                        f"\n\nDiagnosis: {diagnosis}"
                    ),
                },
            ]
            text = self.adapter.invoke(retry_messages)

        ai_msg = AIMessage(content=text)
        evals_delta = self._evals_reported.get("count", 0)
        return_to = state.get("return_to")
        return Command(
            goto=return_to,
            update={
                "messages": [ai_msg],
                "last_report": text,
                "evals_used": state.get("evals_used", 0) + evals_delta,
            },
        )
