"""Unit tests for the OpenAI-compatible backends (OpenRouter, vLLM).

Fully mocked — no API keys, no network. They verify the per-backend endpoint
and auth conventions (explicit arg > env > class default) and that the shared
invoke/usage machinery works through the subclass. Cross-backend interface
parity is enforced separately in test_backend_parity.py.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from adda._src.backends.openrouter import OpenRouterAdapter
from adda._src.backends.vllm import VLLMAdapter

# --------------------------------------------------------------------------
# Endpoint + auth resolution: explicit > env > class default
# --------------------------------------------------------------------------

def test_openrouter_defaults(monkeypatch):
    monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    a = OpenRouterAdapter(model="anthropic/claude-3.5-sonnet", system_prompt="s")
    assert a._base_url == "https://openrouter.ai/api/v1"
    assert a._api_key is None  # no key baked in — must be supplied


def test_openrouter_reads_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-secret")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://proxy.example/v1")
    a = OpenRouterAdapter(model="m", system_prompt="s")
    assert a._base_url == "https://proxy.example/v1"
    assert a._api_key == "or-secret"


def test_vllm_defaults(monkeypatch):
    monkeypatch.delenv("VLLM_BASE_URL", raising=False)
    monkeypatch.delenv("VLLM_API_KEY", raising=False)
    a = VLLMAdapter(model="meta-llama/Llama-3.1-8B-Instruct", system_prompt="s")
    assert a._base_url == "http://localhost:8000/v1"
    assert a._api_key == "EMPTY"  # vLLM usually needs no auth


def test_vllm_reads_env(monkeypatch):
    monkeypatch.setenv("VLLM_BASE_URL", "http://gpu-box:8001/v1")
    monkeypatch.setenv("VLLM_API_KEY", "served-key")
    a = VLLMAdapter(model="m", system_prompt="s")
    assert a._base_url == "http://gpu-box:8001/v1"
    assert a._api_key == "served-key"


def test_explicit_args_beat_env_and_default(monkeypatch):
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://env/v1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")
    a = OpenRouterAdapter(
        model="m", system_prompt="s",
        base_url="https://explicit/v1", api_key="explicit-key")
    assert a._base_url == "https://explicit/v1"
    assert a._api_key == "explicit-key"


# --------------------------------------------------------------------------
# Wiring: _build_agent points ChatOpenAI at the resolved endpoint + key
# --------------------------------------------------------------------------

def test_build_agent_passes_endpoint_and_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-secret")
    a = OpenRouterAdapter(model="anthropic/claude-3.5-sonnet", system_prompt="s")
    with patch("langchain_openai.ChatOpenAI") as MockLLM, \
            patch("langgraph.prebuilt.create_react_agent") as mock_cra:
        a._build_agent()
        MockLLM.assert_called_once()
        kw = MockLLM.call_args.kwargs
        assert kw["model"] == "anthropic/claude-3.5-sonnet"
        assert kw["base_url"] == "https://openrouter.ai/api/v1"
        assert kw["api_key"] == "or-secret"
        mock_cra.assert_called_once()


# --------------------------------------------------------------------------
# Shared machinery works through the subclass (mock the agent — no network)
# --------------------------------------------------------------------------

def test_invoke_returns_content_and_populates_usage():
    from langchain_core.messages import AIMessage

    msg = AIMessage(content="the answer")
    msg.usage_metadata = {"input_tokens": 11, "output_tokens": 7}
    fake_agent = MagicMock()
    fake_agent.invoke.return_value = {"messages": [msg]}

    a = VLLMAdapter(model="m", system_prompt="s")
    a._agent = fake_agent  # inject — no real server call
    out = a.invoke([{"role": "user", "content": "go"}])

    assert out == "the answer"
    assert a.last_usage["input_tokens"] == 11
    assert a.last_usage["output_tokens"] == 7
    assert a.last_usage["total_cost_usd"] is None


def test_copy_returns_self():
    a = VLLMAdapter(model="m", system_prompt="s")
    assert a.copy() is a


def test_select_native_tools_excludes_closures():
    tools = ["Bash", "Read", "Done", "FollowUp", "WriteNote", "Write"]
    native = OpenRouterAdapter.select_native_tools(tools)
    assert native == ["Bash", "Read", "Write"]  # closures dropped


# ---------------------------------------------------------------------------
# A request with no user turn is refused here, not by the provider
#
# Ollama answers a user-less payload with an opaque 500 ("no user query found
# in messages") that names nothing and reads as intermittent. It is reachable:
# nodes.parsing._to_adapter_messages and _to_lc_messages BOTH keep only
# Human/AI messages and silently discard every other role, so a history of
# system/tool messages filters to an empty list, and thread_id is fresh per
# invoke so nothing server-side backfills the turn.
#
# Whether a real run reaches that shape is still unestablished — these pin the
# guard that will say so attributably when it next happens.
# ---------------------------------------------------------------------------

def test_a_userless_payload_is_refused_with_a_diagnosable_error():
    from adda._src.backends.openai_compatible import UserlessPayloadError

    a = VLLMAdapter(model="m", system_prompt="s")

    class _NeverCalled:
        def invoke(self, *args, **kwargs):
            raise AssertionError("must not reach the provider")

    a._agent = _NeverCalled()
    with pytest.raises(UserlessPayloadError) as exc:
        a.invoke([{"role": "system", "content": "rules"},
                  {"role": "tool", "content": "output"}])

    msg = str(exc.value)
    # The error must carry the evidence: what arrived, and what survived.
    assert "system" in msg and "tool" in msg
    assert "2 message(s) in" in msg
    assert "0 survived" in msg


def test_the_userless_guard_is_not_retried_as_transient():
    """Retrying an unanswerable payload five times with backoff burns wall
    budget and buries the cause deeper."""
    from adda._src.backends.base import is_transient_error
    from adda._src.backends.openai_compatible import UserlessPayloadError

    assert is_transient_error(UserlessPayloadError("no user turn")) is False


def test_a_normal_payload_still_passes_the_guard():
    """The guard must not fire on the ordinary case."""
    a = VLLMAdapter(model="m", system_prompt="s")

    class _Fake:
        def invoke(self, state, config=None):
            from langchain_core.messages import AIMessage
            return {"messages": [AIMessage(content="fine")]}

    a._agent = _Fake()
    assert a.invoke([{"role": "user", "content": "go"}]) == "fine"


def test_both_converters_drop_unrecognised_roles():
    """Pins the shape that makes the guard necessary, in both stages. This is
    the defect the guard instruments; fixing it means preserving these roles,
    which changes what EVERY backend sees and is a separate change."""
    from langchain_core.messages import SystemMessage, ToolMessage

    from adda._src.backends.openai_compatible import _to_lc_messages
    from adda._src.nodes.parsing import _to_adapter_messages

    state = [SystemMessage(content="rules"),
             ToolMessage(content="out", tool_call_id="t1")]
    assert _to_adapter_messages(state) == []
    assert _to_lc_messages([{"role": "system", "content": "x"},
                            {"role": "tool", "content": "y"}]) == []


# ---------------------------------------------------------------------------
# Block content was DESTROYED, not merely flattened
#
# Both converters joined block lists on ``c.get("text", "")``, so every block
# that was not a text block contributed "". A message carrying only
# tool-result blocks therefore arrived as ``content=""`` — the payload gone,
# and a user turn left holding nothing. That is silent data loss on its own,
# and it is also how a request acquires an empty user turn.
# ---------------------------------------------------------------------------

def test_a_tool_result_block_keeps_its_payload():
    """The bug: this returned '' and the tool output vanished."""
    from adda._src.backends.openai_compatible import _flatten_content

    out = _flatten_content([
        {"type": "tool_result", "tool_use_id": "x", "content": "42 rows"},
    ])
    assert out == "42 rows"


def test_a_text_block_still_wins_over_content():
    from adda._src.backends.openai_compatible import _flatten_content

    assert _flatten_content(
        [{"type": "text", "text": "hello", "content": "ignored"}]) == "hello"


def test_mixed_blocks_are_all_kept_in_order():
    from adda._src.backends.openai_compatible import _flatten_content

    out = _flatten_content([
        {"type": "text", "text": "ran the sampler"},
        {"type": "tool_result", "content": "8 rows"},
    ])
    assert out == "ran the sampler 8 rows"


def test_a_plain_string_is_untouched():
    from adda._src.backends.openai_compatible import _flatten_content

    assert _flatten_content("just text") == "just text"


def test_the_graph_converter_keeps_tool_result_payloads():
    from langchain_core.messages import HumanMessage

    from adda._src.nodes.parsing import _to_adapter_messages

    out = _to_adapter_messages([
        HumanMessage(content=[{"type": "tool_result", "content": "8 rows"}]),
    ])
    assert out == [{"role": "user", "content": "8 rows"}]


# ---------------------------------------------------------------------------
# An empty turn is the same thing as a missing one
# ---------------------------------------------------------------------------

def test_an_empty_turn_is_dropped_rather_than_sent():
    """It carries nothing, and a provider that counts non-empty user turns
    rejects the WHOLE request over it — so forwarding it can only convert a
    no-op into a 500."""
    from adda._src.backends.openai_compatible import _to_lc_messages

    assert _to_lc_messages([{"role": "user", "content": ""}]) == []
    assert _to_lc_messages([{"role": "user", "content": "   \n"}]) == []
    assert len(_to_lc_messages([{"role": "user", "content": "real"}])) == 1


def test_an_empty_user_turn_does_not_satisfy_the_guard():
    """The gap that let the reported 500 through: the guard tested for a
    HumanMessage, and ``HumanMessage(content="")`` is one. The provider does
    not care about the type, only about whether a user turn says anything."""
    from adda._src.backends.openai_compatible import UserlessPayloadError

    a = VLLMAdapter(model="m", system_prompt="s")

    class _NeverCalled:
        def invoke(self, *args, **kwargs):
            raise AssertionError("must not reach the provider")

    a._agent = _NeverCalled()
    with pytest.raises(UserlessPayloadError) as exc:
        a.invoke([{"role": "user", "content": "   "},
                  {"role": "ai", "content": "sure"}])

    # the ai turn survives; the empty user turn does not, which is the point
    assert "1 survived" in str(exc.value)
    assert "empty after flattening" in str(exc.value)
