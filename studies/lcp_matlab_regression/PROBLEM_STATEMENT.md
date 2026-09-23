# LCP reformulation of the kinematic match, checked in MATLAB

Take a published contact model, re-express it as a Linear Complementarity
Problem, and prove numerically that the reformulation did not change the
physics. "Prove" here means MATLAB output, not argument.

## Source

Gabbard, Aguero, Cimpeanu, Kuehr, Silver, Barotta, Galeano-Rios & Harris,
**"Drop rebound at low Weber number"**, *JFM* vol. 1019 (2025), arXiv
`2505.00902`. The paper's own LaTeX source is at
`workspace/DropRebound_JFM.tex` — read it, do not work from memory of the
title or abstract.

The model is `\subsection{Kinematic match model formulation}`, and the four
contact-set conditions are in `\subsubsection{The kinematic match}`:
`eqn:km_contact_amplitudes`, `eqn:km_non-contact_amplitudes`,
`eqn:km_pressure_amplitudes`, `eqn:km_contact_derivative`. The evolution
equations the contact pressure couples into are `eqn:nd_dot_U_l_v01` and
`eqn:nd_dot_v`.

## What to produce

**1. Baseline.** Implement the kinematic match (KM) in MATLAB, in
`workspace/km_baseline.m`. Truncate the spherical-harmonic expansion at a
fixed, stated order. Given a set of parameters it must return the contact
radius, the pressure amplitudes, and the centre-of-mass trajectory over a
fixed number of steps.

**2. Regression fixture.** Run the baseline on at least five parameter sets
spanning the design space and write the outputs to
`workspace/baseline_results.json`. This file IS the regression baseline —
there is no external ground truth, and none should be invented.

**3. LCP reformulation.** Re-express the same contact problem as an LCP —
complementarity between gap and pressure — in `workspace/lcp_model.m`,
solving it with a documented pivoting or projection scheme.

**4. The actual claim.** Run the LCP model on the SAME five parameter sets
and compare against `baseline_results.json`. Report the maximum absolute
and relative deviation per output. State a tolerance BEFORE running and
say plainly whether it was met.

## Running MATLAB

`matlab -batch "<statements>"` from the study directory. A warm call takes
about 8 seconds; the first may take longer. Write `.m` files into
`workspace/` and call them by name. Everything reported must come from a
MATLAB run you actually executed in this run — no estimated or recalled
numbers.

## What counts as done

A reformulation that agrees with the baseline within a stated tolerance, or
an honest report of where it does not and why. A disagreement you found and
explained is a better outcome than a agreement you asserted.

If the LCP genuinely cannot reproduce a case, say so and identify which
condition breaks. Do not tune the tolerance to fit the result.

## Scope

No literature survey beyond what grounds the formulation. There is no
external dataset. If you register an oracle over the parameter space, keep
the evaluation count small — the budget is one hour of wall clock, and
MATLAB calls dominate it.
