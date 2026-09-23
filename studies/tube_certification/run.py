"""Five-node wet run: strategizer -> {literature, datagenerator, implementer, critic}.

WHY A LITERATURE REVIEWER, AND WHY THIS PROBLEM.

Two prior runs on this oracle family showed the knowledge tools were not
load-bearing: ConsultF3dasm was called twice in one run and not at all in the
other, because everything the agents needed was already in their prompts, and
where it was not they used Bash. A tool is only exercised by a question it is
the only way to answer.

So the certifiable capacity here cannot be computed from the oracle. The oracle
returns the classical elastic result for a GEOMETRICALLY PERFECT cylinder --
which it says plainly -- and for the thin shells in this design space (R/t up
to ~300) that is known to overstate real capacity substantially. The size of
that gap, and its dependence on R/t, is an empirical result that lives in the
literature and nowhere in this repository. An agent that only evaluates will
certify a number it cannot defend; the arithmetic will be flawless.

The regime structure (Euler vs local shell buckling, ~29/71 here) IS derivable
from the oracle. That part tests thought. The knockdown is what tests whether
anyone reads.

Nothing in PROBLEM_STATEMENT.md mentions imperfections, knockdown factors, or
the literature. It says "geometrically perfect cylinder", which is a true
description of the model, and asks for a number someone will sign.

Usage:
  uv run python studies/tube_certification/run.py
"""
from __future__ import annotations

from pathlib import Path

from adda import (
    AdversarialCritiqueAgent,
    AgenticRun,
    DataGeneratorAgent,
    Edge,
    F3dasmImplementerAgent,
    Graph,
    LiteratureReviewAgent,
    StrategizerAgent,
)

STUDY_DIR = Path(__file__).parent


def build_graph() -> Graph:
    return Graph(
        nodes={
            "strategizer": StrategizerAgent(),
            "literature_reviewer": LiteratureReviewAgent(),
            "datagenerator": DataGeneratorAgent(),
            "implementer": F3dasmImplementerAgent(),
            "critic": AdversarialCritiqueAgent(),
        },
        edges=(
            Edge("strategizer", "literature_reviewer"),
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
