"""Lexical lookup over the Basilisk corpus.

Search is lexical, not embedding-based. Dense embeddings were measured in this
codebase and did not earn their cost, and BM25-style lexical matching is the
repeatedly-effective retriever for code in the published comparisons. Keeping
it lexical also keeps the build deterministic and free of model calls, which
is what turns a corpus rebuild from a project into a script.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .extract import closure, co_occurrence, example_index, header_index

_WORD = re.compile(r"[a-z0-9_]+")
#: Tokens too common in a CFD corpus, or too generic in a question, to
#: discriminate between entries.
_STOP = frozenset({
    "the", "a", "an", "of", "for", "to", "in", "and", "with", "is", "it", "on",
    "how", "do", "i", "can", "what", "must", "which", "be", "use", "using",
    "my", "me", "that", "this", "at", "by", "from", "or", "as", "are", "was",
})
#: A header used by at least this many verified cases is part of the corpus's
#: working vocabulary; rarer ones are too thinly evidenced to call "never
#: stacked" on the strength of an absence.
_ESTABLISHED = 8


def _tokens(text: str) -> list[str]:
    return [t for t in _WORD.findall(text.lower())
            if t not in _STOP and len(t) > 1]


@dataclass
class BasiliskIndex:
    src: Path
    headers: dict[str, dict]
    examples: dict[str, dict]
    pairs: dict[frozenset, int]
    singles: dict[str, int]
    _tok: dict[str, set[str]] = field(default_factory=dict)
    _closure: dict[str, set[str]] = field(default_factory=dict)

    @classmethod
    def build(cls, src: Path) -> "BasiliskIndex":
        headers = header_index(src)
        examples = example_index(src)
        pairs, singles = co_occurrence(examples)
        idx = cls(src, headers, examples, pairs, singles)
        for key in headers:
            idx._closure[key] = closure(src, key)
        for key, c in headers.items():
            idx._tok[key] = set(_tokens(
                f"{key} {c['summary']} {c['doc'][:2000]} "
                f"{' '.join(c['provides'])} {' '.join(c['requires'])} "
                f"{' '.join(c['events'])}"))
        for key, e in examples.items():
            idx._tok[key] = set(_tokens(f"{key} {e['title']}"))
        return idx

    # -- ranking -------------------------------------------------------
    def _rank(self, query: str, limit: int) -> list[tuple[str, int]]:
        q = set(_tokens(query))
        if not q:
            return []
        scored: list[tuple[str, int]] = []
        for key, toks in self._tok.items():
            overlap = len(q & toks)
            if not overlap:
                continue
            # A query naming a file means that file. Weight the key's own
            # words heavily so an exact name beats a topical match.
            scored.append((key, overlap + 3 * len(q & set(_tokens(key)))))
        scored.sort(key=lambda kv: (-kv[1], kv[0]))
        return scored[:limit]

    # -- rendering -----------------------------------------------------
    def _companions(self, key: str) -> tuple[list[str], list[str]]:
        """Verified partners, and established headers never stacked with this.

        The absence is the informative half and is only trustworthy for
        headers the corpus uses often: a header appearing twice tells us
        nothing by not appearing beside another.
        """
        used_with: dict[str, int] = {}
        for pair, n in self.pairs.items():
            if key in pair:
                used_with[next(iter(pair - {key}))] = n
        good = sorted(used_with, key=lambda h: -used_with[h])[:6]

        # Anything reachable from this header, or from a header it is verified
        # with, arrives transitively -- so no case names it separately and its
        # absence carries no information about compatibility.
        free = set(self._closure.get(key, {key}))
        for companion in used_with:
            free |= self._closure.get(companion, set())

        never = [h for h in sorted(self.singles, key=lambda h: -self.singles[h])
                 if h != key and h not in used_with and h not in free
                 and self.singles[h] >= _ESTABLISHED][:6]
        return good, never

    def _entry(self, key: str, source: bool) -> str:
        if key in self.examples:
            e = self.examples[key]
            lines = [f"{key} -- {e['title']}", "",
                     "STACKS: " + ", ".join(e["headers"])]
            if source:
                lines += ["", (self.src / key).read_text(errors="ignore")]
            return "\n".join(lines)

        c = self.headers[key]
        good, never = self._companions(key)
        lines = [f"{key} -- {c['summary']}".rstrip(" -"), ""]
        if c["provides"]:
            lines.append("PROVIDES (declared for you): "
                         + ", ".join(c["provides"]))
        if c["requires"]:
            lines.append("YOU MUST SUPPLY (defaults shown; override before use): "
                         + ", ".join(f"{k}={v}" if v else k
                                     for k, v in c["requires"].items()))
        if c["events"]:
            lines.append("EXTENSION POINTS: " + ", ".join(c["events"]))
        if c["includes"]:
            lines.append("INCLUDES: " + ", ".join(c["includes"]))
        if good:
            lines.append("VERIFIED WITH: " + ", ".join(good))
        if never:
            lines.append(
                "NEVER STACKED WITH (no verified case combines these; usually "
                "an alternative solver for the same thing): " + ", ".join(never))
        cases = [k for k, e in self.examples.items() if key in e["headers"]][:6]
        if cases:
            lines.append("WORKED EXAMPLES: " + ", ".join(cases))
        if c["doc"]:
            lines += ["", c["doc"][:1500]]
        if source:
            lines += ["", (self.src / key).read_text(errors="ignore")]
        return "\n".join(lines)

    def consult(self, query: str, limit: int = 8, source: bool = False) -> str:
        key = query.strip()
        if key in self.headers or key in self.examples:
            return self._entry(key, source)
        hits = self._rank(query, limit)
        if not hits:
            return (f"No Basilisk entry matches {query!r}. This index covers "
                    "the Basilisk source tree only, so a miss means 'not a "
                    "Basilisk concept', not 'does not exist'.")
        out = [f"{len(hits)} match(es) for {query!r} -- call again with one of "
               "these keys for its entry:"]
        for k, _ in hits:
            meta = self.headers.get(k) or self.examples.get(k) or {}
            label = meta.get("summary") or meta.get("title") or ""
            out.append(f"  {k} -- {label}".rstrip(" -"))
        return "\n".join(out)
