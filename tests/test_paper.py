"""The paper draft, checked by the only means available here.

THERE IS NO LATEX TOOLCHAIN IN THIS CONTAINER. Nothing compiles the draft, so
a dangling ``\\input`` or a ``\\cite`` to a key that was never added would sit
undetected until someone tried to build it on another machine -- most likely
the week of a deadline. These tests check what can be checked without LaTeX.

They also enforce the two rules from ``paper/README.md`` that are mechanical
rather than editorial: a work may be cited in the related-work section only if
it was READ IN FULL, and a bibliography entry whose details are unverified must
say so. Both are otherwise honour-system rules, and an honour-system rule in a
document with a deadline is a rule that quietly stops holding.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_PAPER = Path(__file__).resolve().parents[1] / "paper"
_TEX = sorted(_PAPER.rglob("*.tex"))


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_the_paper_tree_exists():
    assert (_PAPER / "main.tex").exists()
    assert (_PAPER / "refs.bib").exists()
    assert _TEX, "no .tex files found"


@pytest.mark.parametrize("tex", _TEX, ids=[p.name for p in _TEX])
def test_every_input_resolves(tex):
    """A missing \\input fails the build, and the build is not run here."""
    for target in re.findall(r"\\input\{([^}]+)\}", _read(tex)):
        name = target if target.endswith(".tex") else target + ".tex"
        assert (_PAPER / name).exists(), (
            f"{tex.name} inputs {target!r}, which does not exist")


def _bib_keys() -> set[str]:
    return set(re.findall(r"@\w+\{([^,]+),", _read(_PAPER / "refs.bib")))


@pytest.mark.parametrize("tex", _TEX, ids=[p.name for p in _TEX])
def test_every_citation_resolves(tex):
    keys = _bib_keys()
    cited = {k.strip()
             for group in re.findall(r"\\cite[tp]?\{([^}]+)\}", _read(tex))
             for k in group.split(",")}
    missing = sorted(cited - keys)
    assert not missing, f"{tex.name} cites keys absent from refs.bib: {missing}"


def test_related_work_cites_only_what_was_read_in_full():
    """paper/README.md rule 4. A related-work section built from abstracts is
    exactly how one becomes wrong, and the rule is worthless unless something
    checks it."""
    bib = _read(_PAPER / "refs.bib")
    entries = dict(re.findall(r"@\w+\{([^,]+),(.*?)\n\}", bib, re.S))
    cited = {k.strip()
             for group in re.findall(
                 r"\\cite[tp]?\{([^}]+)\}",
                 _read(_PAPER / "sections" / "02-related.tex"))
             for k in group.split(",")}
    unread = sorted(k for k in cited if "READ IN FULL" not in entries.get(k, ""))
    assert not unread, (
        f"the related-work section cites works not marked READ IN FULL: "
        f"{unread}. Read them, or remove the citation.")


def test_unverified_bibliography_entries_are_declared_not_silent():
    """Several entries were written from notes rather than from the source.
    That is acceptable in a draft and unacceptable silently, so the marker is
    required to be present and countable -- this test prints the tally."""
    bib = _read(_PAPER / "refs.bib")
    entries = dict(re.findall(r"@\w+\{([^,]+),(.*?)\n\}", bib, re.S))
    unverified = sorted(k for k, v in entries.items() if "[VERIFY]" in v)
    assert unverified, (
        "no entry is marked [VERIFY]. If every entry really has been checked "
        "against its source, delete this test; do not delete the markers.")
    print(f"\n{len(unverified)} of {len(entries)} bib entries need "
          f"verification: {unverified}")


def test_no_section_is_an_empty_stub():
    """A file that exists and says nothing passes every other check here."""
    for tex in _TEX:
        body = re.sub(r"%.*", "", _read(tex))
        assert len(body.strip()) > 120, f"{tex.name} is effectively empty"


def test_the_venue_switch_is_present():
    """The draft is venue-agnostic by decision; the page budget is the knob
    that makes that true rather than aspirational."""
    assert r"\newcommand{\pagebudget}" in _read(_PAPER / "main.tex")
