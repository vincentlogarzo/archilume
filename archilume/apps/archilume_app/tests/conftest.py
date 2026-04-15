"""Shared test configuration for archilume_app tests."""

import sys
from pathlib import Path

# Make the archilume_app package importable without installing it.
# This runs once at collection time instead of per-file sys.path hacks.
_ui_root = str(Path(__file__).parent.parent)
if _ui_root not in sys.path:
    sys.path.insert(0, _ui_root)
