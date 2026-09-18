import os
from pathlib import Path

import pytest

from adda._src.knowledge.basilisk.index import BasiliskIndex

SRC = Path(os.environ.get(
    "ADDA_BASILISK_SRC",
    "/oscar/data/dharri15/eaguerov/basilisk-2025-04")) / "src"

pytestmark = pytest.mark.skipif(not SRC.is_dir(), reason="no Basilisk corpus")


@pytest.fixture(scope="module")
def idx():
    return BasiliskIndex.build(SRC)


def test_a_known_key_returns_its_entry_not_a_menu(idx):
    out = idx.consult("two-phase.h")
    assert "Two-phase interfacial flows" in out
    assert "PROVIDES" in out


def test_a_description_returns_a_menu(idx):
    out = idx.consult("surface tension between two fluids")
    assert "tension.h" in out


def test_an_entry_names_its_verified_companions(idx):
    out = idx.consult("two-phase.h")
    assert "navier-stokes/centered.h" in out


def test_an_entry_names_what_it_never_combines_with(idx):
    """The RULE tier in one assertion: Basilisk says this nowhere."""
    out = idx.consult("navier-stokes/centered.h")
    assert "NEVER STACKED WITH" in out
    assert "layered/hydro.h" in out


def test_an_entry_names_worked_examples(idx):
    out = idx.consult("two-phase.h")
    assert ".c" in out


def test_source_flag_returns_actual_source(idx):
    out = idx.consult("two-phase.h", source=True)
    assert "#include" in out


def test_a_miss_says_what_a_miss_means(idx):
    out = idx.consult("zzzz_not_a_basilisk_concept_zzzz")
    assert "not a Basilisk" in out


def test_limit_is_respected(idx):
    out = idx.consult("flow", limit=3)
    assert len([ln for ln in out.splitlines() if ln.startswith("  ")]) <= 3


def test_never_stacked_excludes_what_arrives_transitively(idx):
    """An absence carries no information if you get the header anyway.

    `two-phase.h` reaches `fractions.h` through `vof.h`, and reaches `utils.h`
    through the centered solver it is verified with, so no case names either
    separately. Reporting them as "never stacked, usually an alternative
    solver" would be the exact opposite of the truth.
    """
    out = idx.consult("two-phase.h")
    never = next(ln for ln in out.splitlines() if ln.startswith("NEVER"))
    assert "fractions.h" not in never
    assert "utils.h" not in never
    # what remains must be genuine alternatives
    assert "layered/hydro.h" in never
    assert "saint-venant.h" in never
