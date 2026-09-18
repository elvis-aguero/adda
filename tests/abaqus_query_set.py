"""A labelled query set for the offline Abaqus documentation lookup.

WHY THIS FILE EXISTS, AND WHY IT CANNOT BE SCORED YET
    ``src/adda/_src/knowledge/abaqus`` ships a reader and a corpus BUILDER,
    never the corpus: Abaqus reference documentation is Dassault Systemes'
    licensed content, so nothing built from it can be redistributed with
    adda (see that package's own docstring). This file is written the same
    way ``tests/adda_source_queries.py`` was written before its index
    existed: against the QUESTION an engineer or an agent writing an input
    deck would actually ask, not against what any particular retriever
    currently returns.

    The consequence is unavoidable and is not a defect in this file: THESE
    QUERIES CANNOT BE SCORED until someone with an Abaqus licence points
    ``ADDA_ABAQUS_DOC_CORPUS`` at a documentation install built with
    ``AbaqusDocs.build()``, and runs retrieval against it. Nothing here
    asserts a recall number. What it fixes, ahead of time and independent of
    any run, is what the RIGHT ANSWER is.

WHAT A GOLD ANSWER IS
    An Abaqus KEYWORD (``*FREQUENCY``, ``*CONTACT PAIR``) or, where no single
    keyword page answers the question, a short list of keywords any one of
    which counts as a hit. These are spelled exactly as Abaqus's own Keywords
    Reference spells them, capitalisation and all, because that is what
    makes the label portable across any real Abaqus documentation install --
    unlike a ``page_id`` or a file path, which exist only inside one built
    corpus and are exactly what CANNOT ship here.

    THE RULE THIS FOLLOWS: a gold label may be REPOINTED if a future Abaqus
    release renames or retires a keyword (``*STEADY STATE DYNAMICS`` becoming
    something else, say). It may NEVER be edited, added to, or narrowed
    because some retriever's current output missed it, ranked it low, or
    found something else instead. Doing that scores the retriever against
    itself. A query whose gold keyword turns out not to exist should be
    DELETED, not repointed to whatever the tool happened to return.

THE FOUR TIERS
    ``keyword``    the asker already names the Abaqus keyword directly
        (``*STATIC``, ``CONTACT PAIR``). This is the control: an exact
        ``title_norm`` lookup should win it outright. A miss here is the
        retrieval equivalent of a typo in the index itself.
    ``task``       a modelling task in plain engineering English, naming no
        keyword ("how do I apply a pressure load to a surface"). This is the
        tier the whole tool is FOR -- nobody who already knew to search
        "*DSLOAD" needed the tool -- and it is the highest-value tier here.
    ``parameter``  a question about one option of an already-named-or-implied
        keyword ("what does NLGEOM do", "how many eigenvalues to extract").
        These probe whether a hit lands on the right keyword's page and not
        merely a page that mentions the parameter in passing.
    ``error``      an error or warning message the user is staring at
        (excessive distortion, a negative eigenvalue, a zero pivot). Gold is
        the keyword whose page documents the control that causes or fixes it.

    Grounding for the ``task`` and ``error`` tiers came in part from reading
    a summary of github.com/LIRAM-LIN/AbaqusAgent (fetched via WebFetch,
    which returned a prose description rather than the raw repository -- see
    the accompanying report for exactly what came back and what did not).
    Its multi-agent pipeline -- interpreting a natural-language mechanics
    problem, writing an .inp file, running it, and diagnosing the error when
    it fails -- is what the task/error split here is modelling: an agent
    doing that work asks modelling questions with no keyword in them, and
    hits error tier only once a run has actually failed. No wording was
    copied from it; nothing here is a claim about what its code contains.

THE HELD-OUT SPLIT
    ``DEVELOPMENT`` (40) may be looked at while building or tuning a
    retriever. ``HELD_OUT`` (20 -- exactly one third of the 60 documentation
    queries) may not be read, reasoned about, or scored until the design is
    frozen. The ids are listed literally rather than computed from a hash or
    a modulus, because a computed split silently reshuffles the moment a
    query is added or removed and the held-out set quietly stops being held
    out. It is stratified per tier for the same reason
    ``adda_source_queries.py`` gives: an un-stratified third-off-the-top
    would leave ``error`` almost entirely in development or almost entirely
    held out, either of which makes that tier's held-out score meaningless.

THE FUZZY LIST IS A SEPARATE MEASUREMENT
    ``FUZZY`` is not a query tier: it is (what the user typed, the keyword
    they meant) pairs aimed squarely at ``AbaqusDocs._did_you_mean``, which
    today has exactly one test (``test_a_wrong_keyword_is_corrected...`` in
    ``tests/test_abaqus_docs.py``, covering only ``*FREQ`` -> ``*FREQUENCY``).
    It is a SPECIFICATION of intended behaviour, written the same way the
    query tiers above are: against what a person plausibly mis-types, not
    against ``difflib.get_close_matches``'s current cutoff of 0.6. Do not
    tune entries in or out of this list to make a particular threshold look
    good; if the fallback's cutoff needs to change, change the cutoff and
    re-run this list against it, not the other way around.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# keyword -- the asker already names it. The control tier: an exact
# title_norm hit should win this outright.
# ---------------------------------------------------------------------------
KEYWORD = [
    ("kw01", "*STATIC", ["*STATIC"]),
    ("kw02", "*BOUNDARY", ["*BOUNDARY"]),
    ("kw03", "*CONTACT PAIR", ["*CONTACT PAIR"]),
    ("kw04", "*FREQUENCY", ["*FREQUENCY"]),
    ("kw05", "*BUCKLE", ["*BUCKLE"]),
    ("kw06", "*SHELL SECTION", ["*SHELL SECTION"]),
    ("kw07", "*SOLID SECTION", ["*SOLID SECTION"]),
    ("kw08", "*ELASTIC", ["*ELASTIC"]),
    ("kw09", "*PLASTIC", ["*PLASTIC"]),
    ("kw10", "*CLOAD", ["*CLOAD"]),
    ("kw11", "*DLOAD", ["*DLOAD"]),
    ("kw12", "*AMPLITUDE", ["*AMPLITUDE"]),
    ("kw13", "*TIE", ["*TIE"]),
    ("kw14", "*EQUATION", ["*EQUATION"]),
    ("kw15", "*RESTART", ["*RESTART"]),
]

# ---------------------------------------------------------------------------
# task -- a modelling task in plain engineering English, no keyword named.
# This is the tier the tool exists for.
# ---------------------------------------------------------------------------
TASK = [
    ("ta01", "how do I apply a pressure load to a surface of my model",
     ["*DSLOAD"]),
    ("ta02", "how do I run a linear buckling analysis to find the buckling load",
     ["*BUCKLE"]),
    ("ta03", "how do I get the natural frequencies and mode shapes of my structure",
     ["*FREQUENCY"]),
    ("ta04", "how do I model two parts touching each other with friction between them",
     ["*CONTACT PAIR", "*FRICTION"]),
    ("ta05", "how do I fix a set of nodes so they cannot move or rotate at all",
     ["*BOUNDARY"]),
    ("ta06", "how do I glue two non-matching meshes together so they move as one",
     ["*TIE"]),
    ("ta07", "how do I apply a concentrated point force at a node",
     ["*CLOAD"]),
    ("ta08", "how do I define a load that varies with time over the step",
     ["*AMPLITUDE"]),
    ("ta09", "how do I turn on large-displacement geometric nonlinearity for a step",
     ["*STEP"]),
    ("ta10", "how do I define a simple linear elastic isotropic material",
     ["*ELASTIC"]),
    ("ta11", "how do I define plastic yield behaviour for a metal",
     ["*PLASTIC"]),
    ("ta12", "how do I set up a heat transfer analysis",
     ["*HEAT TRANSFER"]),
    ("ta13", "how do I couple temperature and displacement in the same analysis",
     ["*COUPLED TEMPERATURE-DISPLACEMENT"]),
    ("ta14", "how do I run a nonlinear implicit static analysis",
     ["*STATIC"]),
    ("ta15", "how do I run an explicit dynamic drop-test simulation",
     ["*DYNAMIC"]),
    ("ta16", "how do I assign a thickness and cross-section to a shell part",
     ["*SHELL SECTION"]),
    ("ta17", "how do I define a solid continuum section for a part",
     ["*SOLID SECTION"]),
    ("ta18", "how do I model a beam with a circular cross-section",
     ["*BEAM SECTION"]),
    ("ta19", "how do I make a rigid link between two nodes so they move together",
     ["*MPC"]),
    ("ta20", "how do I couple a patch of nodes to a single reference node like a rigid coupling",
     ["*COUPLING", "*KINEMATIC"]),
    ("ta21", "how do I set an initial temperature field before the analysis starts",
     ["*INITIAL CONDITIONS"]),
    ("ta22", "how do I ask Abaqus to write stress and displacement to the output database",
     ["*OUTPUT"]),
    ("ta23", "how do I restart an analysis from where a previous run left off",
     ["*RESTART"]),
    ("ta24", "how do I model contact between a rigid tool and a deformable part",
     ["*RIGID BODY", "*CONTACT PAIR"]),
    ("ta25", "how do I write my own material behaviour in Fortran instead of using a built-in model",
     ["*USER MATERIAL"]),
]

# ---------------------------------------------------------------------------
# parameter -- a question about one option of a keyword.
# ---------------------------------------------------------------------------
PARAMETER = [
    ("pa01", "what does the NLGEOM parameter on the *STEP keyword actually do",
     ["*STEP"]),
    ("pa02", "how do I set the number of eigenvalues to extract in a *FREQUENCY step",
     ["*FREQUENCY"]),
    ("pa03", "what eigensolver choices does *FREQUENCY offer, Lanczos vs subspace",
     ["*FREQUENCY"]),
    ("pa04", "what does the UNSYMM parameter on *STEP control",
     ["*STEP"]),
    ("pa05", "how do I turn on automatic stabilization for a *STATIC step",
     ["*STATIC"]),
    ("pa06", "what does the AMPLITUDE parameter on a boundary condition or load do",
     ["*BOUNDARY"]),
    ("pa07", "how do I set the friction coefficient in a *FRICTION definition",
     ["*FRICTION"]),
    ("pa08", "what does the SMOOTH STEP option on an *AMPLITUDE definition do",
     ["*AMPLITUDE"]),
    ("pa09", "what does the ADJUST parameter on *TIE do",
     ["*TIE"]),
    ("pa10", "how do I raise the maximum number of increments allowed in a *STATIC step",
     ["*STATIC"]),
    ("pa11", "what is the difference between OP=NEW and OP=MOD on a keyword like *BOUNDARY",
     ["*BOUNDARY"]),
    ("pa12", "what does the HOURGLASS parameter on *SECTION CONTROLS do",
     ["*SECTION CONTROLS"]),
]

# ---------------------------------------------------------------------------
# error -- an error/warning message the user is staring at.
# ---------------------------------------------------------------------------
ERROR = [
    ("er01", "Abaqus/Explicit aborted the job because too many elements have excessive distortion",
     ["*SECTION CONTROLS"]),
    ("er02", "I'm getting a warning that hourglass energy is a large fraction of the internal energy in my explicit model",
     ["*SECTION CONTROLS"]),
    ("er03", "the Lanczos eigensolver in my buckling step is reporting negative eigenvalues",
     ["*BUCKLE"]),
    ("er04", "my static step keeps cutting back the increment and finally aborts saying the time increment required is less than the minimum specified",
     ["*STATIC"]),
    ("er05", "Abaqus warns about severe overclosure at the start of the step in my contact pairs",
     ["*CONTACT CONTROLS"]),
    ("er06", "the message says the system matrix has a zero or negative pivot",
     ["*CONTROLS"]),
    ("er07", "Abaqus complains that no surface interaction property has been assigned to my contact pair",
     ["*SURFACE INTERACTION"]),
    ("er08", "adaptive meshing keeps failing to remap the solution because element quality got too poor",
     ["*ADAPTIVE MESH"]),
]

# ---------------------------------------------------------------------------
# FUZZY -- (what the user typed, the keyword they meant). A specification for
# the "did you mean" fallback, not a tier scored the same way as the four
# above. Truncations, typos, transpositions, plural/spacing variants, spread
# across many different keywords rather than piled onto a few easy ones.
# ---------------------------------------------------------------------------
FUZZY: list[tuple[str, str]] = [
    ("*STATC", "*STATIC"),
    ("*SATIC", "*STATIC"),
    ("freq", "*FREQUENCY"),
    ("*FREQ", "*FREQUENCY"),
    ("*BOUNDRY", "*BOUNDARY"),
    ("*BOUNDARIES", "*BOUNDARY"),
    ("*CONTACTPAIR", "*CONTACT PAIR"),
    ("*CONTACT PAIRS", "*CONTACT PAIR"),
    ("*BUCKEL", "*BUCKLE"),
    ("buckling", "*BUCKLE"),
    ("*IMPERFETION", "*IMPERFECTION"),
    ("imperfec", "*IMPERFECTION"),
    ("*SHELLSECTION", "*SHELL SECTION"),
    ("*SHEL SECTION", "*SHELL SECTION"),
    ("*SOLIDSECTION", "*SOLID SECTION"),
    ("*SOLID SECION", "*SOLID SECTION"),
    ("*ELASTC", "*ELASTIC"),
    ("*ELESTIC", "*ELASTIC"),
    ("*PLASTC", "*PLASTIC"),
    ("*PALSTIC", "*PLASTIC"),
    ("*CLAOD", "*CLOAD"),
    ("*DLAOD", "*DLOAD"),
    ("*DSLAOD", "*DSLOAD"),
    ("*AMPLITDUE", "*AMPLITUDE"),
    ("*AMPLTUDE", "*AMPLITUDE"),
    ("*TEI", "*TIE"),
    ("*TYE", "*TIE"),
    ("*EQUATON", "*EQUATION"),
    ("*EQATION", "*EQUATION"),
    ("*RESTRT", "*RESTART"),
    ("*COUPLNG", "*COUPLING"),
    ("*FRICTON", "*FRICTION"),
    ("*FRICITON", "*FRICTION"),
    ("*DAMPNG", "*DAMPING"),
    ("*HYPERELASTC", "*HYPERELASTIC"),
    ("*HYPER ELASTIC", "*HYPERELASTIC"),
    ("*CREPE", "*CREEP"),
    ("*ORIENTATON", "*ORIENTATION"),
    ("*SECTIONCONTROLS", "*SECTION CONTROLS"),
    ("*SECTION CONTORLS", "*SECTION CONTROLS"),
    ("*INITALCONDITIONS", "*INITIAL CONDITIONS"),
    ("*SURFACEINTERACTION", "*SURFACE INTERACTION"),
    ("*RIGIDBODY", "*RIGID BODY"),
    ("*RIDGID BODY", "*RIGID BODY"),
    ("*KINEMATC", "*KINEMATIC"),
    ("*DISTRIBUTNG", "*DISTRIBUTING"),
    ("*STEDY STATE DYNAMICS", "*STEADY STATE DYNAMICS"),
    ("*MODALDYNAMIC", "*MODAL DYNAMIC"),
    ("*RANDOMRESPONSE", "*RANDOM RESPONSE"),
    ("*RESPONSESPECTRUM", "*RESPONSE SPECTRUM"),
]

# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------
TIERS = {"keyword": KEYWORD, "task": TASK, "parameter": PARAMETER, "error": ERROR}

ALL = [(tier, qid, q, gold)
       for tier, rows in TIERS.items() for qid, q, gold in rows]

#: Frozen split, one third of the 60 documentation queries (20), stratified
#: per tier. Listed literally, not computed, so adding or removing a query
#: cannot silently reshuffle who is held out.
HELD_OUT_IDS = frozenset({
    "kw03", "kw06", "kw09", "kw12", "kw15",                     # 5 of 15 keyword
    "ta03", "ta06", "ta09", "ta12", "ta15", "ta18", "ta21", "ta24",  # 8 of 25 task
    "pa03", "pa06", "pa09", "pa12",                             # 4 of 12 parameter
    "er03", "er06", "er08",                                     # 3 of 8 error
})

DEVELOPMENT = [r for r in ALL if r[1] not in HELD_OUT_IDS]
HELD_OUT = [r for r in ALL if r[1] in HELD_OUT_IDS]
