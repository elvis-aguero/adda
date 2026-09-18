"""The attestation hook, exercised against real git state.

The hook has exactly three behaviours worth pinning, and one of them is the
reason the whole thing is not self-defeating: it must be a NO-OP in CI. CI
runs `pre-commit run --all-files`, where nobody is committing and there is
nothing to attest to. A hook that failed there would fail every pull request
and be disabled within a day, which is how a rule stops holding without
anyone deciding to drop it.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_TOOL = _ROOT / "internal" / "tools" / "paper_attestation.py"


def _repo(tmp_path: Path) -> Path:
    """A throwaway repo shaped like this one, so the hook is run for real
    rather than against a mocked git."""
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    (tmp_path / "src" / "adda" / "_src").mkdir(parents=True)
    (tmp_path / "paper").mkdir()
    (tmp_path / "internal" / "tools").mkdir(parents=True)
    (tmp_path / "internal" / "tools" / "paper_attestation.py").write_text(
        _TOOL.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "src" / "adda" / "_src" / "a.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    return tmp_path


def _run(repo: Path, *args: str, env: dict | None = None):
    return subprocess.run(
        [sys.executable, "internal/tools/paper_attestation.py", *args],
        cwd=repo, capture_output=True, text=True, env=env)


def test_nothing_staged_is_a_no_op_which_is_what_makes_ci_work(tmp_path):
    """`pre-commit run --all-files` stages nothing. If this returned non-zero
    the hook would fail every pull request."""
    repo = _repo(tmp_path)
    assert _run(repo).returncode == 0


def test_a_commit_that_does_not_touch_watched_code_passes(tmp_path):
    repo = _repo(tmp_path)
    (repo / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    assert _run(repo).returncode == 0, "a docs-only commit must not be blocked"


def test_a_commit_touching_watched_code_is_blocked_and_says_what_changed(tmp_path):
    repo = _repo(tmp_path)
    (repo / "src" / "adda" / "_src" / "b.py").write_text("y = 2\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    out = _run(repo)
    assert out.returncode == 1
    assert "src/adda/_src/b.py" in out.stderr, (
        "the attestation is worth nothing unless it names what is being "
        "attested to")
    assert "attest-paper" in out.stderr, "it must say how to proceed"


def test_a_commit_that_also_touches_the_paper_is_itself_the_attestation(tmp_path):
    repo = _repo(tmp_path)
    (repo / "src" / "adda" / "_src" / "b.py").write_text("y = 2\n")
    (repo / "paper" / "notes.tex").write_text("\\section{x}\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    assert _run(repo).returncode == 0, (
        "someone editing the paper in the same commit has already done the "
        "thing the hook is asking for")


def test_the_escape_hatch_is_named_rather_than_silent(tmp_path):
    """--no-verify disables every hook and leaves no trace. This leaves the
    reason on screen and keeps the other hooks running."""
    repo = _repo(tmp_path)
    (repo / "src" / "adda" / "_src" / "b.py").write_text("y = 2\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    import os

    env = {**os.environ, "ADDA_SKIP_PAPER_ATTESTATION": "1"}
    out = _run(repo, env=env)
    assert out.returncode == 0
    assert "skipped" in out.stderr


def test_attesting_records_who_when_and_through_which_commit(tmp_path):
    repo = _repo(tmp_path)
    assert _run(repo, "--attest").returncode == 0
    data = json.loads((repo / "paper" / "ATTESTATION.json").read_text())
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                          capture_output=True, text=True).stdout.strip()
    assert data["reviewed_through"] == head
    assert data["reviewed_at"].endswith("Z")
    assert data["by"]


def test_declining_is_recorded_rather_than_indistinguishable_from_attesting(
        tmp_path):
    """A decline that looked like an attestation would make the record
    useless: the point of the file is to show later which changes somebody
    actually read the paper against."""
    repo = _repo(tmp_path)
    _run(repo, "--decline", "pure refactor, no design decision")
    data = json.loads((repo / "paper" / "ATTESTATION.json").read_text())
    assert data["declined"], "the decline left no trace"
    assert "refactor" in data["declined"][0]["why"]
    assert data["declined"][0]["through"] == data["reviewed_through"]


def test_this_repository_is_currently_attested():
    """Fails when paper/ATTESTATION.json names a commit this repo does not
    have -- a rebase or a squash can orphan it, and a dangling attestation is
    worse than none because the hook silently stops reporting drift."""
    data = json.loads((_ROOT / "paper" / "ATTESTATION.json").read_text())
    sha = data["reviewed_through"]
    kind = subprocess.run(["git", "cat-file", "-t", sha], cwd=_ROOT,
                          capture_output=True, text=True).stdout.strip()
    if not kind:
        pytest.skip("no git history here (shallow clone or export)")
    assert kind == "commit", f"attested through {sha!r}, which is not a commit"
