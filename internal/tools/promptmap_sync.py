"""Is the prompt map in sync — with the code, and with what is published?

TWO GAPS, AND ONLY ONE OF THEM IS SCRIPTABLE

    code  ->  internal/promptmap.html  ->  the published artifact

    The FIRST arrow is fully checkable here: regenerate from the live graph
    and compare. Until now nothing did. ``tests/test_promptmap.py`` builds the
    map FRESH on every run and asserts against that, so a stale committed file
    passed every one of its 20-odd tests -- which is how the literature
    reviewer's prompt sat in the committed map still naming a tool that had
    been renamed, with a green suite.

    The SECOND arrow cannot be scripted. Publishing goes through the Artifact
    tool, which only a Claude session can call -- there is no CLI and no key
    in this repository, and there should not be. So this records what WAS
    published, in ``promptmap.published.json``, and fails when the committed
    map has moved past it. That converts "somebody has to remember to
    republish" into a red build, which is the most a repository can do about
    an action it cannot perform.

WHY A CONTENT HASH RATHER THAN THE FILE'S BYTES
    The hash covers the DATA the page renders -- prompt text, tool rosters,
    gates, citations -- and not the surrounding HTML. A change to the
    generator's stylesheet should not tell everyone the artifact is stale, and
    a change to a single word of a prompt must.

    uv run python internal/tools/promptmap_sync.py            # report
    uv run python internal/tools/promptmap_sync.py --record V # after publishing
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAP = ROOT / "internal" / "promptmap.html"
RECORD = ROOT / "internal" / "promptmap.published.json"
URL = "https://claude.ai/artifact/EXuUsKPBFJjPbHJKoMSRJr"


def committed_data() -> dict:
    """The DATA block of the map as committed -- what a reader sees today."""
    m = re.search(r"const DATA = (\{.*?\});\n", MAP.read_text(encoding="utf-8"), re.S)
    if not m:
        raise SystemExit(f"{MAP} carries no DATA block")
    return json.loads(m.group(1))


def live_data() -> dict:
    """The map as the CODE says it should be, built from the live objects."""
    gen = ROOT / "internal" / "tools" / "promptmap.py"
    spec = importlib.util.spec_from_file_location("_promptmap", gen)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build()


_LINE_NUMBER_FIELDS = {"line", "line_end", "doc_line", "doc_line_end"}


def _scrub_citations(value):
    """Strip fields that encode WHERE a line is, not WHAT the page says.

    Python's ``ast`` module changed line attribution in 3.12 (decorators and
    multi-line calls now number differently), so ``line``/``line_end``/
    ``doc_line``/``doc_line_end`` -- and the ``key`` field some sections
    derive from them, e.g. ``"delegation.py:116-131"`` -- differ across
    interpreters even when the prompt text is byte-identical. ``differences()``
    above already treats these as noise: it compares only section TEXT, never
    a citation. This makes ``content_hash`` blind to the same fields, so a
    provenance gate fails on what an agent is actually told, not on where the
    compiler thinks a line begins.

    ``key`` is dropped only when it sits beside a ``line`` sibling in the
    same dict -- that is how every citation key is shaped here (see
    ``promptmap.py``'s ``"{file}:{line}-{line_end}"`` builders). A bare
    ``key`` with no ``line`` sibling is a different field entirely (e.g. the
    ``config.yaml runtime:`` switch name in ``_switches()``) and must stay
    hashed, since renaming a config key is a real, meaningful change.

    ``why`` is prose, not a citation field, so it is kept -- but when a
    definition is ambiguous it EMBEDS line numbers in the explanation itself
    (e.g. "defined at delegation.py:116 and delegation.py:2186"). Dropping
    `why` outright would hide a genuine change to the reasoning (a third
    ambiguous definition appearing, or the explanation changing kind), which
    nothing else in this hash covers. So its digit runs are normalised
    instead of the field being dropped: still sensitive to real wording
    changes, still blind to which line the AST attributed them to.
    """
    if isinstance(value, dict):
        drop = set(_LINE_NUMBER_FIELDS)
        if "key" in value and "line" in value:
            drop.add("key")
        out = {}
        for k, v in value.items():
            if k in drop:
                continue
            if k == "why" and isinstance(v, str):
                out[k] = re.sub(r"\d+", "#", v)
                continue
            out[k] = _scrub_citations(v)
        return out
    if isinstance(value, list):
        return [_scrub_citations(v) for v in value]
    return value


def content_hash(data: dict) -> str:
    """Stable over what the page SHOWS, blind to how it is styled, and blind
    to which Python interpreter's AST line attribution produced a citation
    (see ``_scrub_citations``) -- a citation moving is not the same as a
    prompt changing."""
    return hashlib.sha256(
        json.dumps(_scrub_citations(data), sort_keys=True,
                   ensure_ascii=False).encode()
    ).hexdigest()


def differences(old: dict, new: dict) -> list[str]:
    """Human-readable drift, per role and per gate -- not a byte diff.

    Whoever reads this needs to know WHICH agent's instructions moved, since
    that is what decides whether the change matters.
    """
    out: list[str] = []

    def sections(d):
        return {r["id"]: {(lay.get("label"), s.get("tag")): (s.get("text") or "")
                          for lay in r["layers"] for s in lay.get("sections", [])}
                for r in d.get("roles", [])}

    a, b = sections(old), sections(new)
    for rid in sorted(set(a) | set(b)):
        if rid not in a:
            out.append(f"role {rid}: ADDED")
        elif rid not in b:
            out.append(f"role {rid}: REMOVED")
        elif a[rid] != b[rid]:
            moved = sorted({k for k in set(a[rid]) | set(b[rid])
                            if a[rid].get(k) != b[rid].get(k)})
            for label, tag in moved:
                out.append(f"role {rid}: section <{tag}> in {label} changed")
    if len(old.get("gates", [])) != len(new.get("gates", [])):
        out.append(f"gates: {len(old.get('gates', []))} -> "
                   f"{len(new.get('gates', []))}")
    return out


def report() -> int:
    committed, live = committed_data(), live_data()
    ch, lh = content_hash(committed), content_hash(live)
    rec = json.loads(RECORD.read_text(encoding="utf-8")) if RECORD.exists() else {}

    print(f"committed map  {ch[:12]}")
    print(f"live code      {lh[:12]}")
    print(f"published      {(rec.get('content_hash') or '-')[:12]}"
          f"   version {rec.get('artifact_version', '?')}"
          f"   {rec.get('published_at', '')}")
    print()

    status = 0
    if ch != lh:
        status = 1
        print("STALE: the committed map does not match the code.")
        for line in differences(committed, live):
            print(f"  {line}")
        print("\n  Fix:  make promptmap && git add internal/promptmap.html\n")
    elif rec.get("content_hash") != ch:
        status = 2
        print("UNPUBLISHED: the committed map is current, the artifact is not.")
        for line in differences(
                json.loads(RECORD.read_text())["data"], committed) if rec.get("data") else []:
            print(f"  {line}")
        print(f"\n  Publishing needs the Artifact tool, so a Claude session must do it:\n"
              f"    1. read   {URL}\n"
              f"    2. publish internal/promptmap.html to that same url\n"
              f"    3. uv run python internal/tools/promptmap_sync.py --record <version>\n")
    else:
        print("IN SYNC: code, committed map and published artifact agree.")
    return status


def record(version: str) -> int:
    data = committed_data()
    RECORD.write_text(json.dumps({
        "url": URL,
        "artifact_version": version,
        "content_hash": content_hash(data),
        "published_at": _dt.datetime.now(_dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "note": "Written by promptmap_sync.py --record after a successful "
                "publish. The hash covers the map's DATA, not its HTML.",
    }, indent=2) + "\n", encoding="utf-8")
    print(f"recorded version {version} at {content_hash(data)[:12]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record", metavar="VERSION",
                    help="record that this map is now published as VERSION")
    args = ap.parse_args(argv)
    return record(args.record) if args.record else report()


if __name__ == "__main__":
    sys.exit(main())
