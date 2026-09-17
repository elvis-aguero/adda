---
id: surrogate-guided-optimization
title: Surrogate-guided optimization — the acquisition code the prompt leaves to you
tags: [surrogate, gaussian, process, gp, bayesian, optimization, acquisition, expected, improvement, ei, botorch, sklearn, exploit, loop, budget]
audience: [implementer]
---
Working code for the surrogate-guided exploit loop. The implementer prompt
states the RULES (budget guard first, CV before trusting a fit, one delegation
runs the whole loop) and shows the loop's skeleton, but deliberately does not
carry the acquisition implementation — it is ~60 lines that would be paid for
on every implementer call whether or not the delegation is an optimization.
This chapter is that implementation.

## The ledger contract still applies
Everything here is FREE except `evaluator.call(...)`. Fitting the GP, scoring
candidates, and optimising the acquisition are your own computation and are not
metered. Only the oracle call is. See `evaluate-through-get-evaluator` and
`surrogates-are-off-ledger`.

## Fit, and prove the fit before you trust it

```python
import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import Matern
from sklearn.model_selection import cross_val_score

X_train, y_train = data.to_numpy()          # tuple (X, y); to_numpy takes NO arg
y_train = y_train.ravel()

gp = GaussianProcessRegressor(
    kernel=Matern(nu=2.5), n_restarts_optimizer=5, alpha=1e-6,
    normalize_y=True, random_state=0,
)                                           # NOTE: no n_jobs — it raises TypeError
gp.fit(X_train, y_train)

cv_r2 = cross_val_score(gp, X_train, y_train, cv=5, scoring="r2").mean()
```

Report `cv_r2` before any conclusion rests on the surrogate. There is no
universal cutoff: state the fit quality the problem's noise floor makes
achievable, and if `cv_r2` falls short of it, say the surrogate is unreliable
and recommend more exploration rather than reporting its optimum as a result.

## `propose_ei` — Expected Improvement, for MINIMIZATION

The prompt's loop calls `propose_ei(gp, X_train, y_train.min(), bounds)`. You
write it. This version scores a large random candidate set, which needs no
extra dependency and is robust in the dimensionalities these studies use:

```python
from scipy.stats import norm

def propose_ei(gp, X_train, best_f, bounds, n_candidates=20000, xi=0.01, rng=None):
    """Return the (d,) point maximising Expected Improvement for a MINIMIZATION.

    bounds: array-like (d, 2) of (low, high) taken from the domain you built
    from the problem description -- NOT from a loaded store's domain.
    """
    rng = rng or np.random.default_rng(0)
    bounds = np.asarray(bounds, dtype=float)
    cand = rng.uniform(bounds[:, 0], bounds[:, 1], size=(n_candidates, bounds.shape[0]))

    mu, sigma = gp.predict(cand, return_std=True)
    imp = best_f - mu - xi                   # improvement is DOWNWARD
    with np.errstate(divide="ignore", invalid="ignore"):
        z = imp / sigma
        ei = imp * norm.cdf(z) + sigma * norm.pdf(z)
    ei[sigma <= 0.0] = 0.0                   # no uncertainty => no expected gain
    return cand[int(np.argmax(ei))]
```

Three things this gets right that a hand-rolled version usually does not:

- **Sign.** `best_f - mu`, not `mu - best_f`. These studies minimise; flipping
  it turns the acquisition into a search for the worst point, and the loop
  still runs and still burns budget.
- **`sigma == 0`.** At an already-evaluated point the predictive std is zero
  and `imp / sigma` is a division by zero. Zeroing EI there is what stops the
  loop re-proposing a point it has already paid for.
- **`xi`.** A small positive jitter biases toward exploration; at `xi = 0` the
  loop tends to collapse onto the incumbent.

For maximization, negate `y` when fitting and report `-best`. Do not flip the
formula.

## botorch — the GPU / higher-dimensional alternative

Same ledger contract, same budget guard. Use it when `d` is large enough that
random candidate scoring stops covering the space:

```python
import torch
from botorch.models import SingleTaskGP
from botorch.fit import fit_gpytorch_mll
from gpytorch.mlls import ExactMarginalLogLikelihood
from botorch.acquisition import qExpectedImprovement
from botorch.optim import optimize_acqf

lo, hi = bounds[:, 0], bounds[:, 1]
Xn = torch.tensor((X_train - lo) / (hi - lo), dtype=torch.double)   # to [0,1]^d
Y = torch.tensor(-y_train, dtype=torch.double).unsqueeze(-1)        # botorch MAXIMISES

model = SingleTaskGP(Xn, Y)
fit_gpytorch_mll(ExactMarginalLogLikelihood(model.likelihood, model))

unit = torch.stack([torch.zeros(Xn.shape[1], dtype=torch.double),
                    torch.ones(Xn.shape[1], dtype=torch.double)])
cand, _ = optimize_acqf(
    qExpectedImprovement(model, best_f=Y.max()), bounds=unit,
    q=1, num_restarts=10, raw_samples=256,
)
x_next = cand.detach().numpy().ravel() * (hi - lo) + lo              # back to real units
```

botorch **maximises**, so a minimization is fitted on `-y` and the reported
optimum negated back. Normalising inputs to the unit cube is not cosmetic —
the default priors assume it, and an unnormalised fit is quietly bad.

## Budget arithmetic, restated because it is where runs die

Cap the loop BEFORE entering it, from the remaining budget in the task brief:

```python
if budget_remaining <= 0:
    return
n_bo_steps = budget_remaining                       # EI proposes 1 point per step
max_iter = max(1, budget_remaining // (n_starts * (d + 1)))   # finite-difference local method
```

Derivative-free (Nelder-Mead) costs ≈ 1 oracle call per iteration;
finite-difference gradients (L-BFGS-B with `jac=None`) cost ≈ `d+1` forward or
`2d+1` central, with `d` the ACTUAL domain dimensionality — compute it from the
domain, never assume a factor.
