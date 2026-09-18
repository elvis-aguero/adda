"""The prompt/gate provenance map must keep telling the truth.

``internal/tools/promptmap.py`` renders a map that cites, for every piece of
text an agent sees and every gate that can stop it, an exact ``file:line``.
Such a map is only worth anything if a stale one FAILS rather than quietly
citing code that moved. These tests are that failure:

* every gate symbol in the registry still resolves (the generator raises
  ``SystemExit`` when one does not);
* every section of every assembled prompt still resolves to a real file and
  a line inside it — so a prompt that moves takes its citation along;
* the Done() sequence is still parsed out of ``feedback.py``'s own tuple
  rather than hand-listed.

No network, no model, no API cost: everything is read off the live graph
objects and the AST.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_GEN = _ROOT / "internal" / "tools" / "promptmap.py"


def _load():
    spec = importlib.util.spec_from_file_location("_promptmap", _GEN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def promptmap():
    if not _GEN.exists():  # pragma: no cover - the generator is checked in
        # internal/tools/promptmap.py is committed to this repo, not an
        # optional dependency or a piece of local environment -- its absence
        # means the checkout is broken, not that some external condition is
        # unmet. A skip here would hide that behind a green-looking run.
        pytest.fail("internal/tools/promptmap.py is missing from the "
                    "checkout -- this is a repo defect, not an environment "
                    "condition to skip past")
    return _load()


@pytest.fixture(scope="module")
def data(promptmap):
    return promptmap.build()


def test_every_gate_symbol_still_exists(promptmap):
    """A renamed or deleted gate must break the build, not the meeting."""
    gates = promptmap.build_gates()
    assert gates, "the gate registry is empty"
    for gate in gates:
        assert gate["line"] > 0
        assert (_ROOT / gate["file"]).exists(), gate["symbol"]


def test_done_sequence_is_read_from_the_source_tuple(promptmap):
    chain = promptmap.done_chain()
    assert chain[0] == "_pending_refusal", (
        "Done()'s first gate changed; the map's ordering claim is now wrong")
    assert len(chain) >= 3


def test_every_prompt_section_resolves_to_a_real_line(data):
    """No section may be UNRESOLVED: a map with a blank citation is worse
    than no map, because the blank is the one a reviewer will ask about."""
    unresolved = []
    for role in data["roles"]:
        for layer in role["layers"]:
            for section in layer["sections"]:
                source = section.get("source")
                if not source:
                    # A tool the backend SDK supplies has no definition HERE; the
                    # map says so rather than inventing a citation for it.
                    if not section.get("external"):
                        unresolved.append(
                            f"{role['id']}/{layer['kind']}/{section['tag']}")
                    continue
                path = _ROOT / source["file"]
                assert path.exists(), source["file"]
                n_lines = path.read_text(encoding="utf-8").count("\n") + 1
                assert 1 <= source["line"] <= n_lines, source
    assert not unresolved, f"unresolved prompt sections: {unresolved}"


def test_shared_blocks_are_cited_at_their_definition_not_their_use(data):
    """The charter is injected into two roles; both must cite knowledge/,
    which is what makes "cite a clause number" a shared contract."""
    charter = [b for b in data["shared"] if b["name"] == "FALSIFICATION_CHARTER"]
    assert charter, "FALSIFICATION_CHARTER vanished from knowledge/charter.py"
    citing = [
        section["injects"]["file"]
        for role in data["roles"]
        for layer in role["layers"]
        for section in layer["sections"]
        if section.get("injects", {}).get("name") == "FALSIFICATION_CHARTER"
    ]
    assert len(citing) >= 2, "the charter should reach at least two roles"
    assert all(path.endswith("knowledge/charter.py") for path in citing), citing


def test_entry_node_carries_the_run_paths_preamble(data):
    entry = [r for r in data["roles"] if r["entry"]]
    assert len(entry) == 1
    kinds = [layer["label"] for layer in entry[0]["layers"]]
    assert "RUN_PATHS_PREAMBLE_TEMPLATE" in kinds
    workers = [r for r in data["roles"] if not r["entry"]]
    for worker in workers:
        labels = [layer["label"] for layer in worker["layers"]]
        assert "WORKSPACE_PREAMBLE_TEMPLATE" in labels, worker["id"]


def _sources(data):
    for role in data["roles"]:
        for layer in role["layers"]:
            for key in ("definition", "assembled_at"):
                if layer.get(key):
                    yield f"{role['id']}/{layer['kind']}/{key}", layer[key]
            for section in layer["sections"]:
                if section.get("source"):
                    yield f"{role['id']}/{layer['kind']}/{section['tag']}", section["source"]


def test_a_citation_never_claims_a_span_it_did_not_verify(data):
    """The map may under-resolve; it may not overstate.

    An earlier generator searched a fixed 240-character head of each template
    and then reported that head's line count as the block's end — labelled
    ``exact``. Every template longer than seven lines was cited short while
    looking precise, which is the one failure mode a provenance map cannot
    have. A span is now only reported by a probe that matched the whole text
    (``exact``), read the syntax tree (``ast``), or matched line by line and
    says which end is which (``lines``); anything else is an anchor with no
    end line at all.
    """
    for where, source in _sources(data):
        assert source["match"] in {
            "exact", "ast", "lines", "line", "tag", "symbol", "docstring",
            "literal"}, where
        if source.get("span"):
            assert source["line_end"] >= source["line"], where
        else:
            assert "line_end" not in source, f"{where} reports an unverified end line"


def test_an_exact_citation_spans_exactly_the_text_it_cites(data):
    """``exact`` means the block is verbatim at those lines — so the line
    count of the cited text and of the cited span must agree."""
    for role in data["roles"]:
        for layer in role["layers"]:
            for section in layer["sections"]:
                source = section.get("source") or {}
                if source.get("match") != "exact":
                    continue
                span = source["line_end"] - source["line"]
                assert span == section["text"].strip("\n").count("\n"), (
                    f"{role['id']}/{section['tag']}: cited {source['file']}:"
                    f"{source['line']}-{source['line_end']} for a "
                    f"{section['text'].count(chr(10)) + 1}-line block")


def test_text_built_elsewhere_is_cited_to_the_code_that_builds_it(data):
    """The ``.format()`` fields in the preambles are whole stanzas written in
    ``agent_runtime.py``. Folding them into the template's own citation is how
    a resource stanza ends up attributed to ``agent_prompts.py``, where nobody
    searching for it will ever find it. The preamble stays ONE readable block,
    so the attribution lives in its parts.

    ``{roster}`` is entry-only: it lists the delegation targets read off the
    live graph, and a worker has none.
    """
    for role in data["roles"]:
        preamble = role["layers"][0]
        assert len(preamble["sections"]) == 1, (
            f"{role['id']}: the preamble is one prompt and must read as one block")
        parts = preamble["sections"][0]["parts"]
        fields = {part["field"]: part for part in parts if part.get("field")}
        expected = {"{resources}", "{knowledge}"}
        if preamble["label"] == "RUN_PATHS_PREAMBLE_TEMPLATE":
            expected.add("{roster}")
        assert set(fields) == expected, role["id"]
        for field, part in fields.items():
            assert part["source"]["file"].endswith("runtime/agent_runtime.py"), field


def test_the_preamble_parts_reassemble_into_the_preamble(data):
    """Whatever the map says about where each stretch comes from, the stretches
    in order ARE the prompt — a reader may assume concatenation, because that
    is what ``.format()`` does."""
    for role in data["roles"]:
        section = role["layers"][0]["sections"][0]
        assert "".join(p["text"] for p in section["parts"]) == section["text"]
        assert section["chars"] == len(section["text"])


def test_an_editable_section_is_exactly_the_lines_it_cites(data):
    """The page offers to edit a section only when the map can write the edit
    back. That promise is only safe if the cited lines ARE the section: read
    ``file`` from ``line`` to ``line_end`` and you must get the text back,
    character for character, or applying an edit would corrupt the source.

    Sections the map located by a weaker probe are marked not-editable with a
    reason instead — the same discipline as the citations themselves: never
    offer precision the generator cannot actually deliver.
    """
    seen: set[str] = set()
    for role in data["roles"]:
        for layer in role["layers"]:
            for section in layer["sections"]:
                edit = section["edit"]
                if not edit["ok"]:
                    assert edit["why"], f"{role['id']}: not-editable with no reason"
                    continue
                if edit.get("mode") == "literal":
                    # A different promise, just as checkable: the text is a
                    # stretch INSIDE the cited literal, appearing exactly once,
                    # so an edit replaces that stretch and nothing else.
                    import ast as _ast
                    src = (_ROOT / edit["file"]).read_text(encoding="utf-8")
                    node = next(
                        n for n in _ast.walk(_ast.parse(src))
                        if isinstance(n, _ast.Constant) and isinstance(n.value, str)
                        and n.lineno == edit["line"] and n.end_lineno == edit["line_end"]
                    )
                    assert node.value.count(section["text"].strip("\n")) == 1, (
                        f"{role['id']}/{section['tag']}: the cited literal does not "
                        f"hold this text exactly once, so an edit would have to guess")
                    continue
                if edit.get("mode") == "docstring":
                    # A docstring span is the LITERAL — quotes and indentation
                    # included — so the promise is different but just as checkable:
                    # the text shown must be what Python reads out of it.
                    import ast as _ast
                    src = (_ROOT / edit["file"]).read_text(encoding="utf-8")
                    node = next(
                        n for n in _ast.walk(_ast.parse(src))
                        if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))
                        and n.body and getattr(n.body[0], "lineno", None) == edit["line"]
                    )
                    assert _ast.get_docstring(node) == section["doc"], (
                        f"{role['id']}/{section['label']}: the catalog shows text the "
                        f"cited docstring does not contain")
                    continue
                lines = (_ROOT / edit["file"]).read_text(encoding="utf-8").splitlines()
                span = "\n".join(lines[edit["line"] - 1:edit["line_end"]])
                assert span == section["text"].strip("\n"), (
                    f"{role['id']}/{section['tag']}: {edit['file']}:{edit['line']}-"
                    f"{edit['line_end']} is not the text the page would let you edit")
                seen.add(edit["key"])
    assert seen, "no section is editable — the page has nothing to offer"


def test_shared_text_says_who_else_reads_it(data):
    """The charter is one block injected into several roles. Editing it from one
    role's page changes what the others see, so the page must say so before the
    edit, not after it lands."""
    charter = [
        section["edit"]
        for role in data["roles"]
        for layer in role["layers"]
        for section in layer["sections"]
        if section.get("injects", {}).get("name") == "FALSIFICATION_CHARTER"
        and section["edit"]["ok"]
    ]
    assert charter, "the charter is no longer an editable shared block"
    for edit in charter:
        assert edit["shared"]["also"], "a shared block that names no other reader"


def test_a_gate_offers_its_docstring_and_nothing_else(promptmap):
    """A gate card may be edited, but only its description.

    What a gate DOES is its code, and the one-line effect on the card is this
    map's own summary — neither is text a page can responsibly hand someone an
    edit box over. So the editable span is the docstring literal, and it must
    actually be that: read it back and Python must find the same text there.
    """
    import ast

    for gate in promptmap.build_gates():
        edit = gate["edit"]
        if not edit["ok"]:
            assert edit["why"], gate["symbol"]
            continue
        assert edit["mode"] == "docstring", gate["symbol"]
        tree = ast.parse((_ROOT / edit["file"]).read_text(encoding="utf-8"))
        node = next(
            n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.body and getattr(n.body[0], "lineno", None) == edit["line"]
        )
        assert ast.get_docstring(node) == gate["doc"], (
            f"{gate['symbol']}: the card shows text its cited docstring does not hold")


def test_a_gate_message_is_what_its_cited_expression_renders(promptmap):
    """A gate's nudge is prompt: it lands in the agent's context and steers it.

    The map shows it, so the map must be able to prove it. Re-parse the cited
    expression and render it the same way — it must come back identical, or the
    page is showing text the source does not produce.
    """
    import ast

    total = 0
    for gate in promptmap.build_gates():
        for message in gate["messages"]:
            total += 1
            # The segment is a multi-line expression lifted out of its
            # parentheses, so give it its own before re-parsing.
            expr = ast.parse("(" + message["source_expr"] + ")", mode="eval").body
            assert promptmap._render_message(expr) == message["text"], (
                f"{gate['symbol']}: the card shows a message its source does not render")
            assert message["edit"]["ok"] and message["edit"]["mode"] == "message"
    assert total >= 10, "the gates stopped saying anything to the agent — suspicious"


def test_a_computed_block_is_never_silently_reported_as_absent(data):
    """A generated map that claims a prompt section is empty, when every real
    run injects one, is worse than a map that fails to build.

    The `{roster}` helper first guessed at an import, failed, and hit its own
    `except Exception: return ""`. The map then printed "roster is empty for
    strategizer — nothing is injected" and looked perfectly fine. The entry
    role's roster is non-empty on the default graph, so an empty one means the
    builder broke, not that the prompt changed.
    """
    entry = [r for r in data["roles"]
             if r["layers"][0]["label"] == "RUN_PATHS_PREAMBLE_TEMPLATE"]
    assert entry, "no entry role found"
    for role in entry:
        parts = {p["field"]: p for p in role["layers"][0]["sections"][0]["parts"]
                 if p.get("field")}
        roster = parts["{roster}"]
        assert not roster["empty"], (
            f"{role['id']}: the roster rendered empty — the builder is broken, "
            "since the default graph wires four delegation targets")
        assert "<delegation_roster>" in roster["text"]


def test_the_rendered_roster_matches_the_graph_it_claims_to_describe(data):
    """The map enumerates its roles from `_graphs._default_graph()`; the roster
    must come from the same graph, or the page shows two different systems."""
    from adda._src.agents import _graphs

    graph = _graphs._default_graph()
    targets = {e.target for e in graph.edges if e.source == graph.entry}

    entry = next(r for r in data["roles"]
                 if r["layers"][0]["label"] == "RUN_PATHS_PREAMBLE_TEMPLATE")
    text = next(p["text"] for p in entry["layers"][0]["sections"][0]["parts"]
                if p.get("field") == "{roster}")

    for t in targets:
        assert t in text, f"{t} is wired but missing from the rendered roster"


# ---------------------------------------------------------------------------
# A tool the agent gets must be a tool the map shows
#
# render_tool_catalog builds the <tools> block from the LIVE closure dict's
# keys, so ConsultHandbook -- bound at agent_runtime.py as
# closure_tools["ConsultHandbook"] = _consult_handbook -- is really in every
# agent's prompt. The map built its catalog by scanning PascalCase `def`s, and
# that function is snake_case, so the one tool every single node is given was
# absent from the page that claims to be the agent's-eye view.
# ---------------------------------------------------------------------------


def test_every_role_shows_the_universally_injected_handbook_tool(data):
    for role in data["roles"]:
        assert "ConsultHandbook" in role["tools"], (
            f"{role['id']}: gets ConsultHandbook at runtime but the map omits it"
        )


def test_the_injected_tool_carries_its_real_docstring(data):
    """Showing the name without the text would be a different lie: the agent
    reads _consult_handbook's docstring, so the map must cite that."""
    for role in data["roles"]:
        catalog = next(lyr for lyr in role["layers"] if lyr["kind"] == "catalog")
        entry = next((s for s in catalog["sections"]
                      if s.get("label") == "ConsultHandbook"), None)
        assert entry is not None, f"{role['id']}: no ConsultHandbook catalog entry"
        assert "handbook" in entry["text"].lower()
        assert "chapter" in entry["text"].lower()


def test_a_per_delegation_rebind_is_not_treated_as_universal():
    """leaf.py rebinds closure_tools["Write"] per delegation. That is not a
    universal injection, and adding it would put Write in the strategizer's
    catalog -- a tool it does not have."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                           / "internal" / "tools"))
    import promptmap as pm

    assert "Write" in pm.injected_tool_docs(), "the Write rebind should still resolve"
    assert "Write" not in pm.universal_tool_names()


# ---------------------------------------------------------------------------
# A .format()-assembled block has no single home. Its pieces do.
#
# annotate_edits refused the WHOLE run_paths preamble because it carries
# parts -- so the template's own prose, which is a verbatim span of
# agent_prompts.py, and the prose inside a computed stanza, which is a string
# constant in the module that builds it, were both unreachable from the page.
# Only the formatted-in values have no source text to edit.
# ---------------------------------------------------------------------------


def _all_pieces(data):
    return [(role["id"], sec, pc)
            for role in data["roles"]
            for lyr in role["layers"]
            for sec in lyr.get("sections", [])
            for pc in (sec.get("pieces") or [])]


def test_the_assembled_preamble_offers_its_written_pieces(data):
    for role in data["roles"]:
        sec = next(s for lyr in role["layers"] for s in lyr.get("sections", [])
                   if s.get("parts"))
        assert sec["pieces"], f"{role['id']}: assembled section offers nothing"
        assert not sec["edit"]["ok"], "the block as a whole still has no one home"


def test_no_piece_is_offered_without_somewhere_to_write_it(data):
    """The map's standing rule: editability is derived from the citation,
    never asserted. A box with no span behind it is the failure being avoided."""
    for role_id, _sec, pc in _all_pieces(data):
        assert pc["edit"]["ok"] and pc["edit"].get("key"), role_id
        assert pc["edit"]["mode"] in ("span", "literal")
        assert pc["edit"]["file"] and pc["edit"]["line"]


def test_every_pieces_citation_actually_holds_its_text(data):
    """Re-resolve each piece against the tree. A citation the map cannot
    reproduce is exactly the overstatement this page exists to avoid."""
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "internal" / "tools"))
    import promptmap as pm

    for role_id, _sec, pc in _all_pieces(data):
        text = pc["text"].strip("\n")
        if pc["edit"]["mode"] == "literal":
            held = pm.containing_literal(text, [root / pc["edit"]["file"]])
            assert held is not None, f"{role_id}: {pc['label']!r} no longer resolves"
            assert held["file"] == pc["edit"]["file"]
        else:
            src = (root / pc["edit"]["file"]).read_text(encoding="utf-8")
            assert text in src, f"{role_id}: {pc['label']!r} is not in its cited file"


def test_the_computed_resource_stanza_is_reachable(data):
    """Its prose is an f-string constant with one home, even though its
    numbers are supplied per run -- so the wording IS editable from the page."""
    fields = {pc.get("field") for _r, _s, pc in _all_pieces(data)}
    assert "{resources}" in fields
