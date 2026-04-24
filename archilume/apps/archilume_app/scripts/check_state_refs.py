"""Cross-reference EditorState attribute usages against definitions.

Scans component files for ``EditorState.X`` and ``S.X`` (local-alias) references
and reports names that are not defined as a state var, computed var, or event
handler in ``state/editor_state.py``. Catches the failure mode where a component
reaches for an attribute that was never added to the state class — the same bug
that surfaces at Reflex compile time as ``AttributeError: type object 'EditorState'
has no attribute '<name>'``.

Exit code: 0 when clean, 1 when at least one reference is missing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "archilume_app" / "components"
STATE_FILE = ROOT / "archilume_app" / "state" / "editor_state.py"


def _collect_refs() -> set[str]:
    refs: set[str] = set()
    pattern = re.compile(r"(?:EditorState|\bS)\.(\w+)")
    for file in COMPONENTS.rglob("*.py"):
        for match in pattern.finditer(file.read_text(encoding="utf-8")):
            refs.add(match.group(1))
    return refs


def _collect_defined() -> set[str]:
    text = STATE_FILE.read_text(encoding="utf-8")
    defined: set[str] = set()
    for match in re.finditer(r"^    ([a-zA-Z_][a-zA-Z_0-9]*)\s*:", text, re.M):
        defined.add(match.group(1))
    for match in re.finditer(r"^    (?:async\s+)?def ([a-zA-Z_][a-zA-Z_0-9]*)\(", text, re.M):
        defined.add(match.group(1))
    return defined


def main() -> int:
    refs = _collect_refs()
    defined = _collect_defined()
    missing = sorted(refs - defined)
    if missing:
        print("EditorState references with no matching definition:", file=sys.stderr)
        for name in missing:
            print(f"  - {name}", file=sys.stderr)
        print(
            "\nAdd these as state vars, computed vars (@rx.var), or event handlers "
            "in archilume_app/state/editor_state.py.",
            file=sys.stderr,
        )
        return 1
    print(f"OK — {len(refs)} EditorState references all resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
