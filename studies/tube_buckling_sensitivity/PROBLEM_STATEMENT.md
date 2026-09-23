# Which parameter controls the buckling load of a thin-walled tube?

## Context
A thin-walled circular tube is used as a pin-ended compression strut. Before we
commit to a tolerance spec with the supplier, we need to know which of its four
parameters actually drives the critical buckling load over the ranges we can
buy, and whether any two of them interact strongly enough that they cannot be
toleranced independently of one another.

## Objective
Build the dataset and, from it, answer two questions:

1. Rank `E`, `R`, `t` and `L` by their influence on `P_cr` over the ranges
   below.
2. State whether any pair of parameters interacts — that is, whether the effect
   of one depends on the level of another — and give the evidence.

## Success criteria
The deliverable reports:
- the ranking, with the quantitative basis for it;
- the interaction answer, with the evidence that supports it;
- how the design points were chosen, and how many evaluations were used.

A ranking asserted without data behind it does not meet the criteria. Neither
does an interaction claim that rests on a single pair of points.

## Design space
| variable | type | bounds | units |
|---|---|---|---|
| `E` | continuous | [60e9, 210e9] | Pa |
| `R` | continuous | [0.010, 0.040] | m |
| `t` | continuous | [0.0005, 0.0030] | m |
| `L` | continuous | [0.30, 1.20] | m |

The thin-wall assumption behind the oracle holds only where `t < R/5`. Outside
that, the returned number is not physically meaningful.

## Oracle
`workspace/evaluator.py:evaluate` — kwargs `E`, `R`, `t`, `L`; returns `P_cr`
in newtons. Declared in `config.yaml` under `evaluator.entrypoint`.

## Deliverables
- `pipeline.ipynb` — the single deliverable. Its leading markdown cells carry
  the ranking, the interaction answer and the evidence; its code cells are the
  lazy f3dasm Pipeline that produced the dataset. Re-executed, it reproduces
  its numbers from the canonical ledger with no new evaluations.
