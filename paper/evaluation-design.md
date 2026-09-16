# Evaluation design

Fixed before any run, so the analysis cannot be chosen after seeing the data.
Every figure below is computed from `studies/run_ledger.csv` in this
repository and is reproducible from it.

## What the existing data is, and is not

`studies/run_ledger.csv` holds **76 runs across 66 distinct commits** — close
to one commit per run. It is a longitudinal log, not an experiment: every row
confounds a feature change with everything else in that diff. It is used here
**only** to estimate variance and activation rates, never as a result.

The anchor study is `agentic_black_box_3d`, n=46:

| outcome | n |
|---|---|
| GATED | 28 (60.9%) |
| UNGATED | 6 |
| FAILED | 2 |
| watchdog_killed | 10 |

## Two findings that constrain the whole design

### Dose: most features do nothing in most runs

Activation rate per signal, measured as the fraction of the 46 anchor runs in
which it fired at least once (`diagnostics` column):

| signal | runs | rate |
|---|---|---|
| MILESTONE_BLOCK | 43 | 93.5% |
| ERROR_RETURN | 36 | 78.3% |
| **SCIENCE_DRIFT** | **9** | **19.6%** |
| CONSISTENCY_FLAG | 7 | 15.2% |
| REPRO_GATE_BOUNCE | 6 | 13.0% |
| VERDICT_SUBSTANCE_FLAG | 4 | 8.7% |

A feature that does nothing in 80% of runs has an intent-to-treat effect near
1.0 whatever its effect on the runs it touches. If the true effect among
treated runs is 1.5×, the ITT effect is roughly 1.08×, and the sample size
needed rises by more than an order of magnitude at the same variance.

**Consequence:** the activation rate is a pre-registered manipulation check,
reported per arm. Features below roughly 20% dose are reported as
**descriptive, not inferential** — we say what happened, we do not claim an
effect. Ablating the science monitor or the verdict validator as if they were
high-dose interventions would be a power error dressed as a null result.

### Censoring: the endpoint is missing exactly where it matters

All **10 watchdog-killed runs carry no token and no cost data** (verified:
10/46 rows have an empty `output_tokens`, and all ten are watchdog-killed). The
watchdog is an *external* wall-clock cutoff, not an error condition — at least
one killed run had already reached a critic PASS
(`internal/AUDIT-20260623.md`).

So the continuous endpoint is computed over survivors only, and survival is
post-treatment. **If disabling a feature makes runs hang, those runs vanish
from the token analysis and the survivors look cheaper** — an arm could be
reported as a cost saving when it actually broke the system. Runs are also
right-censored at `run_backstop_multiple × budget`, truncating any effect that
lengthens runs while shifting mass into the unmeasured stratum.

**Consequences, all pre-registered:**

1. `watchdog_killed` and `FAILED` are never pooled. Killed runs are reported as
   right-censoring; failures as failures.
2. Completion rate is reported per arm, beside the endpoint, always.
3. The token result is stated as conditional on completion, and a cost
   difference from an arm whose completion rate differs materially from
   baseline is flagged, not interpreted.
4. Attrition changes the budget: 10/46 = 21.7% loss means retaining 10 usable
   runs per arm needs ≈13 launched.

## Endpoints

**Primary (continuous): tokens to outcome.** From the anchor study's 36
completed runs, the log-scale spread is small:

| metric | sd(log) | n/arm for 1.5× | for 2× |
|---|---|---|---|
| output_tokens | 0.321 | 10 | 4 |
| cost_usd | 0.354 | 12 | 5 |
| delegations | 0.438 | 19 | 7 |
| ledger_rows | 1.064 | 109 | 37 |

**Secondary (binary): success rate**, reported with a Wilson interval and an
explicit underpowered label. For two proportions at α=0.05 two-sided and 80%
power,

$$n = \frac{\left(z_{\alpha/2}\sqrt{2\bar p\bar q} + z_{\beta}\sqrt{p_1q_1 + p_2q_2}\right)^2}{(p_1-p_2)^2}$$

and detecting a shift from the observed 0.61 to 0.71 needs ≈351 runs per arm.
That is why the binary endpoint cannot be primary on a paid model.

`ledger_rows` is excluded as an endpoint: at sd(log)=1.064 it is noise at this
scale.

Two cautions carried from the caveats above: the variance estimate is
conditional on completion, and it comes from runs spanning many commits, so it
is if anything an over-estimate — paired arms should be tighter, making n=10
conservative. **On an open-weight backend `cost_usd` is unavailable entirely**
(no self-hosted backend reports a price), so tokens and wall-clock carry the
analysis there.

## Design

Leave-one-out against a full baseline. Twelve factors full-factorial is 4096
cells and is not on the table; a pair is promoted to a $2^k$ design only where
OFAT suggests coupling.

- Model pinned, and named in the writeup. AbaqusAgent's own table moves from
  90%/90% to 65%/45% across models at fixed architecture.
- Arm order randomized across the whole sweep, so condition is not confounded
  with time (a sequential sweep runs for days; model behaviour can shift).
- Replicate treated as a blocking factor.
- Analysis on the log scale: geometric mean ratio with CI for tokens; Wilson
  interval for rates.

### What is and is not ablatable

| factor | dose | status |
|---|---|---|
| hypothesis ledger | high | inferential — but a **partial** ablation, see below |
| milestones | 93% | inferential |
| critic node | high | needs an external blinded judge; `outcome` is unusable |
| literature reviewer node | high | cleanest arm; its prompt already hedges "WHEN PRESENT" |
| retrieval mode / citation weighting | high | needs the resolved mode asserted per run |
| science monitor | 20% | descriptive |
| verdict validator | 9% | descriptive |
| reproduction gate | 13% | descriptive |
| delegation log | — | **not ablatable**: it is run substrate (delegation-id allocation, Done() liveness reconciliation, the critic's evidence block, SUPPORTED-confirm) |

**The critic arm cannot use the run outcome.** With no critic in the graph
there is nothing to review the conclusion, so "success" would be recorded by
the agent's own say-so. It needs a post-hoc judge over the archived
deliverable, blinded to condition.

**The hypothesis-ledger arm is partial and must be reported as such.** Its
tools and its own prompt section can be withheld, but the Popperian workflow is
the strategizer's operating model — argued, enforced and resolved across three
other prompt sections that are the agent's scientific method rather than ledger
documentation. Removing those too would not be an ablation; it would be a
different agent.

## Unanswered before the first run

**What is the baseline?** Leave-one-out gives within-system comparisons. It
does not answer "compared to what" — an agent with no scaffolding at all, a
competent human, or the same system on an easier problem. This has to be named
before the runs, not chosen after seeing them.

**Is the task set off the floor?** If baseline success on the target problems
is near zero, no ablation can move it and the study reports nothing. Confirm
from a pilot; if it is on the floor, the fix is an easier task tier, not a
larger n.

**A pilot is required.** Every figure on this page was measured on Claude runs
of one study. On a different model and a different task set the variance, the
completion rate, the activation rates and the baseline will all differ. Roughly
10 baseline runs, measured, before any arm is sized.
