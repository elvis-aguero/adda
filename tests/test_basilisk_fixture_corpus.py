"""The Basilisk pipeline, exercised in CI against a synthetic corpus.

Every other Basilisk test skips without a real checkout, so before this file
the extractor, the index, the ranker and the compatibility derivation were
verified by nobody but their author on a machine nobody else has. These assert
the BEHAVIOUR those tests describe, on a tree that travels with the repository.

They deliberately do NOT assert retrieval quality. Quality is a property of the
real corpus and is measured against it; a synthetic tree would only measure how
well the fixture was written to flatter the ranker.
"""
from __future__ import annotations

import pytest

from adda._src.knowledge.basilisk.extract import (
    card, closure, co_occurrence, example_index, header_index, includes)
from adda._src.knowledge.basilisk.index import BasiliskIndex

from .basilisk_fixture import build_corpus


@pytest.fixture(scope="module")
def src(tmp_path_factory):
    return build_corpus(tmp_path_factory.mktemp("basilisk"))


@pytest.fixture(scope="module")
def index(src):
    return BasiliskIndex.build(src)


# --- extraction --------------------------------------------------------------

def test_only_quoted_includes_are_basilisk(src):
    """Angle-bracket includes are C stdlib. Every case here has one, so a
    reader that took them would report stdio.h as a solver dependency."""
    got = includes(src / "test" / "bubble_rise.c")
    assert "navier-stokes/centered.h" in got
    assert not any(h.startswith("stdio") for h in got)


def test_every_case_is_indexed_with_its_title_and_headers(src):
    idx = example_index(src)
    assert len(idx) == 18
    assert idx["test/bubble_rise.c"]["title"] == "Rising bubble in a tank"
    assert "two-phase.h" in idx["test/bubble_rise.c"]["headers"]
    assert any(k.startswith("test/") for k in idx)
    assert any(k.startswith("examples/") for k in idx)


def test_a_card_separates_what_a_header_provides_from_what_it_asks_for(src):
    """`(const)` is Basilisk's own marker for user-supplied, and a field
    carrying it must not also be reported as provided."""
    c = card(src / "navier-stokes" / "centered.h", "navier-stokes/centered.h")
    assert "pressure_c" in c["provides"]
    assert "viscosity_mu" in c["requires"]
    assert "viscosity_mu" not in c["provides"], (
        "a (const) field is the user's to supply, not the header's to give")
    assert c["summary"] == "Centered Navier-Stokes"


def test_transitive_includes_are_followed(src):
    """two-phase.h reaches fractions.h through vof.h. The whole compatibility
    correction depends on this being true."""
    assert closure(src, "two-phase.h") >= {"two-phase.h", "vof.h", "fractions.h"}


def test_the_generated_parser_directory_is_never_indexed(src):
    """ast/ is Basilisk's yacc output: machine-generated C with no physics,
    and the single largest dense artifact in the real tree."""
    (src / "ast").mkdir(exist_ok=True)
    (src / "ast" / "grammar.h").write_text("scalar yy_noise[];\n")
    assert "ast/grammar.h" not in header_index(src)


# --- the derivation the tool exists for --------------------------------------

def test_co_occurrence_counts_what_cases_actually_stack(src):
    pairs, singles = co_occurrence(example_index(src))
    assert singles["navier-stokes/centered.h"] == 9
    assert singles["saint-venant.h"] == 8
    assert pairs[frozenset({"navier-stokes/centered.h", "two-phase.h"})] == 6


def test_an_alternative_solver_is_derived_as_never_stacked(index):
    """Nothing labels saint-venant.h as an alternative to centered Navier-
    Stokes. The index must work it out from nine cases using one and eight
    using the other, with no case using both."""
    good, never = index._companions("navier-stokes/centered.h")
    assert "two-phase.h" in good
    assert "saint-venant.h" in never


def test_a_header_reached_transitively_is_never_called_incompatible(index):
    """The correction that makes this tier safe. two-phase.h and fractions.h
    never appear together in a case's include list -- because two-phase.h
    already pulls fractions.h in through vof.h. Reading that absence as
    incompatibility invents a constraint the physics does not have, which is
    worse than returning nothing."""
    _, never = index._companions("two-phase.h")
    assert "fractions.h" not in never
    assert "vof.h" not in never


def test_a_thinly_used_header_is_never_called_incompatible(index):
    """_ESTABLISHED = 8: an absence is only evidence when the header is
    common enough that its absence could have been otherwise."""
    for key in index.headers:
        _, never = index._companions(key)
        for h in never:
            assert index.singles[h] >= 8, (
                f"{h} is used by {index.singles.get(h)} cases; its absence "
                f"beside {key} carries no information")


# --- the tool surface --------------------------------------------------------

def test_an_exact_key_returns_its_entry_not_a_menu(index):
    out = index.consult("two-phase.h")
    assert out.startswith("two-phase.h")
    assert "VERIFIED WITH" in out


def test_a_phrase_returns_a_menu_of_keys(index):
    out = index.consult("rising bubble")
    assert "match(es)" in out
    assert "test/bubble_rise.c" in out


def test_a_miss_says_what_it_searched(index):
    out = index.consult("kubernetes helm chart")
    assert "Basilisk" in out
    assert "does not exist" in out


def test_source_is_returned_only_when_asked(index):
    assert "event ns_projection" not in index.consult("navier-stokes/centered.h")
    assert "event ns_projection" in index.consult(
        "navier-stokes/centered.h", source=True)
