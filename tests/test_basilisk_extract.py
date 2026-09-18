import os
from pathlib import Path

import pytest

from adda._src.knowledge.basilisk.extract import (co_occurrence, example_index,
                                                  includes)

SRC = Path(os.environ.get(
    "ADDA_BASILISK_SRC",
    "/oscar/data/dharri15/eaguerov/basilisk-2025-04")) / "src"

corpus = pytest.mark.skipif(not SRC.is_dir(), reason="no Basilisk corpus")


def test_includes_reads_quoted_includes_only(tmp_path):
    f = tmp_path / "x.c"
    f.write_text('#include "two-phase.h"\n#include <stdio.h>\n')
    assert includes(f) == {"two-phase.h"}


@corpus
def test_example_index_titles_the_cases():
    idx = example_index(SRC)
    assert idx["examples/bubble.c"]["title"] == "Bubble rising in a large tank"
    assert "navier-stokes/centered.h" in idx["examples/bubble.c"]["headers"]


@corpus
def test_example_index_covers_both_test_and_examples():
    idx = example_index(SRC)
    assert len(idx) > 200
    assert any(k.startswith("test/") for k in idx)
    assert any(k.startswith("examples/") for k in idx)


@corpus
def test_co_occurrence_finds_the_known_pairs():
    pairs, singles = co_occurrence(example_index(SRC))
    assert singles["navier-stokes/centered.h"] > 50
    assert pairs[frozenset({"navier-stokes/centered.h", "two-phase.h"})] >= 10


@corpus
def test_alternative_momentum_solvers_never_co_occur():
    """The physics the co-occurrence signal must reproduce: the layered
    shallow-water solver is an ALTERNATIVE to centered Navier-Stokes, so no
    verified case stacks them. Nobody labelled this; it falls out of the
    corpus, which is what makes the RULE tier answerable at all."""
    pairs, _ = co_occurrence(example_index(SRC))
    for other in ("layered/hydro.h", "layered/nh.h", "green-naghdi.h"):
        key = frozenset({"navier-stokes/centered.h", other})
        assert pairs.get(key, 0) == 0, f"unexpected co-occurrence with {other}"
