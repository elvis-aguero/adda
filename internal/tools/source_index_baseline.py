"""The control an agent-facing source index has to beat: ripgrep -- and the
index, scored against it on the same queries.

A coding agent with a shell already reads this repository. So the number a
lookup tool must improve on is not zero — it is what ``rg`` scores on the
same questions, scored the same way. Run this BEFORE building the index, and
again after, and report both.

Two controls are scored, because the weaker one would be a strawman:
raw match counts (which favour long files, and on this repo that is
``agent_runtime.py`` and ``delegation.py``), and matches-per-kilobyte.
Whichever scores HIGHER is the bar.

    uv run python internal/tools/source_index_baseline.py [--held-out]

``--held-out`` scores the frozen split. Do not pass it until the design is
frozen; that is what makes the split worth having.

``--index`` additionally scores ``PackageApi("adda")`` in four unit
configurations. The comparison is the point: the unit set turned out to be
package-dependent, and nothing but running both arms shows that.
"""
from __future__ import annotations

import argparse
import collections
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tests"))
import adda_source_queries as Q  # noqa: E402

#: Words carrying no retrieval signal in a question about source. Kept small
#: and generic on purpose: a stoplist tuned against these very queries would
#: make the control look worse and the index look better, which is the
#: opposite of what a control is for.
STOP = frozenset(
    "how do i the a an of to in is it and or what where when which for does "
    "can my me on at that this with from without so be are was there here "
    "into out up off no not has have if its".split())


def _rank(query: str, k: int = 5, *, per_kb: bool) -> list[str]:
    toks = [t for t in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]+", query.lower())
            if t not in STOP]
    if not toks:
        return []
    pat = "|".join(re.escape(t) for t in toks)
    try:
        out = subprocess.run(
            ["rg", "-i", "--count-matches", "-e", pat, "src/adda",
             "-g", "*.py", "-g", "*.md"],
            capture_output=True, text=True, timeout=120, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    scores: dict[str, float] = {}
    for line in out.splitlines():
        if ":" not in line:
            continue
        path, n = line.rsplit(":", 1)
        try:
            hits = int(n)
        except ValueError:
            continue
        if per_kb:
            hits = hits * 1000 / max(pathlib.Path(path).stat().st_size, 1)
        scores[path] = scores.get(path, 0) + hits
    return [p for p, _ in sorted(scores.items(), key=lambda kv: -kv[1])[:k]]


def score(rows, label: str, *, per_kb: bool, show_misses: bool = False):
    hit1 = hit5 = 0
    mrr = 0.0
    per: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0, 0])
    misses = []
    for tier, qid, query, gold in rows:
        got = _rank(query, per_kb=per_kb)
        rank = next((i for i, p in enumerate(got, 1) if p in set(gold)), None)
        if rank == 1:
            hit1 += 1
            per[tier][0] += 1
        if rank:
            hit5 += 1
            per[tier][1] += 1
            mrr += 1 / rank
        else:
            misses.append((tier, qid, query, got[:3]))
        per[tier][2] += 1
    n = len(rows) or 1
    tiers = "  ".join(f"{t[:4]} {v[0] / v[2]:.2f}" for t, v in sorted(per.items()))
    print(f"{label:36s} r@1 {hit1 / n:.2f}  r@5 {hit5 / n:.2f}  "
          f"MRR {mrr / n:.2f}   {tiers}")
    if show_misses:
        for tier, qid, query, got in misses:
            print(f"    MISS [{tier}] {qid} {query!r}")
            for p in got:
                print(f"         rg: {p}")
    return hit1 / n, mrr / n


def _score_index(rows, units) -> tuple[float, float, float, dict]:
    """The adda index, scored exactly as the ripgrep control is.

    Entries are ranked, then collapsed to their FILE, because the query set's
    gold labels are files -- a module entry and a function entry in the same
    file are one answer, not two.
    """
    root = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "src"))
    from adda._src.knowledge.f3dasm_api import PackageApi

    api = PackageApi("adda", units=units)

    def rank(query: str, k: int = 5) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for entry in api._rank(query, 60):
            where = (entry.where or "").rsplit(":", 1)[0]
            path = "src/" + where if where.startswith("adda/") else where
            if path == "?" or path in seen:
                continue
            seen.add(path)
            out.append(path)
            if len(out) >= k:
                break
        return out

    hit1 = hit5 = 0
    mrr = 0.0
    per: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0, 0])
    for tier, _qid, query, gold in rows:
        got = rank(query)
        r = next((i for i, p in enumerate(got, 1) if p in set(gold)), None)
        if r == 1:
            hit1 += 1
            per[tier][0] += 1
        if r:
            hit5 += 1
            per[tier][1] += 1
            mrr += 1 / r
        per[tier][2] += 1
    n = len(rows) or 1
    return hit1 / n, hit5 / n, mrr / n, {t: v[0] / v[2] for t, v in per.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--held-out", action="store_true",
                    help="score the frozen split instead of DEVELOPMENT")
    ap.add_argument("--misses", action="store_true")
    ap.add_argument("--index", action="store_true",
                    help="also score the adda index, in four unit configurations")
    args = ap.parse_args()

    rows = Q.HELD_OUT if args.held_out else Q.DEVELOPMENT
    split = "HELD OUT" if args.held_out else "DEVELOPMENT"
    print(f"=== ripgrep control, {split} split (n={len(rows)}) ===")
    a = score(rows, "rg, raw match counts", per_kb=False,
              show_misses=args.misses)
    b = score(rows, "rg, matches per kilobyte", per_kb=True)
    print(f"\nthe bar to beat: r@1 {max(a[0], b[0]):.2f}, "
          f"MRR {max(a[1], b[1]):.2f}")

    if args.index:
        print("\n=== PackageApi('adda'), by what it indexes ===")
        for units in (("symbol",), ("symbol", "module"), ("symbol", "constant"),
                      ("symbol", "module", "constant"),
                      ("symbol", "module", "constant", "markdown")):
            r1, r5, mrr, per = _score_index(rows, units)
            tiers = "  ".join(f"{t[:4]} {v:.2f}" for t, v in sorted(per.items()))
            print(f"{'+'.join(units):30s} r@1 {r1:.2f}  r@5 {r5:.2f}  "
                  f"MRR {mrr:.2f}   {tiers}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
