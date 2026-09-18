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

    DEPENDENCIES, precisely. READING a corpus is stdlib-only (sqlite3, re,
    html, pathlib), so an agent consulting the docs adds nothing to adda.
    BUILDING one parses the documentation's HTML and needs lxml, declared as
    the optional `abaqus` extra: it was reaching lxml only as a transitive of
    `arxiv`, which is the trap the viewer extra is explicitly declared to
    avoid.
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

        ConsultAbaqus("*FREQUENCY")          -> table-of-contents style hits
        ConsultAbaqus("simakey-r-frequency") -> that whole page

    The switch is "is this argument a known page_id", which is unambiguous:
    page ids are distinctive and search hands the exact string back.

    UNCONFIGURED RETURNS NOTHING AT ALL, not a tool that explains itself.
    The first version declared the tool anyway, reasoning that an agent must
    not read "no corpus" as "not documented". But that belief is only
    available to an agent that HAS the tool; withhold it and the agent is
    simply one without an Abaqus manual, exactly like the base
    DataGeneratorAgent. ``runtime/features.py`` states the rule this follows:
    "Withholding is the point. Leaving a dead tool registered does not produce
    an agent without the feature -- it produces an agent that keeps calling a
    tool that errors", and those errors are counted as ERROR_RETURN, the one
    KPI whose target is zero. It also stops a study that will never use Abaqus
    paying catalog tokens for it in every model call.

    A corpus that IS configured but cannot be read is the genuinely ambiguous
    case, and there the tool stays and says which failure occurred.
    """
    root = Path(corpus) if corpus else corpus_dir()
    if root is None:
        return {}

    def ConsultAbaqus(query: str, limit: int = 8) -> str:
        """Look up Abaqus reference documentation.

        Pass a keyword (``*FREQUENCY``), a phrase, or a page_id returned by an
        earlier search to read that page in full.
        """
        try:
            from .reader import AbaqusDocs
            return AbaqusDocs(root).consult(query, limit=limit)
        except Exception as exc:                      # noqa: BLE001
            return (f"Abaqus docs unavailable ({exc!s}). This means the corpus "
                    "could not be read, NOT that the keyword is undocumented.")

    return {"ConsultAbaqus": ConsultAbaqus}
