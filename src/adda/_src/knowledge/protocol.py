"""The contract every knowledge provider owes, and the registry of them.

WHY THIS EXISTS
    Five corpora were built by five agents at five times: f3dasm's API, adda's
    own source, the Abaqus manual, the Basilisk source tree, and the
    literature corpus. Four converged on the same call shape without
    coordination -- because three copied the first -- and the two oldest did
    not. Convergence by imitation is not a contract: nothing failed when a
    provider drifted, and one divergence (an uncapped reply) defeats the
    purpose of the tool it appears in.

WHAT IS UNIFORM, AND WHAT DELIBERATELY IS NOT
    UNIFORM: the call shape, the dispatch, the failure mode, the cap. These
    are properties of "a reference an agent consults", not of any one corpus,
    and an agent that learns one provider should be able to use all five.

    NOT UNIFORM, ON EVIDENCE: the retrieval mechanism. Measured on labelled
    query sets, the right internals differ per corpus -- f3dasm wants symbols
    only with hand-weighted name/summary/body tiers and gets WORSE when
    modules and constants are added (r@1 0.77 -> 0.62); adda needs all four
    unit kinds or it loses to ripgrep; Abaqus needs BM25 because its documents
    vary in length by two orders of magnitude, which is exactly the condition
    f3dasm's 250 uniform entries do not have. Forcing one ranker would make
    three providers worse to make a table look tidy. Sisters in contract,
    cousins in mechanism, and that is the correct shape.

    ALSO NOT UNIFORM: the agent-facing TOOL NAMES. ``CorpusSearch`` and
    ``ConsultHandbook`` do not match ``Consult<X>Docs``, and renaming them
    would be a prompt change, not a refactor -- both are named in the
    strategizer's, the implementer's and the literature reviewer's prompt
    text. Changing what an agent is told, with no measurement that the new
    name works better, is the kind of unmeasured behaviour change this
    project has spent its effort learning not to make.

THE CONTRACT
    1. ``consult(query, limit=8)`` is the canonical method. A provider may
       accept more (``source=True``), never fewer.
    2. DISPATCH ON THE QUERY. A key that names an entry exactly returns THAT
       ENTRY; anything else returns a MENU of candidate keys. A reference is
       used in two steps and one call should serve both.
    3. A MISS IS HONEST. It says what was searched and that the miss is about
       this index, not about reality. An agent told "no results" concludes the
       thing does not exist.
    4. THE REPLY IS CAPPED. The whole point is to keep the corpus OUT of the
       context window; an unbounded page defeats it. ``MAX_REPLY_CHARS``.
    5. UNCONFIGURED RETURNS ``{}``, not a tool that explains itself. A
       registered tool that errors produces an agent that keeps calling it,
       and those are counted as ERROR_RETURN -- the one KPI whose target is 0.

``tests/test_knowledge_protocol.py`` asserts all five against every provider.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

__all__ = ["MAX_REPLY_CHARS", "KnowledgeProvider", "clip", "providers"]

#: Cap on any single reply. 6000 characters is roughly 1500 tokens -- enough
#: for one entry with its documentation, far less than the corpus it stands
#: in for. Chosen by f3dasm's index first and adopted here rather than
#: re-derived, because a per-corpus cap would make the budget an agent has to
#: reason about instead of a constant it can ignore.
MAX_REPLY_CHARS = 6000


def clip(text: str, limit: int = MAX_REPLY_CHARS) -> str:
    """Truncate to the cap, saying so rather than ending mid-sentence.

    Silent truncation is worse than none: an agent cannot tell a short answer
    from a cut-off one, and will act on a half-read rule as though it were
    whole.
    """
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + (
        f"\n\n[truncated at {limit} characters — narrow the query, or ask for "
        f"one key by name to read its full entry]")


@runtime_checkable
class KnowledgeProvider(Protocol):
    """What a knowledge corpus must offer. See the contract above."""

    def consult(self, query: str, limit: int = 8) -> str:
        """A key returns its entry; anything else returns a menu."""
        ...


def providers() -> dict[str, dict]:
    """Every provider, with how to build it and how to tell if it is live.

    Declared in one place so the contract test cannot silently stop covering
    one. A provider added without an entry here is a provider nothing checks,
    which is the state this module was written to end.
    """
    from ..agents.literature_tools.corpus import build_corpus_closures
    from .abaqus import ENV_VAR as ABAQUS_ENV
    from .abaqus import build_abaqus_docs_closures
    from .basilisk import ENV_VAR as BASILISK_ENV
    from .basilisk import build_basilisk_docs_closures
    from .f3dasm_api import build_f3dasm_api_closures

    return {
        "f3dasm": {
            "build": build_f3dasm_api_closures,
            "tool": "ConsultF3dasmDocs",
            "env": None,          # a declared dependency; always available
        },
        "adda": {
            "build": _build_adda_closures,
            "tool": "ConsultAddaDocs",
            "env": None,
        },
        "abaqus": {
            "build": build_abaqus_docs_closures,
            "tool": "ConsultAbaqusDocs",
            "env": ABAQUS_ENV,
        },
        "basilisk": {
            "build": build_basilisk_docs_closures,
            "tool": "ConsultBasiliskDocs",
            "env": BASILISK_ENV,
        },
        "literature": {
            "build": build_corpus_closures,
            "tool": "CorpusSearch",   # legacy name, kept: it is prompt text
            "env": None,
            "needs_args": True,
        },
    }


def _build_adda_closures() -> dict:
    """adda's own index, as a tool.

    It had none: ``adda-docs`` is a console script for somebody else's coding
    agent, and adda's own agents write f3dasm code rather than adda code. It
    is registered here so the contract covers it, and so a graph that wants it
    can have it.
    """
    from .f3dasm_api import AddaApi

    api = AddaApi()

    def ConsultAddaDocs(query: str, limit: int = 8, source: bool = False):
        """Look up adda itself — its API, its concepts and its rules.

        Introspected from the installed package, so it cannot be out of date.
        A phrase returns a menu of matching keys; passing one of those keys
        back returns its full entry.

        Indexes four kinds of thing: symbols with their public import path,
        module docstrings (where this package argues WHY something exists),
        declared constants, and the knowledge-base rules shipped inside it.
        """
        return api.consult(query, limit=limit, source=source)

    return {"ConsultAddaDocs": ConsultAddaDocs}
