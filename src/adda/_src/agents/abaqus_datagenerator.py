"""DataGeneratorAgent with offline Abaqus reference documentation attached.

WHY A SEPARATE AGENT AND NOT A FLAG ON DataGeneratorAgent
    Every tool costs catalog tokens in every model call for the agent holding
    it, which is the same reasoning DataGeneratorAgent already applies when it
    withholds the f3dasm API lookup from the critic and strategizer. A study
    whose oracle is not an Abaqus model should not pay for this tool, so it is
    opt-in by class rather than always-on.

MEASURED EFFECT
    On an oracle-construction benchmark (build a DataGenerator that runs
    Abaqus end to end and reports a value graded against a withheld
    reference), the arm holding this tool produced a solver-traceable value in
    4/4 runs; the arm without it produced one in 0/5. The failure mode is
    specific and worth stating, because it is not "wrong answer": the runs
    without documentation wrote decks that RAN TO COMPLETION and produced an
    ODB with no eigenvalue frames, then registered an empty result. One run
    diagnosed it explicitly -- "0 frames found" against its own earlier claim
    that the frequency step had produced eigenvalues.

    The tool's most valuable behaviour turned out to be handling wrong
    guesses. Of 24 consultations in one run, 8 named a keyword that does not
    exist, and every one returned a correction: *FREQ -> *FREQUENCY,
    *MODAL -> *MODAL FILE/*MODAL PRINT. Across 346 consultations in 230
    transcripts, no agent ever wrote that the tool had failed it.
"""
from __future__ import annotations

from .datagenerator import DataGeneratorAgent


class AbaqusDataGeneratorAgent(DataGeneratorAgent):
    """DataGeneratorAgent that can read the Abaqus reference manual.

    Set ``ADDA_ABAQUS_DOC_CORPUS`` to a corpus directory, or pass
    ``corpus_dir=`` to the constructor. With neither, the tool is WITHHELD and
    this agent is indistinguishable from its base class -- see
    ``build_abaqus_docs_closures`` for why that is safer than declaring a tool
    that cannot answer.
    """

    role = "datagenerator"

    def __init__(self, *args, corpus_dir=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._abaqus_corpus_dir = corpus_dir

    def build_closure_tools(
        self,
        study_dir,
        delegation_id=None,
        lit_reviewer_notes_dir=None,
    ) -> dict:
        """Inherited tools plus ConsultAbaqus.

        super() IS called, so the literature-corpus tools and the f3dasm API
        lookup survive: this agent wants papers for methodology, the f3dasm
        API for plumbing, and the solver manual for mechanics.
        """
        tools = super().build_closure_tools(
            study_dir,
            delegation_id=delegation_id,
            lit_reviewer_notes_dir=lit_reviewer_notes_dir,
        ) or {}
        from ..knowledge.abaqus import build_abaqus_docs_closures
        tools.update(build_abaqus_docs_closures(self._abaqus_corpus_dir))
        return tools
