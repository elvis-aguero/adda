"""Basilisk source lookup as an opt-in datagenerator tool.

Basilisk is not redistributed here. Point ``ADDA_BASILISK_SRC`` at a Basilisk
checkout -- the directory CONTAINING ``src/``.
"""
from __future__ import annotations

import os
from pathlib import Path

from ...prompts.tool_catalog import tool_examples

ENV_VAR = "ADDA_BASILISK_SRC"


def corpus_dir() -> Path | None:
    """The configured Basilisk checkout, or None when unset or unreadable."""
    raw = os.environ.get(ENV_VAR)
    if not raw:
        return None
    root = Path(raw).expanduser()
    return root if (root / "src").is_dir() else None


def build_basilisk_docs_closures(corpus: str | Path | None = None) -> dict:
    """``{name: callable}`` for the Basilisk lookup, or ``{}`` when unavailable.

    One tool, two behaviours -- the way a person uses a reference:

        ConsultBasilisk("rising bubble")   -> menu of matching entries
        ConsultBasilisk("two-phase.h")     -> that entry

    UNCONFIGURED RETURNS NOTHING AT ALL, not a tool that explains itself.
    Leaving a dead tool registered does not produce an agent without the
    feature -- it produces one that keeps calling a tool that errors, and those
    are counted as ERROR_RETURN, the one KPI whose target is zero. It also
    stops a study that will never touch Basilisk paying catalog tokens for it
    in every model call.
    """
    root = Path(corpus) if corpus else corpus_dir()
    if root is None or not (root / "src").is_dir():
        return {}

    from .index import BasiliskIndex
    index = BasiliskIndex.build(root / "src")

    # A named function, not a lambda: the runtime renders this docstring into
    # the generated <tools> catalog, which is the agent's only documentation.
    @tool_examples(
        "ConsultBasilisk('adaptive mesh refinement')",
    )
    def ConsultBasilisk(query: str, limit: int = 8, source: bool = False):
        """Look up the Basilisk CFD source tree -- solvers and worked cases.

        Read from the checkout this run executes against, so it cannot be out
        of date.

        Two steps, like a reference. A DESCRIPTION returns a menu: one line per
        match, up to `limit`. A KEY from that menu returns its entry.
          ConsultBasilisk("rising bubble")        # menu
          ConsultBasilisk("two-phase.h")          # entry
          ConsultBasilisk("two-phase.h", source=True)
        Add source=True only when the entry does not settle the question.

        Search is LEXICAL -- your words against keys, titles, and the literate
        documentation Basilisk keeps inside its own source. Use Basilisk's own
        vocabulary where you know it ("adapt" not "refine", "view" not
        "plot", "vof", "embed"); plain physics works for the rest.

        A HEADER entry gives four things no single file states:
          - PROVIDES: fields the header declares for you.
          - YOU MUST SUPPLY: fields you are expected to set, with their
            defaults.
          - VERIFIED WITH / NEVER STACKED WITH: which headers working cases
            combine this one with, and which they never do. Basilisk documents
            no compatibility rules anywhere; this is derived from 213 verified
            cases, so "never stacked" usually means an alternative solver for
            the same physics -- stacking those is a mistake, not an option.
          - WORKED EXAMPLES: cases that actually compile and run.

        An EXAMPLE entry gives the full header stack a working case uses.
        Prefer starting from a worked example over composing from scratch.

        Covers the Basilisk tree only, so a miss means "not a Basilisk
        concept", not "does not exist".
        """
        return index.consult(query, limit=int(limit), source=bool(source))

    return {"ConsultBasilisk": ConsultBasilisk}
