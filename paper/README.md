# `paper/` — the draft, and the record it is drawn from

This tree is the working draft of a paper about a3dasm. It is **not** user
documentation. `docs/` is for someone trying to run a study; this is for
someone deciding whether to believe the design.

Keeping them apart is deliberate. User docs are organised by task ("author a
study", "watch a run"); a paper is organised by argument (claim, evidence,
threat). Writing one in the other's shape makes the docs unreadable and the
paper unconvincing, and the two rot at different rates — docs track the code,
a draft tracks what we can defend.

## Status

| File | What it is | State |
|---|---|---|
| `OUTLINE.md` | Section skeleton, with what is venue-dependent marked | drafted |
| `related-work.md` | Literature read in full, with what transfers and what does not | drafted, thin |
| `evaluation-design.md` | The ablation design and the statistics that constrain it | drafted |
| `threats.md` | Limitations, collected in one place | drafted |
| `method.md` | The design as an argument, not an inventory | first pass |
| results | — | **blocked on the ablation runs** |

**The venue is undecided**, so everything here is written to be
venue-independent. What changes with the venue: the thesis sentence, which
related work gets weight, and the headline of the evaluation. What does not:
the method argument, the empirical record, the evaluation design, the threats.
Those are what this tree contains.

## Where the material comes from

Most of the raw material already exists in the repository and has not been
harvested. In rough order of value:

- **`internal/AUDIT-20260623.md`** and `-reruns.md` — real KPI tables from wet
  runs: run ids, feature combinations, outcome, gate attempts, evals, wall
  clock, diagnostics. Already the shape an ablation table needs.
- **`internal/BACKLOG.md`** — 35 numbered defects with root causes, the run
  that exposed each, and what it cost. This is the honest record of what
  breaks when you build epistemic scaffolding, and it is the answer to a
  reviewer asking how we know any of it works.
- **`studies/run_ledger.csv`** — 76 runs of telemetry across 66 commits. Not
  an experiment (see `evaluation-design.md`), but the source of every variance
  and dose figure quoted here.
- **`internal/FEATURES.md`** — the feature catalog, with an enforced contract
  that every agent tool appears in it. Organised by implementation; the method
  section reorganises it by argument.
- **`internal/OPEN_DESIGN_SPACE_FRAMEWORK.md`** — design spec written as
  methodology, including a "decisive test before any code".
- **Code comments and commit messages.** A large share of the *rationale* —
  why a design and not the obvious alternative — is written at the point of
  implementation. That is a genuine asset of this repository and it is almost
  entirely unharvested. Harvesting it is the bulk of `method.md`.

## Rules for this tree

1. **Every number carries its source.** A figure in this tree names the file it
   was computed from, and is reproducible from the repository. A figure we
   cannot recompute does not go in.
2. **Separate what we measured from what we believe.** Design rationale is
   argument; run figures are evidence; anything else is labelled as a
   conjecture and stays out of the claims.
3. **Negative results stay.** The backlog is full of things that did not work,
   including several where a feature appeared to be on and was not. Those are
   the most defensible content here, not an embarrassment to be tidied.
4. **No claim of novelty without having read the thing it is novel against.**
   `related-work.md` records which papers were read in full and which are
   title-only. Only the former may be argued with.
