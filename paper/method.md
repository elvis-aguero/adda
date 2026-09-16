# Method

First pass. The job of this section is to turn `internal/FEATURES.md` from an
inventory into an argument: for each mechanism, **what it does, what it is
instead of, and what it costs**. The inventory answers the first; the second
and third mostly live in code comments and commit messages and are the bulk of
the harvest still to do.

Each subsection below carries a `HARVEST:` note naming where its rationale is
currently written.

---

## 3.1 The graph and the open loop

A hub-and-spoke graph: a **strategizer** with outgoing edges to
**literature reviewer**, **data generator**, **implementer** and **critic**.
Behaviour follows topology, not role — any node with an outgoing edge
orchestrates, whatever it is called — which is why a study can run a two- or
three-node graph without a different code path.

*Instead of:* a fixed pipeline of stages, or a fully-connected team. The hub
keeps one agent accountable for the run's scientific direction while letting
specialists be swapped or removed.

*Costs:* the hub is a bottleneck and carries the longest context. Removing a
specialist is a graph edit, which the evaluation exploits.

HARVEST: `src/a3dasm/_src/nodes/orchestration.py` module docstring;
`graph_builder.py`; `internal/CODE_TOUR.md`.

## 3.2 The epistemic layer

Four mechanisms, deliberately separable.

**The hypothesis ledger.** An append-only record of falsifiable hypotheses and
their verdicts (OPEN / SUPPORTED / FALSIFIED / INCONCLUSIVE), mutated only
through tools, never edited directly. Every delegation cites the hypothesis it
tests.

*Instead of:* letting the agent keep its claims in its context window. The
ledger survives context compaction, is auditable after the fact, and makes
"what did this run actually claim" a file rather than a reading exercise.

*Costs:* it is prompt surface and tool calls; and because delegations must cite
a hypothesis, it shapes how work is decomposed — which is a benefit or a
constraint depending on the problem.

**The falsification charter.** One binding text defining how a hypothesis may
be tested and labelled — severity of the attempt, verdict follows the result,
no goalpost-moving — spliced into both the strategizer's and the critic's
prompts so both cite the same standard.

*Instead of:* per-agent instructions that can drift apart. A shared constant is
the cheapest way to make two agents answerable to one rule.

**The live verdict referee.** When a hypothesis is closed, an independent judge
checks *at the moment of assertion* that the verdict obeys the charter, and is
fed its own prior rulings on the same hypothesis so a borderline verdict cannot
silently flip. Runs on the critic's model, not the strategizer's. Advisory: on
timeout or failure the verdict stands.

*Instead of:* checking only at the end, when the run has already been built on
the claim.

*Costs:* an extra model call per verdict, deliberately budgeted tight (a hung
call once froze a run for ~89 minutes, which is why the timeout exists).
Measured activation: **8.7% of runs** — see `evaluation-design.md`.

**The drift monitor.** Background rules that bracket the evaluation ledger from
both directions — evaluations reported but never written, and rows written with
no attributable owner — and escalate repeated drift to the critic.

*Costs:* activation **19.6%**; descriptive rather than inferential in any
ablation.

HARVEST: `src/a3dasm/_src/epistemics/*` docstrings; `knowledge/charter.py`;
`internal/FEATURES.md` §A.

## 3.3 The deliverable and the reproduction gate

The run closes on a notebook that has been **executed and reproduced before the
close is allowed**, not written up afterwards. A deliverable that fails to
reproduce after a bounded number of sighted attempts closes the run FAILED —
loudly, and distinctly from an unvalidated conclusion.

*Instead of:* a report plus a promise. This is the mechanism most likely to be
the paper's headline for a mechanics audience, because it converts "the agent
says it found X" into "here is a notebook that re-derives X from the recorded
data".

*Costs:* it constrains what the agent may produce, and the gate is a real
failure mode — reproduction bounces appear in **13.0%** of runs.

HARVEST: `nodes/reproduction_gate.py`; `evaluation/notebook_exec.py`;
BACKLOG #27/#28/#30 for what it took to make the switch honest.

## 3.4 Anti-drift: generated, not typed

The claim: **everything the agent is told is derived from the live system**,
so the prompt cannot describe a system that no longer exists.

- The tool catalog is rendered from the live closure dictionary at every
  invocation, not maintained by hand.
- The run diagram is generated from the live graph.
- A feature owns its knob, its tools and its prompt section as one unit, and a
  test fails if a declared prompt section is absent from the prompt claiming to
  own it.
- The run-knob table in the docs is checked against the source: a knob read in
  the code but undocumented, documented but unread, or documented with the
  wrong default, fails the build.

*Instead of:* documentation and prompts maintained in parallel with the code.
The failure this prevents is specific and was observed repeatedly: a flag that
appears to disable a feature while the agent is still instructed to use it.

*Costs:* generation makes the prompt harder to read as a single artifact —
which is why a provenance map exists that cites every prompt fragment back to
its source line.

HARVEST: `internal/tools/promptmap.py` and its contract; `runtime/features.py`;
`tests/test_settings_contract.py`; `tests/test_features.py`.

## 3.5 Provenance: recorded, not reconstructed

The run records, rather than re-derives: its outcome, **how** it terminated,
**whether anything reviewed it**, the resolved configuration it actually ran
with after precedence, and per-call telemetry broken down by role, phase and
model.

*Instead of:* inferring these afterwards from artifacts. The argument for this
is empirical and is the strongest single piece of evidence in the paper for the
whole provenance stance: when the outcome *was* inferred — grepped from the
run's own final report — backstop kills and critic-less runs both recorded as
validated successes, and those rows are still in the ledger (`threats.md` §1).

*Costs:* a schema to maintain, and a migration for historical rows, which
cannot be back-filled honestly and are left blank.

HARVEST: `runtime/terminal.py` docstring; `infra/telemetry.py`; the commits
that introduced them.

## 3.6 Resource governance

One hard boundary (a memory cap, for host safety) and soft budgets everywhere
else: evaluation budget nudges rather than stops, wall-clock and cost act as
resumable backstops rather than crashes.

*Instead of:* hard limits on the science. The distinction is deliberate — a
budget that kills a run mid-conclusion destroys the run's value, so backstops
checkpoint and halt resumably instead.

*Costs:* a resumable halt is a state the analysis must handle, and it is the
source of the censoring problem in the evaluation.

HARVEST: `nodes/lifecycle.py`; `runtime/run_setup.py` (`resolve_mem_cap_bytes`);
`internal/FEATURES.md` §D.

---

## What this section still owes

1. **The alternatives, in the author's voice.** Most "instead of" lines above
   are reconstructed from code comments. The real design alternatives — what
   was tried and abandoned — are in commit messages and in the backlog, and
   are more convincing than a retrospective rationalisation.
2. **A worked example.** One run, end to end, with the actual artifacts: the
   problem statement in, the hypotheses proposed, a delegation, a verdict and
   its referee ruling, the reproduction gate firing, the notebook out. The
   audits have the raw material.
3. **Honest costs.** Each mechanism's cost is asserted qualitatively above.
   Several are measurable from telemetry (`by_role`, `by_phase`) and should be
   quantified rather than described.
