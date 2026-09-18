import os
from pathlib import Path

import pytest

from adda._src.knowledge.basilisk.extract import (co_occurrence, example_index,
                                                  includes)

_ROOT = os.environ.get("ADDA_BASILISK_SRC", "")
#: Guarded on the ENV VAR, never on whether a path happens to exist. An empty
#: default made ``Path("") / "src"`` resolve to this repository's own src/,
#: which exists -- so the suite silently stopped skipping and scored the index
#: against adda's Python instead of a Basilisk checkout.
SRC = Path(_ROOT) / "src" if _ROOT else None

corpus = pytest.mark.corpus


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


from adda._src.knowledge.basilisk.extract import card, header_index  # noqa: E402


@corpus
def test_card_reads_the_centered_solver_contract():
    c = card(SRC / "navier-stokes/centered.h", "navier-stokes/centered.h")
    assert "Navier" in c["summary"]
    # fields the header DECLARES for you
    assert {"p", "u", "g", "pf", "uf"} <= set(c["provides"])
    # fields the USER must supply -- Basilisk marks these with (const)
    assert {"mu", "a", "alpha", "rho"} <= set(c["requires"])
    # extension points
    assert "projection" in c["events"]
    assert "acceleration" in c["events"]
    assert len(c["events"]) == 15


@corpus
def test_card_records_defaults_for_required_fields():
    c = card(SRC / "navier-stokes/centered.h", "navier-stokes/centered.h")
    assert c["requires"]["mu"] == "zerof"
    assert c["requires"]["alpha"] == "unityf"


@corpus
def test_a_required_field_is_not_also_reported_as_provided():
    c = card(SRC / "navier-stokes/centered.h", "navier-stokes/centered.h")
    assert not (set(c["provides"]) & set(c["requires"]))


@corpus
def test_header_index_covers_the_solver_library_and_skips_the_parser():
    idx = header_index(SRC)
    assert len(idx) > 250
    assert "two-phase.h" in idx
    assert not any(k.startswith("ast/") for k in idx)


@corpus
def test_provides_is_the_interface_not_the_internals():
    """Basilisk declares file-scope fields flush left and function-local
    temporaries indented. `alphav`, `du` and a loop's `s` are scratch
    variables inside events in centered.h; reporting them as fields the header
    PROVIDES would invite an agent to use names that do not exist at file
    scope."""
    c = card(SRC / "navier-stokes/centered.h", "navier-stokes/centered.h")
    assert set(c["provides"]) == {"p", "u", "g", "pf", "uf"}
    for scratch in ("alphav", "du", "s", "af", "gf"):
        assert scratch not in c["provides"]
