# Tolerancing a thin-walled tube in axial compression

## Context
We buy thin-walled circular tube and use it as a pin-ended compression strut.
Tightening a tolerance costs money, so we want to spend it on whichever
dimensions actually govern the capacity, and we want to know what happens to
that answer across the range of sizes we buy, not just at one nominal size.

## Objective
Using the oracle, determine what governs the axial capacity `P_cr` across the
design space below, and give the supplier a tolerance recommendation that
holds over the whole range we buy — or, if no single recommendation holds,
say what the range must be split into and where.

Support whatever you conclude with evidence from the data you generate.

## Success criteria
The deliverable answers, with evidence:
- what a change in each of `E`, `R`, `t`, `L` does to `P_cr`, and whether that
  answer is the same everywhere in the design space;
- the tolerance recommendation, stated so a supplier could act on it;
- how the design points were chosen and how many evaluations were used.

A recommendation that a reader cannot act on, or that is contradicted
elsewhere in the same design space, does not meet the criteria.

## Design space
| variable | type | bounds | units |
|---|---|---|---|
| `E` | continuous | [60e9, 210e9] | Pa |
| `R` | continuous | [0.010, 0.040] | m |
| `t` | continuous | [0.0005, 0.0030] | m |
| `L` | continuous | [0.15, 0.70] | m |

The oracle's thin-wall assumptions hold where `t < R/5`. Outside that the
returned number is not physically meaningful.

## Oracle
`workspace/evaluator.py:evaluate` — kwargs `E`, `R`, `t`, `L`; returns `P_cr`
in newtons. Declared in `config.yaml` under `evaluator.entrypoint`.

## Deliverables
- `pipeline.ipynb` — the single deliverable. Its leading markdown cells carry
  the answer and the evidence; its code cells are the lazy f3dasm Pipeline
  that produced the data. Re-executed, it reproduces its numbers from the
  canonical ledger with no new evaluations.
