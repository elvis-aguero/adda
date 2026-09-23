"""Three-node wet run: strategizer -> {datagenerator, implementer}, all Haiku.

Why these three and not the stock five. The task needs a DataGenerator built
from the supplied callable (DataGeneratorAgent), and it needs somebody to
actually sample the space and call the evaluator -- which is the implementer's
exclusive job: "You are the ONLY agent that calls the evaluator." Without it
nothing would ever be measured. No literature_reviewer, because the question is
answered from the run's own data rather than from papers. No critic, which is
the cost of this topology and is stated plainly below.

WHAT THIS RUN CANNOT TELL YOU: with no critic there is no critic gate, so the
run closes UNGATED and nothing independent has reviewed the findings. Read the
deliverable as a draft, not as a validated result.

Usage:
  uv run python studies/tube_buckling_sensitivity/run.py
"""
from __future__ import annotations

from pathlib import Path

from adda import (
    AgenticRun,
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
        },
        edges=(
            Edge("strategizer", "datagenerator"),
            Edge("strategizer", "implementer"),
        ),
        entry="strategizer",
    )


def main() -> None:
    report = AgenticRun(
        study_dir=STUDY_DIR,
        graph=build_graph(),
        interactive=False,
    ).execute()
    print(report)


if __name__ == "__main__":
    main()
