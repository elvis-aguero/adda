"""DataGeneratorAgent with the Basilisk source tree attached.

WHY A SEPARATE AGENT AND NOT A FLAG ON DataGeneratorAgent
    Every tool costs catalog tokens in every model call for the agent holding
    it, which is the reasoning DataGeneratorAgent already applies when it
    withholds the f3dasm API lookup from the critic and strategizer, and which
    AbaqusDataGeneratorAgent applies to the solver manual. A study whose
    oracle is not a Basilisk simulation should not pay for this tool, so it is
    opt-in by class rather than always-on.

WHY A SOURCE INDEX AND NOT AN AST INDEX
    Basilisk's 297 solver headers are only 59k lines, but a C grammar
    represents them as roughly two million syntax nodes at depth ~100, of
    which ~73% are single-child precedence rungs carrying no information --
    one literal assignment is 28 levels deep. Worse, Basilisk C is a DSL
    compiled by qcc, so a C parser emits error nodes on the constructs that
    carry the physics (foreach, event, scalar s[]), and discards as comments
    the literate documentation that is 16% of every solver file. Headers do
    not even parse standalone: they are fragments assuming their dependencies
    are in scope. So this indexes the tree at the granularity Basilisk is
    AUTHORED in -- the solver header and the worked case.

MEASURED AGAINST RIPGREP, NOT AGAINST NOTHING
    An agent with a shell already reads the tree, so the control is ripgrep
    over the same files, ranked by match count. See
    ``tests/test_basilisk_vs_ripgrep.py`` for the per-tier scores and
    ``tests/basilisk_source_queries.py`` for the frozen query set those
    scores are computed on.
"""
from __future__ import annotations

from .datagenerator import DataGeneratorAgent


class BasiliskDataGeneratorAgent(DataGeneratorAgent):
    """DataGeneratorAgent that can read the Basilisk source tree.

    Set ``ADDA_BASILISK_SRC`` to a Basilisk checkout (the directory containing
    ``src/``), or pass ``corpus_dir=`` to the constructor. With neither, the
    tool is WITHHELD and this agent is indistinguishable from its base class --
    see ``build_basilisk_docs_closures`` for why that is safer than declaring
    a tool that cannot answer.
    """

    role = "datagenerator"

    def __init__(self, *args, corpus_dir=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._basilisk_corpus_dir = corpus_dir

    def build_closure_tools(
        self,
        study_dir,
        delegation_id=None,
        lit_reviewer_notes_dir=None,
    ) -> dict:
        """Inherited tools plus ConsultBasiliskDocs.

        super() IS called, so the literature-corpus tools and the f3dasm API
        lookup survive: this agent wants papers for methodology, the f3dasm
        API for plumbing, and the Basilisk tree for the simulation itself.
        """
        tools = super().build_closure_tools(
            study_dir,
            delegation_id=delegation_id,
            lit_reviewer_notes_dir=lit_reviewer_notes_dir,
        ) or {}
        from ..knowledge.basilisk import build_basilisk_docs_closures
        tools.update(build_basilisk_docs_closures(self._basilisk_corpus_dir))
        return tools
