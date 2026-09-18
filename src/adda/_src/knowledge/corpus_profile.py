"""Measure a corpus before indexing it, and again on every rebuild.

Onboarding asks what a corpus's native unit is. The rebuild gate asks whether
that answer is still true. Both are the same measurements, which is why they
are one function: a profile that is only taken once cannot detect drift, and a
knowledge base that degrades quietly across upstream releases is worse than one
that fails loudly.
"""
from __future__ import annotations

from pathlib import Path

#: Relative change in a measured field that counts as drift. Chosen so a corpus
#: growing by an ordinary release does not trip it, but a convention change --
#: a renamed construct, a restructured tree -- does.
TOLERANCE = 0.5


def profile(root: Path, *, exts: tuple[str, ...],
            markers: tuple[str, ...] = ()) -> dict:
    """Measurements that decide how a corpus should be indexed.

    ``markers`` are literal substrings whose frequency characterises the
    corpus's dialect; for Basilisk these are the constructs a C parser cannot
    read, which is exactly what makes an off-the-shelf AST index useless there.
    """
    files = [p for p in sorted(root.rglob("*")) if p.suffix in exts]
    lines = prose = 0
    counts = dict.fromkeys(markers, 0)
    for p in files:
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        in_block = False
        for line in text.splitlines():
            lines += 1
            if "/**" in line:
                in_block = True
            if in_block:
                prose += 1
            if "*/" in line:
                in_block = False
        for m in markers:
            counts[m] += text.count(m)
    return {
        "files": len(files),
        "lines": lines,
        "prose_fraction": round(prose / lines, 4) if lines else 0.0,
        "markers": counts,
    }


def drift(old: dict, new: dict) -> list[str]:
    """Human-readable drift descriptions. Empty means the build may publish."""
    out: list[str] = []
    for key in ("files", "lines", "prose_fraction"):
        a, b = old.get(key, 0), new.get(key, 0)
        if a and abs(b - a) / a > TOLERANCE:
            out.append(f"{key}: {a} -> {b}")
    for name, a in old.get("markers", {}).items():
        b = new.get("markers", {}).get(name, 0)
        if a and abs(b - a) / a > TOLERANCE:
            out.append(f"marker {name!r}: {a} -> {b}")
    return out
