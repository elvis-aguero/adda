"""Structural checks for the blind literature query set.

These tests validate the SHAPE of ``adda_literature_queries.py`` -- gold ids
are real, ids and query strings are not duplicated, the held-out split is
real and stratified. They do not run, import, or score any retriever: doing
that would defeat the point of the file they are checking.

``_MANIFEST_PAPER_IDS`` below is a frozen copy of the 132 ``paper_id``
values from the manifest the query set was written against
(``scratchpad/litcorpus_manifest.md``, a session-local file outside this
repo, not committed here). It is copied inline rather than read from that
path at test time so this test keeps working regardless of where or whether
that scratch file still exists -- the manifest's *job* (letting a blind
query author see what each paper is about) is already done; this test only
needs the id list, which is small and stable enough to freeze.
"""
from __future__ import annotations

import collections

import pytest

from . import adda_literature_queries as Q

#: 132 paper_id values, exactly as spelled in the manifest table (131
#: `registered` + 1 `orphan_dir_no_csv_row_no_embeddings`). Frozen here, not
#: parsed from the manifest file, so this check does not depend on a
#: session-local scratch path surviving.
_MANIFEST_PAPER_IDS = frozenset({
    "adany_silvestre_schafer_2009_gbt_cfsm", "adma201904845_sup_0001_suppmat__1",
    "arxiv_1104_5207", "arxiv_1203_1481", "arxiv_1304_3569", "arxiv_1304_6294",
    "arxiv_1406_1104", "arxiv_1407_4273", "arxiv_1502_03396", "arxiv_1508_03099",
    "arxiv_1609_07856", "arxiv_1612_05987", "arxiv_1612_05988", "arxiv_1702_06470",
    "arxiv_1707_03673", "arxiv_1804_03072", "arxiv_1807_00066", "arxiv_1809_01188",
    "arxiv_1902_05038", "arxiv_1904_04610", "arxiv_1905_00187", "arxiv_1910_09210",
    "arxiv_2004_11055", "arxiv_2005_05067", "arxiv_2008_07421", "arxiv_2010_07850",
    "arxiv_2012_12185", "arxiv_2108_10976", "arxiv_2205_02034", "arxiv_2205_04348",
    "arxiv_2209_15126", "arxiv_2302_12097", "arxiv_2303_04920", "arxiv_2308_13758",
    "arxiv_2309_11344", "arxiv_2401_07881", "arxiv_2403_02299", "arxiv_2403_02505",
    "arxiv_2403_08026", "arxiv_2408_05415", "arxiv_2409_12652", "arxiv_2410_16452",
    "arxiv_2503_20670", "arxiv_2505_09373", "arxiv_2505_23372", "arxiv_2506_14619",
    "arxiv_2508_10802", "arxiv_2511_06039", "arxiv_2512_01118", "arxiv_2512_15139",
    "arxiv_2607_15706", "arxiv_cond_mat_0004121",
    "bertoldi_2017_harnessing_instabilities",
    "chen2017_3dprinted_hierarchical_honeycomb", "doi_10_1002_adma_201904845",
    "doi_10_1002_adma_202305254", "doi_10_1002_smll_200900853",
    "doi_10_1007_s00161_025_01389_6", "doi_10_1007_s00170_022_09924_4",
    "doi_10_1007_s00419_022_02192_4", "doi_10_1007_s00466_023_02332_9",
    "doi_10_1007_s12213_019_00113_3", "doi_10_1007_s40430_025_06016_8",
    "doi_10_1016_j_actaastro_2019_02_014", "doi_10_1016_j_ijmecsci_2026_111562",
    "doi_10_1016_j_istruc_2023_03_124", "doi_10_1038_ncomms15568",
    "doi_10_1038_ncomms2553", "doi_10_1038_ncomms4266", "doi_10_1038_s41467_017_00670_w",
    "doi_10_1038_s41467_019_13978_6", "doi_10_1038_s41467_022_28696_9",
    "doi_10_1038_s41467_023_41679_8", "doi_10_1038_s41467_024_51104_3",
    "doi_10_1038_s41467_025_66443_y", "doi_10_1038_s41528_017_0004_y",
    "doi_10_1038_s41586_024_08037_0", "doi_10_1038_s41586_025_08658_z",
    "doi_10_1038_s41598_018_20795_2", "doi_10_1038_s41598_018_30737_7",
    "doi_10_1038_s41598_019_48581_8", "doi_10_1038_s41598_020_74147_0",
    "doi_10_1038_s41598_023_47525_7", "doi_10_1038_s43246_020_00107_w",
    "doi_10_1038_s44172_024_00223_2", "doi_10_1038_s44455_025_00004_7",
    "doi_10_1038_srep18306", "doi_10_1073_pnas_0807476105",
    "doi_10_1073_pnas_1515602112", "doi_10_1088_1361_665x_abde50",
    "doi_10_1098_rsta_2024_0005", "doi_10_1109_jmems_2007_897090",
    "doi_10_1109_tro_2023_3324571", "doi_10_1115_1_4053378",
    "doi_10_1177_1045389x241259371", "doi_10_1186_s10033_021_00606_y",
    "doi_10_1186_s40192_015_0038_8", "doi_10_12921_cmst_2004_10_02_137_145",
    "doi_10_13052_17797179_2012_714848", "doi_10_1371_journal_pone_0168218",
    "doi_10_1590_s1679_78252014001200009", "doi_10_2140_jomms_2006_1_63",
    "doi_10_2478_jbe_2013_0006", "doi_10_25103_jestr_072_27", "doi_10_2514_6_2018_0942",
    "doi_10_3389_fams_2019_00034", "doi_10_3389_fmats_2018_00022",
    "doi_10_3389_fmats_2019_00169", "doi_10_3389_fmats_2020_00134",
    "doi_10_3846_2029882x_2016_1277169", "doi_10_5194_ms_10_133_2019",
    "doi_10_5194_ms_2_109_2011", "doi_10_5194_ms_2_205_2011", "doi_10_5194_ms_8_29_2017",
    "doi_10_5194_wes_5_685_2020", "doi_10_62913_engj_v26i4_527",
    "doi_10_62913_engj_v39i1_769", "doi_10_62913_engj_v54i3_1116", "ginsbourger_2010",
    "glauz_schafer_2025_generalized_ltb", "hoang_adany_2020_torsional_buckling",
    "hussein2015_thesis_curved_beams_multistable_microrobots",
    "kesavan2018_belly_column", "kobelev_2021_column_buckling_optimization",
    "lee_oh_li_2002_tapered_columns", "liu2025_CMCS_SI", "meng_thesis_2012",
    "migliaccio_eccomas_2021", "patil_2014_helical_springs",
    "tan2020_graded_reentrant_honeycomb", "yin2018_hierarchical_honeycomb",
    "zhang_fractal_lattice_energy_absorption_2025",
})


def test_manifest_id_count_is_132():
    assert len(_MANIFEST_PAPER_IDS) == 132


@pytest.mark.parametrize(
    ("qid", "pid"),
    [(qid, pid) for qid, _q, gold, _tier in Q.QUERIES for pid in gold])
def test_every_gold_id_appears_in_the_manifest(qid, pid):
    assert pid in _MANIFEST_PAPER_IDS, (
        f"query {qid} is labelled with paper_id {pid!r}, which does not "
        f"appear in the manifest. Gold ids must be copied exactly as "
        f"spelled there.")


def test_query_ids_are_unique():
    dupes = [i for i, c in collections.Counter(q[0] for q in Q.QUERIES).items()
             if c > 1]
    assert not dupes, f"duplicate query ids: {dupes}"


def test_query_strings_are_unique():
    dupes = [s for s, c in collections.Counter(q[1] for q in Q.QUERIES).items()
             if c > 1]
    assert not dupes, f"duplicate query strings: {dupes}"


def test_every_held_out_id_exists_in_queries():
    ids = {q[0] for q in Q.QUERIES}
    missing = Q.HELD_OUT_IDS - ids
    assert not missing, f"HELD_OUT_IDS names ids with no query: {sorted(missing)}"


def test_the_held_out_split_is_frozen_and_real():
    assert len(Q.DEVELOPMENT) + len(Q.HELD_OUT) == len(Q.QUERIES)
    assert Q.HELD_OUT, "the held-out split is empty"
    assert Q.DEVELOPMENT, "the development split is empty"


def test_every_tier_is_represented_in_both_splits():
    """Stratification is the point of the split: a tier held out entirely, or
    not at all, makes the held-out score unreadable for that tier."""
    for split, rows in (("development", Q.DEVELOPMENT), ("held out", Q.HELD_OUT)):
        tiers = {r[3] for r in rows}
        assert tiers == set(Q.TIERS), (
            f"{split} split is missing tiers: {set(Q.TIERS) - tiers}")


def test_no_query_is_gold_labelled_with_the_known_metadata_bug_paper():
    """The manifest flags `adma201904845_sup_0001_suppmat__1` as having a
    title that does not match its content. No query should be built on that
    mismatch in either direction."""
    flagged = "adma201904845_sup_0001_suppmat__1"
    offenders = [qid for qid, _q, gold, _tier in Q.QUERIES if flagged in gold]
    assert not offenders, (
        f"queries {offenders} are gold-labelled with the flagged "
        f"metadata-bug paper; this file must not build queries on it")


def test_roughly_one_third_is_held_out():
    frac = len(Q.HELD_OUT) / len(Q.QUERIES)
    assert 0.28 <= frac <= 0.40, f"held-out fraction {frac:.2f} is not ~1/3"


def test_gold_lists_are_nonempty_and_deduplicated():
    for qid, _q, gold, _tier in Q.QUERIES:
        assert gold, f"query {qid} has an empty gold list"
        assert len(gold) == len(set(gold)), f"query {qid} has duplicate gold ids"
