"""Every knowledge provider, held to one contract.

WHY PARAMETRISED OVER A REGISTRY
    Five corpora were built by five agents at five times, and four converged
    on the same call shape by imitation rather than by contract. Imitation
    does not fail when someone drifts: two providers shipped with NO REPLY CAP
    at all, which defeats the one thing the tool exists for -- keeping a
    corpus out of the context window. Nothing said a word, because nothing was
    comparing them.

    So this iterates ``knowledge.protocol.providers()``. A provider added
    without a registry entry is a provider nothing checks, and
    ``test_the_registry_covers_every_builder`` makes that state fail.

WHAT THIS ACTUALLY COVERS, WHICH IS LESS THAN IT LOOKS
    ``_LIVE`` holds only the providers needing no corpus and no constructor
    arguments: f3dasm and adda. Abaqus is skipped without its licensed docs,
    and literature needs a corpus object. So the parametrised tests below run
    against two of five unless something supplies the rest.

    Basilisk is the one that can be supplied, and is: the synthetic fixture
    from ``tests/basilisk_fixture.py`` is pointed at by env var at the bottom
    of this file, which takes the real coverage to three of five. Saying this
    out loud matters -- a contract test parametrised over a registry LOOKS
    like it covers everything in the registry, and that appearance is exactly
    the kind of thing this project keeps catching itself on.

WHAT IS NOT ASSERTED HERE
    Retrieval quality, and mechanism. Quality is measured per corpus against
    its own labelled queries, and the mechanisms are deliberately different --
    f3dasm gets WORSE with adda's unit mix and vice versa, measured. A test
    that forced one ranker would be enforcing tidiness against evidence.
"""
from __future__ import annotations

import os

import pytest

from adda._src.knowledge.protocol import (
    MAX_REPLY_CHARS,
    KnowledgeProvider,
    clip,
    providers,
)

_PROVIDERS = providers()
_LIVE = [n for n, s in _PROVIDERS.items()
         if not s["env"] and not s.get("needs_args")]


def _closures(name: str) -> dict:
    return _PROVIDERS[name]["build"]()


# --- the registry itself ----------------------------------------------------

def test_the_registry_covers_every_builder():
    """A provider absent from the registry is unchecked by everything below."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "adda" / "_src"
    found = set()
    for path in root.rglob("*.py"):
        if path.name == "protocol.py":
            continue
        for m in re.findall(r"^def (build_\w*closures)", path.read_text(), re.M):
            found.add(m)
    registered = {s["build"].__name__ for s in _PROVIDERS.values()}
    # _build_adda_closures is defined inside protocol.py itself
    missing = sorted(found - registered - {"build_declared_shared_closures"})
    known_non_knowledge = {
        "build_delegation_closures", "build_ledger_closures",
        "build_notes_closures", "build_feedback_closures",
        "build_notebook_closures", "build_openalex_closures",
        "build_semantic_scholar_closures"}
    assert not (set(missing) - known_non_knowledge), (
        f"these closure builders are not in the provider registry, so nothing "
        f"holds them to the contract: {sorted(set(missing) - known_non_knowledge)}")


# --- the contract, per provider --------------------------------------------

@pytest.mark.parametrize("name", sorted(_PROVIDERS))
def test_an_unconfigured_provider_returns_nothing_at_all(name):
    """Not a tool that explains itself. A registered tool that errors makes an
    agent that keeps calling it, and those are ERROR_RETURN -- the one KPI
    whose target is zero."""
    spec = _PROVIDERS[name]
    if not spec["env"]:
        pytest.skip(f"{name} needs no corpus, so it is always configured")
    assert not os.environ.get(spec["env"]), (
        f"{spec['env']} is set in this environment; this test cannot check "
        f"the unconfigured path")
    assert spec["build"]() == {}


@pytest.mark.parametrize("name", _LIVE)
def test_the_tool_is_registered_under_its_declared_name(name):
    """The registry's name is what lands in the prompt catalogue. A mismatch
    means the catalogue and the registry disagree about what exists."""
    assert _PROVIDERS[name]["tool"] in _closures(name)


@pytest.mark.parametrize("name", _LIVE)
def test_consult_returns_text_and_a_phrase_returns_a_menu(name):
    fn = _closures(name)[_PROVIDERS[name]["tool"]]
    out = fn("how do I run a simulation")
    assert isinstance(out, str) and out.strip()


@pytest.mark.parametrize("name", _LIVE)
def test_a_reply_is_capped(name):
    """The whole point of a lookup is to keep the corpus OUT of the context
    window. Two providers shipped uncapped and nothing noticed."""
    fn = _closures(name)[_PROVIDERS[name]["tool"]]
    for query in ("a", "the", "run", "data", "solver", "store"):
        assert len(fn(query)) <= MAX_REPLY_CHARS + 200, (
            f"{name} returned {len(fn(query))} chars for {query!r}")


@pytest.mark.parametrize("name", _LIVE)
def test_a_miss_says_the_miss_is_about_this_index(name):
    """An agent told a bare 'no results' concludes the thing does not exist,
    when it may simply live in another corpus."""
    fn = _closures(name)[_PROVIDERS[name]["tool"]]
    out = fn("zzqx wqjm vbrt")
    assert "zzqx" in out, f"{name} does not echo what it searched"


# --- the shared helpers -----------------------------------------------------

def test_clip_says_it_truncated():
    """Silent truncation is worse than none: an agent cannot tell a short
    answer from a cut-off one, and acts on half a rule as though it were
    whole."""
    assert clip("x" * 10, limit=100) == "x" * 10
    out = clip("x" * 500, limit=100)
    assert len(out) < 500 and "truncated" in out


def test_the_protocol_is_structural_not_nominal():
    """Providers live in four packages and share no base class. The contract
    has to be satisfiable by shape, or uniformity would mean a refactor of
    working, measured code."""
    from adda._src.knowledge.f3dasm_api import AddaApi

    assert isinstance(AddaApi(), KnowledgeProvider)


# --- basilisk, against the synthetic fixture --------------------------------
#
# Not a duplicate of the parametrised tests above: those skip basilisk because
# it is env-gated, and this supplies the env. It is the only provider whose
# corpus CAN be synthesised, so it is the only one that can be lifted out of
# the skip.

@pytest.fixture(scope="module")
def basilisk_closures(tmp_path_factory, monkeypatch_session=None):
    from adda._src.knowledge.basilisk import build_basilisk_docs_closures

    from .basilisk_fixture import build_corpus

    root = tmp_path_factory.mktemp("basilisk_protocol")
    build_corpus(root)
    return build_basilisk_docs_closures(root)


def test_basilisk_registers_its_declared_tool(basilisk_closures):
    assert "ConsultBasilisk" in basilisk_closures


def test_basilisk_caps_its_reply(basilisk_closures):
    """It shipped uncapped. A solver header with its full literate
    documentation and a source dump is exactly the unbounded page the cap
    exists to prevent."""
    fn = basilisk_closures["ConsultBasilisk"]
    for query in ("a", "solver", "flow", "navier-stokes/centered.h"):
        assert len(fn(query)) <= MAX_REPLY_CHARS + 200, query
    assert len(fn("navier-stokes/centered.h", source=True)) <= MAX_REPLY_CHARS + 200


def test_basilisk_dispatches_a_key_to_an_entry_and_a_phrase_to_a_menu(
        basilisk_closures):
    fn = basilisk_closures["ConsultBasilisk"]
    assert fn("two-phase.h").startswith("two-phase.h")
    assert "match(es)" in fn("rising bubble")


def test_basilisk_says_a_miss_is_about_this_index(basilisk_closures):
    out = basilisk_closures["ConsultBasilisk"]("zzqx wqjm vbrt")
    assert "zzqx" in out


# --- the reason the rename was worth doing ----------------------------------

def test_no_prompt_names_a_tool_that_does_not_exist():
    """A tool name written by hand into prompt text can desync from the tool.

    This is the defect the rename was really about. ``ConsultHandbook``
    appears in 46 places across prompts, code and tests; ``CorpusSearch``
    appeared in 44. Nothing compared them to the live tool set, so a prompt
    could instruct an agent to call something that no longer existed and the
    only symptom would be the agent trying, failing, and recording an
    ERROR_RETURN -- the one KPI whose target is zero.

    Scanned from the promptmap's own data, which is generated from the live
    Graph and Agent objects, so this asserts what the model is ACTUALLY sent
    rather than what any source file happens to contain.
    """
    import json
    import pathlib
    import re

    html = pathlib.Path(__file__).resolve().parents[1] / "internal" / "promptmap.html"
    if not html.exists():
        pytest.skip("promptmap.html not generated; run `make promptmap`")
    blob = re.search(r"const DATA = (\{.*?\});\n", html.read_text(), re.S)
    assert blob, "promptmap.html carries no DATA block"
    data = json.loads(blob.group(1))

    live = {t for role in data["roles"] for t in role["tools"]}
    live |= {spec["tool"] for spec in _PROVIDERS.values()}

    named: set[str] = set()
    for role in data["roles"]:
        for layer in role["layers"]:
            for section in layer.get("sections", []):
                named |= set(re.findall(r"\b(Consult[A-Z]\w+)",
                                        section.get("text") or ""))

    ghosts = sorted(named - live)
    assert not ghosts, (
        f"prompt text names these tools, which no agent is given: {ghosts}. "
        f"Either the tool was renamed and the prompt was not, or the prompt "
        f"is instructing the agent to call something that does not exist.")


def test_every_knowledge_tool_follows_the_naming_scheme():
    """``Consult<Corpus>``. Not cosmetic: an agent handed five references
    should be able to guess the fifth from the four it has seen."""
    import re

    for name, spec in _PROVIDERS.items():
        assert re.fullmatch(r"Consult[A-Z]\w+", spec["tool"]), (
            f"{name} registers {spec['tool']!r}, which is off-scheme")


def test_no_rendered_text_calls_a_tool_that_is_no_longer_defined():
    """The check above covers ``Consult*`` names only, which is why a merge of
    thirteen other tools could leave the map saying ``CheckDeliverable()`` in
    a gate's phase and ``MilestoneSkip(reason)`` as a gate's escape while
    every test stayed green.

    This one reads EVERYTHING the map renders -- prompt sections, tool
    descriptions, gate messages, the map's own gate table -- and flags any
    call-shaped token in the tool naming vocabulary that no longer has a
    definition anywhere in the package. The vocabulary is the verbs tool
    names are built from; a library class (``ExperimentData(``) is not in
    it, and a retired tool name always is.
    """
    import importlib.util
    import json
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    html = root / "internal" / "promptmap.html"
    if not html.exists():
        pytest.skip("promptmap.html not generated; run `make promptmap`")
    blob = re.search(r"const DATA = (\{.*?\});\n", html.read_text(), re.S)
    assert blob, "promptmap.html carries no DATA block"
    data = json.loads(blob.group(1))
    text = json.dumps(data, ensure_ascii=False)

    spec = importlib.util.spec_from_file_location(
        "_promptmap_for_ghosts", root / "internal" / "tools" / "promptmap.py")
    pm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pm)
    defined = set(pm.tool_docs()) | set(pm.injected_tool_docs())
    defined |= {spec["tool"] for spec in _PROVIDERS.values()}
    # The backend-native tools (Read, Bash, ...) have no definition in this
    # package; the roster is the authority that they exist.
    defined |= {t for role in data["roles"] for t in role["tools"]}

    verbs = ("Add|Ask|Cancel|Check|Confer|Consult|Corpus|Delegat|Delete|Done|"
             "Edit|FollowUp|Get|Hypothesis|Ledger|Link|Milestone|Oracle|Query|"
             "Read|Recall|Reply|Report|Run|Show|Wait|Write")
    called = set(re.findall(rf"\b((?:{verbs})[A-Za-z]*)\(", text))
    ghosts = sorted(called - defined)
    assert not ghosts, (
        f"the prompt map renders calls to {ghosts}, which no longer exist. "
        "A tool was renamed or merged and this text was not updated.")
