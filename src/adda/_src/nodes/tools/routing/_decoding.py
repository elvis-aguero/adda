"""Decode a list-valued tool argument the model may emit as a string.

Model backends hand adda parsed Python values off ``tool_calls`` — there is
no serialization step and no pydantic coercion on this path — but a model
can still choose to encode a list-shaped argument AS a string: JSON
(``'["H1","H2"]'``), Python repr (``"['H1', 'H2']"``), a tuple repr
(``"('H1', 'H2')"``), comma-joined (``'H1, H2'``), or a bare scalar
(``'H1'``). Every tool that accepts a ``list``-typed argument
(``Delegate``'s ``hypothesis_ids``, ``AskForFeedback``'s ``hypothesis_ids``,
``QueryStore``'s ``delegation_ids``/``columns``, …) must decode all of these
the same way — this is the one shared place that does it, so a decoding gap
is fixed once for the whole class of argument, not patched at just the one
call site where a failure happened to surface.

Only :func:`ast.literal_eval` is used to interpret a Python-literal string —
never ``eval`` — because the input is untrusted model output.
``literal_eval`` cannot execute a call or any expression with a side effect
(it raises instead of evaluating), so it stays safe even against an
adversarial string like ``"[__import__('os').system('true')]"``.
"""
from __future__ import annotations

import ast
import json


def decode_list_arg(raw) -> list[str]:
    """Decode one list-valued tool argument into ``list[str]``.

    ``raw`` is a real list (each element stringified) or a string encoding
    a list — JSON array, Python list/tuple repr, comma-joined, or a bare
    scalar (returned as a one-element list). Never raises: a malformed
    bracket/paren-delimited string degrades to a one-element list holding
    the raw string, same as an unparseable JSON string always has.

    Precedence matters. A bracket/paren-delimited string is tried as JSON
    first, then — only once JSON fails — as a Python literal, BEFORE any
    comma-splitting. Otherwise ``"['H1', 'H2']"`` would be split on its
    *internal* comma into fragments (``"['H1'"``, ``"'H2']"``) instead of
    being parsed as the 2-element list it actually encodes.
    """
    if isinstance(raw, list):
        return [str(h) for h in raw]
    s = str(raw).strip()
    if s[:1] in ("[", "("):
        try:
            decoded = json.loads(s)
        except json.JSONDecodeError:
            try:
                decoded = ast.literal_eval(s)
            except (ValueError, SyntaxError):
                return [s]
        return (
            [str(h) for h in decoded]
            if isinstance(decoded, (list, tuple)) else [s]
        )
    if "," in s:
        return [p.strip() for p in s.split(",") if p.strip()]
    return [s]
