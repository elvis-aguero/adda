# Outline

Sections marked **[venue]** change with the target venue and are deliberately
left as questions rather than guessed at. Everything else is venue-independent
and is where the work should go now.

---

## 1. Introduction **[venue]**

The thesis sentence is undecided because the venue is. Three framings the
material can carry, with what each would have to defend:

| Framing | Claim | Must defend |
|---|---|---|
| Agents / ML systems | Epistemic scaffolding (hypothesis ledger, falsification charter, live verdict referee, drift monitor) measurably changes what an autonomous research agent produces | That the scaffolding does something a better prompt would not; ablations are the expected evidence |
| Computational mechanics | An agentic layer over f3dasm that takes a problem statement to a reproducing notebook | That the science it produces is correct and non-trivial, on real design problems |
| Software | The tool, its architecture, its interfaces | Only that it works and is usable; no novelty claim |

What is defensible in all three, and is the honest core of the contribution:

- The system closes every run with a **notebook that has been executed and
  reproduced before the run is allowed to close**, not written up afterwards.
- Claims are carried in a **falsifiable ledger with verdicts**, and the
  verdicts are refereed against a written charter at the moment of assertion.
- Everything the agent is told is **generated from the live system** rather
  than typed — tool catalog from live closures, run diagram from the live
  graph — so the prompt cannot drift from the code.
- The run's **provenance is recorded rather than reconstructed**: outcome,
  termination, whether anything reviewed it, the resolved configuration, and
  per-call telemetry.

## 2. Related work **[venue for emphasis]**

See `related-work.md`. Four papers read in full. The survey is thin and is the
single largest known gap.

## 3. Method

See `method.md`. Structure:

3.1 The graph and the open loop
3.2 The epistemic layer — ledger, charter, referee, monitor
3.3 The deliverable and the reproduction gate
3.4 Anti-drift: generated, not typed
3.5 Provenance and the run record
3.6 Resource governance

Each subsection owes the reader: what it does, what it is instead of, and what
it costs.

## 4. Implementation

Short. The graph is LangGraph; the primitives are f3dasm; the agent surface is
declared per role. The interesting part is 3.4 and belongs there, not here.

## 5. Evaluation

See `evaluation-design.md`. **Blocked on runs.** The design is fixed, the
statistics that constrain it are computed, and the instrument is in place. The
headline table is a leave-one-out ablation with a continuous primary endpoint.

## 6. Threats to validity

See `threats.md`. Unusually important here: several of the threats are ones we
found by having the system lie to us, and they are more convincing stated
plainly than minimised.

## 7. Limitations and future work

Includes the pieces deliberately not built: full run-scoped isolation, a
labelled retrieval query set, the documentation-as-traversable-tree idea.

## 8. Reproducibility statement

The repository, the pinned model, the study definitions, the run ledger, and
which figures in the paper are recomputable from which files. Write this early
— it disciplines the rest.

---

## What blocks what

```
venue decision ──> §1 thesis ──> §2 emphasis ──> §5 headline
                                                      │
run isolation ──> sweep layer ──> ablation runs ──────┴──> §5 results
                                                           §6 (dose, censoring)
harvest (code comments, BACKLOG, AUDIT) ──> §3 method ──> §7
```

Nothing except §1, §2's emphasis and §5's results is blocked. The method
harvest is the largest piece of writeable work and it can start now.

## Known gaps, ranked

1. **No results.** The evaluation is designed and unrun.
2. **Related work is four papers.** Enough to position against; not a survey.
3. **The method argument is unharvested** — the rationale lives in code
   comments and commit messages, not in prose.
4. **No baseline.** "Compared to what" is unanswered: an agent with no
   scaffolding, a human, or the same agent on an easier task? §5 needs this
   named before the runs, not after.
5. **The anchor study is not in the repository.** Every variance figure quoted
   here comes from `agentic_black_box_3d`, which is not committed. Without it
   the numbers are not reproducible and the paper has no runnable baseline.
