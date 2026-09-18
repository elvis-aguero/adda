"""What adda's docstrings are worth, measured where a reader actually lands.

WHY A TOOL AND NOT A ONE-OFF REPORT
    "75% of defs have a docstring" is a number that cannot be acted on: it
    counts a private helper's one-liner the same as the description of a tool
    the model is told is AUTHORITATIVE. This weights by who reads the text.

THE FOUR AUDIENCES, IN PRIORITY ORDER
    P0  the public API -- ``adda.__all__`` and the public methods of those
        classes. What a person types.
    P1  the agent-facing tool descriptions. These are NOT documentation: they
        are PROMPT, injected verbatim by ``render_tool_catalog`` under a
        header telling the model they are authoritative. A thin one is a
        run-quality defect, not a docs defect, and it is paid on every call.
    P2  the declared knobs in ``settings.KNOWN_KEYS``.
    P3  everything else.

WHAT IT REFUSES TO MEASURE
    Prose quality. There is no threshold on "is this well written", because
    any such threshold would be satisfied by padding. The checks here are all
    things that are either true or false about the text: absent, unread by
    anyone, shorter than the shortest useful description, naming a file that
    does not exist.

    The one number that IS a judgement call -- ``--tool-floor``, the length
    below which an agent-facing description is called thin -- is exposed as a
    flag and defaults to 220 characters, which is where this repo's own
    distribution has a visible gap (median 505, and six tools below 220).

THE FINDING THIS WAS WRITTEN FOR
    A public symbol that nothing in the repository ever constructs. Its
    docstring cannot be wrong, because nothing it describes runs -- and it is
    still the first thing a reader of ``adda.__all__`` meets.

    uv run python internal/tools/docstring_audit.py [--tool-floor N] [--all]
"""
from __future__ import annotations

import argparse
import ast
import collections
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: Extensions worth checking a docstring reference against. A docstring that
#: points at a file which no longer exists is stale in a way no reader can
#: detect from the text.
_PATH_RE = re.compile(
    r"``([^`]+?\.(?:py|md|json|jsonl|ipynb|csv|yaml|html))``"
    r"|`([^`]+?\.(?:py|md|json|jsonl|ipynb|csv|yaml|html))`")

#: Named here rather than inferred: these are produced by a RUN, not shipped
#: in the tree, so "does this path exist" is the wrong question for them.
_RUNTIME_ARTIFACTS = frozenset({
    "run_config.json", "hypotheses.json", "pipeline.ipynb", "solution.md",
    "delegation_log.jsonl", "diagnostics.jsonl", "run_ledger.csv",
    "PROBLEM_STATEMENT.md", "config.yaml",
})


def _symbols():
    """Every def/class in the package, with the class that owns it."""
    out = []
    for path in sorted((ROOT / "src/adda").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for top in tree.body:
            stack = [(top, None)]
            while stack:
                node, owner = stack.pop()
                if isinstance(node, ast.ClassDef):
                    stack += [(s, node.name) for s in node.body]
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                         ast.ClassDef)):
                    continue
                args = getattr(node, "args", None)
                out.append({
                    "name": node.name, "owner": owner,
                    "file": str(path.relative_to(ROOT)), "line": node.lineno,
                    "doc": ast.get_docstring(node),
                    "args": [] if args is None else [
                        a.arg for a in args.posonlyargs + args.args
                        + args.kwonlyargs if a.arg not in ("self", "cls")],
                })
    return out


def _rendered_tools():
    """The tool descriptions AS THE MODEL RECEIVES THEM.

    Read from the promptmap's own data rather than from source, because what
    reaches the model is the rendered catalog: a docstring that never makes
    it into a live closure is not a prompt problem, and one that does is,
    wherever it happens to be written.
    """
    html = ROOT / "internal/promptmap.html"
    if not html.exists():
        return {}
    blob = re.search(r"const DATA = (\{.*?\});\n", html.read_text(), re.S)
    if not blob:
        return {}
    tools: dict[str, str] = {}
    for role in json.loads(blob.group(1))["roles"]:
        for layer in role["layers"]:
            if layer.get("label") != "<tools> catalog":
                continue
            for section in layer.get("sections", []):
                m = re.match(r"### (\w+)\n(.*)", (section.get("text") or "").strip(),
                             re.S)
                if m:
                    tools.setdefault(m.group(1), m.group(2).strip())
    return tools


def _reference_index() -> collections.Counter:
    """Every name used in a VALUE position, counted from the AST.

    Four rules were tried here and three were wrong. The record matters more
    than the result, because each wrong one produced a confident, plausible,
    false list:

    1. ``Name(`` -- counts constructions. Called ``Agent`` dead: it is a base
       class nobody calls and everybody subclasses.
    2. A regex widened to annotations. Called ``Task`` ALIVE, on the strength
       of ``## Stage 1: Task restatement`` inside a prompt string. This
       repository stores a great deal of English in string literals, so any
       regex over source text reads prose as code.
    3. AST names, minus one per import. Called ``get_evaluator`` dead --
       ``adda/__init__.py`` imports every public name, so the decrements
       outweighed the uses.

    4. Calls, base classes and annotations only. Called ``DebuggerAgent``
       dead: the tests that exercise it pass it as a bare class object inside
       a tuple, which is none of those three.

    What is left is the narrow question actually being asked: does this name
    appear anywhere, in code, other than its own definition and the plumbing
    that re-exports it? Publication is not use -- a dead export is precisely
    a name that is exported and nothing else.
    """
    refs: collections.Counter = collections.Counter()

    #: Pure re-export surfaces. A name listed here is being PUBLISHED, not
    #: used, and counting the publication as a use makes every export
    #: self-justifying.
    reexport = {ROOT / "src/adda/__init__.py"}

    for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "tests").rglob("*.py")):
        if path in reexport:
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        skip: set[int] = set()
        for node in ast.walk(tree):
            # `__all__ = [...]` publishes names; it does not use them.
            if isinstance(node, ast.Assign) and any(
                    isinstance(tgt, ast.Name) and tgt.id == "__all__"
                    for tgt in node.targets):
                skip |= {id(sub) for sub in ast.walk(node)}
            # `from x import Name` is plumbing, not a use of the concept.
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                skip |= {id(sub) for sub in ast.walk(node)}
            # a class/def statement DEFINES its name; that is not a use
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                skip.add(id(node))
        for node in ast.walk(tree):
            if id(node) in skip:
                continue
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                refs[node.id] += 1
            elif isinstance(node, ast.Attribute):
                refs[node.attr] += 1
    return refs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tool-floor", type=int, default=220,
                    help="chars below which an agent-facing description is "
                         "reported as thin (default: 220)")
    ap.add_argument("--all", action="store_true",
                    help="include P3, which is most of the package")
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT / "src"))
    import adda
    from adda._src.runtime import settings

    public = set(adda.__all__)
    tools = _rendered_tools()
    syms = _symbols()

    def priority(s):
        if s["name"] in public and s["owner"] is None:
            return "P0 public API"
        if s["owner"] in public and not s["name"].startswith("_"):
            return "P0 public method"
        if s["name"] in tools:
            return "P1 agent tool"
        if s["name"] in settings.KNOWN_KEYS:
            return "P2 knob"
        return "P3"

    for s in syms:
        s["prio"] = priority(s)
    surface = [s for s in syms
               if args.all or not s["prio"].startswith("P3")]

    print(f"=== surface audited: {len(surface)} symbols "
          f"({collections.Counter(s['prio'] for s in surface).most_common()}) ===\n")

    missing = [s for s in surface if s["doc"] is None]
    print(f"--- no docstring at all: {len(missing)} ---")
    for s in missing:
        print(f"    [{s['prio']}] {s['file']}:{s['line']} {s['name']}")

    print(f"\n--- agent-facing descriptions under {args.tool_floor} chars "
          f"(the model is told these are AUTHORITATIVE) ---")
    thin = sorted((len(b), n) for n, b in tools.items() if len(b) < args.tool_floor)
    for n, name in thin:
        print(f"    {n:5d}  {name}")
    if tools:
        lens = sorted(len(b) for b in tools.values())
        print(f"    ({len(thin)} of {len(tools)}; median {lens[len(lens) // 2]})")

    print("\n--- docstrings naming a file that does not exist ---")
    for s in surface:
        for a, b in _PATH_RE.findall(s["doc"] or ""):
            ref = (a or b).split(":")[0].strip()
            base = pathlib.Path(ref).name
            if base in _RUNTIME_ARTIFACTS:
                continue
            if not (ROOT / ref).exists() and not any(
                    p.name == base for p in ROOT.rglob(base)):
                print(f"    [{s['prio']}] {s['file']}:{s['line']} "
                      f"{s['name']} -> {ref}")

    print("\n--- PUBLIC BUT DEAD: exported, documented, never used ---")
    refs = _reference_index()
    dead = []
    for name in sorted(public):
        s = next((x for x in syms if x["name"] == name and x["owner"] is None), None)
        if s is None:
            continue
        if refs[name] <= 0:
            dead.append((name, s))
            print(f"    {s['file']}:{s['line']} {name}  "
                  f"-- referenced {max(refs[name], 0)} times "
                  f"repo-wide, incl. tests")
    if not dead:
        print("    none")
    print(f"\n{len(dead)} dead public export(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
