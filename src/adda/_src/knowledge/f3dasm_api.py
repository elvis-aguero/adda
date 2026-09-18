"""f3dasm's API, read off the INSTALLED package at run time.

WHY THIS EXISTS
    The implementer and datagenerator write f3dasm code. What they know about
    f3dasm is whatever the model remembers plus ``F3DASM_CORE_IDIOMS`` — 85
    lines of hand-verified snippets. Everything else is a guess, and a wrong
    guess costs a delegation to discover.

    f3dasm's documented surface is ~117,000 characters of docstring across 243
    symbols (measured, see ``tests/test_f3dasm_api.py``). That is roughly the
    size of adda's entire static prompt, so it cannot be injected; it has to be
    looked up. This module is the lookup.

NEVER STALE, BY CONSTRUCTION
    The index is built by importing the f3dasm that this run will actually
    execute against — not by parsing a checked-out source tree, which on a
    cluster may be a different version or absent entirely. If f3dasm moves an
    API, the index moves with it in the same process.

    ``tests/test_f3dasm_api.py`` additionally asserts that every entry still
    matches live introspection, so a stale hand-edit cannot survive CI. This is
    the same discipline ``knowledge/idioms.py`` already applies to its snippets.

THE ONE DETAIL THAT MAKES THIS USEFUL RATHER THAN HARMFUL
    ``__module__`` is a LIE for every public f3dasm symbol. ``ExperimentData``
    reports ``f3dasm._src.experimentdata``; the import an agent must write is
    ``from f3dasm import ExperimentData``. A naive inspect/AST index hands over
    the private path, and the agent writes a fragile private import — worse
    than no tool at all. So every entry resolves its CANONICAL PUBLIC PATH by
    walking f3dasm's 9 public namespaces, and the entry leads with the import
    line rather than the definition site.

    Of 125 symbols defined in f3dasm, only 47 are publicly reachable. The other
    78 are answerable — an agent reading a traceback needs to look them up —
    but they are marked PRIVATE with an explicit "do not import this", so a
    lookup cannot be mistaken for an endorsement.
"""

from __future__ import annotations

import importlib
import inspect
import pathlib
import pkgutil
import warnings
from dataclasses import dataclass, field

__all__ = ["ADDA_UNITS", "AddaApi", "Entry", "F3dasmApi", "PackageApi",
           "build_index"]

#: Cap on a single consult() reply, from the shared contract. Every provider
#: uses the same number so the budget is a constant an agent can ignore rather
#: than something it has to reason about per tool.
from .protocol import MAX_REPLY_CHARS as _MAX_CHARS

#: Dropped from concept queries. An agent writes "how do I sample the design
#: space"; only three of those words carry signal, and counting the rest
#: rewards whichever docstring happens to be longest.
#:
#: Being short of a function word is not harmless. "get the best design found
#: so far" kept ``so`` and ``far``; ``so`` then matched ``sobol`` and lifted
#: that symbol's COVERAGE from 1/5 to 2/5, which is a multiplier on the whole
#: score — so a stray preposition, not a concept, put a sampler above
#: ``ExperimentData.get_n_best_output``.
#:
#: A stopword may appear INSIDE a symbol name — ``from_file``, ``to_numpy``,
#: ``store_as_json``, ``select_with_status`` all hinge on a particle — and that
#: is harmless while some other token still tells those symbols apart. What is
#: NOT allowed is a stopword that is the ONLY thing distinguishing two symbols:
#: ``all`` was in this list until ``mark`` and ``mark_all`` showed that it
#: carries the whole distinction, so it was taken out.
#: ``tests/test_f3dasm_api_retrieval.py`` enforces exactly that, over the live
#: index rather than a hand-kept list of exceptions. Exact-name lookup is
#: scored above tokenisation, so a symbol NAMED for a stopword
#: (``ExperimentSample.get``) stays reachable regardless.
_STOP = frozenset("""
a about after again against along already also although always am an and
another any anyone anything are around as at away back be because been before
being below between both but by can cannot come could did do does doing done
down during each either else enough even ever every far few for from further
get getting give go going good got had has have having he her here hers him his
how however i if in indeed instead into is it its itself just keep kept let
like likely made make many may maybe me might mine more most much must my
myself near need needs neither never next no nor not nothing now of off often
on once one only onto or other others our ours out over own per perhaps please
put quite rather really same say see seem seen several shall she should since
so some somehow someone something sometimes somewhat soon still such sure take
taken tell than that the their theirs them themselves then there therefore
these they thing things this those though through thus to together too toward
under unless until up upon us use used useful using usually very via want was
way ways we well were what whatever when whenever where whether which while who
whom whose why will with within without would yet you your yours
""".split())


#: Everyday English -> the word f3dasm actually uses in a symbol name.
#:
#: WHY THIS EXISTS. Four of the five query tiers are saturated (r@5 = 1.00);
#: every remaining point is in `synonym`, where the query deliberately avoids
#: f3dasm's vocabulary — "save my results to disk" for ``store``, "load a
#: previous run" for ``from_file``. That is VOCABULARY MISMATCH, and no amount
#: of lexical tuning reaches it: the right symbol shares no token with the
#: query, so it scores zero before any weighting applies.
#:
#: HOW IT WAS AUTHORED, which decides whether the measurement means anything.
#: The right-hand side is the token frequency of f3dasm's own symbol NAMES
#: (``store`` 16, ``call`` 13, ``sample`` 12, ``load`` 8 …); the left-hand side
#: is ordinary English for each. It was written from the API surface and from
#: general usage, NOT by reading which labelled queries fail — an alias map
#: tuned against the query set would score well and generalise to nothing.
#: Terms already in f3dasm's vocabulary are deliberately absent: "sample" needs
#: no alias.
_ALIASES: dict[str, tuple[str, ...]] = {
    # persistence
    "save": ("store",), "write": ("store",), "persist": ("store",),
    "dump": ("store",), "serialize": ("store",), "export": ("store",),
    "read": ("load", "from"), "open": ("load", "from"),
    "restore": ("load", "from"), "import": ("load", "from"),
    "deserialize": ("load", "from"), "reload": ("load", "from"),
    # running an evaluation
    "execute": ("call", "run"), "invoke": ("call", "run"),
    "apply": ("call", "run"), "simulate": ("evaluate", "call"),
    "compute": ("evaluate", "call"), "score": ("evaluate",),
    "solver": ("datagenerator",), "simulator": ("datagenerator",),
    "oracle": ("datagenerator",), "blackbox": ("datagenerator",),
    "objective": ("output",), "response": ("output",), "target": ("output",),
    # the design space
    "variable": ("parameter",), "knob": ("parameter",),
    "feature": ("parameter",), "dimension": ("parameter",),
    "factor": ("parameter",),
    "category": ("categorical",), "choice": ("categorical",),
    "option": ("categorical",), "label": ("categorical", "output"),
    "integer": ("discrete",), "int": ("discrete",), "float": ("continuous",),
    "real": ("continuous",), "bounds": ("continuous", "parameter"),
    "range": ("continuous", "parameter"), "fixed": ("constant",),
    # designs of experiments
    "doe": ("sample", "sampler"), "draw": ("sample",),
    "lhs": ("latin",), "hypercube": ("latin",),
    "quasirandom": ("sobol",), "discrepancy": ("sobol",),
    "factorial": ("grid",), "sweep": ("grid",),
    # the data
    "dataset": ("data", "experimentdata"), "table": ("pandas", "data"),
    "dataframe": ("pandas",), "matrix": ("numpy", "array"),
    "vector": ("numpy", "array"), "tensor": ("numpy", "array"),
    "missing": ("nan",), "null": ("nan",), "empty": ("nan",),
    "size": ("len",), "count": ("len",), "many": ("len",),
    "merge": ("add",), "combine": ("add",), "concatenate": ("add",),
    "append": ("add",), "join": ("add",),
    "filter": ("select",), "subset": ("select",), "where": ("select",),
    "optimal": ("best",), "optimum": ("best",),
    "minimum": ("best",), "maximum": ("best",), "top": ("best",),
    # execution environment
    "parallel": ("mpi",), "cluster": ("mpi",), "hpc": ("mpi",),
    "slurm": ("mpi",), "distributed": ("mpi",),
    "config": ("yaml",), "settings": ("yaml",),
    "workflow": ("step", "pipeline"), "chain": ("step", "pipeline"),
    "stage": ("step",),
}

#: An alias hit is real evidence but weaker than the word f3dasm itself uses,
#: so it never outranks a literal match. Below ~0.5 the expansion stops
#: rescuing anything; above ~0.8 it starts reordering queries that were
#: already right.
_ALIAS_WEIGHT = 0.6


def _expand(toks: list[str], aliases: dict[str, tuple]) -> dict[str, str]:
    """``{alias term: the query token it stands in for}``.

    Keyed by the introduced term so scoring can look it up, valued by the
    origin so COVERAGE is still counted per query token — an expanded term
    must not let one query word cover the query twice.
    """
    out: dict[str, str] = {}
    for t in toks:
        for alias in aliases.get(t, ()):
            if alias not in toks:
                out.setdefault(alias, t)
    # An English term for one f3dasm identifier is often TWO words -- "black
    # box" for ``blackbox``, "latin hypercube" for ``latin``. Looking up single
    # tokens alone can never reach those keys, which is a gap in the mechanism
    # rather than in the vocabulary.
    for a, b in zip(toks, toks[1:], strict=False):
        for alias in aliases.get(a + b, ()):
            if alias not in toks:
                out.setdefault(alias, a)
    return out


@dataclass(frozen=True)
class Entry:
    """One f3dasm symbol, as an agent needs to see it."""

    #: dotted name used as the lookup key — the public path when there is one
    key: str
    kind: str                      # class | function | method | module | constant | markdown
    #: ``from X import Y`` line, or None when the symbol is private
    import_line: str | None
    signature: str
    summary: str                   # first paragraph of the docstring
    doc: str                       # the whole docstring
    where: str                     # file:line, for reading the source
    private: bool = False
    #: public path of the owning class, for a method
    owner: str | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)
    #: set when the live object is NOT f3dasm's own — adda monkeypatches two
    #: ExperimentData methods at import time, so what runs differs from what
    #: f3dasm documents. Naming the patch is the whole point: this is
    #: behaviour no docstring in f3dasm describes.
    patched_by: str | None = None


def _summary(doc: str) -> str:
    """First paragraph of a numpydoc docstring — before any section header.

    f3dasm documents in numpydoc, so the text above ``Parameters\\n------`` is
    the one-line meaning; everything below is detail the agent asks for only
    once it has chosen the symbol.
    """
    out: list[str] = []
    for line in doc.splitlines():
        if set(line.strip()) == {"-"} and out:
            out.pop()               # drop the header line above the rule
            break
        if not line.strip() and out:
            break
        out.append(line.strip())
    return " ".join(out).strip()


def _signature(obj, drop_self: bool = False) -> str:
    """Rendered signature. ``self`` is dropped for methods: the agent writes
    ``data.store(...)``, never ``store(data, ...)``, so showing it is noise
    that also invites a wrong call."""
    try:
        sig = inspect.signature(obj)
    except (TypeError, ValueError):
        return "(...)"
    if drop_self:
        params = [p for n, p in sig.parameters.items() if n != "self"]
        try:
            sig = sig.replace(parameters=params)
        except ValueError:
            pass
    return str(sig)


def _where(obj, package: str = "f3dasm") -> tuple[str, str | None]:
    """``(file:line, patched_by)`` for a live object.

    ``patched_by`` is set when the source file lies OUTSIDE the package being
    indexed — i.e. something has replaced that package's own function. adda
    does exactly that to two f3dasm ExperimentData methods, so the distinction
    is not hypothetical, and an index that silently reported adda's patch as
    f3dasm's API would be actively misleading.

    When the package being indexed IS adda, the same test does the right thing
    by construction: adda's own files sit inside adda's root, so they take the
    early return and no patch is claimed.
    """
    try:
        f = inspect.getsourcefile(obj) or "?"
        _, line = inspect.getsourcelines(obj)
    except (OSError, TypeError):
        return "?", None
    pkg = _package_root(package)
    if pkg and f.startswith(pkg):
        # package-relative: the absolute site-packages prefix is noise and
        # differs between machines
        return f"{package}{f[len(pkg):]}:{line}", None
    owner = "adda" if "/adda/" in f else _pkg_of(f)
    short = f.rsplit("/site-packages/", 1)[-1]
    if "/src/" in short:
        short = short.split("/src/", 1)[-1]
    return f"{short}:{line}", owner


def _package_root(package: str = "f3dasm") -> str | None:
    """Directory the package lives in, or None when it does not import."""
    try:
        mod = importlib.import_module(package)
        return (mod.__file__ or "").rsplit("/", 1)[0] or None
    except Exception:  # noqa: BLE001
        return None


def _pkg_of(path: str) -> str:
    tail = path.rsplit("/site-packages/", 1)[-1]
    return tail.split("/", 1)[0].removesuffix(".py")


def _module_entries(mods: dict, package: str, index: dict) -> None:
    """One entry per module, carrying its module docstring.

    WHY THIS IS NOT FREE, AND WHY IT WAS ORIGINALLY LEFT OUT
        The walk already imports every module -- the docstring is sitting on
        the object the loop is holding. It was discarded rather than unvisited,
        which is a design choice, not a limitation, and the choice was right
        for f3dasm: its module docstrings are thin, and its knowledge really
        does live in symbols.

        adda is the opposite. 23% of its docstring mass (72,061 of 314,202
        characters) is in module docstrings, because the house convention puts
        the "WHY THIS EXISTS" argument at the top of the file rather than on
        any one symbol. Indexing symbols only cannot reach it.

    ``import_line`` is None and ``private`` is False on purpose. A module
    under ``_src`` is not something to import -- the entry exists to point a
    reader at a FILE -- but marking it private would apply the 0.15 crowding
    penalty meant for private SYMBOLS, and sink exactly the text this was
    added to surface.
    """
    for name, mod in mods.items():
        doc = inspect.getdoc(mod) or ""
        if not doc:
            continue
        f = getattr(mod, "__file__", None) or "?"
        root = _package_root(package)
        where = f"{package}{f[len(root):]}:1" if root and f.startswith(root) else f"{f}:1"
        index[name] = Entry(
            key=name, kind="module", import_line=None, signature="",
            summary=_summary(doc), doc=doc, where=where, private=False,
        )


def _constant_entries(mods: dict, package: str, index: dict) -> None:
    """One entry per module-level CONSTANT, carrying its value.

    The value is the point. ``settings.KNOWN_KEYS`` is the entire declared
    knob surface of this package and it is a frozenset, so a symbol-only walk
    -- which indexes classes and functions -- cannot see it, and "where do I
    set the context window" has nothing to match. Rendering the value into
    the entry's text puts every knob name in the corpus exactly once.

    UPPER_SNAKE only. Lower-case module globals are caches, locks, compiled
    regexes and singletons -- state, not vocabulary -- and indexing them adds
    noise with no question behind it.
    """
    root = _package_root(package)
    for name, mod in mods.items():
        f = getattr(mod, "__file__", None) or "?"
        where = f"{package}{f[len(root):]}" if root and f.startswith(root) else f
        for attr, v in vars(mod).items():
            if not attr.isupper() or attr.startswith("_"):
                continue
            if inspect.isclass(v) or inspect.isfunction(v) or inspect.ismodule(v):
                continue
            key = f"{name}.{attr}"
            if key in index:
                continue
            rendered = repr(v)
            if len(rendered) > 600:
                rendered = rendered[:600] + " …"
            # The module's own docstring is prepended to the BODY (weight 2,
            # not 12) so the constant is reachable by the concept its module
            # explains -- BACKSTOP_USD = 'backstop_usd' is a literal that
            # teaches nothing on its own, while terminal.py's docstring is
            # what says a run can be stopped by a cost ceiling. Body weight,
            # because the module already has its own entry and should still
            # outrank its constants for a question about the concept.
            mdoc = inspect.getdoc(mod) or ""
            index[key] = Entry(
                key=key, kind="constant", import_line=None, signature="",
                summary=f"{attr} = {rendered[:200]}",
                doc=f"{attr} = {rendered}\n\n{mdoc}",
                where=f"{where}:1", private=False,
            )


def _markdown_entries(package: str, index: dict) -> None:
    """One entry per markdown file SHIPPED INSIDE the package.

    The invariant tier was the one the symbol, module and constant units all
    left at 0.20. "Can I call the objective directly instead of
    get_evaluator" is answered by ``knowledge/entries/0001-*.md``, which is
    not Python, so no walk over module attributes can reach it however it is
    weighted. That was a missing unit, not a ranking problem.

    Package-shipped markdown only -- files under the installed package root.
    Repository docs are not indexed: they are not installed, so an index
    built from the running package could not find them on a cluster, which is
    the same never-stale argument that made this whole module introspective.
    """
    root = _package_root(package)
    if not root:
        return
    for path in sorted(pathlib.Path(root).rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        rel = str(path)[len(root):].lstrip("/")
        key = f"{package}:{rel}"
        index[key] = Entry(
            key=key, kind="markdown", import_line=None, signature="",
            summary=_summary(text), doc=text,
            where=f"{package}/{rel}:1", private=False,
        )


def build_index(package: str = "f3dasm", *, units: tuple[str, ...] = ("symbol",)
                ) -> dict[str, Entry]:
    """Introspect an INSTALLED package. Returns ``{key: Entry}``.

    Raises ``ImportError`` when the package is absent — the caller decides
    whether that is fatal (for f3dasm it is not: the tool simply is not
    offered).

    ``package`` exists because the three problems this function solves are not
    f3dasm's. Any package that keeps its implementation under a private
    subpackage and re-exports a curated surface has the same ones: a
    ``__module__`` that names the private definition site rather than the
    import a caller must write, a public surface much smaller than the set of
    defined symbols, and no way to tell from source alone whether something
    has been replaced at run time. adda is built exactly that way, so the same
    walk indexes it with no special-casing.
    """
    pkg_mod = importlib.import_module(package)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        root = pkg_mod.__file__
        assert root
        pkg_dir = root.rsplit("/", 1)[0]
        names = [package] + [
            m.name for m in pkgutil.walk_packages([pkg_dir], f"{package}.")
        ]
        mods = {}
        for n in names:
            try:
                mods[n] = importlib.import_module(n)
            except Exception:  # noqa: BLE001 — an optional extra may be absent
                continue

        # Pass 1 — the canonical public path for every object reachable from a
        # public namespace. Shortest wins, so `f3dasm.ExperimentData` beats
        # `f3dasm.design.ExperimentData`.
        public: dict[int, str] = {}
        for name, mod in mods.items():
            if "._src" in name:
                continue
            for attr, v in vars(mod).items():
                if attr.startswith("_"):
                    continue
                if not (inspect.isclass(v) or inspect.isfunction(v)):
                    continue
                if not getattr(v, "__module__", "").startswith(package):
                    continue
                path = f"{name}.{attr}"
                cur = public.get(id(v))
                if cur is None or path.count(".") < cur.count("."):
                    public[id(v)] = path

        # Pass 2 — one entry per symbol DEFINED in f3dasm, keyed by its public
        # path where it has one.
        index: dict[str, Entry] = {}
        for name, mod in mods.items():
            for attr, v in vars(mod).items():
                if attr.startswith("_"):
                    continue
                if not (inspect.isclass(v) or inspect.isfunction(v)):
                    continue
                if getattr(v, "__module__", "") != name:
                    continue        # re-export; the definer owns the entry
                pub = public.get(id(v))
                key = pub or f"{name}.{attr}"
                if key in index:
                    continue
                doc = inspect.getdoc(v) or ""
                where, patched = _where(v, package)
                index[key] = Entry(
                    key=key,
                    kind="class" if inspect.isclass(v) else "function",
                    import_line=_import_line(pub) if pub else None,
                    signature=_signature(v),
                    summary=_summary(doc),
                    doc=doc,
                    where=where,
                    private=pub is None,
                    patched_by=patched,
                )
                if inspect.isclass(v):
                    _add_methods(index, v, key, pub is None, package)

        if "module" in units:
            _module_entries(mods, package, index)
        if "constant" in units:
            _constant_entries(mods, package, index)
        if "markdown" in units:
            _markdown_entries(package, index)
    return index


def _akin(tok: str, name: str) -> bool:
    """Whether a query token matches a word in a symbol's name.

    Bidirectional on purpose, and this is not cosmetic: plain ``tok in name``
    misses "parameters" against ``add_parameter`` and "sampling" against
    ``sampler``, which is exactly how "define input parameters" returned
    ``move_to_input`` and three private sampler helpers while ``Domain`` — the
    class for defining input parameters — scored nothing on its name.

    Guarded at 4 characters: below that, containment is coincidence ("id" in
    "grid").
    """
    if tok == name:
        return True
    if len(tok) < 4 or len(name) < 4:
        return False
    return tok in name or name in tok


def _in_text(tok: str, text: str) -> bool:
    """Same tolerance, against prose. A docstring says "parameter" where the
    agent typed "parameters"."""
    if tok in text:
        return True
    return len(tok) > 4 and tok.rstrip("s") in text

def _import_line(pub: str) -> str:
    mod, _, leaf = pub.rpartition(".")
    return f"from {mod} import {leaf}"


#: Dunders worth indexing: construction plus the operators f3dasm gives
#: meaning to. Everything else (``__repr__``, ``__eq__``, ``__reduce__``, the
#: container protocol) is Python plumbing an agent never needs to look up.
_KEPT_DUNDERS = frozenset({
    "__init__", "__add__", "__radd__", "__iadd__", "__rshift__", "__or__",
    "__call__", "__getitem__", "__len__", "__iter__", "__contains__",
})


def _add_methods(
    index: dict[str, Entry], cls, cls_key: str, private: bool,
    package: str = "f3dasm",
) -> None:
    """Index a class's own public methods.

    Only methods defined ON this class: inherited ones belong to the base, and
    duplicating them would make every subclass re-list the same text. ``__init__``
    is kept — its signature is how the class is constructed, which is the single
    most-looked-up fact about any class.

    OPERATOR dunders are kept too. They are the one kind of API a lexical index
    is otherwise blind to: an agent cannot search for ``>>``, and nothing in a
    symbol list hints that ``a >> b`` builds a ``ChainedBlock`` or that
    ``data + other`` merges two ``ExperimentData``. Drop them and the operator
    is unreachable — findable only by reading the owning class's own docstring
    and hoping it says so. Every other dunder is protocol noise.
    """
    for mn, mv in vars(cls).items():
        if mn.startswith("_") and mn not in _KEPT_DUNDERS:
            continue
        fn = mv.__func__ if isinstance(mv, (classmethod, staticmethod)) else mv
        if not (inspect.isfunction(fn) or inspect.ismethod(fn)):
            continue
        doc = inspect.getdoc(fn) or ""
        where, patched = _where(fn, package)
        key = f"{cls_key}.{mn}"
        index[key] = Entry(
            key=key,
            kind="method",
            import_line=None,       # reached through its class, not imported
            signature=_signature(fn, drop_self=True),
            summary=_summary(doc),
            doc=doc,
            where=where,
            private=private,
            owner=cls_key,
            patched_by=patched,
        )


class PackageApi:
    """Query an installed package's API. One entry point, three behaviours.

    The shape follows how a person uses a reference: look something up, read
    the entry, and only then open the source. Each step costs more context than
    the last, so each is a separate request rather than one fat page.

    ``package`` selects what is indexed. The ranker below is package-agnostic
    on purpose: every prior it encodes -- a name beats a summary beats a body,
    an exact name is unbeatable, a private symbol is answerable but must not
    crowd a concept search -- is a fact about PYTHON PACKAGES, not about
    f3dasm.

    ``aliases`` is the one part that is NOT transferable, and it defaults to
    empty for every package but f3dasm. The f3dasm map is 84 hand-written
    English->f3dasm pairs, added after seeing which queries missed, which
    makes it an answer fitted to its own test. Inheriting it by default would
    carry that fit to a package it was never measured on and read as if the
    ranker had simply generalised.
    """

    def __init__(self, package: str = "f3dasm",
                 aliases: dict[str, tuple] | None = None,
                 units: tuple[str, ...] = ("symbol",)) -> None:
        self._package = package
        self._aliases = (
            _ALIASES if aliases is None and package == "f3dasm"
            else (aliases or {}))
        self._index = build_index(package, units=units)

    # -- retrieval ---------------------------------------------------------

    def _rank(self, query: str, limit: int) -> list[Entry]:
        """Name matches first, then summary, then the body of the docstring.

        Deliberately not BM25. The corpus is ~250 symbols and the query an
        agent types is usually a NAME (``ExperimentData.store``,
        ``create_sampler``), so an exact or prefix hit must never be outranked
        by a symbol that merely mentions the word in prose.

        The tiers matter. A term in the symbol's own NAME is near-proof of
        relevance; in its one-line SUMMARY it is strong; buried in a parameter
        description it is weak. Scoring those equally is what buried
        ``create_sampler`` under ``Domain`` for "how do I sample the design
        space" — Domain's prose says "design" and "space" repeatedly, while the
        function actually named for the job said "sample" once.

        Stopwords are dropped for the same reason: "how do I ..." carries no
        signal, and letting it dilute coverage rewards long docstrings.
        """
        q = query.strip().lower()
        # A traceback pastes the PRIVATE path —
        # ``f3dasm._src.experimentdata.ExperimentData`` — and the symbol wanted
        # is its last segment. Without this the query degrades into a bag of
        # words over {f3dasm, src, experimentdata}, which every method of that
        # class matches as well as the class itself: the query above returned
        # set_project_dir, sort and join, and never the class. Scored BELOW the
        # whole-query tiers so "ExperimentData.store" still resolves to that
        # method rather than to every symbol named store.
        tail = q.rsplit(".", 1)[-1] if "." in q else ""
        toks = [t for t in q.replace(".", " ").replace("_", " ").split()
                if t and t not in _STOP]
        # Everyday English -> f3dasm's own word, at a discount (see _ALIASES).
        # Scored alongside the literal tokens rather than replacing them, so a
        # query that already speaks f3dasm is ranked exactly as before.
        aliases = _expand(toks, self._aliases)
        scored: list[tuple[float, int, str]] = []
        for key, e in self._index.items():
            leaf = key.rsplit(".", 1)[-1].lower()
            k = key.lower()
            score = 0.0
            if k == q or leaf == q:
                score = 1000
            elif leaf.startswith(q) or k.endswith("." + q):
                score = 500
            elif q and q in k:
                score = 250
            elif tail and (leaf == tail or k.endswith("." + tail)):
                score = 200
            elif toks:
                # Name tokens are the symbol's IDENTITY: its own name and,
                # for a method, its owning class. NOT the module path.
                # ``k.split(".")`` used to drop ``design``, ``optimization``
                # and ``_src`` into this 60-weight tier, so EVERY
                # ``f3dasm.design.*`` symbol earned a free name-tier hit on the
                # word "design" — a word in most DoE queries. That is how
                # ``design.sobol`` (51.9) outranked
                # ``ExperimentData.get_n_best_output`` (36.5) for "get the best
                # design found so far": the right answer matched "best" in both
                # its name and its summary and still lost to a package folder.
                # Withholding the name tier from MODULE entries was tried
                # and REJECTED. The reasoning was sound -- a module's key is a
                # file path, so `runtime.run`, `run_setup` and `run_diagram`
                # each take a 60-weight hit on the bare word "run" -- and one
                # query visibly improved. On all 128 labelled queries it made
                # things worse: r@1 0.344 -> 0.320, MRR 0.436 -> 0.424, and
                # the comparison against ripgrep fell out of significance
                # (p 0.0385 -> 0.117). A filename is a weak signal, not a
                # worthless one.
                name_toks = set(leaf.replace("_", " ").split())
                if e.owner:
                    name_toks |= set(e.owner.rsplit(".", 1)[-1]
                                     .lower().replace("_", " ").split())
                summ = e.summary.lower()
                body = e.doc.lower()
                hit_name = sum(1 for t in toks
                               if any(_akin(t, n) for n in name_toks))
                hit_summ = sum(1 for t in toks if _in_text(t, summ))
                hit_body = sum(1 for t in toks if _in_text(t, body))
                a_name = sum(1 for t in aliases
                             if any(_akin(t, n) for n in name_toks))
                a_summ = sum(1 for t in aliases if _in_text(t, summ))
                a_body = sum(1 for t in aliases if _in_text(t, body))
                hit_name += _ALIAS_WEIGHT * a_name
                hit_summ += _ALIAS_WEIGHT * a_summ
                hit_body += _ALIAS_WEIGHT * a_body
                if hit_name or hit_summ or hit_body:
                    score = 60 * hit_name + 12 * hit_summ + 2 * hit_body
                    # Coverage is measured over name AND summary TOGETHER, on
                    # DISTINCT terms. A symbol answering half the query in its
                    # name and half in its summary is a better hit than one
                    # matching a single term twice — which is how
                    # `ExperimentSample.store` outranked the samplers for
                    # "sample the design space": it matched "sample" (a data
                    # record, not the verb) and nothing else.
                    # An alias covers the QUERY TOKEN it stands in for, never
                    # itself: "save my results" must not count as two terms
                    # covered because ``store`` was added on "save"'s behalf.
                    covered = {t for t in toks
                               if any(_akin(t, n) for n in name_toks)
                               or _in_text(t, summ)}
                    covered |= {origin for alias, origin in aliases.items()
                                if any(_akin(alias, n) for n in name_toks)
                                or _in_text(alias, summ)}
                    score *= 0.35 + 0.65 * (len(covered) / len(toks))
            if not score:
                continue
            if e.private:
                # An agent searching by concept wants the public API. Private
                # symbols stay reachable by exact name, but must not crowd a
                # concept search — f3dasm has 78 of them against 47 public.
                score *= 0.15
            if e.kind != "method":
                score *= 1.15      # a class/function is a better entry point
            # Centrality is a TIEBREAK, never a multiplier. Scaling scores by
            # it was measured and rejected: at any weight that fixed anything
            # it also put ``ExperimentSample`` above ``create_sampler`` for
            # "how do I sample the design space" and ``ExperimentData`` above
            # ``Domain.add_parameter`` for "define input parameters" — a
            # central class beating the function actually named for the job,
            # which is the precise failure this ranker's name tier exists to
            # prevent. As a tiebreak it cannot do that: it only orders
            # candidates that already scored IDENTICALLY, which is the
            # collision it was built for — four symbols named ``store``, on
            # Domain, ExperimentData, ExperimentSample and a private class.
            scored.append((score, -len(key), key))
        scored.sort(reverse=True)
        return [self._index[k] for _, _, k in scored[:limit]]

    # -- rendering ---------------------------------------------------------

    def _render_hit(self, e: Entry) -> str:
        mark = " [PRIVATE]" if e.private else ""
        head = f"{e.key}{mark} ({e.kind})"
        return f"{head}\n    {e.summary or '(undocumented)'}"

    def _render_entry(self, e: Entry) -> str:
        lines = [f"{e.key}  ({e.kind})"]
        if e.patched_by:
            # Ahead of everything else: the agent is about to act on this, and
            # what runs is not what f3dasm's own documentation describes.
            lines += [
                "",
                f"!! REPLACED AT RUNTIME BY {e.patched_by}. In a run, this is "
                f"NOT {self._package}'s",
                f"   implementation — {e.patched_by} substitutes its own at "
                "import time. The",
                "   signature and docstring below are the REPLACEMENT's, and "
                "they are what",
                "   actually executes. f3dasm's own documentation for this "
                "name describes",
                "   behaviour you will not get.",
            ]
        if e.private:
            lines += [
                "",
                "PRIVATE — internal to f3dasm, NOT part of its public API. Do",
                "not import this path; it can change without notice. Shown",
                "because reading a traceback or the source may require it.",
            ]
        elif e.import_line:
            lines += ["", e.import_line]
        elif e.owner:
            lines += ["", f"reached through {e.owner}"]
        leaf = e.key.rsplit(".", 1)[-1]
        lines += ["", f"{leaf}{e.signature}", ""]
        lines.append(e.doc or "(no docstring)")
        lines += ["", f"defined at {e.where}"]
        if e.kind == "class":
            meth = sorted(
                k.rsplit(".", 1)[-1] for k in self._index
                if self._index[k].owner == e.key
            )
            if meth:
                lines += ["", "methods: " + ", ".join(meth)]
        return "\n".join(lines)

    # -- the tool ----------------------------------------------------------

    def consult(self, query: str, limit: int = 8, source: bool = False) -> str:
        q = (query or "").strip()
        if not q:
            return "ERROR: pass a symbol name or a phrase to look up."

        exact = self._index.get(q) or self._resolve(q)
        if exact is not None:
            if source:
                return self._source(exact)
            return _clip(self._render_entry(exact))
        if source:
            return (
                f"ERROR: source requested for {q!r}, which is not a known "
                "f3dasm symbol. Search for it first (without source=True) to "
                "find its exact name."
            )

        hits = self._rank(q, limit)
        if not hits:
            return (
                f"No {self._package} symbol matches {q!r}.\n\n"
                f"This searches the INSTALLED {self._package} only — not your "
                f"study code, not Abaqus, not other libraries. A miss here "
                f"means it is not in {self._package}, not that it does not "
                f"exist.\n\nTry the bare name of something you know is "
                f"there ({self._examples()}), or a word for what it DOES."
            )
        body = "\n".join(self._render_hit(h) for h in hits)
        return _clip(
            f"{len(hits)} match(es) for {q!r} in {self._package} "
            f"{self.version()}:\n\n{body}\n\n"
            "Pass one of these names back to read its full entry."
        )

    def _resolve(self, q: str) -> Entry | None:
        """Accept the name an agent would plausibly type.

        A traceback says ``f3dasm._src.experimentdata.ExperimentData``; a
        person says ``ExperimentData``. Both must land on the same entry, or
        the tool fails exactly when the agent is debugging.
        """
        if q in self._index:
            return self._index[q]
        leaf_matches = [
            e for k, e in self._index.items() if k.rsplit(".", 1)[-1] == q
        ]
        if len(leaf_matches) == 1:
            return leaf_matches[0]
        # a private/definition path for something re-exported publicly
        tail = q.split(".")[-2:]
        if len(tail) == 2:
            suffix = ".".join(tail)
            cand = [e for k, e in self._index.items() if k.endswith(suffix)]
            if len(cand) == 1:
                return cand[0]
        return None

    def _source(self, e: Entry) -> str:
        obj = self._object(e.key)
        if obj is None:
            return f"ERROR: could not locate {e.key} to read its source."
        try:
            src = inspect.getsource(obj)
        except (OSError, TypeError) as exc:
            return f"ERROR: source unavailable for {e.key}: {exc}"
        return _clip(f"{e.key}  —  {e.where}\n\n{src}")

    def _object(self, key: str):
        parts = key.split(".")
        for cut in range(len(parts) - 1, 0, -1):
            try:
                obj = importlib.import_module(".".join(parts[:cut]))
            except ImportError:
                continue
            for p in parts[cut:]:
                obj = getattr(obj, p, None)
                if obj is None:
                    break
            if obj is not None:
                return obj
        return None

    def _examples(self) -> str:
        """Two real public names, for a miss message that can help.

        Derived from the live index rather than hardcoded. The hardcoded pair
        this replaced named f3dasm symbols, which is useless advice when the
        index holds a different package -- and would go stale in either.
        """
        names = sorted(
            k.rsplit(".", 1)[-1] for k, e in self._index.items()
            if not e.private and e.kind == "class" and "." in k
        )
        return ", ".join(names[:2]) if names else "a public name"

    # -- orientation -------------------------------------------------------

    def version(self) -> str:
        try:
            from importlib.metadata import version
            return version(self._package)
        except Exception:  # noqa: BLE001
            return "(version unknown)"

    def overview(self) -> str:
        """The public surface, one line each — the map, not the territory."""
        pub = sorted(
            (k, e) for k, e in self._index.items()
            if not e.private and e.kind in ("class", "function")
        )
        lines = [
            f"{self._package} {self.version()} — {len(pub)} public symbols "
            f"({len(self._index)} indexed including methods and internals).",
            "",
        ]
        for k, e in pub:
            lines.append(f"{k}  —  {e.summary or '(undocumented)'}")
        return _clip("\n".join(lines))


def _clip(text: str) -> str:
    if len(text) <= _MAX_CHARS:
        return text
    return (
        text[:_MAX_CHARS]
        + f"\n\n[... truncated at {_MAX_CHARS} chars. Ask for a specific "
          "symbol to see its entry in full.]"
    )


# --- the agent-facing tool --------------------------------------------------

#: Built once per process. Introspection walks 43 modules; an agent that
#: consults twice in a turn should pay for that once.
class F3dasmApi(PackageApi):
    """``PackageApi`` bound to f3dasm, with f3dasm's alias map."""

    def __init__(self) -> None:
        super().__init__("f3dasm", _ALIASES)


#: What indexing adda needs that indexing f3dasm does not, measured on 128
#: labelled queries. f3dasm's knowledge is in its symbols, so modules and
#: constants are pure crowding there (r@1 0.77 -> 0.62). adda's is in its
#: module docstrings, its declared constants and its knowledge-base markdown,
#: and indexing all four is the difference between losing to ripgrep and
#: beating it (r@1 0.24 -> 0.41 on the set that motivated the change).
ADDA_UNITS = ("symbol", "module", "constant", "markdown")


class AddaApi(PackageApi):
    """``PackageApi`` bound to adda itself, for an agent reading THIS package.

    No alias map. f3dasm's is 84 hand-written English->f3dasm pairs added
    after seeing which queries missed, and on 70 independently written queries
    it bought nothing at all (synonym r@1 0.47 on the set it came from, 0.06
    on the blind set). Carrying that shape to adda would inherit the fitting
    without the benefit.
    """

    def __init__(self) -> None:
        super().__init__("adda", {}, units=ADDA_UNITS)


_API: F3dasmApi | None = None
_API_FAILED = False


def _api() -> F3dasmApi | None:
    global _API, _API_FAILED
    if _API is None and not _API_FAILED:
        try:
            _API = F3dasmApi()
        except Exception:  # noqa: BLE001
            # A broken or absent f3dasm must never break the agent; it simply
            # runs without the tool, exactly as it did before this existed.
            _API_FAILED = True
    return _API


def build_f3dasm_api_closures() -> dict:
    """``{name: callable}`` for the f3dasm API lookup, or ``{}`` when
    unavailable.

    Returned only when the ``f3dasm_api`` feature is on AND f3dasm imports —
    a tool that is present but broken is worse than one that is absent, since
    the agent spends calls discovering it does not work.
    """
    from ..runtime import features

    if not features.enabled("f3dasm_api"):
        return {}
    api = _api()
    if api is None:
        return {}

    # A named function, not a lambda: the runtime renders this docstring into
    # the generated <tools> catalog, which is the agent's only documentation
    # for it.
    def ConsultF3dasm(query: str, limit: int = 8, source: bool = False):
        """Look up the INSTALLED f3dasm's API — signature, docstring, source.

        Introspected from the package this run executes against, so it cannot
        be out of date. Use it before guessing any f3dasm name or argument.

        Two steps, like a reference. A DESCRIPTION returns a menu: one line per
        matching symbol, up to `limit`. A NAME from that menu returns its entry:
        the import line to write, the full signature, and the docstring.
          ConsultF3dasm("sample the design space")   # menu
          ConsultF3dasm("f3dasm.create_sampler")     # entry
          ConsultF3dasm("f3dasm.create_sampler", source=True)
        Add source=True only when the docstring does not settle the question.

        Search is LEXICAL — your words against symbol names (weighted heavily)
        and docstrings; singular/plural and sampler/sampling are folded. Give
        the real name when you know it, otherwise f3dasm's own vocabulary
        ("sample", "store", "optimize", "domain"). A traceback's private path
        resolves to its public symbol.

        Three things no other source gives you:
          - The PUBLIC import path. f3dasm defines its classes under
            f3dasm._src.*, which is NOT what you import; the entry gives the
            line to write.
          - PRIVATE marks an internal symbol: read it to understand a
            traceback, never import it.
          - Where adda REPLACES an f3dasm method at runtime, the entry says so
            and describes what actually executes.

        Covers the installed f3dasm only — not your study code and not other
        libraries, so a miss means "not an f3dasm symbol", not "does not exist".
        """
        return api.consult(query, limit=int(limit), source=bool(source))

    return {"ConsultF3dasm": ConsultF3dasm}
