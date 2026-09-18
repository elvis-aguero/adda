from pathlib import Path

from adda._src.knowledge.corpus_profile import drift, profile


def test_profile_counts_files_and_lines(tmp_path: Path):
    (tmp_path / "a.h").write_text("/** doc */\nint x;\n")
    (tmp_path / "b.h").write_text("int y;\n")
    p = profile(tmp_path, exts=(".h",))
    assert p["files"] == 2
    assert p["lines"] == 3
    assert p["prose_fraction"] > 0.0


def test_drift_is_empty_for_identical_profiles(tmp_path: Path):
    (tmp_path / "a.h").write_text("int x;\n")
    p = profile(tmp_path, exts=(".h",))
    assert drift(p, p) == []


def test_drift_names_the_field_that_moved():
    old = {"files": 297, "lines": 58782, "prose_fraction": 0.16, "markers": {}}
    new = {"files": 297, "lines": 58782, "prose_fraction": 0.02, "markers": {}}
    msgs = drift(old, new)
    assert len(msgs) == 1
    assert "prose_fraction" in msgs[0]
