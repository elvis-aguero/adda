"""Ask adda about itself — the lookup an agent uses instead of reading files.

WHY THIS EXISTS
    Code is increasingly read by agents, and an agent that wants to change
    adda starts by not knowing where anything is. Its options are to grep, or
    to read files until it finds the answer. Both spend context on material it
    will discard.

    This is the third package adda indexes this way. f3dasm and Abaqus are
    indexed FOR adda's own agents, who write f3dasm code and Abaqus decks.
    This one is indexed for YOUR agent, working on or with adda.

WHAT MAKES AN ANSWER GOOD HERE, AND HOW IT IS CHECKED
    Not latency. A reply is worth its tool call when it carries the CONCEPT --
    when the agent can act on it without opening the file. So the index holds
    four kinds of thing, and three of them are not symbols:

      symbol    classes, functions, methods, with the PUBLIC import path
      module    the module docstring, where this package argues WHY a thing
                exists -- 23% of its docstring mass
      constant  declared module-level values, each carrying its module's
                docstring, so BACKSTOP_USD is reachable by the concept "a run
                can be stopped by a cost ceiling" and not only by its literal
      markdown  the knowledge base shipped inside the package, which states
                the rules -- what an agent may and may not do

    That mix is not a guess. On 128 labelled queries (48 written alongside the
    tool, 80 written blind by an agent barred from running it), symbols alone
    LOSE to ripgrep; all four together beat it: r@1 0.375 vs 0.23, MRR 0.459
    vs 0.32, exact McNemar p = 0.0096. The same four units measured on f3dasm
    make it WORSE, which is why the unit set is a parameter and not a default.

    ``internal/tools/source_index_baseline.py`` reproduces all of it.

WHAT IT IS NOT
    Not a search over your study code, your notebooks, or the repository's
    docs/ site. It indexes the INSTALLED adda package and nothing else, which
    is what lets it be correct on a cluster where no checkout exists.

USE
    adda-explain "how do I stop a run that is burning money"
    adda-explain AgenticRun                 # an exact name gives the entry
    adda-explain --source AgenticRun        # then the source, if needed
    adda-explain --overview                 # the public surface, one line each

    Or from Python::

        from adda.explain import explain
        print(explain("where does a run decide it is over"))
"""
from __future__ import annotations

import argparse

__all__ = ["explain", "main", "overview"]

_API = None


def _api():
    """Built once per process. Introspecting the package is not free, and a
    tool that rebuilds per call would be paid for on every question."""
    global _API
    if _API is None:
        from ._src.knowledge.f3dasm_api import AddaApi
        _API = AddaApi()
    return _API


def explain(query: str, limit: int = 8, source: bool = False) -> str:
    """Look adda up. A phrase returns a menu; a name returns its entry."""
    return _api().consult(query, limit=limit, source=source)


def overview() -> str:
    """Adda's public surface, one line each — the map, not the territory."""
    return _api().overview()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="adda-explain",
        description="Look up adda's own API, concepts and rules.",
        epilog="A phrase returns a menu of matches; pass a name back for its "
               "full entry. Searches the INSTALLED adda only.")
    parser.add_argument("query", nargs="*", help="a name, or a phrase")
    parser.add_argument("--source", action="store_true",
                        help="print the source of an exactly-named symbol")
    parser.add_argument("--overview", action="store_true",
                        help="list the public surface instead of searching")
    parser.add_argument("-n", "--limit", type=int, default=8,
                        help="how many matches to list (default 8)")
    args = parser.parse_args(argv)

    if args.overview:
        print(overview())
        return 0
    if not args.query:
        parser.print_help()
        return 2
    print(explain(" ".join(args.query), limit=args.limit, source=args.source))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
