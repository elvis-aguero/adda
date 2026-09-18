"""Labelled queries for an agent-facing index of the Basilisk source tree.

WHY THIS FILE EXISTS, AND WHY IT EXISTS FIRST
    Written after the tool, a query set measures whatever the tool already
    does. Written before it, it is the thing the tool has to satisfy. This file
    is written against the QUESTION, not against any implementation. Nothing
    here may be edited to accommodate a retriever: fixing a label because a
    tool missed it is the failure mode this file exists to prevent.

    Every gold path below was verified against the corpus before being written.
    Three drafted labels did not survive that check and were removed rather
    than kept and hoped for: `foreach_dimension` has no definition site in the
    headers (it is a qcc compiler construct), and neither "maximum timestep
    reached" nor "not enough memory for the tree grid" is a string Basilisk
    emits. An invented gold answer is worse than a missing query, because it
    scores a tool against a fact that is not true.

THE BASELINE IS RIPGREP, NOT NOTHING
    An agent with a shell already reads a 59k-line source tree. The honest
    control is `rg -il <the query's own words>` over the same files, scored the
    same way. A tier where the index does not beat that control is a tier where
    the index should not ship.

THE HELD-OUT SPLIT
    DEVELOPMENT may be looked at while building. HELD_OUT may not be read,
    reasoned about, or scored until the design is frozen. Stratified by tier so
    the held-out set is not accidentally the easy third.

WHAT A GOLD ANSWER IS
    The file(s) a correct answer must name, relative to Basilisk's `src/`.
    Where more than one is listed, ANY of them at rank 1 counts as a hit.
"""
from __future__ import annotations

TIERS = {
    "n": "NAME",     # control: rg is excellent at exact names and should win
    "c": "CONCEPT",  # English from outside Basilisk's vocabulary; the target
    "e": "ERROR",    # a string the agent did not choose
    "r": "RULE",     # "am I allowed to?" -- no grep can serve this
    "k": "KNOB",     # "how do I turn this off / change it"
}

#: CONTROL. The agent already holds the identifier and wants the file. ripgrep
#: is excellent here and is expected to win; an index that merely ties has cost
#: nothing, but one that loses badly is broken.
NAME = [
    ("n01", "two-phase.h", ["two-phase.h"]),
    ("n02", "saint-venant.h", ["saint-venant.h"]),
    ("n03", "adapt_wavelet", ["grid/tree-common.h"]),
    ("n04", "contact_angle", ["contact.h"]),
    ("n05", "curvature", ["curvature.h"]),
    ("n06", "embed.h", ["embed.h"]),
]

#: THE TARGET. Nobody greps "two-phase" for "simulate a bubble" and nobody
#: greps "vof" for "track an interface". If the index does not win here it wins
#: nowhere.
CONCEPT = [
    ("c01", "simulate a rising bubble in a liquid",
     ["examples/bubble.c", "test/rising.c"]),
    ("c02", "add surface tension between two fluids", ["tension.h"]),
    ("c03", "flow around a solid obstacle of arbitrary shape", ["embed.h"]),
    ("c04", "shallow water equations for a tsunami",
     ["saint-venant.h", "examples/tsunami.c"]),
    ("c05", "vortex shedding behind a cylinder", ["examples/karman.c"]),
    ("c06", "break up a liquid jet into droplets", ["examples/atomisation.c"]),
    ("c07", "refine the mesh where the solution varies quickly",
     ["grid/tree-common.h"]),
    ("c08", "track the interface between two immiscible fluids",
     ["vof.h", "two-phase.h"]),
    ("c09", "axisymmetric flow about a central axis", ["axi.h"]),
    ("c10", "make pictures and movies of the simulation", ["view.h", "draw.h"]),
]

#: The agent is staring at output whose words it did not choose. Every string
#: below is one Basilisk actually emits, located in the corpus.
ERROR = [
    ("e01", "contact_angle() cannot be used for which is the normal",
     ["contact.h"]),
    ("e02", "could not restore from", ["view.h"]),
    ("e03", "dump(): must specify a file name when using MPI", ["output.h"]),
]

#: "Am I allowed to?" The answer is a RULE about a header, not the header.
#: Basilisk states these NOWHERE -- one #error in the whole tree
#: (grid/gpu/glad.h) and zero prose ordering constraints -- so they must be
#: DERIVED from co-occurrence across the verified example corpus. This tier is
#: the differentiator claim: if the index cannot answer these, it is a search
#: engine with extra steps.
RULE = [
    ("r01", "can I use the layered solver together with centered Navier-Stokes",
     ["layered/hydro.h", "navier-stokes/centered.h"]),
    ("r02", "what must I define before including navier-stokes/centered.h",
     ["navier-stokes/centered.h"]),
    ("r03", "which solvers work with two-phase.h",
     ["two-phase.h", "navier-stokes/centered.h"]),
    ("r04", "is green-naghdi compatible with the centered solver",
     ["green-naghdi.h", "saint-venant.h"]),
]

#: "How do I turn this off / point it somewhere else." Doubles as a drift
#: check: a knob no query can reach is a knob nobody can find.
KNOB = [
    ("k01", "limit the size of the timestep", ["timestep.h", "run.h"]),
    ("k02", "change the tolerance of the Poisson solver", ["poisson.h"]),
    ("k03", "run the Stokes limit without inertia",
     ["navier-stokes/centered.h"]),
]

ALL = NAME + CONCEPT + ERROR + RULE + KNOB

#: Stratified so the held-out set is not accidentally the easy third.
HELD_OUT_IDS = frozenset({"n02", "n05", "c03", "c06", "c09",
                          "e03", "r03", "k02"})

HELD_OUT = [q for q in ALL if q[0] in HELD_OUT_IDS]
DEVELOPMENT = [q for q in ALL if q[0] not in HELD_OUT_IDS]
