"""Offline Abaqus reference documentation as an agent tool.

WHY THIS EXISTS
    An agent that writes Abaqus input decks is working against a solver whose
    reference manual it cannot read. Every wrong keyword costs a full solve to
    discover, and some cost much more: a beam-to-beam contact investigation
    died on a rule stated plainly in the documentation (line-element surfaces
    cannot act as a contact MAIN surface).

WHAT SHIPS HERE AND WHAT DOES NOT
    The reader and the corpus BUILDER ship. The corpus does NOT: Abaqus
    documentation is Dassault Systemes' licensed content and cannot be
    redistributed. Point ADDA_ABAQUS_DOC_CORPUS at a directory you built from
    the documentation your own licence entitles you to read.

    Both modules are stdlib-only (sqlite3, re, html, pathlib) -- no new
    dependency is added to adda.
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "ADDA_ABAQUS_DOC_CORPUS"


def corpus_dir() -> Path | None:
    """Where the caller's corpus lives, or None if unconfigured."""
    raw = os.environ.get(ENV_VAR)
    return Path(raw) if raw else None


def build_abaqus_docs_closures(corpus: str | Path | None = None) -> dict:
    """One tool, two behaviours -- the way a person uses a manual.

        ConsultAbaqusDocs("*FREQUENCY")          -> table-of-contents style hits
        ConsultAbaqusDocs("simakey-r-frequency") -> that whole page

    The switch is "is this argument a known page_id", which is unambiguous:
    page ids are distinctive and search hands the exact string back.

    A missing or unreadable corpus must never break the agent -- it degrades
    to a tool that reports the corpus is unavailable, because an agent that
    cannot tell "no corpus" from "not documented" will conclude the latter.
    """
    root = Path(corpus) if corpus else corpus_dir()

    def ConsultAbaqusDocs(query: str, limit: int = 8) -> str:
        """Look up Abaqus reference documentation.

        Pass a keyword (``*FREQUENCY``), a phrase, or a page_id returned by an
        earlier search to read that page in full.
        """
        if root is None:
            return (f"Abaqus docs unavailable: {ENV_VAR} is not set. "
                    "This means NOT CONFIGURED, not 'undocumented' -- do not "
                    "conclude a keyword does not exist from this message.")
        try:
            from .reader import AbaqusDocs
            return AbaqusDocs(root).consult(query, limit=limit)
        except Exception as exc:                      # noqa: BLE001
            return (f"Abaqus docs unavailable ({exc!s}). This means the corpus "
                    "could not be read, NOT that the keyword is undocumented.")

    return {"ConsultAbaqusDocs": ConsultAbaqusDocs}
