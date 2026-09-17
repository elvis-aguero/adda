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
import pkgutil
import warnings
from dataclasses import dataclass, field

__all__ = ["Entry", "F3dasmApi", "build_index"]

#: Cap on a single consult() reply. The point of the tool is to keep the
#: package OUT of the context window; an unbounded page defeats it.
_MAX_CHARS = 6000

#: Dropped from concept queries. An agent writes "how do I sample the design
#: space"; only three of those words carry signal, and counting the rest
#: rewards whichever docstring happens to be longest.
_STOP = frozenset("""
a an and are as at be by can do does for from get how i if in into is it its
me my of on or that the their then there these this to use used using want
was what when where which who why will with you your
""".split())


@dataclass(frozen=True)
class Entry:
    """One f3dasm symbol, as an agent needs to see it."""

    #: dotted name used as the lookup key — the public path when there is one
    key: str
    kind: str                      # class | function | method
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


def _where(obj) -> tuple[str, str | None]:
    """``(file:line, patched_by)`` for a live object.

    ``patched_by`` is set when the source file lies OUTSIDE the f3dasm package
    — i.e. something has replaced f3dasm's own function. adda does exactly that
    to two ExperimentData methods, so the distinction is not hypothetical, and
    an index that silently reported adda's patch as f3dasm's API would be
    actively misleading.
    """
    try:
        f = inspect.getsourcefile(obj) or "?"
        _, line = inspect.getsourcelines(obj)
    except (OSError, TypeError):
        return "?", None
    pkg = _f3dasm_root()
    if pkg and f.startswith(pkg):
        # package-relative: the absolute site-packages prefix is noise and
        # differs between machines
        return f"f3dasm{f[len(pkg):]}:{line}", None
    owner = "adda" if "/adda/" in f else _pkg_of(f)
    short = f.rsplit("/site-packages/", 1)[-1]
    if "/src/" in short:
        short = short.split("/src/", 1)[-1]
    return f"{short}:{line}", owner


def _f3dasm_root() -> str | None:
    try:
        import f3dasm
        return (f3dasm.__file__ or "").rsplit("/", 1)[0] or None
    except Exception:  # noqa: BLE001
        return None


def _pkg_of(path: str) -> str:
    tail = path.rsplit("/site-packages/", 1)[-1]
    return tail.split("/", 1)[0].removesuffix(".py")


def build_index() -> dict[str, Entry]:
    """Introspect the installed f3dasm. Returns ``{key: Entry}``.

    Raises ``ImportError`` when f3dasm is absent — the caller decides whether
    that is fatal (it is not: the tool simply is not offered).
    """
    import f3dasm

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        root = f3dasm.__file__
        assert root
        pkg_dir = root.rsplit("/", 1)[0]
        names = ["f3dasm"] + [
            m.name for m in pkgutil.walk_packages([pkg_dir], "f3dasm.")
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
                if not getattr(v, "__module__", "").startswith("f3dasm"):
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
                where, patched = _where(v)
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
                    _add_methods(index, v, key, pub is None)
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
    index: dict[str, Entry], cls, cls_key: str, private: bool
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
        where, patched = _where(fn)
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


class F3dasmApi:
    """Query the installed f3dasm's API. One entry point, three behaviours.

    The shape follows how a person uses a reference: look something up, read
    the entry, and only then open the source. Each step costs more context than
    the last, so each is a separate request rather than one fat page.
    """

    def __init__(self) -> None:
        self._index = build_index()

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
        toks = [t for t in q.replace(".", " ").replace("_", " ").split()
                if t and t not in _STOP]
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
            elif toks:
                name_toks = set(
                    leaf.replace("_", " ").split()) | set(k.split("."))
                summ = e.summary.lower()
                body = e.doc.lower()
                hit_name = sum(1 for t in toks
                               if any(_akin(t, n) for n in name_toks))
                hit_summ = sum(1 for t in toks if _in_text(t, summ))
                hit_body = sum(1 for t in toks if _in_text(t, body))
                if hit_name or hit_summ or hit_body:
                    score = 60 * hit_name + 12 * hit_summ + 2 * hit_body
                    # Coverage is measured over name AND summary TOGETHER, on
                    # DISTINCT terms. A symbol answering half the query in its
                    # name and half in its summary is a better hit than one
                    # matching a single term twice — which is how
                    # `ExperimentSample.store` outranked the samplers for
                    # "sample the design space": it matched "sample" (a data
                    # record, not the verb) and nothing else.
                    covered = {t for t in toks
                               if any(_akin(t, n) for n in name_toks)
                               or _in_text(t, summ)}
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
                f"NOT f3dasm's",
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
                f"No f3dasm symbol matches {q!r}.\n\n"
                "This searches the INSTALLED f3dasm only — it does not know "
                "about your study code, Abaqus, or other libraries. If you "
                "expected an f3dasm symbol here, try the bare name "
                "(ExperimentData, create_sampler) or a word from what it does "
                "('sample', 'optimize', 'store')."
            )
        body = "\n".join(self._render_hit(h) for h in hits)
        return _clip(
            f"{len(hits)} match(es) for {q!r} in f3dasm "
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
        import f3dasm  # noqa: F401  (ensures the package is importable)

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

    # -- orientation -------------------------------------------------------

    def version(self) -> str:
        try:
            from importlib.metadata import version
            return version("f3dasm")
        except Exception:  # noqa: BLE001
            return "(version unknown)"

    def overview(self) -> str:
        """The public surface, one line each — the map, not the territory."""
        pub = sorted(
            (k, e) for k, e in self._index.items()
            if not e.private and e.kind in ("class", "function")
        )
        lines = [
            f"f3dasm {self.version()} — {len(pub)} public symbols "
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
    def ConsultF3dasmDocs(query: str, limit: int = 8, source: bool = False):
        """Look up the INSTALLED f3dasm's API — signature, docstring, source.

        Introspected from the package this run executes against, so it cannot
        be out of date. Use it before guessing any f3dasm name or argument.

        Two steps, like a reference. A DESCRIPTION returns a menu: one line per
        matching symbol, up to `limit`. A NAME from that menu returns its entry:
        the import line to write, the full signature, and the docstring.
          ConsultF3dasmDocs("sample the design space")   # menu
          ConsultF3dasmDocs("f3dasm.create_sampler")     # entry
          ConsultF3dasmDocs("f3dasm.create_sampler", source=True)
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

    return {"ConsultF3dasmDocs": ConsultF3dasmDocs}
