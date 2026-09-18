"""Make ignoring the paper a deliberate act rather than an accidental one.

WHAT THIS CAN AND CANNOT DO
    It cannot verify that paper/ is up to date. Nothing can: whether a change
    to the code needs a change to the argument is a judgement, and a hook that
    claimed to make it would be lying. What it does is narrower and is the
    only honest version of the request -- when a commit changes the code the
    paper describes, the committer is shown exactly what has changed since
    they last said "the paper reflects this", and must either say it again or
    explicitly decline.

    So this is an ATTESTATION, not a check. The signature is worth something
    because it is refreshed while looking at a diff, and worth nothing if it
    is refreshed reflexively. `make attest-paper` prints the diff first for
    that reason: an attestation you cannot avoid reading is the entire
    mechanism.

WHY IT BLOCKS RATHER THAN WARNS
    A warning in a pre-commit hook is read once and then never again. The cost
    of blocking is bounded at one command, and the escape hatch is explicit
    and logged in the attestation file rather than silent.

WHY IT IS A NO-OP IN CI
    CI runs `pre-commit run --all-files`, where nobody is committing and there
    is nothing to attest to. A hook that failed there would fail every pull
    request and would be disabled within a day -- which is how a rule stops
    holding without anyone deciding to drop it.

    uv run python internal/tools/paper_attestation.py            # the check
    uv run python internal/tools/paper_attestation.py --attest   # sign it
    uv run python internal/tools/paper_attestation.py --decline "reason"
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ATTESTATION = ROOT / "paper" / "ATTESTATION.json"

#: Set this to commit without attesting. Named rather than silent: --no-verify
#: disables every hook and leaves no trace, while this leaves the reason in
#: the terminal and keeps the other hooks running.
ESCAPE = "ADDA_SKIP_PAPER_ATTESTATION"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True, check=False).stdout.strip()


def _load() -> dict:
    if not ATTESTATION.exists():
        return {"reviewed_through": "", "watches": ["src/adda/_src"]}
    return json.loads(ATTESTATION.read_text(encoding="utf-8"))


def _staged(watches: list[str]) -> list[str]:
    out = _git("diff", "--cached", "--name-only", "--", *watches)
    return [ln for ln in out.splitlines() if ln.strip()]


def _drift(since: str, watches: list[str]) -> list[str]:
    """Files the paper describes that have changed since the last signature."""
    if not since:
        return []
    if _git("cat-file", "-t", since) != "commit":
        return ["(the attested commit is not in this repository's history)"]
    out = _git("diff", "--name-only", f"{since}..HEAD", "--", *watches)
    return [ln for ln in out.splitlines() if ln.strip()]


def check() -> int:
    if os.environ.get(ESCAPE):
        print(f"paper attestation skipped via {ESCAPE}", file=sys.stderr)
        return 0

    data = _load()
    watches = data.get("watches") or ["src/adda/_src"]
    staged = _staged(watches)
    if not staged:
        return 0                      # nothing the paper describes is changing

    # A commit that also touches the paper is itself the attestation.
    if _git("diff", "--cached", "--name-only", "--", "paper"):
        return 0

    drift = _drift(data.get("reviewed_through", ""), watches)
    pending = sorted(set(staged) | set(drift))
    print(
        "\n  The paper has not been attested against these changes.\n\n"
        "  paper/sections/03-method.tex is a register of design decisions. A\n"
        "  decision taken and never recorded is lost, and this is the only\n"
        "  moment anyone is looking at both the change and the paper.\n",
        file=sys.stderr)
    print(f"  Changed since the last attestation ({len(pending)} file(s)):",
          file=sys.stderr)
    for name in pending[:20]:
        print(f"    {name}", file=sys.stderr)
    if len(pending) > 20:
        print(f"    … and {len(pending) - 20} more", file=sys.stderr)
    print(
        "\n  Then do ONE of:\n"
        "    • add the entry to paper/sections/03-method.tex and stage it\n"
        "    • make attest-paper            (the paper already covers this)\n"
        "    • make decline-paper WHY='…'   (no design decision here)\n",
        file=sys.stderr)
    return 1


def _write(data: dict) -> None:
    ATTESTATION.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def attest(decline: str | None = None) -> int:
    data = _load()
    watches = data.get("watches") or ["src/adda/_src"]
    head = _git("rev-parse", "HEAD")
    drift = _drift(data.get("reviewed_through", ""), watches)

    if drift:
        print(f"Attesting the paper covers these {len(drift)} changed file(s):")
        for name in drift:
            print(f"  {name}")
        print()

    data["reviewed_through"] = head
    data["reviewed_at"] = _dt.datetime.now(_dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    data["by"] = _git("config", "user.name") or os.environ.get("USER", "unknown")
    data["watches"] = watches
    history = data.setdefault("declined", [])
    if decline:
        history.append({"at": data["reviewed_at"], "by": data["by"],
                        "through": head, "why": decline})
        print(f"Declined, recorded in {ATTESTATION.name}: {decline}")
    else:
        print(f"Attested through {head[:9]} by {data['by']}")
    _write(data)
    print(f"Stage it:  git add {ATTESTATION.relative_to(ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--attest", action="store_true")
    ap.add_argument("--decline", metavar="WHY",
                    help="attest, recording that no design decision was taken")
    args = ap.parse_args(argv)
    if args.attest or args.decline:
        return attest(args.decline)
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
