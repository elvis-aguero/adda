"""Public entry point for adda's run watchdog.

    python -m adda.watchdog <study-dir> --budget <duration>

Runs the study as a child process, owns the wall-clock deadline from the
parent, and force-exits (and reaps) a genuinely wedged run. The real
implementation lives in ``adda._src.infra.watchdog_launcher`` — this
top-level package exists only so ``python -m adda.watchdog`` resolves,
mirroring ``adda/viewer``'s own thin-forwarding convention.
"""
from __future__ import annotations
