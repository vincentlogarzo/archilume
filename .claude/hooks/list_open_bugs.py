"""SessionStart hook — surface active bug trackers across sessions.

Reads ``.claude/bugs/open/*.md`` and prints one line per bug. Silent when no
bugs are open. Cross-platform (Windows + Linux + macOS) — uses pathlib and
self-locates the project root from the script's filesystem position.

Invoke via: ``python .claude/hooks/list_open_bugs.py``
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Hook lives at <repo_root>/.claude/hooks/list_open_bugs.py
REPO_ROOT = Path(__file__).resolve().parents[2]
BUGS_DIR = REPO_ROOT / ".claude" / "bugs" / "open"

_FRONT_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_FIELD_RE = re.compile(r"^([a-z_]+):\s*(.+?)\s*$", re.MULTILINE)
_TITLE_RE = re.compile(r"^# (.+?)\s*$", re.MULTILINE)


def _parse(md_text: str) -> tuple[str, dict[str, str]]:
    """Return (title, frontmatter_fields) from a bug markdown file."""
    fm_match = _FRONT_RE.search(md_text)
    fields: dict[str, str] = {}
    if fm_match:
        for key, val in _FIELD_RE.findall(fm_match.group(1)):
            fields[key] = val
    title_match = _TITLE_RE.search(md_text)
    title = title_match.group(1) if title_match else "(untitled)"
    return title, fields


def main() -> int:
    if not BUGS_DIR.is_dir():
        return 0
    files = sorted(BUGS_DIR.glob("*.md"))
    if not files:
        return 0
    print(f"[OPEN BUGS] {len(files)} active in .claude/bugs/open/:")
    for f in files:
        try:
            title, fields = _parse(f.read_text(encoding="utf-8"))
        except OSError:
            continue
        status = fields.get("status", "?")
        sev = fields.get("severity", "?")
        tags = fields.get("tags", "[]")
        print(f"  - {f.stem}: {title} [status={status}, sev={sev}] tags={tags}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
