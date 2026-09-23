"""Critical buckling load of a pin-ended thin-walled circular tube.

Euler buckling with the thin-wall second moment of area:

    I    = pi * R**3 * t          (thin wall, t << R)
    P_cr = pi**2 * E * I / L**2
         = pi**3 * E * R**3 * t / L**2

Deterministic and analytic: the study is about which parameter dominates and
whether the parameters interact, not about solver cost.
"""
from __future__ import annotations

import math


def evaluate(E: float, R: float, t: float, L: float) -> float:
    """Return P_cr in newtons for one tube geometry."""
    I = math.pi * R**3 * t
    return math.pi**2 * E * I / L**2
