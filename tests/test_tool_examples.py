"""Every tool an agent holds shows at least one call, and every shown call is
one the tool would accept.

WHY A TEST AND NOT A CONVENTION
    A tool's description is read by a model that has never seen the code.
    Prose tells it what a tool is for; an example tells it how to call it,
    and for a tool with optional or format-sensitive parameters that second
    part is where the mistakes are (Anthropic's tool-use guidance says the
    same, for the same reason). The convention existed -- ``@tool_examples``
    -- and three of the strategizer's thirty tools followed it.

    The second half matters as much as the first. An example that names a
    parameter the tool does not have teaches a call that fails, and it would
    keep teaching it after every rename: examples are hand-written text, so
    they drift exactly the way hard-coded tool names in prompts drifted. So
    each one is parsed and checked against the signature of the function it
    decorates -- its own name, only real parameters, no more positional
    arguments than the tool takes.

Read from the syntax tree, the same way the prompt map reads the catalog, so
it covers a tool whether or not a test ever builds the node that holds it.
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _promptmap():
    spec = importlib.util.spec_from_file_location(
        "_promptmap_for_examples", _ROOT / "internal" / "tools" / "promptmap.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _held_tools() -> set[str]:
    """Every closure tool the shipped agents are given."""
    from adda._src.runtime.agent_runtime import _default_graph

    names: set[str] = set()
    for agent in _default_graph().nodes.values():
        names |= set(agent.tools)
    # Granted by topology, by the runtime, or by a knowledge provider rather
    # than listed in an agent's `tools`.
    names |= {"Delegate", "Wait", "Reply", "FollowUp", "RecallHistory",
              "Confer", "ConsultHandbook", "ReportEvals", "AskForFeedback",
              "ConsultF3dasm", "ConsultLiterature", "CorpusAdd"}
    return names


def _definitions() -> dict[str, list[ast.FunctionDef]]:
    """Every definition a registered tool name is rendered from."""
    pm = _promptmap()
    out: dict[str, list[ast.FunctionDef]] = {}
    sites = {**{k: v for k, v in pm.injected_tool_docs().items()},
             **pm.tool_docs()}
    for name, doc in sites.items():
        locs = {f"{doc['file']}:{doc['def_line']}", *doc.get("ambiguous", [])}
        for loc in locs:
            file, line = loc.rsplit(":", 1)
            tree = ast.parse((_ROOT / file).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and node.lineno == int(line)):
                    out.setdefault(name, []).append(node)
    return out


def _examples(fn: ast.FunctionDef) -> list[str]:
    for dec in fn.decorator_list:
        if (isinstance(dec, ast.Call)
                and getattr(dec.func, "id", getattr(dec.func, "attr", ""))
                == "tool_examples"):
            return [a.value for a in dec.args if isinstance(a, ast.Constant)]
    return []


_DEFS = _definitions()
_HELD = sorted(t for t in _held_tools() if t in _DEFS)


def test_the_held_tools_are_found():
    """Guard the guard: if the scan finds nothing, every check below passes
    vacuously."""
    assert len(_HELD) >= 25, _HELD


@pytest.mark.parametrize("tool", _HELD)
def test_every_held_tool_shows_a_call(tool):
    for fn in _DEFS[tool]:
        assert _examples(fn), (
            f"{tool} (line {fn.lineno}) has no @tool_examples — the model is "
            "told what it does but never shown how to call it")


@pytest.mark.parametrize("tool", _HELD)
def test_every_example_is_a_call_the_tool_accepts(tool):
    for fn in _DEFS[tool]:
        params = [a.arg for a in fn.args.args if a.arg != "self"]
        kwonly = [a.arg for a in fn.args.kwonlyargs]
        for example in _examples(fn):
            call = ast.parse(example, mode="eval").body
            assert isinstance(call, ast.Call), f"{tool}: {example!r} is not a call"
            called = getattr(call.func, "id", None)
            assert called == tool, (
                f"{tool}'s example calls {called!r}: {example!r}")
            assert len(call.args) <= len(params), (
                f"{tool}: {example!r} passes {len(call.args)} positional "
                f"arguments; the tool takes {params}")
            for kw in call.keywords:
                assert kw.arg in params + kwonly, (
                    f"{tool}: {example!r} names {kw.arg!r}, which is not a "
                    f"parameter of the tool ({params + kwonly})")
