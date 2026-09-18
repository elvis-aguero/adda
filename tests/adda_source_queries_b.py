"""A second, independent labelled query set for the same retrieval tool as
``adda_source_queries.py``: an agent-facing index over adda's OWN source
(``src/adda/_src/``), not over f3dasm.

WHO IS ASKING
    An external software engineer, or a coding agent working on or with
    adda, who has read none of this codebase's internal vocabulary. They
    have a real question — "how do I turn this off", "why did my run stop",
    "what is this traceback" — and they ask it the way a person who does not
    yet know the words "backstop" or "science_monitor" actually would. They
    were never shown ``adda_source_queries.py``, and its 48 queries are not a
    model to imitate; this file exists to add breadth and a second, unbiased
    sample of the same question space, not to restate the first sample in
    different words.

WHY A SEPARATE FILE, WRITTEN THIS WAY
    Every query below was written against a question first, and only
    resolved to a gold file second — by actually reading the code that
    answers it and confirming the file still says what the query assumes.
    Nothing here was authored by looking at what a retriever returns and
    writing a query that would make it look good. That direction of travel
    is the one failure mode that would make this whole exercise worthless:
    a query set is a ruler, and a ruler that gets bent to match the thing it
    is measuring is not a ruler anymore.

THE ONE RULE, STATED ONCE SO IT IS NOT MISSED
    A gold label may be REPOINTED when the code it names moves or is
    renamed — ``tests/test_adda_source_queries_b.py``-style existence checks
    (see the sibling file's own test) are what makes that rot loud instead
    of silent. A gold label may NEVER be edited because a retriever missed
    it, scored it low, or ranked something else first. Those are findings
    about the retriever, not defects in the question. If a query turns out
    to have no defensible single answer once written, it is dropped (see the
    accompanying report), never kept and quietly re-pointed at whatever came
    back.

SCHEMA
    Identical to ``adda_source_queries.py``: per tier, a list of
    ``(id, query_string, [gold_paths])`` tuples. Gold paths are
    repository-relative. IDs are prefixed by tier letter and numbered from
    50, so they cannot collide with the first file's 01-numbered ids even if
    both are ever merged into one set. Several gold paths are listed only
    where a question genuinely has more than one defensible home; any one of
    them at rank 1 counts as correct.

THE HELD-OUT SPLIT
    ``HELD_OUT_IDS`` below is exactly one third of this file's 80 queries
    (27), stratified so every tier appears in both ``DEVELOPMENT`` and
    ``HELD_OUT``. The ids are listed literally rather than computed from a
    hash, for the same reason the first file does it that way: a computed
    split silently reshuffles the moment a query is added or removed, and a
    held-out set that moves under you was never really held out.
"""
from __future__ import annotations

S = "src/adda/_src/"

# =============================================================================
# NAME — the asker already has the identifier and wants the definition.
# Ripgrep is expected to win this tier; it is the control, not the target.
# =============================================================================
NAME = [
    ("n50", "DelegationLog", [S + "infra/delegation_log.py"]),
    ("n51", "InstrumentedDataGenerator", [S + "evaluation/instrumented.py"]),
    ("n52", "LookupDataGenerator", [S + "evaluation/lookup.py"]),
    ("n53", "what is the ResourceBackend class",
     [S + "infra/resource_backend.py"]),
    ("n54", "MilestoneLedger", [S + "epistemics/milestones.py"]),
    ("n55", "what is PROTECTED_STORE_SENTINEL",
     [S + "evaluation/_f3dasm_compat.py"]),
    ("n56", "the math_dsl Workspace class", [S + "epistemics/math_dsl.py"]),
    ("n57", "AbaqusDocs", [S + "knowledge/abaqus/reader.py"]),
    ("n58", "WorkerSession", [S + "nodes/tools/routing/delegation.py"]),
    ("n59", "render_tool_catalog", [S + "prompts/tool_catalog.py"]),
    ("n60", "FALSIFICATION_CHARTER", [S + "knowledge/charter.py"]),
    ("n61", "resolve_phase", [S + "runtime/phases.py"]),
]

# =============================================================================
# CONCEPT — plain English, no shared vocabulary with the codebase. The
# hardest and most valuable tier: these are questions, never grep terms.
# =============================================================================
CONCEPT = [
    ("c50", "how do I get a math derivation actually checked instead of "
     "just trusting the model's own algebra",
     [S + "agents/math_expert.py", S + "epistemics/math_dsl.py"]),
    ("c51", "what stops the critic and the strategizer from arguing past "
     "each other about what counts as a falsified hypothesis",
     [S + "knowledge/charter.py"]),
    ("c52", "where does it decide the process backlog is done before "
     "letting the implementer touch any experiment",
     [S + "epistemics/milestones.py"]),
    ("c53", "how does it avoid corrupting the evaluation ledger when two "
     "delegations try to write to it at the same time",
     [S + "evaluation/instrumented.py"]),
    ("c54", "what actually turns the raw Abaqus documentation pages into "
     "something a lookup tool can search",
     [S + "knowledge/abaqus/builder.py"]),
    ("c55", "where does it decide how much memory one worker process is "
     "allowed to use before it gets killed",
     [S + "infra/resource_backend.py"]),
    ("c56", "how does it keep a delegation's leftover background job from "
     "running forever after the delegation itself ends",
     [S + "infra/watchdog_cleanup.py"]),
    ("c57", "does every delegation leave behind some kind of "
     "version-controlled snapshot of what it changed",
     [S + "infra/workspace_vcs.py"]),
    ("c58", "how does a downloaded paper actually get turned into text the "
     "corpus can search",
     [S + "literature/literature_corpus.py"]),
    ("c59", "why would every literature search suddenly start failing at "
     "once instead of just the one call that got rate-limited",
     [S + "literature/http_client.py"]),
    ("c60", "how does the literature reviewer search papers when there is "
     "no embedding model installed",
     [S + "literature/embedder.py"]),
    ("c61", "what actually draws the picture of the agent graph",
     [S + "runtime/run_diagram.py"]),
    ("c62", "how does a delegation find out how much money and time is "
     "left before it has to explain itself",
     [S + "runtime/constraint_snapshot.py"]),
    ("c63", "where is the list of every backend name it knows how to "
     "dispatch to",
     [S + "backends/registry.py"]),
    ("c64", "how do I tell adda's own injected messages apart from what a "
     "tool actually returned",
     [S + "nodes/notices.py"]),
    ("c65", "where does it decide whether an error was the model's own "
     "fault or just a network blip",
     [S + "nodes/recording.py"]),
    ("c66", "what makes the graph treat some agents as delegators and "
     "others as agents that just answer",
     [S + "nodes/node.py"]),
    ("c67", "where do I look to see what is actually in the evaluation "
     "ledger without touching it",
     [S + "nodes/tools/routing/store.py"]),
    ("c68", "how does the critique agent decide to fail a run instead of "
     "letting it pass",
     [S + "agents/critic.py"]),
    ("c69", "who actually turns a raw dataset or an external solver into "
     "something the pipeline can call",
     [S + "agents/datagenerator.py"]),
    ("c70", "how does an agent trace a bug back to what actually caused it "
     "instead of just patching the symptom",
     [S + "agents/debugger.py"]),
    ("c71", "what curated write-ups can an agent go read mid-run instead of "
     "guessing",
     [S + "knowledge/kb.py"]),
    ("c72", "how does the list of tools an agent sees get built without "
     "anyone hand-writing it",
     [S + "prompts/tool_catalog.py"]),
    ("c73", "what do I actually run if I just want to launch this from the "
     "command line",
     [S + "runtime/run.py"]),
    ("c74", "how does resuming a run pick back up in the same state it "
     "left off in",
     [S + "runtime/graph_state.py"]),
    ("c75", "how does a whole agentic run get wrapped up so f3dasm's own "
     "optimizer interface can call it like any other optimizer",
     [S + "runtime/optimizer.py"]),
    ("c76", "where does it decide which open hypothesis a piece of "
     "evidence actually supports",
     [S + "nodes/tools/routing/ledger.py"]),
    ("c77", "what does the viewer show for a run that was started without "
     "debug logging turned on",
     [S + "viewer/readers.py"]),
]

# =============================================================================
# ERROR — a traceback or error string the asker did not choose. Some of
# these words ARE in the source; the interesting cases are where the message
# is assembled far from the decision that actually caused it.
# =============================================================================
ERROR = [
    ("e50", "ERROR: hypothesis ledger not available in this run.",
     [S + "nodes/tools/routing/ledger.py", S + "runtime/features.py"]),
    ("e51", "ValueError: Evaluator file not found",
     [S + "evaluation/oracle_resolution.py"]),
    ("e52", "ValueError: entry=... not in nodes (entry node undeclared)",
     [S + "backends/base.py"]),
    ("e53", "ERROR: hypothesis_ids must not be empty.",
     [S + "nodes/tools/routing/delegation.py"]),
    ("e54", "ERROR: no critic connected.",
     [S + "nodes/critic_gate.py"]),
    ("e55", "500 no user query found in messages",
     [S + "backends/openai_compatible.py"]),
    ("e56", "RuntimeError: Refusing to overwrite the PROTECTED canonical "
     "store",
     [S + "evaluation/_f3dasm_compat.py"]),
    ("e57", "ERROR: the deliverable must be pipeline.ipynb (a notebook)",
     [S + "nodes/tools/routing/notebook.py"]),
    ("e58", "RuntimeError: No Claude credentials available for the "
     "container",
     [S + "infra/container_runner.py"]),
    ("e59", "AgenticRunError: resume_from=... is not a resumable run dir "
     "(no debug/thread_id)",
     [S + "runtime/agent_runtime.py"]),
    ("e60", "ValueError: 'experiment_data' is reserved",
     [S + "runtime/run_setup.py"]),
    ("e61", "domain is rate-limited (cooldown ...s remaining: ...s)",
     [S + "literature/http_client.py"]),
    ("e62", "TimeoutError: serve job ... not RUNNING after ...s — GPU "
     "queue may be busy",
     [S + "infra/slurm_llm.py"]),
    ("e63", "AttributeError: 'Domain' object has no attribute "
     "'add_continuous_input'",
     [S + "knowledge/entries/0008-experimentdata-input-and-to-numpy.md"]),
    ("e64", "vLLM server at ... did not answer within ...s",
     [S + "infra/slurm_llm.py"]),
]

# =============================================================================
# INVARIANT — "am I allowed to do X?" The answer is a RULE about a symbol,
# never the symbol itself. No grep can serve this tier.
# =============================================================================
INVARIANT = [
    ("i50", "can I skip a process milestone without giving a reason",
     [S + "epistemics/milestones.py", S + "nodes/tools/routing/ledger.py"]),
    ("i51", "does the evidence number I cite have to literally appear in "
     "the worker's report",
     [S + "knowledge/entries/0006-evidence-anchors-to-the-report.md"]),
    ("i52", "am I allowed to start delegating real experiments before a "
     "ground-truth source is registered",
     [S + "knowledge/entries/0007-author-and-register-a-source.md",
      S + "epistemics/milestones.py"]),
    ("i53", "can I call data.store() on my local copy right after the "
     "evaluator finishes running",
     [S + "knowledge/entries/0009-pipeline-building-patterns.md",
      S + "evaluation/_f3dasm_compat.py"]),
    ("i54", "is 'strategy A beats strategy B' a hypothesis I can register",
     [S + "knowledge/entries/0003-hypotheses-are-bounded-claims.md"]),
    ("i55", "does calling Done() once actually close the run",
     [S + "nodes/tools/routing/feedback.py"]),
    ("i56", "does a run the watchdog killed ever come back as GATED",
     [S + "runtime/terminal.py"]),
    ("i57", "is the debugger part of the graph I get by default",
     [S + "agents/_graphs.py"]),
    ("i58", "do I have to turn on the SLURM-hosted LLM to run a study on a "
     "cluster",
     [S + "knowledge/entries/0010-running-a-study-on-slurm.md"]),
    ("i59", "does the datagenerator have to go through get_evaluator() to "
     "try out the generator it just wrote",
     [S + "knowledge/entries/0001-evaluate-through-get-evaluator.md"]),
    ("i60", "can one delegation cover sampling, fitting a surrogate, and "
     "running the whole optimization loop at once",
     [S + "knowledge/entries/0004-one-delegation-one-experiment.md"]),
    ("i61", "is it fine to import torch at the top of a pipeline cell with "
     "no fallback",
     [S + "knowledge/entries/0009-pipeline-building-patterns.md"]),
    ("i62", "can the literature reviewer answer from what it remembers "
     "instead of quoting the corpus",
     [S + "agents/literature.py"]),
]

# =============================================================================
# KNOB — "how do I turn this off / configure it / point it somewhere else."
# =============================================================================
KNOB = [
    ("k50", "how do I stop it from asking me clarifying questions before "
     "the run even starts",
     [S + "runtime/agent_runtime.py", S + "epistemics/reviewer.py"]),
    ("k51", "how do I pick back up a run that got interrupted partway "
     "through",
     [S + "runtime/agent_runtime.py"]),
    ("k52", "how do I raise the hard dollar ceiling on a run that stopped "
     "because it hit it",
     [S + "runtime/agent_runtime.py"]),
    ("k53", "how do I run this unattended with no one there to answer a "
     "question",
     [S + "runtime/agent_runtime.py"]),
    ("k54", "how do I give the literature reviewer a Semantic Scholar API "
     "key",
     [S + "agents/literature_tools/semantic_scholar.py",
      S + "runtime/settings.py"]),
    ("k55", "how do I turn off the citation-count weighting in literature "
     "ranking",
     [S + "literature/literature_corpus.py", S + "runtime/settings.py"]),
    ("k56", "how do I force plain substring search instead of hybrid "
     "ranking for the paper corpus",
     [S + "literature/literature_corpus.py", S + "runtime/settings.py"]),
    ("k57", "how do I get the agent's own model served on a SLURM GPU node "
     "instead of a hosted API",
     [S + "infra/slurm_llm.py",
      S + "knowledge/entries/0010-running-a-study-on-slurm.md"]),
    ("k58", "how do I run the whole thing inside a container instead of "
     "directly on my machine",
     [S + "infra/container_runner.py"]),
    ("k59", "how do I stop the model from capping its own reply length",
     [S + "backends/context_budget.py"]),
    ("k60", "how do I let people other than me reach the viewer",
     [S + "viewer/__main__.py"]),
    ("k61", "how do I turn off the run's cost/time backstop entirely",
     [S + "nodes/_constants.py"]),
]

TIERS = {"name": NAME, "concept": CONCEPT, "error": ERROR,
         "invariant": INVARIANT, "knob": KNOB}

ALL = [(tier, qid, q, gold)
       for tier, rows in TIERS.items() for qid, q, gold in rows]

#: Frozen split, one third of this file's 80 queries (27), stratified by
#: tier. Listed literally, not computed, so adding a query later cannot
#: silently reshuffle which ones were already held out.
HELD_OUT_IDS = frozenset({
    "n52", "n55", "n58", "n61",                              # 4 of 12 name
    "c50", "c53", "c56", "c59", "c62",
    "c65", "c68", "c71", "c74", "c77",                       # 10 of 28 concept
    "e50", "e53", "e56", "e59", "e62",                       # 5 of 15 error
    "i51", "i55", "i58", "i61",                              # 4 of 13 invariant
    "k51", "k54", "k57", "k60",                              # 4 of 12 knob
})

DEVELOPMENT = [r for r in ALL if r[1] not in HELD_OUT_IDS]
HELD_OUT = [r for r in ALL if r[1] in HELD_OUT_IDS]
