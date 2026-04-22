"""Archilume Reflex app package.

Pins ``REFLEX_STATES_WORKDIR`` to an absolute path next to this package so
Reflex's on-disk state manager never creates a ``.states/`` directory at the
caller's cwd (e.g. the repo root) when this package is imported.
"""

import os
from pathlib import Path

os.environ.setdefault(
    "REFLEX_STATES_WORKDIR",
    str(Path(__file__).resolve().parent.parent / ".states"),
)
