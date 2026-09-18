"""Labelled queries for adda's literature-retrieval index over the frozen
supercompressible-metamaterials corpus (132 papers, see the manifest this set
was written from: ``scratchpad/litcorpus_manifest.md``, outside this repo).

WHY THIS FILE WAS WRITTEN BLIND
    A query set written by someone who has read the retriever's ranking code,
    or who checked candidate queries against the corpus text, measures the
    tool's own shape rather than the retrieval problem. This repo has a
    direct measurement of that effect: r@1 fell from 0.40 to 0.31 between a
    query set written alongside the retriever and one written blind against
    it. The author of this file read only the manifest -- paper_id, title,
    and a plain-English description of what each paper is about -- and never
    ran, read, or grepped anything that ranks or scores. Nothing here may be
    edited because a retriever missed it; that is precisely the failure mode
    a blind set exists to prevent.

THE FIVE TIERS, AND WHAT EACH ONE IS FOR
    TITLE   -- the CONTROL. A near-verbatim title or a distinctive
               author+topic pairing. Exact lexical match should win here;
               this tier costs a retriever nothing to tie and is a red flag
               if lost badly.
    CONCEPT -- the tier the whole proposal rests on. A researcher's question
               phrased in their own words, deliberately avoiding the paper's
               own vocabulary. Nobody searching for "why does a shell
               collapse all at once" types "subcritical buckling instability"
               unless they already know the field's term for what they are
               asking about.
    METHOD  -- "which work used <a technique described by what it does, not
               what it is called> to do <a thing>." Tests whether a retriever
               can match a functional description of a method against a
               paper that used it, without the method's name as a crutch.
    FINDING -- "which paper reports that <an outcome, described, never
               quoted>." Tests whether a retriever can match a paraphrased
               result to the paper that produced it.
    CROSS   -- genuinely multi-paper questions. Gold is a SET; any one member
               at rank 1 counts as a hit. Tests whether a retriever surfaces a
               body of related work rather than one lucky title match.

THE HELD-OUT SPLIT
    ``HELD_OUT_IDS`` (40 of 120, listed literally, stratified per tier so
    the held-out set is not accidentally the easy third) may not be read,
    reasoned about, or scored until the retriever's design is frozen.
    ``DEVELOPMENT`` (80) is fair game while building.

WHAT A GOLD ANSWER IS
    ``paper_id`` strings exactly as spelled in the manifest. Where more than
    one id is listed, ANY of them at rank 1 counts as a hit -- for CONCEPT,
    METHOD and FINDING queries this is used sparingly, only when a question
    is genuinely answered by more than one paper; for CROSS queries it is the
    point of the tier. ``tests/test_adda_literature_queries.py`` asserts
    every gold id named here appears in the manifest, so a copy-paste error
    in a paper_id cannot silently ship as a query nobody can ever satisfy.

A NOTE ON ONE PAPER DELIBERATELY LEFT OUT
    The manifest flags one entry, `adma201904845_sup_0001_suppmat__1`, whose
    recorded title does not match its actual content (a corpus metadata bug,
    not a description error). No query below is built on that paper, in
    either direction -- not on its wrong title, and not exploiting the
    mismatch as a "gotcha." It is simply not used as a gold label anywhere
    in this file.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# TIER 1 -- TITLE (control tier). Near-verbatim titles or distinctive
# author+topic pairs, lifted from the manifest on purpose: this is the one
# tier where doing so is correct, because it exists to measure whether exact
# lexical match works at all, not whether the retriever is clever.
# ---------------------------------------------------------------------------
TITLE = [
    ("t01", "On the feasibility of pentamode mechanical metamaterials",
     ["arxiv_1203_1481"]),
    ("t02", "Programmable Mechanical Metamaterials, Florijn Coulais van Hecke",
     ["arxiv_1407_4273"]),
    ("t03", "Bayesian Machine Learning in Metamaterial Design: Fragile Becomes Supercompressible",
     ["doi_10_1002_adma_201904845"]),
    ("t04", "Data-Driven Design for Metamaterials and Multiscale Systems: A Review",
     ["doi_10_1002_adma_202305254"]),
    ("t05", "Harnessing Instabilities to Design Tunable Architected Cellular Materials",
     ["bertoldi_2017_harnessing_instabilities"]),
    ("t06", "Harnessing plasticity in sequential metamaterials for ideal shock absorption",
     ["doi_10_1038_s41586_024_08037_0"]),
    ("t07", "Large recoverable elastic energy in chiral metamaterials via twist buckling",
     ["doi_10_1038_s41586_025_08658_z"]),
    ("t08", "Rediscovering the Cross-Section: Snapping Mechanical Metamaterials under Tension",
     ["arxiv_1612_05987"]),
    ("t09", "Bistable Auxetic Mechanical Metamaterials Inspired by Ancient Geometric Motifs",
     ["arxiv_1612_05988"]),
    ("t10", "Seventy years of tensegrities (and counting)",
     ["doi_10_1007_s00419_022_02192_4"]),
    ("t11", "Hierarchical honeycomb auxetic metamaterials",
     ["doi_10_1038_srep18306"]),
    ("t12", "Generalized Elastic Lateral-Torsional Buckling of Steel Beams, Glauz and Schafer",
     ["glauz_schafer_2025_generalized_ltb"]),
    ("t13", "Torsional Buckling of Thin-Walled Columns with Transverse Stiffeners, Hoang and Adany",
     ["hoang_adany_2020_torsional_buckling"]),
    ("t14", "Kriging Is Well-Suited to Parallelize Optimization, Ginsbourger",
     ["ginsbourger_2010"]),
    ("t15", "GBT and cFSM: two modal approaches to the buckling analysis of unbranched thin-walled members",
     ["adany_silvestre_schafer_2009_gbt_cfsm"]),
]

# ---------------------------------------------------------------------------
# TIER 2 -- CONCEPT. A question in plain English, deliberately steering away
# from any paper's own vocabulary. Where a query still shares words with a
# title or description, they are ordinary words (shell, beam, column, twist)
# rather than the paper's distinctive multi-word phrasing.
# ---------------------------------------------------------------------------
CONCEPT = [
    ("c01", "why do compressed cylindrical shells fail suddenly instead of gradually losing load",
     ["doi_10_3389_fams_2019_00034"]),
    ("c02", "what makes a material get fatter when you pull on it instead of thinner",
     ["doi_10_12921_cmst_2004_10_02_137_145"]),
    ("c03", "can a covering of overlapping hard plates on a flexible rod be tuned to resist twisting more or less",
     ["arxiv_1809_01188"]),
    ("c04", "how does dry sliding friction between overlapping rigid plates show up as apparent viscous damping",
     ["arxiv_2303_04920"]),
    ("c05", "is there a way to predict when a pre-stressed arch will suddenly flip to its other shape",
     ["doi_10_1109_jmems_2007_897090"]),
    ("c06", "how do robots use a segment that can hold two different rest shapes without continuous power",
     ["doi_10_1007_s12213_019_00113_3"]),
    ("c07", "what geometric trick lets a folded tube act like both a spring and a memory device",
     ["doi_10_1038_s41467_017_00670_w"]),
    ("c08", "why would engineers deliberately let a structural part deform plastically instead of avoiding it",
     ["doi_10_1038_s41586_024_08037_0"]),
    ("c09", "how do you keep a lattice of thin struts from bending sideways so the whole thing stays stiff under load",
     ["arxiv_2409_12652"]),
    ("c10", "does letting the edge of a shell slide against a rigid surface change whether it snaps abruptly or eases into a new shape",
     ["arxiv_2503_20670"]),
    ("c11", "how much force can a woven fabric wrapped around a tube withstand before it wrinkles",
     ["arxiv_2512_15139"]),
    ("c12", "how do additive-manufacturing print settings affect how far a finished part's dimensions drift from the design",
     ["doi_10_1007_s00170_022_09924_4"]),
    ("c13", "is there a mathematical shortcut for finding the best cross-section shape for a column resisting compression",
     ["kobelev_2021_column_buckling_optimization"]),
    ("c14", "how should you pick the fiber angles in a composite flapping wing so it twists the right amount as it bends",
     ["arxiv_2505_23372"]),
    ("c15", "what stops a solar-array-like folding boom from tearing itself apart as it unfolds",
     ["doi_10_1016_j_actaastro_2019_02_014"]),
    ("c16", "how do you search a design space efficiently when most of the candidate designs are outright invalid",
     ["arxiv_2004_11055"]),
    ("c17", "is there a cheap surrogate that tells an optimizer which candidate points are worth an expensive simulation",
     ["arxiv_2005_05067"]),
    ("c18", "why not just wait for one simulation to fail before shrinking the search neighborhood -- is there something smarter",
     ["arxiv_2506_14619"]),
    ("c19", "why might crumpling a wire into a tight ball look different depending on how much it can bend versus permanently deform",
     ["doi_10_1038_ncomms15568"]),
    ("c20", "how does a spiral crack pattern let a flat sheet pop into a 3D shape",
     ["doi_10_1073_pnas_1515602112"]),
    ("c21", "what lets a flexible circuit stretch like rubber without snapping its wires",
     ["doi_10_1038_ncomms4266"]),
    ("c22", "why do batteries need a special wiring layout to bend around a joint and still charge wirelessly",
     ["doi_10_1038_ncomms2553"]),
    ("c23", "how do bone and insect shells get their toughness from the angle at which fiber layers are stacked",
     ["doi_10_1038_s41467_019_13978_6"]),
    ("c24", "does spontaneous curling built into a rod's rest shape change how easily it buckles under a squeeze",
     ["arxiv_cond_mat_0004121"]),
    ("c25", "how tightly can a rope be wound around a post before friction alone holds it in place",
     ["arxiv_2205_04348"]),
    ("c26", "what happens to the stiffness of a twisted pair of strands as you keep twisting them further",
     ["arxiv_2309_11344"]),
    ("c27", "how does removing material in a checkerboard pattern from a stretched sheet make it pop into three dimensions",
     ["arxiv_1702_06470"]),
    ("c28", "can folding creases be arranged so a cut sheet rotates as it is squeezed",
     ["arxiv_1707_03673"]),
    ("c29", "why would you deliberately break the mirror symmetry of a repeating structure to change how it fails",
     ["arxiv_1502_03396"]),
    ("c30", "how can confining certain panels of a folded structure change how much energy it absorbs each cycle",
     ["doi_10_1098_rsta_2024_0005"]),
    ("c31", "what geometric feature lets a beam pinched into an hourglass shape act as an on/off switch under load",
     ["arxiv_2205_02034"]),
    ("c32", "how does confinement from neighboring cells change whether a lattice unit buckles inward or outward",
     ["arxiv_1407_4273"]),
    ("c33", "why does a soft robot arm built from a stack of twist-locking segments hold a pose without a motor at every joint",
     ["arxiv_2008_07421"]),
    ("c34", "how do biological filament bundles held together by crosslinking proteins end up with a preferred thickness",
     ["arxiv_1104_5207"]),
    ("c35", "why do bridge trusses built from riveted double-angle sections sometimes buckle at a lower load than a single solid bar of the same area",
     ["doi_10_62913_engj_v39i1_769"]),
]

# ---------------------------------------------------------------------------
# TIER 3 -- METHOD. "Which work used <technique, described functionally> to
# do <thing>." The gold paper is the one that actually used the technique.
# ---------------------------------------------------------------------------
METHOD = [
    ("m01", "which study used high-speed-camera image correlation to track a tensegrity column's wave motion after an impact",
     ["doi_10_3389_fmats_2018_00022"]),
    ("m02", "which paper combined the Rayleigh-Ritz method with continuous displacement functions to model an I-shaped strut's interactive buckling",
     ["arxiv_1304_6294"]),
    ("m03", "which work built a beam theory embedded in 2D space, using Timoshenko-style kinematics, to capture a chiral lattice's static response",
     ["doi_10_1007_s00161_025_01389_6"]),
    ("m04", "which paper used a relaxed micromorphic continuum model to explain size-dependent bending stiffness in a metamaterial beam",
     ["doi_10_1007_s00466_023_02332_9"]),
    ("m05", "which study derived a mathematical shell model bonded to an elastic foundation by modifying Koiter's equations",
     ["arxiv_2012_12185"]),
    ("m06", "which paper applied the method of multiple scales to reduce a helical rod's governing equations to an equivalent straight-rod theory",
     ["arxiv_2403_02299"]),
    ("m07", "which work used a Cosserat-rod formulation with contact constraints to capture combined bending and twisting of an overlapping-plate substrate",
     ["arxiv_2108_10976"]),
    ("m08", "which paper used full-field image-processing strain measurement on a simple bending rig to characterize a thin composite flexure",
     ["doi_10_2514_6_2018_0942"]),
    ("m09", "which study used digital image correlation together with high-fidelity finite-element wrinkle simulations to analyze a thin membrane",
     ["doi_10_2140_jomms_2006_1_63"]),
    ("m10", "which paper derived an analytical tangent matrix for a new arc-length continuation scheme to solve softening damage problems",
     ["arxiv_2308_13758"]),
    ("m11", "which study used asymptotic post-buckling coefficients -- the initial slope and curvature terms -- inside a sizing and topology optimization loop for trusses",
     ["arxiv_2505_09373"]),
    ("m12", "which paper used a stiffness-probe procedure, perturbing a structure locally and tracking the response as load increases, to find buckling loads of a cable-stayed column",
     ["doi_10_62913_engj_v54i3_1116"]),
    ("m13", "which work trained a machine-learning surrogate to invert the design of a layered structure for a prescribed nonlinear force-displacement curve",
     ["doi_10_1016_j_ijmecsci_2026_111562"]),
    ("m14", "which study used machine learning to optimize the thickness distribution across a bistable curved shell",
     ["doi_10_1016_j_istruc_2023_03_124"]),
    ("m15", "which paper compared two different modal-decomposition frameworks for separating a thin-walled member's buckling into global, distortional and local components",
     ["adany_silvestre_schafer_2009_gbt_cfsm"]),
    ("m16", "which work used LS-DYNA crash simulations to compare hexagonal, Kagome and triangular hierarchical honeycomb tessellations",
     ["yin2018_hierarchical_honeycomb"]),
    ("m17", "which paper used pyrolysis of a stereolithography-printed polymer scaffold to make a carbon microlattice",
     ["doi_10_3389_fmats_2019_00169"]),
    ("m18", "which study used a numerical procedure to compute buckling loads of tapered columns with a regular-polygon cross-section",
     ["lee_oh_li_2002_tapered_columns"]),
    ("m19", "which paper used a shape-optimized non-prismatic column design, checked against both buckling and strength limits, to cut material from an encased composite column",
     ["kesavan2018_belly_column"]),
    ("m20", "which study used electrostatic actuation experiments alongside theory to characterize an arch-shaped micro-beam's pull-in instability",
     ["doi_10_1109_jmems_2007_897090"]),
    ("m21", "which paper used piezoelectric actuation to trigger the snap-through of a pre-buckled clamped beam",
     ["doi_10_1177_1045389x241259371"]),
    ("m22", "which study used in-situ compression testing plus digital image correlation to reveal the node-rotation deformation mechanism of a 3D chiral lattice",
     ["doi_10_1038_s41598_018_30737_7"]),
    ("m23", "which paper used a dimensional-analysis technique, defining dimensionless mass and rigidity factors, to get a closed-form optimum for a compressed column",
     ["kobelev_2021_column_buckling_optimization"]),
    ("m24", "which paper used a Bayesian probabilistic machine-learning framework to design a metamaterial unit cell that recovers after being crushed",
     ["doi_10_1002_adma_201904845"]),
    ("m25", "which study used a Kriging-based sequential design strategy to propose several simulation points per iteration instead of one at a time",
     ["ginsbourger_2010"]),
]

# ---------------------------------------------------------------------------
# TIER 4 -- FINDING. "Which paper reports that <outcome>." The outcome is
# described, never quoted, and the gold paper is whose result it is.
# ---------------------------------------------------------------------------
FINDING = [
    ("f01", "which paper reports that a supercompressible unit cell keeps high strength and stiffness while recovering from near-total collapse",
     ["doi_10_1002_adma_201904845"]),
    ("f02", "which paper reports that friction between sliding scale-like plates can look just like ordinary viscous damping even though the contact itself is dry friction",
     ["arxiv_2303_04920"]),
    ("f03", "which paper reports that a kirigami cylinder's pop-up transition can spread outward from a single starting flaw rather than happening everywhere at once",
     ["arxiv_1905_00187"]),
    ("f04", "which paper reports that plastic yielding of the base material can be used on purpose to program the order in which a metamaterial's cells buckle",
     ["arxiv_2410_16452"]),
    ("f05", "which paper reports that a 3D printed lattice with thin, periodically arranged members stays flexible up to large strain without losing stiffness",
     ["arxiv_2409_12652"]),
    ("f06", "which paper reports that adding holes with the right symmetry to a cylindrical shell can stop it twisting out of shape under load",
     ["doi_10_1038_s41467_024_51104_3"]),
    ("f07", "which paper reports that combining torsion with curved-shell buckling in one metamaterial gives unusually high energy absorption per unit weight",
     ["doi_10_1038_s41467_025_66443_y"]),
    ("f08", "which paper reports that a chiral lattice can store an especially large amount of recoverable elastic energy by buckling under twist rather than compression",
     ["doi_10_1038_s41586_025_08658_z"]),
    ("f09", "which paper reports that letting a shock-absorbing metamaterial deform plastically, instead of avoiding it, gives a flatter and more ideal force response",
     ["doi_10_1038_s41586_024_08037_0"]),
    ("f10", "which paper reports that a titanium rotating-squares auxetic pattern tolerates more strain once the connection regions are rounded with variable-radius fillets",
     ["doi_10_1088_1361_665x_abde50"]),
    ("f11", "which paper reports that small geometric tweaks at the member level of a re-entrant honeycomb can noticeably boost its auxetic response",
     ["doi_10_1038_s41598_023_47525_7"]),
    ("f12", "which paper reports that a cellular material can be engineered so its Poisson's ratio flips sign partway through compression rather than staying fixed",
     ["doi_10_1038_s41467_022_28696_9"]),
    ("f13", "which paper reports that stretchable circuits laid out in a fractal, self-similar pattern can accommodate much larger deformation than a straight serpentine trace",
     ["doi_10_1038_ncomms4266"]),
    ("f14", "which paper reports that a wirelessly rechargeable battery can be made to stretch by using a self-similar serpentine interconnect layout",
     ["doi_10_1038_ncomms2553"]),
    ("f15", "which paper reports that a thin sheet cut with a square array of orthogonal slits naturally buckles out of plane under simple stretching",
     ["arxiv_1702_06470"]),
    ("f16", "which paper reports mapping every stable buckled shape a cylindrical shell can hold into a navigable landscape so a chosen target shape can be reached",
     ["arxiv_1910_09210"]),
    ("f17", "which paper reports that whether an elastic shell snaps abruptly or eases into a new shape depends on the boundary contact condition, not only on its geometry",
     ["arxiv_2503_20670"]),
    ("f18", "which paper reports that how fast an arch snaps through depends strongly on how slender it is and on small shape imperfections",
     ["arxiv_2508_10802"]),
    ("f19", "which paper reports that a rod's own built-in spontaneous twist changes the compressive load at which it buckles",
     ["arxiv_cond_mat_0004121"]),
    ("f20", "which paper reports that fiber layers stacked at a gradually rotating angle, as in insect cuticle, give a laminate extra fracture resistance",
     ["doi_10_1038_s41467_019_13978_6"]),
    ("f21", "which paper reports that a woven column's buckling capacity depends on how tightly its strands are interlaced",
     ["arxiv_2512_01118"]),
    ("f22", "which paper reports that knitted fabric wrapped around a cylinder wrinkles into three-dimensional patterns rather than uniform axisymmetric folds",
     ["arxiv_2512_15139"]),
    ("f23", "which paper reports that a fractal, branching lattice architecture can be tuned to spread out load and absorb more energy per unit mass than a plain lattice",
     ["zhang_fractal_lattice_energy_absorption_2025"]),
    ("f24", "which paper reports that layering re-entrant honeycomb walls with hexagonal and triangular sub-lattices raises a sandwich panel's crashworthiness",
     ["tan2020_graded_reentrant_honeycomb"]),
    ("f25", "which paper reports that a hierarchical honeycomb built from triangular sub-lattices keeps its overall shape even after very large in-plane compression",
     ["chen2017_3dprinted_hierarchical_honeycomb"]),
]

# ---------------------------------------------------------------------------
# TIER 5 -- CROSS. Questions genuinely answered by two or more papers. Gold
# is the SET; any one member at rank 1 counts as correct.
# ---------------------------------------------------------------------------
CROSS = [
    ("x01", "which papers study the mechanics of overlapping fish-scale-like plates on a flexible substrate",
     ["arxiv_1508_03099", "arxiv_1807_00066", "arxiv_1809_01188",
      "arxiv_2108_10976", "arxiv_2303_04920", "arxiv_2403_08026",
      "doi_10_1038_s41598_020_74147_0"]),
    ("x02", "which papers investigate chiral mechanical metamaterials",
     ["doi_10_1007_s00161_025_01389_6", "doi_10_1038_s43246_020_00107_w",
      "doi_10_1038_s41598_018_30737_7", "doi_10_1038_s41586_025_08658_z",
      "doi_10_1038_s41467_025_66443_y", "arxiv_2209_15126",
      "liu2025_CMCS_SI"]),
    ("x03", "which papers deal with tensegrity structures",
     ["arxiv_1406_1104", "arxiv_1904_04610", "doi_10_1007_s00419_022_02192_4",
      "doi_10_3389_fmats_2018_00022", "doi_10_2478_jbe_2013_0006"]),
    ("x04", "which papers discuss auxetic materials with a negative Poisson's ratio",
     ["doi_10_1038_srep18306", "doi_10_1038_s41598_018_20795_2",
      "doi_10_1038_s41598_023_47525_7", "doi_10_1088_1361_665x_abde50",
      "doi_10_12921_cmst_2004_10_02_137_145",
      "doi_10_1038_s41467_024_51104_3", "doi_10_3389_fmats_2020_00134"]),
    ("x05", "which papers cover stretchable electronics built with serpentine or mesh interconnects",
     ["doi_10_1002_smll_200900853", "doi_10_1038_ncomms2553",
      "doi_10_1038_ncomms4266", "doi_10_1073_pnas_0807476105",
      "doi_10_1038_s41528_017_0004_y"]),
    ("x06", "which papers concern flexure hinges or other compliant-mechanism joints",
     ["doi_10_5194_ms_2_109_2011", "doi_10_5194_ms_8_29_2017",
      "meng_thesis_2012", "doi_10_1186_s10033_021_00606_y",
      "doi_10_5194_ms_2_205_2011"]),
    ("x07", "which papers study bistable buckled beams or arches used as switches",
     ["arxiv_1902_05038", "doi_10_1109_jmems_2007_897090",
      "doi_10_1177_1045389x241259371", "arxiv_2511_06039",
      "doi_10_1371_journal_pone_0168218"]),
    ("x08", "which papers analyze thin-walled cold-formed steel columns under compression",
     ["adany_silvestre_schafer_2009_gbt_cfsm",
      "doi_10_1590_s1679_78252014001200009",
      "doi_10_3846_2029882x_2016_1277169",
      "hoang_adany_2020_torsional_buckling",
      "glauz_schafer_2025_generalized_ltb"]),
    ("x09", "which papers use origami folding patterns to build a mechanical metamaterial",
     ["doi_10_1038_s41467_017_00670_w", "doi_10_1098_rsta_2024_0005",
      "doi_10_1115_1_4053378", "arxiv_2008_07421",
      "doi_10_1038_s44455_025_00004_7"]),
    ("x10", "which papers use kirigami cut patterns to make sheets or shells buckle into new shapes",
     ["arxiv_1702_06470", "arxiv_1707_03673", "arxiv_1905_00187",
      "doi_10_1073_pnas_1515602112"]),
    ("x11", "which papers apply Bayesian optimization to expensive-to-evaluate constrained design problems",
     ["arxiv_2004_11055", "arxiv_2005_05067", "arxiv_2506_14619",
      "ginsbourger_2010"]),
    ("x12", "which papers use machine learning to inversely design or optimize snapping or bistable shell structures",
     ["doi_10_1016_j_ijmecsci_2026_111562", "doi_10_1016_j_istruc_2023_03_124",
      "doi_10_1002_adma_201904845"]),
    ("x13", "which papers review the broader state of the art in mechanical or architected metamaterials",
     ["bertoldi_2017_harnessing_instabilities", "doi_10_1002_adma_202305254",
      "doi_10_1038_s41467_023_41679_8", "doi_10_3389_fams_2019_00034"]),
    ("x14", "which papers study honeycomb structures inspired by biological hierarchy for energy absorption",
     ["chen2017_3dprinted_hierarchical_honeycomb",
      "tan2020_graded_reentrant_honeycomb", "yin2018_hierarchical_honeycomb"]),
    ("x15", "which papers examine the buckling behavior of thin cylindrical or conical shells",
     ["doi_10_25103_jestr_072_27", "doi_10_1007_s40430_025_06016_8",
      "arxiv_1910_09210", "arxiv_2503_20670", "doi_10_3389_fams_2019_00034"]),
    ("x16", "which papers study helical filaments or rods under torsion",
     ["arxiv_1104_5207", "arxiv_1609_07856", "arxiv_2309_11344",
      "arxiv_2403_02299", "arxiv_cond_mat_0004121"]),
    ("x17", "which papers focus on deployable or high-strain composite structures for space applications",
     ["doi_10_1016_j_actaastro_2019_02_014", "doi_10_1038_s44172_024_00223_2",
      "doi_10_2514_6_2018_0942", "doi_10_5194_ms_2_205_2011",
      "doi_10_13052_17797179_2012_714848"]),
    ("x18", "which papers report on lattice or truss structures optimized for energy absorption under impact",
     ["doi_10_3389_fmats_2019_00169", "doi_10_3389_fmats_2020_00134",
      "zhang_fractal_lattice_energy_absorption_2025",
      "doi_10_5194_ms_10_133_2019"]),
    ("x19", "which papers study snap-through dynamics of arches or shells, including how fast the transition happens",
     ["arxiv_2010_07850", "arxiv_2508_10802", "doi_10_1109_jmems_2007_897090",
      "arxiv_2607_15706"]),
    ("x20", "which papers investigate microrobotic or MEMS-scale bistable and compliant mechanisms",
     ["doi_10_1007_s12213_019_00113_3",
      "hussein2015_thesis_curved_beams_multistable_microrobots",
      "doi_10_1186_s10033_021_00606_y"]),
]

TIERS = {"title": TITLE, "concept": CONCEPT, "method": METHOD,
         "finding": FINDING, "cross": CROSS}

QUERIES = [(qid, q, gold, tier)
           for tier, rows in TIERS.items() for qid, q, gold in rows]

#: Frozen split. One third (40 of 120) held out, stratified by tier so the
#: held-out set is not accidentally the easy third. The ids are listed
#: literally rather than computed, because a hash-based split silently
#: reshuffles the moment a query is added and the held-out set stops being
#: held out.
HELD_OUT_IDS = frozenset({
    "t02", "t05", "t09", "t12", "t15",                          # 5 of 15 title
    "c02", "c05", "c08", "c11", "c14", "c17", "c20", "c23",
    "c26", "c29", "c32", "c35",                                 # 12 of 35 concept
    "m02", "m05", "m08", "m11", "m14", "m17", "m20", "m23",     # 8 of 25 method
    "f02", "f05", "f08", "f11", "f14", "f17", "f20", "f23",     # 8 of 25 finding
    "x02", "x05", "x08", "x11", "x14", "x17", "x20",            # 7 of 20 cross
})

DEVELOPMENT = [r for r in QUERIES if r[0] not in HELD_OUT_IDS]
HELD_OUT = [r for r in QUERIES if r[0] in HELD_OUT_IDS]
