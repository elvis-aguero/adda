"""Six-node all-Haiku run: LCP reformulation checked against a MATLAB baseline.

Every node is on Haiku deliberately — this run exists to exercise the full
graph (and the live viewer) end to end, not to produce the strongest
possible science.
"""
from __future__ import annotations

from pathlib import Path

from adda import (
    AgenticRun,
    DataGeneratorAgent,
    Edge,
    F3dasmImplementerAgent,
    Graph,
    LiteratureReviewAgent,
    MathExpertAgent,
    StrategizerAgent,
)
from adda._src.agents import AdversarialCritiqueAgent

STUDY_DIR = Path(__file__).parent


def build_graph() -> Graph:
    return Graph(
        nodes={
            "strategizer": StrategizerAgent(),
            "literature_reviewer": LiteratureReviewAgent(),
            "math_expert": MathExpertAgent(),
            "implementer": F3dasmImplementerAgent(),
            "datagenerator": DataGeneratorAgent(),
            "critic": AdversarialCritiqueAgent(),
        },
        edges=(
            Edge("strategizer", "literature_reviewer"),
            Edge("strategizer", "math_expert"),
            Edge("strategizer", "implementer"),
            Edge("strategizer", "datagenerator"),
            Edge("strategizer", "critic"),
            Edge("math_expert", "literature_reviewer"),
            Edge("implementer", "math_expert"),
        ),
        entry="strategizer",
    )


def main() -> None:
    report = AgenticRun(
        study_dir=STUDY_DIR,
        graph=build_graph(),
        # TTY-gated inside AgenticRun, so this only takes effect under tmux.
        interactive=True,
    ).execute()
    print(report)


if __name__ == "__main__":
    main()
