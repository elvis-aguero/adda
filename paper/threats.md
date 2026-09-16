# Threats to validity

Collected in one place because they are scattered across code comments, the
backlog and the audits, and because several of them are the most defensible
content the paper has. They were found by the system reporting something untrue
and being caught, which is a better argument for the provenance machinery than
any claim we could make for it.

---

## 1. Measurement threats — things the system got wrong about itself

These are not hypothetical. Each was live, each is in the historical data, and
each was found by reading the code rather than by the run failing loudly.

**The run's outcome was recovered by grepping its own prose.** Terminal state
was determined by searching the final report for banner strings and defaulting
to GATED when none matched. Two classes of non-success were therefore recorded
as validated successes: a run killed by the time backstop, the USD ceiling or
repeated errors (the HALTED banner matches no pattern), and any run in a graph
with no critic (no banner is emitted at all). **Rows of both kinds are in
`studies/run_ledger.csv` now.** Any analysis of the historical ledger must
treat `GATED` as unreliable before the fix.

**A feature's flag did not turn the feature off.** Tools are gated on a static
declaration, never on whether the backing object exists, and each role prompt
is one literal string. A disabled feature therefore left its tools registered
and its instructions in the prompt; the agent called a tool, received an error
string, and the run recorded an `ERROR_RETURN` diagnostic — the one KPI whose
target is zero. An arm built that way measures an agent confused by broken
tools. `internal/BACKLOG.md` #27, #28 and #30 are three successive rounds of
this for a single feature.

**Cost was unmeasured for an entire class of run.** Tokens and cost were parsed
out of the stamped deliverable, so a study configured without a notebook
recorded no cost at all (BACKLOG #31), and only two of the four token fields
survived — the two dropped were the cache fields, which are precisely what a
prompt-section change moves. Separately, unpriced calls were summed as `0.0`,
so a run on an open-weight backend reported a cost of zero, indistinguishable
from a run that was genuinely free.

**Implication for the paper.** Any figure computed from a run predating these
fixes inherits them. The reproducibility statement must say which figures come
from which side of that line, and the ablation must run on the fixed system.

## 2. Statistical threats

**Informative censoring.** The token endpoint exists only for runs that
finished, and 10 of 46 anchor runs carry no token data at all — every one of
them watchdog-killed. A feature that makes runs hang removes its own worst
cases from the endpoint. See `evaluation-design.md` for the pre-registered
handling.

**Dose.** Several features act in a minority of runs — the science monitor in
19.6%, the verdict validator in 8.7%. Their intent-to-treat effects are
attenuated toward 1.0 and they are reported descriptively.

**The variance prior does not transfer.** Every dispersion figure quoted was
measured on one study, one model, and runs spanning 66 commits. A different
model or task set changes all of it.

**No correction for multiplicity.** A leave-one-out sweep over ~12 factors is
~12 comparisons. Either pre-register the primary factor or report adjusted
intervals; do not do both post hoc.

## 3. Construct threats

**"Success" is the system's own gate.** GATED means a critic agent, running the
same model family, passed the conclusion. That is not ground truth. For the
critic ablation it is not even meaningful, since with no critic nothing
reviews the run.

**Partial ablations.** The hypothesis-ledger arm removes the machinery, not the
idea: the Popperian workflow is argued throughout the strategizer's method. The
arm answers "what does the ledger machinery buy on top of the framing", which
is a narrower question than "does hypothesis-driven operation help" and must be
reported as the narrower one.

**Judge and judged share a model.** The critic, the verdict referee and the
agent under review are the same family. Shared blind spots are invisible to
this design.

## 4. External validity

**One system, one framework.** Everything is measured on adda over f3dasm. No
claim transfers to other agentic research systems without re-measurement.

**Small task set.** The anchor study is a single black-box optimisation
problem, and **it is not committed to the repository** — which is both an
external-validity threat and a reproducibility defect.

**Model dependence is large and demonstrated.** AbaqusAgent's ablation moves
from 90%/90% to 65%/45% purely by changing the model at fixed architecture.
Any single-model result here is a statement about that model.

## 5. Threats we have chosen to accept

**Cross-run corpus reuse.** The literature corpus is study-scoped by design, so
a run can answer using papers acquired by an earlier run. This is deliberate —
re-embedding every run is waste — but it is a contamination channel for
literature arms specifically, and those arms need either a cold corpus or an
explicit note.

**Study-scope deliverable.** The notebook lives at the study root, so parallel
runs of one study are unsafe without a per-run copy. Sequential runs are fine.
The sweep layer owns this; the package does not fix it.

**No seed or temperature control.** There is none anywhere in the system, so
run-to-run variance is uncontrolled and replicates are the only handle. There
is no "same seed, one flag flipped" comparison available, and the paper should
not imply otherwise.
