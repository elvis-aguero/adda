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


#: Fields the header declares for itself: `scalar p[];`, `vector u[], g[];`
#: Anchored at column 0, which is what makes this the header's INTERFACE
#: rather than its internals: Basilisk declares file-scope fields flush left
#: and function-local temporaries indented, so allowing leading whitespace
#: here silently reports scratch variables (`alphav`, `du`, a loop's `s`) as
#: though the header provided them.
_DECLARES = re.compile(
    r'^(?:face |symmetric )?(?:scalar|vector|tensor) ([^;]+);', re.M)
#: Fields the USER overrides. `(const)` is Basilisk's OWN marker for
#: "user-supplied, here is the default", which is what makes this contract
#: mechanical rather than a reading of the English prose beside it.
_REQUIRES = re.compile(
    r'^\(const\) (?:face )?(?:scalar|vector|tensor) ([^;]+);', re.M)
_EVENT = re.compile(r'^event\s+(\w+)\s*\(', re.M)
_DOCBLOCK = re.compile(r'/\*\*(.*?)\*/', re.S)


def _names(clause: str) -> dict[str, str]:
    """`mu = zerof, a = zerof` -> {'mu': 'zerof', 'a': 'zerof'}."""
    out: dict[str, str] = {}
    for part in clause.split(","):
        part = part.strip()
        if not part:
            continue
        name, _, default = part.partition("=")
        name = name.strip().removesuffix("[]").strip()
        if name.isidentifier():
            out[name] = default.strip()
    return out


def card(path: Path, rel: str) -> dict:
    """One Basilisk header as an agent needs to see it: interface, no bodies.

    Declaration-level rather than function-level deliberately. In controlled
    comparison, chunking code at function granularity is the WORST of the
    common strategies and declaration granularity among the best -- a function
    body torn from its surrounding declarations is not self-contained, whereas
    an interface is.
    """
    text = path.read_text(errors="ignore")
    blocks = _DOCBLOCK.findall(text)
    doc = blocks[0].strip() if blocks else ""
    summary = _title(doc) or next(
        (ln.strip() for ln in doc.splitlines() if ln.strip()), "")

    provides: dict[str, str] = {}
    for clause in _DECLARES.findall(text):
        provides.update(_names(clause))
    requires: dict[str, str] = {}
    for clause in _REQUIRES.findall(text):
        requires.update(_names(clause))
    # A `(const)` declaration also matches _DECLARES; the user-supplied
    # reading is the informative one, so it wins.
    for name in requires:
        provides.pop(name, None)

    return {
        "key": rel,
        "kind": "header",
        "summary": summary,
        "doc": doc,
        "provides": sorted(provides),
        "requires": requires,
        "events": _EVENT.findall(text),
        "includes": sorted(includes(path)),
        "where": rel,
    }


def header_index(src: Path) -> dict[str, dict]:
    """Every solver header, excluding the compiler's own generated parser.

    `ast/` is Basilisk's yacc-generated C parser -- 28k lines of machine output
    with no fluid dynamics in it, and the single largest dense artifact in the
    tree. Indexing it as though it were domain code is most of what made a
    naive whole-repo index unusable.
    """
    out: dict[str, dict] = {}
    for path in sorted(src.rglob("*.h")):
        rel = str(path.relative_to(src))
        if rel.startswith(("ast/", "darcsit/")):
            continue
        out[rel] = card(path, rel)
    return out
