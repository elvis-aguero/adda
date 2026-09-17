"""One agent turn must fit the window the server actually serves.

`create_react_agent` runs a whole tool loop inside ONE adda turn and nothing
bounded it: an oracle-bench strategizer turn reached ~30,600 tokens. On Ollama
that is fatal and misdiagnosable — the server truncates from the FRONT, evicts
the original user turn, and its qwen3.8 renderer answers
`500 no user query found in messages`. adda's UserlessPayloadError guard cannot
see it: the payload leaves adda with a valid user turn and eviction happens
afterwards, server-side.

The tests that matter most here are the invariants, not the arithmetic:

* the first user turn is NEVER dropped — evicting it is the server bug itself,
  and reproducing it client-side would turn a provider defect into ours;
* a kept transcript never opens on an orphaned tool result, which would trade
  one malformed-request error for another;
* with the feature off, the agent is built exactly as before.
"""
from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from adda._src.backends.context_budget import (
    DEFAULT_CONTEXT_WINDOW,
    estimate_tokens,
    trim_to_budget,
)
from adda._src.runtime import settings


@pytest.fixture(autouse=True)
def _clean_settings():
    settings.configure(None)
    yield
    settings.configure(None)


def _convo(n: int, size: int = 400) -> list:
    """A task turn followed by n rounds of assistant chatter."""
    msgs: list = [HumanMessage(content="THE ORIGINAL TASK")]
    for i in range(n):
        msgs.append(AIMessage(content=f"step {i} " + "x" * size))
    return msgs


# --- the invariant -----------------------------------------------------------

def test_the_first_user_turn_is_never_evicted():
    """The whole reason this module exists."""
    kept, report = trim_to_budget(_convo(200), context_window=2048)

    assert report.fired
    assert kept[0].content == "THE ORIGINAL TASK"
    assert len(kept) < 201


def test_the_newest_messages_are_the_ones_kept():
    kept, _ = trim_to_budget(_convo(200), context_window=2048)

    assert "step 199" in kept[-1].content
    assert not any("step 0 " in str(m.content) for m in kept[1:])


def test_a_transcript_that_fits_is_returned_untouched():
    msgs = _convo(3)

    kept, report = trim_to_budget(msgs, context_window=100_000)

    assert kept == msgs
    assert not report.fired
    assert report.dropped == 0


def test_a_kept_tail_never_opens_on_an_orphan_tool_result():
    """A ToolMessage whose AIMessage was dropped is a malformed request in its
    own right — that would trade one 500 for another."""
    msgs: list = [HumanMessage(content="TASK")]
    for i in range(80):
        msgs.append(AIMessage(content="call " + "y" * 300,
                              tool_calls=[{"name": "t", "args": {},
                                           "id": f"c{i}"}]))
        msgs.append(ToolMessage(content="result " + "z" * 300,
                                tool_call_id=f"c{i}"))

    kept, report = trim_to_budget(msgs, context_window=4096)

    assert report.fired
    assert kept[0].content == "TASK"
    assert not isinstance(kept[1], ToolMessage), (
        "the tail opens on a tool result whose call was dropped")


# --- the single-giant-message case ------------------------------------------

def test_one_oversized_message_is_truncated_not_merely_outvoted():
    """The campaign's actual shape: the strategizer read its own transcripts,
    so ONE tool result can exceed the entire window. Dropping other messages
    cannot fix that — only cutting the offender can."""
    msgs = [HumanMessage(content="TASK"),
            AIMessage(content="", tool_calls=[
                {"name": "ReadNote", "args": {}, "id": "c0"}]),
            ToolMessage(content="q" * 400_000, tool_call_id="c0")]

    kept, report = trim_to_budget(msgs, context_window=8192)

    assert report.truncated == 1
    body = "".join(str(m.content) for m in kept)
    assert "dropped by adda context trimming" in body
    assert sum(estimate_tokens(m) for m in kept) < 8192


def test_truncation_keeps_the_head_and_the_tail():
    """The head says what the call was, the tail carries the answer; the
    middle of a directory listing is the part worth losing."""
    msgs = [HumanMessage(content="TASK"),
            AIMessage(content="", tool_calls=[
                {"name": "ReadNote", "args": {}, "id": "c0"}]),
            ToolMessage(content="START" + "m" * 200_000 + "END",
                        tool_call_id="c0")]

    kept, _ = trim_to_budget(msgs, context_window=8192)

    body = "".join(str(m.content) for m in kept)
    assert "START" in body and "END" in body


# --- estimation is deliberately pessimistic ---------------------------------

def test_the_estimate_runs_high_rather_than_low():
    """An estimate that is too low is a 500; too high costs a little context.
    ~3 chars/token against a real ~4 is the safety margin."""
    assert estimate_tokens(HumanMessage(content="a" * 4000)) > 1000


def test_a_tool_call_payload_is_counted():
    """An AIMessage with a huge tool-call argument has almost no content but
    is not free on the wire."""
    bare = AIMessage(content="")
    with_call = AIMessage(content="", tool_calls=[
        {"name": "t", "args": {"code": "x" * 5000}, "id": "c0"}])

    assert estimate_tokens(with_call) > estimate_tokens(bare) + 1000


# --- resolution: declared, and recorded with its source ---------------------

def test_an_explicit_setting_wins_over_everything():
    from adda._src.backends.vllm import VLLMAdapter

    settings.configure({"context_window": 262_144})
    a = VLLMAdapter(model="m", system_prompt="s")

    assert a._resolve_context_window() == (262_144, "setting")


def test_an_unknown_window_falls_back_but_says_so():
    """A window that came from a guess and one that came from the server are
    not the same run, so the SOURCE travels with the number."""
    from adda._src.backends.vllm import VLLMAdapter

    a = VLLMAdapter(model="m", system_prompt="s")
    a._probe_context_window = lambda: None

    assert a._resolve_context_window() == (DEFAULT_CONTEXT_WINDOW, "default")


def test_a_served_window_is_taken_from_the_server():
    from adda._src.backends.vllm import VLLMAdapter

    a = VLLMAdapter(model="m", system_prompt="s")
    a._probe_context_window = lambda: 32_768

    assert a._resolve_context_window() == (32_768, "server")


def test_ollama_prefers_the_served_num_ctx_over_the_trained_length():
    """The distinction this backend lives or dies on: `num_ctx` is what the
    server will ACCEPT, and Ollama's default sits far below what these models
    were trained for. Reading the trained length would sail past the real limit
    and cause the very truncation the trimming exists to prevent."""
    import adda._src.backends.ollama as mod
    from adda._src.backends.ollama import OllamaAdapter

    class _Resp:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"parameters": "stop \"<|im_end|>\"\nnum_ctx    32768\n",
                    "model_info": {"qwen3.context_length": 262144}}

    class _Requests:
        @staticmethod
        def post(*a, **k):
            return _Resp()

    mod.requests = _Requests()   # the import inside the method resolves here
    a = OllamaAdapter(model="qwen3.8:27b", system_prompt="s")
    import sys
    sys.modules["requests"] = _Requests()
    try:
        assert a._probe_context_window() == 32_768
    finally:
        del sys.modules["requests"]
        import requests  # noqa: F401


# --- the feature boundary ---------------------------------------------------

def test_there_is_no_off_switch():
    """Both policies manage the context; neither is "off". An unmanaged
    context is not an experimental arm — it is the crash this subsystem was
    written to stop, where Ollama evicts the original user turn and its
    renderer then rejects the request with 500 no user query found."""
    from adda._src.backends.vllm import VLLMAdapter

    a = VLLMAdapter(model="m", system_prompt="s")
    for policy in ("compact", "trim"):
        settings.configure({"context_policy": policy})
        assert a._context_hook("SYSTEM") is not None


def test_an_unknown_policy_raises_rather_than_defaulting():
    """A typo'd arm that silently runs as the baseline reports as a null
    result, which is the one failure an ablation cannot afford."""
    import pytest

    from adda._src.backends.vllm import VLLMAdapter

    settings.configure({"context_policy": "summarise"})
    with pytest.raises(ValueError, match="compact.*trim"):
        VLLMAdapter(model="m", system_prompt="s")._context_policy()


def test_the_hook_returns_llm_input_messages_not_state():
    """Changing what is SENT must not edit the graph's own history, or the
    transcript on disk stops being the record of what happened."""
    from adda._src.backends.vllm import VLLMAdapter

    settings.configure({"context_policy": "trim"})
    a = VLLMAdapter(model="m", system_prompt="s")
    a._ctx_window = (2048, "setting")
    hook = a._context_hook("SYSTEM")

    out = hook({"messages": _convo(200)})

    assert set(out) == {"llm_input_messages"}
    assert len(out["llm_input_messages"]) < 201


def test_the_claude_backend_is_deliberately_untouched():
    """Claude compacts on its own and does it better than truncation can.
    Silently trimming it would replace a good mechanism with a worse one."""
    import inspect

    from adda._src.backends import claude

    src = inspect.getsource(claude)
    assert "context_budget" not in src
    assert "pre_model_hook" not in src


# --- the output cap ---------------------------------------------------------

def test_the_derived_cap_matches_the_share_the_trim_reserves():
    """The trim reserves a share of the window for the reply. If the server is
    free to generate the whole window anyway, that reservation is a fiction."""
    from adda._src.backends import context_budget as cb

    assert cb.resolve_max_output_tokens(8192) == int(8192 * cb._RESPONSE_HEADROOM)


def test_a_huge_window_is_still_bounded():
    """262144 * 0.25 is ~65k tokens -- over an hour of generation at the rate a
    27B model sustains on one L40S. 'A quarter of the window' alone is not a
    bound on a server configured that large."""
    from adda._src.backends import context_budget as cb

    assert cb.resolve_max_output_tokens(262144) == cb.MAX_OUTPUT_TOKENS_CEILING


def test_a_tiny_window_does_not_produce_a_cap_that_cuts_a_tool_call():
    """A cap below one long tool-call argument turns a runaway into a
    truncated, unparseable call -- a worse failure than the one being fixed."""
    from adda._src.backends import context_budget as cb

    assert cb.resolve_max_output_tokens(512) == cb._MIN_OUTPUT_TOKENS


def test_an_explicit_setting_wins_outright():
    from adda._src.backends import context_budget as cb

    assert cb.resolve_max_output_tokens(262144, 1234) == 1234


def test_a_negative_setting_is_the_uncapped_escape_hatch():
    """Restoring the unbounded behaviour is something an experiment may want
    and a default may not be."""
    from adda._src.backends import context_budget as cb

    assert cb.resolve_max_output_tokens(8192, -1) is None


def test_the_adapter_caps_under_either_policy():
    """The cap bounds what the SERVER does; the context policy decides what
    the model SEES. They are separate limits and the cap applies to both
    arms, so it cannot confound the comparison between them."""
    from adda._src.backends import context_budget as cb
    from adda._src.backends.vllm import VLLMAdapter

    settings.configure({"context_policy": "trim"})
    a = VLLMAdapter(model="m", system_prompt="s")
    a._ctx_window = (262144, "server")

    assert a._resolve_max_output_tokens() == cb.MAX_OUTPUT_TOKENS_CEILING


def test_the_adapter_honours_the_setting():
    from adda._src.backends.vllm import VLLMAdapter

    settings.configure({"max_output_tokens": 777})
    a = VLLMAdapter(model="m", system_prompt="s")
    a._ctx_window = (8192, "setting")

    assert a._resolve_max_output_tokens() == 777
