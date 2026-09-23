"""Four-node wet run: strategizer -> {datagenerator, implementer, critic}, Haiku.

WHY FOUR NODES. The prior run (tube_buckling_sensitivity, 20260920T005201)
closed in 470 s on two delegations and got its headline answer wrong while
looking rigorous: it fitted in log space, where a multiplicative oracle is
exactly additive, found no interaction terms, and recommended tolerancing the
parameters independently. Nothing in that graph was positioned to ask whether
the coordinates it chose answered the question that was asked. The critic is
here to be that thing.

WHY THIS PROBLEM. The same run's strategizer pre-specified the whole method in
one delegation -- "120-point Latin Hypercube, seed=42" -- and asked the
implementer only for descriptive statistics. The scientific question never
reached the node doing the work, and no node ever faced a choice worth
observing. A four-factor screen is a recognisable pattern, so it got a recipe
from memory. This oracle is the lower of two failure mechanisms whose
parameter dependence has nothing in common, so the method cannot be read off
the statement: what to do depends on what the data turns out to look like.

Usage:
  uv run python studies/tube_buckling_regimes/run.py
"""
from __future__ import annotations

from pathlib import Path

from adda import (
    AgenticRun,
    AdversarialCritiqueAgent,
    DataGeneratorAgent,
    Edge,
    F3dasmImplementerAgent,
    Graph,
    StrategizerAgent,
)

STUDY_DIR = Path(__file__).parent


def build_graph() -> Graph:
    return Graph(
        nodes={
            "strategizer": StrategizerAgent(),
            "datagenerator": DataGeneratorAgent(),
            "implementer": F3dasmImplementerAgent(),
            "critic": AdversarialCritiqueAgent(),
        },
        edges=(
            Edge("strategizer", "datagenerator"),
            Edge("strategizer", "implementer"),
            Edge("strategizer", "critic"),
        ),
        entry="strategizer",
    )


def main() -> None:
    print(AgenticRun(study_dir=STUDY_DIR, graph=build_graph(),
                     interactive=False).execute())


if __name__ == "__main__":
    main()
