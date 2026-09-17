"""Retrieval quality for the f3dasm lookup, measured rather than eyeballed.

``tests/test_f3dasm_api.py`` asks "does this specific query still work". This
file asks "is retrieval as good as it was", over the 56 labelled queries in
``tests/f3dasm_query_set.py``, reported per tier.

The distinction is not academic. Both bugs fixed alongside this file were
invisible to the golden set:

* module path segments were scored in the NAME tier, so every
  ``f3dasm.design.*`` symbol earned a free top-weight hit on the word "design";
* ``so`` and ``far`` were not stopwords, so ``so`` matched ``sobol`` and lifted
  its coverage multiplier.

Together they put ``f3dasm.design.sobol`` (51.9) above
``f3dasm.ExperimentData.get_n_best_output`` (36.5) for "get the best design
found so far" — a query with an unambiguous right answer that matched "best" in
BOTH its name and its summary and still lost to a package folder.

The golden set also carried two FALSE PASSES, found by this file, because it
asserted the expected key as a SUBSTRING of the rendered page:
``"f3dasm.ExperimentData" in out`` is satisfied by
``f3dasm.ExperimentData.set_project_dir``. Both are fixed there; the floors
below are measured against exact-key comparison.

ON THE FLOORS
    They are recorded measurements, not targets. ``synonym`` read 0.59 r@5
    with a purely lexical ranker; the alias map took it to 0.71 and the floors
    below were re-recorded against that. Writing them down is exactly what let
    the map be judged rather than argued about — and what will let an
    embedding be judged against the map.
"""
from __future__ import annotations

import pytest

pytest.importorskip("f3dasm")

from adda._src.knowledge.f3dasm_api import (  # noqa: E402
    _STOP,
    F3dasmApi,
)

from .f3dasm_query_set import (  # noqa: E402
    QUERIES,
    evaluate,
    format_report,
)


@pytest.fixture(scope="module")
def api():
    return F3dasmApi()


@pytest.fixture(scope="module")
def scores(api):
    return evaluate(lambda q, n: [h.key for h in api._rank(q, n)])


# --- the labels themselves must not rot ------------------------------------

def test_every_label_is_a_live_symbol(api):
    """A renamed f3dasm symbol must fail the build, not score zero forever.

    Without this the query set degrades silently: the label stops matching
    anything, recall drops, and the drop reads as a ranker regression.
    """
    unknown = sorted(
        {k for _, accept, _ in QUERIES for k in accept} - set(api._index))
    assert not unknown, f"query set references symbols f3dasm no longer has: {unknown}"


def test_the_query_set_covers_every_tier():
    tiers = {t for _, _, t in QUERIES}
    assert tiers == {"name", "dotted", "traceback", "vocab", "synonym"}
    assert len(QUERIES) >= 50


# --- the floors -------------------------------------------------------------

def test_a_known_name_is_always_found(scores):
    """The agent knows what it wants and is checking a signature. A miss here
    is not a ranking nuance, it is the tool failing at its one job."""
    assert scores["name"]["r@3"] == 1.0, format_report(scores)
    assert scores["name"]["r@1"] >= 0.90, format_report(scores)


def test_a_dotted_name_resolves_exactly(scores):
    assert scores["dotted"]["r@1"] == 1.0, format_report(scores)


def test_a_traceback_path_resolves_to_its_public_symbol(scores):
    """`f3dasm._src.experimentdata.ExperimentData` must reach the class.

    This tier read 0.75 before the tail rule: the private path degraded into a
    bag of words that every method of the class matched as well as the class.
    """
    assert scores["traceback"]["r@5"] == 1.0, format_report(scores)


def test_a_concept_in_f3dasms_own_words_is_found(scores):
    """The case the lexical ranker is actually built for."""
    assert scores["vocab"]["r@3"] >= 0.94, format_report(scores)
    assert scores["vocab"]["r@5"] == 1.0, format_report(scores)


def test_the_synonym_tier_is_recorded_not_hidden(scores):
    """The KNOWN-WEAK tier. These queries avoid f3dasm's vocabulary on purpose
    — "save" not "store", "supercomputer" not "slurm", "black box" not
    "DataGenerator" — which is vocabulary mismatch: the right symbol shares no
    token with the query, so it scores zero before any weighting applies.

    The alias map (``_ALIASES``) is what the floor was written down FOR. It
    moved this tier, measured on the same 56 queries:

        r@1  0.29 -> 0.47      r@3  0.41 -> 0.65
        r@5  0.59 -> 0.71      MRR  0.39 -> 0.57

    and left every other tier byte-identical, which is the property that
    matters — an expansion that bought this tier by disturbing the four
    saturated ones would be a worse ranker with a better average.

    Six of 17 still miss at k=5, and they are worth naming because they say
    what an embedding would and would not buy. Two are RANKING, not
    vocabulary ("save my results to a file" reaches ``store`` and then loses
    to ``Domain.store``: three classes carry that method and nothing tells
    them apart). Two are vocabulary this map simply does not carry. Two are
    genuinely conceptual — "pick points to try next" shares no word with
    ``create_optimizer`` in any vocabulary — and those are the only ones an
    embedding is clearly the answer for.
    """
    assert scores["synonym"]["r@5"] >= 0.68, format_report(scores)
    assert scores["synonym"]["mrr"] >= 0.55, format_report(scores)


def test_overall_quality_does_not_regress(scores):
    assert scores["all"]["r@5"] >= 0.89, format_report(scores)
    assert scores["all"]["mrr"] >= 0.82, format_report(scores)


# --- the alias map -----------------------------------------------------------

def test_a_query_already_in_f3dasms_words_is_unchanged(api):
    """Expansion must be additive. A query that already speaks f3dasm has to
    rank exactly as it did before the map existed, or the four saturated tiers
    were bought at a price paid somewhere invisible."""
    from adda._src.knowledge.f3dasm_api import _expand

    for q in ("store the experiment data", "create_sampler latin",
              "call the datagenerator", "domain add_float"):
        toks = [t for t in q.replace("_", " ").split()]
        introduced = _expand(toks)
        assert not (set(introduced) & set(toks)), (
            f"{q!r}: expansion re-introduced a token the query already had")


def test_an_alias_covers_its_origin_not_itself(api):
    """"save my results" must not count as two terms covered because ``store``
    was added on "save"'s behalf — coverage multiplies the whole score, so a
    double-count there inflates every aliased query."""
    from adda._src.knowledge.f3dasm_api import _expand

    assert _expand(["save"]) == {"store": "save"}


def test_a_two_word_english_term_reaches_a_one_word_identifier(api):
    """"black box" cannot match the key ``blackbox`` by single-token lookup.
    That is a gap in the mechanism, not in the vocabulary."""
    from adda._src.knowledge.f3dasm_api import _expand

    assert "datagenerator" in _expand(["black", "box"])


def test_every_alias_points_at_a_word_f3dasm_actually_uses(api):
    """Derived from the live index, not from a hand-kept list. An alias whose
    target appears in no symbol name is dead weight that can only add noise —
    and would survive forever, because nothing else would ever mention it."""
    from adda._src.knowledge.f3dasm_api import _ALIASES

    vocab: set[str] = set()
    for key, entry in api._index.items():
        leaf = key.rsplit(".", 1)[-1].lower()
        vocab |= set(leaf.replace("_", " ").split())
        if entry.owner:
            vocab |= set(entry.owner.rsplit(".", 1)[-1].lower().split("_"))

    dead = sorted({t for targets in _ALIASES.values() for t in targets}
                  - vocab)
    assert not dead, f"aliases pointing at words f3dasm never uses: {dead}"


# --- the two fixed bugs, pinned as behaviour --------------------------------

def test_a_module_segment_earns_no_name_tier_credit(api):
    """Bug 1. "design" is a word in most DoE queries and a package folder in
    f3dasm; scoring it as a NAME match made the folder decide the ranking."""
    got = [h.key for h in api._rank("get the best design found so far", 3)]
    assert got[0] == "f3dasm.ExperimentData.get_n_best_output", got
    # not every f3dasm.design.* symbol crowding the result
    assert sum(1 for k in got if k.startswith("f3dasm.design.")) <= 1, got


def test_a_stray_function_word_cannot_decide_a_ranking(api):
    """Bug 2. "so" survived tokenisation and matched "sobol", which raised that
    symbol's COVERAGE — a multiplier on the whole score, not a small bonus."""
    for word in ("so", "far", "already", "which", "next"):
        assert word in _STOP, word
    assert "f3dasm.design.sobol" not in [
        h.key for h in api._rank("get the best design found so far", 3)]


def test_no_new_symbol_pair_is_distinguished_only_by_a_stopword(api):
    """The opposite failure to bug 2, derived from the index rather than from
    a hand-kept list of words someone thought were safe.

    A stopword INSIDE a name is fine — ``from_file``, ``to_numpy``,
    ``store_as_json`` and ``select_with_status`` all hinge on a particle while
    keeping a distinguishing token. The failure is a stopword that carries the
    WHOLE distinction: ``all`` was in the list until ``mark`` and ``mark_all``
    showed it was the only thing between them, and it was removed.

    Two collisions remain and are pinned rather than fixed, because removing
    their words would cost far more than it buys:

    * ``DataGenerator`` / ``datagenerator`` differ only in case — not a
      stopword problem at all, and both are reachable by exact name.
    * ``from_numpy`` / ``to_numpy`` differ only by ``from``/``to``. Stopping
      those two particles is worth more across the whole corpus than the one
      pair it blurs, and both still resolve by exact name.

    A THIRD collision appearing means a new stopword swallowed a real
    distinction, and that is what this fails on.
    """
    import collections

    groups = collections.defaultdict(set)
    for key, e in api._index.items():
        leaf = key.rsplit(".", 1)[-1]
        if e.private or leaf.startswith("__"):
            continue
        sig = (key.rsplit(".", 1)[0],
               frozenset(t for t in leaf.lower().replace("_", " ").split()
                         if t not in _STOP))
        groups[sig].add(key)

    collisions = {tuple(sorted(v)) for v in groups.values() if len(v) > 1}
    assert collisions == {
        ("f3dasm.DataGenerator", "f3dasm.datagenerator"),
        ("f3dasm.ExperimentSample.from_numpy",
         "f3dasm.ExperimentSample.to_numpy"),
    }, collisions


def test_every_public_symbol_is_reachable_by_its_own_name(api):
    """The reachability guarantee, over the whole public surface rather than a
    sample: exact-leaf matching is scored ABOVE tokenisation, so it holds even
    for a name that is also a stopword.

    ``__init__`` is excluded because 22 symbols share that leaf and only five
    fit in a top-5 — an agent asks for ``ExperimentData.__init__`` or for the
    class, both of which resolve exactly.
    """
    missed = []
    for key, e in api._index.items():
        leaf = key.rsplit(".", 1)[-1]
        if e.private or leaf == "__init__":
            continue
        if key not in [h.key for h in api._rank(leaf, 5)]:
            missed.append(key)
    assert not missed, missed


def test_a_stopword_that_is_also_a_symbol_name_still_resolves(api):
    """``ExperimentSample.get`` is named for a stopword. Exact-name matching
    runs before the stopword filter, so it stays reachable — this is the
    invariant that lets the stopword list be generous."""
    assert "get" in _STOP
    assert "f3dasm.ExperimentSample.get" in [h.key for h in api._rank("get", 5)]


# --- the report ------------------------------------------------------------

def test_report(scores, capsys):
    """Not an assertion — it prints the table. ``pytest -s -k report`` is the
    diagnostic to run when changing the ranker."""
    with capsys.disabled():
        print("\n" + format_report(scores))


# ---------------------------------------------------------------------------
# Collision queries, held out
#
# tests/f3dasm_collision_queries.py holds 18 queries written from the
# summaries of symbols that SHARE A LEAF NAME — four `store`s, four
# `from_yaml`s, six `arm`s — and which the 56-query set never touches. They
# were frozen before anything was measured against them.
#
# They exist because a centrality tiebreak was once added here to order such
# symbols, justified on the 56-query set, and then measured on these: it moved
# not one of them. It was reverted. The queries stayed, because the thing they
# measure — can this index resolve a name collision — is real regardless of
# how it is resolved.
# ---------------------------------------------------------------------------


def _held_out_scores(api):
    from tests.f3dasm_collision_queries import AMBIGUOUS, DISAMBIGUATED

    out = {}
    for name, qs in (("disambiguated", DISAMBIGUATED), ("ambiguous", AMBIGUOUS)):
        hits = ranks = 0.0
        for q, gold in qs:
            got = [h.key for h in api._rank(q, 5)]
            pos = got.index(gold) + 1 if gold in got else None
            hits += pos == 1
            ranks += 1 / pos if pos else 0
        out[name] = (hits / len(qs), ranks / len(qs))
    return out


def test_a_collision_query_that_names_its_owner_resolves(api):
    """When the query says WHICH class, the right member must come first."""
    s = _held_out_scores(api)
    assert s["disambiguated"][0] >= 0.90, s
    assert s["disambiguated"][1] >= 0.90, s


def test_an_ambiguous_collision_query_is_recorded_as_weak(api):
    """The open problem, written down rather than hidden. A query that does
    not say which class sits at r@1 0.25: these do not produce score TIES, so
    a tiebreak cannot reach them — they produce different scores favouring the
    wrong symbol. Closing this needs a prior that SHIFTS scores, and every
    version of that measured so far regressed the vocab tier."""
    s = _held_out_scores(api)
    assert s["ambiguous"][0] >= 0.25, s
