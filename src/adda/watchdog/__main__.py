"""``python -m adda.watchdog`` — see ``adda._src.infra.watchdog_launcher``
for the real CLI implementation."""
from __future__ import annotations

import sys

from .._src.infra.watchdog_launcher import main

if __name__ == "__main__":
    sys.exit(main())
