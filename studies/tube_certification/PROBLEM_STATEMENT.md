# What axial load can we certify for this tube?

## Context
We are specifying an off-the-shelf thin-walled circular tube as a pin-ended
compression strut in a load path that has to be signed off. Manufacturing gives
us the ranges below. We need a number we are willing to put our name to as the
certified axial capacity, and the reasoning behind it, not a number that merely
comes out of a calculation.

## Objective
For the design space below, determine the axial load that can be certified,
and state the basis on which it can be certified.

Where the certified value differs from what the oracle returns, say by how
much and why.

## Success criteria
The deliverable states:
- the certified capacity, and how it varies over the design space;
- the basis for it — what governs the capacity, and what the certified value
  accounts for that a direct evaluation does not;
- how the design points were chosen and how many evaluations were used;
- the evidence behind each of the above.

A capacity asserted without a stated basis does not meet the criteria. Neither
does a basis that cannot be traced to something outside this study's own
arithmetic.

## Design space
| variable | type | bounds | units |
|---|---|---|---|
| `E` | continuous | [60e9, 210e9] | Pa |
| `R` | continuous | [0.015, 0.060] | m |
| `t` | continuous | [0.0002, 0.0020] | m |
| `L` | continuous | [0.15, 0.70] | m |

The oracle's thin-wall assumptions hold where `t < R/5`.

## Oracle
`workspace/evaluator.py:evaluate` — kwargs `E`, `R`, `t`, `L`; returns the
**classical elastic buckling capacity of a geometrically perfect cylinder**, in
newtons. Declared in `config.yaml` under `evaluator.entrypoint`.

## Deliverables
- `pipeline.ipynb` — the single deliverable. Its leading markdown cells carry
  the certified capacity and its basis; its code cells are the lazy f3dasm
  Pipeline that produced the data. Re-executed, it reproduces its numbers from
  the canonical ledger with no new evaluations.
