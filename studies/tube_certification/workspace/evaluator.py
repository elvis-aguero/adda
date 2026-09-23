"""Classical elastic buckling capacity of a perfect thin-walled circular tube.

Returns the lower of the two classical closed forms, since the tube gives way
by whichever mechanism reaches its critical value first:

  Euler (global) column buckling, pin-ended:
      I    = pi * R**3 * t
      P_e  = pi**2 * E * I / L**2

  Local shell buckling (axial wall crippling), classical elastic value:
      sigma_cr = E * t / (R * sqrt(3 * (1 - nu**2)))
      P_l      = sigma_cr * 2 * pi * R * t

Both assume a geometrically perfect cylinder of isotropic linear-elastic
material. Deterministic; no noise.
"""
from __future__ import annotations

import math

NU = 0.30  # Poisson's ratio, structural metals


def evaluate(E: float, R: float, t: float, L: float) -> float:
    """Return the classical elastic capacity P_cr in newtons."""
    P_euler = math.pi**2 * E * (math.pi * R**3 * t) / L**2
    sigma_local = E * t / (R * math.sqrt(3.0 * (1.0 - NU**2)))
    P_local = sigma_local * 2.0 * math.pi * R * t
    return min(P_euler, P_local)
