"""The ship gate: a tier where the index does not beat ripgrep does not ship.

An agent with a shell already reads a 59k-line source tree. Measuring this
index against "no lookup at all" would measure the easy effect -- any
retrieval beats none by a wide margin in every published comparison -- and
would tell us nothing about whether the index is worth its build.
"""
from __future__ import annotations

import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path

import pytest

from adda._src.knowledge.basilisk.index import BasiliskIndex

from .basilisk_source_queries import DEVELOPMENT, TIERS

_ROOT = os.environ.get("ADDA_BASILISK_SRC", "")
#: Guarded on the ENV VAR, never on whether a path happens to exist. An empty
#: default made ``Path("") / "src"`` resolve to this repository's own src/,
#: which exists -- so the suite silently stopped skipping and scored the index
#: against adda's Python instead of a Basilisk checkout.
SRC = Path(_ROOT) / "src" if _ROOT else None

pytestmark = pytest.mark.corpus
_WORD = re.compile(r"[A-Za-z0-9_.-]+")


def rg_rank1(query: str) -> str | None:
    """The control: ripgrep with the query's own words, best file it names.

    Ranked by match count, not by whatever the filesystem returns first. A
    competent agent with a shell would do at least this much, and beating a
    control that returns the alphabetically-first file of hundreds would not
    be evidence of anything.
    """
    words = [w for w in _WORD.findall(query) if len(w) > 2]
    if not words:
        return None
    pattern = "|".join(re.escape(w) for w in words)
    try:
        out = subprocess.run(
            ["rg", "-ic", "-e", pattern, "."],
            cwd=SRC, capture_output=True, text=True, timeout=120).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    scored = []
    for line in out.splitlines():
        path, _, count = line.rpartition(":")
        if path and count.isdigit():
            scored.append((int(count), path.lstrip("./")))
    if not scored:
        return None
    scored.sort(key=lambda kv: (-kv[0], kv[1]))
    return scored[0][1]


def index_rank1(idx: BasiliskIndex, query: str) -> str | None:
    """The key the index would have the agent open first.

    A menu announces itself on its first line and lists candidates indented;
    an ENTRY names its key on the first line and may contain arbitrary
    indented documentation below it. Scanning for "any indented line" confuses
    the two, and picks an indented LaTeX line out of a solver's derivation
    instead of the key the tool actually returned.
    """
    out = idx.consult(query, limit=1)
    lines = out.splitlines()
    if not lines:
        return None
    if lines[0].startswith("No Basilisk entry"):
        return None
    if "match(es) for" in lines[0]:
        for line in lines[1:]:
            if line.startswith("  "):
                return line.strip().split(" -- ")[0].strip()
        return None
    return lines[0].split(" -- ")[0].strip()


@pytest.fixture(scope="module")
def idx():
    return BasiliskIndex.build(SRC)


def _score(idx, queries):
    s: dict = defaultdict(lambda: {"n": 0, "idx": 0, "rg": 0})
    for qid, query, gold in queries:
        tier = TIERS[qid[0]]
        s[tier]["n"] += 1
        if index_rank1(idx, query) in gold:
            s[tier]["idx"] += 1
        if rg_rank1(query) in gold:
            s[tier]["rg"] += 1
    return s


def test_report_per_tier_scores(idx, capsys):
    """Prints the table the ship decision is made from."""
    s = _score(idx, DEVELOPMENT)
    with capsys.disabled():
        print(f"\n{'tier':<9}{'n':>3}{'index':>7}{'rg':>5}")
        for tier in ("NAME", "CONCEPT", "ERROR", "RULE", "KNOB"):
            v = s[tier]
            print(f"{tier:<9}{v['n']:>3}{v['idx']:>7}{v['rg']:>5}")
    assert s


def test_concept_tier_beats_ripgrep(idx):
    """'If the index does not win here it wins nowhere.'"""
    s = _score(idx, [q for q in DEVELOPMENT if q[0].startswith("c")])["CONCEPT"]
    assert s["idx"] > s["rg"], f"CONCEPT: index {s['idx']} vs rg {s['rg']}"


def test_rule_tier_is_answered_at_all(idx):
    """The differentiator. Basilisk states no compatibility rules anywhere, so
    rg cannot serve this tier; the index must."""
    s = _score(idx, [q for q in DEVELOPMENT if q[0].startswith("r")])["RULE"]
    assert s["idx"] > 0, "RULE: a search engine with extra steps"


def test_name_tier_does_not_collapse(idx):
    """rg is expected to win the control tier; the index must not be broken."""
    qs = [q for q in DEVELOPMENT if q[0].startswith("n")]
    s = _score(idx, qs)["NAME"]
    assert s["idx"] >= len(qs) // 2, f"NAME: index {s['idx']}/{len(qs)} -- broken"
