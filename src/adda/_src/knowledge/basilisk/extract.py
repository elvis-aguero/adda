"""Extract Basilisk's source tree into indexable units.

Basilisk is not an importable package, so the introspection walk that indexes
f3dasm and adda cannot reach it. Nor do its headers parse standalone -- even
Basilisk's own parser fails on `two-phase.h`, because headers are fragments
that assume their dependencies are already in scope. So this reads the tree as
text, using markers the language itself defines.
"""
from __future__ import annotations

import itertools
import re
from collections import Counter
from pathlib import Path

_INCLUDE = re.compile(r'^\s*#\s*include\s+"([^"]+)"', re.M)
_TITLE = re.compile(r'^#\s+(.+)$', re.M)


def includes(path: Path) -> set[str]:
    """Quoted includes only -- angle-bracket includes are C stdlib, not Basilisk."""
    try:
        text = path.read_text(errors="ignore")
    except OSError:
        return set()
    return {h for h in _INCLUDE.findall(text) if h.endswith(".h")}


def _title(text: str) -> str:
    """The first Markdown H1 inside a literate block titles the unit."""
    m = _TITLE.search(text)
    return " ".join(m.group(1).split()) if m else ""


def example_index(src: Path) -> dict[str, dict]:
    """Every verified case in `test/` and `examples/`, keyed by relative path.

    These are the highest-value units in the corpus: worked code that compiles
    and runs, which is what an agent composing a new simulation should start
    from rather than assembling headers from first principles.
    """
    out: dict[str, dict] = {}
    for sub in ("test", "examples"):
        directory = src / sub
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.c")):
            hs = includes(path)
            if not hs:
                continue
            out[f"{sub}/{path.name}"] = {
                "title": _title(path.read_text(errors="ignore")),
                "headers": sorted(hs),
            }
    return out


def co_occurrence(index: dict[str, dict]
                  ) -> tuple[dict[frozenset, int], dict[str, int]]:
    """How often headers appear together across verified cases.

    This is the only available source of compatibility truth. Basilisk states
    its rules nowhere -- one `#error` in the entire tree and no prose ordering
    constraints -- but a pair that sixteen working cases stack is verified
    good, and a pair no case ever stacks is evidence of incompatibility. That
    is how alternative momentum solvers separate out with nothing labelled by
    hand: the layered shallow-water family and green-naghdi never appear
    alongside centered Navier-Stokes, because they solve the same thing a
    different way.
    """
    pairs: Counter = Counter()
    singles: Counter = Counter()
    for case in index.values():
        hs = case["headers"]
        singles.update(hs)
        for a, b in itertools.combinations(sorted(hs), 2):
            pairs[frozenset({a, b})] += 1
    return dict(pairs), dict(singles)
