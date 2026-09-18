"""A small Basilisk-shaped source tree, built in a temp directory.

WHY THIS EXISTS
    48 of the 54 Basilisk tests skipped without a corpus, so the index was
    exercised by CI not at all and every published figure came from a tree
    only its author could reach. A suite that is green because it checked
    nothing looks exactly like a suite that is green because everything works.

    The Abaqus tool has the same shape and a genuine excuse -- its corpus is
    Dassault's licensed content and cannot be redistributed -- so it ships
    SYNTHETIC fixtures instead. This is that, for Basilisk.

WHAT IT IS AND IS NOT
    Not a subset of Basilisk and not a substitute for measuring against the
    real tree. It is hand-written and carries no Basilisk code, so it raises
    no licensing question at all. It reproduces the STRUCTURE the extractor
    reads -- literate `/** # Title */` blocks, column-0 field declarations,
    `(const)` user-supplied fields, `event` markers, quoted includes, and a
    test/ + examples/ case layout -- which is what the code under test
    actually depends on.

    The physics is deliberately plausible but invented. Nothing here should
    ever be cited as a fact about Basilisk.

THE ONE PROPERTY IT IS BUILT TO EXERCISE
    `_ESTABLISHED = 8` means a header must appear in at least eight cases
    before its ABSENCE beside another is allowed to mean anything. So the
    fixture ships twelve cases, enough for the "never stacked with" derivation
    -- the tier that justifies the whole tool -- to fire and be asserted on.
"""
from __future__ import annotations

from pathlib import Path

#: rel path -> file body. Written flush-left on purpose: the extractor treats
#: column 0 as the header's INTERFACE and indented declarations as internals.
_HEADERS: dict[str, str] = {
    "utils.h": '/**\n# Utilities\nShared helpers.\n*/\nscalar sample_field[];\n',
    "fractions.h": '/**\n# Volume fractions\nGeometric reconstruction.\n*/\n'
                   'scalar cell_fraction[];\n',
    "vof.h": '/**\n# VOF advection\nAdvects a tracer.\n*/\n'
             '#include "fractions.h"\n'
             'scalar advected[];\nevent vof_advection (i++);\n',
    "two-phase.h": '/**\n# Two-phase flow\nTwo incompressible phases.\n*/\n'
                   '#include "vof.h"\n'
                   'scalar phase_indicator[];\n'
                   'face vector phase_mu[];\n'
                   'event phase_properties (i++);\n',
    "tension.h": '/**\n# Surface tension\nCurvature-driven force.\n*/\n'
                 '(const) scalar surface_sigma[];\n'
                 'event tension_force (i++);\n',
    "reduced.h": '/**\n# Reduced gravity\nBuoyancy as an interfacial force.\n*/\n'
                 '(const) vector reduced_gravity[];\n',
    "view.h": '/**\n# Visualisation\nDraws pictures of a running case.\n*/\n'
              'scalar drawn[];\n',
    "axi.h": '/**\n# Axisymmetric\nAxisymmetric metric.\n*/\nscalar axi_metric[];\n',
    "navier-stokes/centered.h":
        '/**\n# Centered Navier-Stokes\nIncompressible flow on a centered grid.\n*/\n'
        '#include "utils.h"\n'
        'scalar pressure_c[];\nvector velocity_c[], accel_c[];\n'
        '(const) face vector viscosity_mu[];\n'
        'event ns_projection (i++);\nevent ns_advection (i++);\n',
    # The alternative momentum solvers. Nothing labels these as alternatives:
    # the derivation must find that out from their never appearing beside
    # centered.h in any case.
    "saint-venant.h":
        '/**\n# Saint-Venant\nShallow-water equations.\n*/\n'
        '#include "utils.h"\n'
        'scalar water_depth[];\nvector discharge[];\n'
        'event sv_update (i++);\n',
    "layered/hydro.h":
        '/**\n# Layered hydrostatic\nMultilayer hydrostatic solver.\n*/\n'
        '#include "utils.h"\n'
        'scalar layer_thickness[];\n',
}

#: case -> (title, includes). Twelve cases, so centered.h clears _ESTABLISHED
#: and the absence of saint-venant.h beside it becomes informative.
_CASES: dict[str, tuple[str, list[str]]] = {
    "test/bubble_rise.c": ("Rising bubble in a tank",
                           ["navier-stokes/centered.h", "two-phase.h", "tension.h"]),
    "test/droplet_fall.c": ("Falling droplet",
                            ["navier-stokes/centered.h", "two-phase.h", "reduced.h"]),
    "test/jet_breakup.c": ("Jet breakup",
                           ["navier-stokes/centered.h", "two-phase.h", "tension.h",
                            "axi.h"]),
    "test/lid_cavity.c": ("Lid-driven cavity",
                          ["navier-stokes/centered.h"]),
    "test/poiseuille.c": ("Poiseuille flow",
                          ["navier-stokes/centered.h"]),
    "test/taylor_green.c": ("Taylor-Green vortex",
                            ["navier-stokes/centered.h", "view.h"]),
    "test/rayleigh_taylor.c": ("Rayleigh-Taylor instability",
                               ["navier-stokes/centered.h", "two-phase.h",
                                "reduced.h", "view.h"]),
    "examples/atomisation.c": ("Atomisation of a liquid jet",
                               ["navier-stokes/centered.h", "two-phase.h",
                                "tension.h", "view.h"]),
    "examples/coalescence.c": ("Coalescence of two drops",
                               ["navier-stokes/centered.h", "two-phase.h",
                                "tension.h"]),
    # The shallow-water family: never beside centered.h, which is the signal.
    # BOTH families must clear _ESTABLISHED for the derivation to fire -- the
    # candidate whose absence is being read has to be common enough that its
    # absence could have been otherwise. Writing only two shallow-water cases
    # produced an empty "never" list and a passing-looking fixture that proved
    # nothing, which is the failure this file exists to prevent.
    "test/dam_break.c": ("Dam break over a step", ["saint-venant.h"]),
    "test/tsunami.c": ("Tsunami run-up", ["saint-venant.h", "view.h"]),
    "test/lake_at_rest.c": ("Lake at rest", ["saint-venant.h"]),
    "test/bore.c": ("Undular bore", ["saint-venant.h"]),
    "test/gaussian_hump.c": ("Gaussian hump", ["saint-venant.h", "view.h"]),
    "test/parabolic_basin.c": ("Oscillations in a parabolic basin",
                               ["saint-venant.h"]),
    "examples/river_flood.c": ("River flooding", ["saint-venant.h", "view.h"]),
    "examples/shock_train.c": ("Train of shocks", ["saint-venant.h"]),
    "examples/layered_lake.c": ("Lake at rest, layered",
                                ["layered/hydro.h", "view.h"]),
}


def build_corpus(root: Path) -> Path:
    """Write the fixture tree under ``root`` and return its ``src`` directory."""
    src = root / "src"
    for rel, body in _HEADERS.items():
        path = src / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    for rel, (title, headers) in _CASES.items():
        path = src / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(f'#include "{h}"\n' for h in headers)
        path.write_text(
            f"/**\n# {title}\nA worked case.\n*/\n{body}"
            '#include <stdio.h>\nint main() { return 0; }\n',
            encoding="utf-8")
    return src
