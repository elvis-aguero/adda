"""Summarising compaction: the invariants, and the failure it must not cause."""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from adda._src.backends import context_compaction as cc
from adda._src.runtime import settings


def _convo(n: int, size: int = 400) -> list:
    msgs: list = [HumanMessage(content="THE ORIGINAL TASK: minimise Branin.")]
    for i in range(n):
        msgs.append(AIMessage(content=f"step {i} " + "x" * size))
    return msgs


def _summarizer(text: str) -> str:
    return "D001 found f=0.42 at x=(1.0, 2.0); D002 failed on a bad domain."


# --- what it must never do --------------------------------------------------

def test_the_first_user_turn_survives_compaction():
    """Evicting it is the server bug this whole subsystem exists to avoid;
    reproducing it here would turn a provider's fault into ours."""
    msgs = _convo(80)
    kept, report = cc.compact_to_budget(
        msgs, context_window=4096, reserve_tokens=0,
        summarize=_summarizer, cache={})

    assert report.fired
    assert kept[0] is msgs[0]
    assert "THE ORIGINAL TASK" in kept[0].content


def test_the_tail_never_opens_on_an_orphaned_tool_result():
    """A ToolMessage whose AIMessage was summarised away has no call to
    answer, which is a malformed request in its own right — one provider
    error traded for another."""
    msgs = _convo(60)
    msgs.append(AIMessage(content="calling", tool_calls=[
        {"name": "T", "args": {}, "id": "1"}]))
    msgs.append(ToolMessage(content="y" * 4000, tool_call_id="1"))

    kept, _ = cc.compact_to_budget(
        msgs, context_window=3000, reserve_tokens=0,
        summarize=_summarizer, cache={})

    body = [m for m in kept if m.__class__.__name__ != "SystemMessage"]
    assert not (len(body) > 1 and body[1].__class__.__name__ == "ToolMessage")


def test_a_failed_summary_falls_back_to_trimming():
    """A context policy that can fail the turn is worse than the truncation
    it replaced."""
    def _boom(_text):
        raise RuntimeError("the server said no")

    msgs = _convo(80)
    kept, report = cc.compact_to_budget(
        msgs, context_window=4096, reserve_tokens=0,
        summarize=_boom, cache={})

    assert report.fired
    assert kept[0] is msgs[0]
    assert all(m.__class__.__name__ != "SystemMessage" for m in kept)


def test_an_empty_summary_is_treated_as_a_failure():
    """A model that answers with whitespace has not summarised anything, and
    substituting it would silently delete the span."""
    msgs = _convo(80)
    kept, _ = cc.compact_to_budget(
        msgs, context_window=4096, reserve_tokens=0,
        summarize=lambda _t: "   \n ", cache={})

    assert all(m.__class__.__name__ != "SystemMessage" for m in kept)


# --- what it must do --------------------------------------------------------

def test_a_conversation_that_already_fits_is_untouched():
    """No generation, no summary, nothing removed."""
    msgs = _convo(3, size=50)
    calls = []
    kept, report = cc.compact_to_budget(
        msgs, context_window=100_000, reserve_tokens=0,
        summarize=lambda t: calls.append(t) or "x", cache={})

    assert not report.fired
    assert kept == msgs
    assert not calls


def test_the_summary_is_labelled_as_a_summary():
    """Neither the agent nor a person reading the transcript may mistake it
    for something that was actually said."""
    kept, _ = cc.compact_to_budget(
        _convo(80), context_window=4096, reserve_tokens=0,
        summarize=_summarizer, cache={})

    note = next(m for m in kept if m.__class__.__name__ == "SystemMessage")
    assert "SUMMARY, not a transcript" in note.content
    assert "D001 found f=0.42" in note.content


def test_compaction_actually_shrinks_the_payload():
    msgs = _convo(80)
    kept, report = cc.compact_to_budget(
        msgs, context_window=4096, reserve_tokens=0,
        summarize=_summarizer, cache={})

    assert report.after < report.before
    assert len(kept) < len(msgs)


def test_an_unchanged_span_is_summarised_once():
    """The hook runs on every model call inside a turn and usually wants the
    SAME span it just compacted. Without the memo, "one generation per
    compaction" would be an aspiration."""
    calls = []
    cache: dict = {}
    msgs = _convo(80)

    def _count(text):
        calls.append(text)
        return _summarizer(text)

    for _ in range(4):
        cc.compact_to_budget(msgs, context_window=4096, reserve_tokens=0,
                             summarize=_count, cache=cache)

    assert len(calls) == 1


def test_a_changed_span_is_summarised_again():
    calls: list = []
    cache: dict = {}

    def _count(text):
        calls.append(text)
        return _summarizer(text)

    cc.compact_to_budget(_convo(80), context_window=4096, reserve_tokens=0,
                         summarize=_count, cache=cache)
    grown = _convo(80) + [AIMessage(content="something new " + "z" * 4000)]
    cc.compact_to_budget(grown, context_window=4096, reserve_tokens=0,
                         summarize=_count, cache=cache)

    assert len(calls) == 2


def test_the_instruction_asks_for_numbers_and_forbids_invention():
    """An adda run's conclusions have to trace to ledgered numbers, so a
    summary that keeps the narrative and drops the figures reads as if the
    evidence is still there."""
    assert "numerical result" in cc.SUMMARY_INSTRUCTION
    assert "delegation id" in cc.SUMMARY_INSTRUCTION
    assert "do not supply one" in cc.SUMMARY_INSTRUCTION


# --- the policy -------------------------------------------------------------

def test_compaction_is_the_default_policy():
    from adda._src.backends.vllm import VLLMAdapter

    settings.configure({})
    assert VLLMAdapter(model="m", system_prompt="s")._context_policy() == "compact"


def test_the_summariser_does_not_re_enter_the_agent():
    """A pre_model_hook that calls back into the tool loop is a recursion,
    not a hook — and a summary is not allowed to take actions."""
    import inspect

    from adda._src.backends.openai_compatible import OpenAICompatibleAdapter

    src = inspect.getsource(OpenAICompatibleAdapter._summarize)
    assert "create_react_agent" not in src
    assert "self.invoke" not in src
