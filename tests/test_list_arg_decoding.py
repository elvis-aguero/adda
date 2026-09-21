"""Table-driven coverage of the shared list-argument decoder.

A model can encode a list-valued tool argument as a string in several
shapes: a real list, JSON, Python-repr (single quotes), tuple-repr,
comma-joined, or a bare scalar. Every tool that accepts a ``list``-typed
argument decodes through one shared function
(``adda._src.nodes.tools.routing._decoding.decode_list_arg``) — this
module is that decoder's own unit coverage; ``test_nodes.py`` covers the
end-to-end regression (Delegate/AskForFeedback actually firing).

Reproduced on a real 6.2h cluster run (baseline arm, FAILED, 0 evals): the
model emitted ``hypothesis_ids=['H1', 'H2']`` — Python repr, single quotes
— which the old ``_parse_hypothesis_ids`` could not decode (only real
list / JSON / comma-joined / bare were handled), so ``Delegate`` rejected
the whole repr string as one bogus id and no worker ever fired.
"""
from __future__ import annotations

import pytest

from adda._src.nodes.tools.routing._decoding import decode_list_arg


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Real list passthrough (elements stringified).
        (["H1", "H2"], ["H1", "H2"]),
        ([], []),
        # JSON array — must keep working byte-identical to before the fix.
        ('["H1","H2"]', ["H1", "H2"]),
        ('["H1"]', ["H1"]),
        # Python-repr list (single quotes) — the cluster-run failure mode.
        ("['H1', 'H2']", ["H1", "H2"]),
        ("['H1']", ["H1"]),  # single-element must stay single-element
        # Tuple repr — must not be split on its internal comma.
        ("('H1', 'H2')", ["H1", "H2"]),
        # Comma-joined.
        ("H1, H2", ["H1", "H2"]),
        ("H1,H2", ["H1", "H2"]),
        # Bare scalar.
        ("H1", ["H1"]),
        # Whitespace-only bare scalar.
        ("  H1  ", ["H1"]),
    ],
)
def test_decode_list_arg_shapes(raw, expected):
    assert decode_list_arg(raw) == expected


def test_decode_list_arg_malformed_bracket_degrades_not_raises():
    """An unparseable bracketed string must degrade to a one-element list,
    never raise — same fallback JSON decoding already used."""
    raw = "[H1, H2"  # missing closing bracket
    result = decode_list_arg(raw)
    assert result == [raw]


def test_decode_list_arg_literal_eval_is_not_eval():
    """A string containing a call/side-effect expression must NOT execute —
    ast.literal_eval rejects it, so it degrades to the raw string as a
    single inert element instead of running anything."""
    raw = "[__import__('os').system('true')]"
    result = decode_list_arg(raw)
    assert result == [raw]


def test_decode_list_arg_empty_string_preserves_prior_behavior():
    """Empty string is not one of the encodings under repair here — keep
    whatever the pre-fix decoder already did for it (a one-element list
    holding the empty string), so this fix touches nothing beyond repr/tuple
    decoding."""
    assert decode_list_arg("") == [""]
