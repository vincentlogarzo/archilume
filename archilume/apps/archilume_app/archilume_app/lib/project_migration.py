"""One-shot migration of legacy project.toml files to the new mode taxonomy.

Two historical mode generations are recognised and collapsed into the current
two-mode taxonomy:

* First-generation modes (free-text workflow tags)::

    archilume   — generic HDR mode, synonym for ``hdr``
    hdr         — archilume-rendered or pre-rendered sunlight HDRs
    iesve       — IESVE-derived daylight with .pic images

* Second-generation modes (four-way sim/markup split)::

    sunlight-sim       sunlight-markup
    daylight-sim       daylight-markup

The current taxonomy (see ``project_modes.py``) keeps only the physical
workflow choice::

    sunlight       daylight

Inference rules:

* ``iesve`` / ``daylight-sim`` / ``daylight-markup``  → ``daylight``
* ``archilume`` / ``hdr`` / ``sunlight-sim`` / ``sunlight-markup``
                                                       → ``sunlight``

The sim/markup flavour is no longer encoded in the mode — the editor picks
the appropriate image directory at runtime based on what is on disk.

The migration is idempotent: if ``mode`` is already in the new taxonomy, the
function is a no-op. A dead ``image_dir = ""`` key in ``[paths]`` is dropped
while rewriting.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover — fallback for 3.10
    import tomli as tomllib  # type: ignore


LEGACY_MODES = frozenset({
    # First-gen
    "archilume", "hdr", "iesve",
    # Second-gen (4-way sim/markup split)
    "sunlight-sim", "sunlight-markup",
    "daylight-sim", "daylight-markup",
})
NEW_MODES = frozenset({"sunlight", "daylight"})

_DAYLIGHT_LEGACY = frozenset({"iesve", "daylight-sim", "daylight-markup"})


def needs_migration(mode: str) -> bool:
    return mode in LEGACY_MODES


def infer_new_mode(legacy_mode: str, paths) -> str:
    """Map a legacy mode id to the current two-mode taxonomy.

    ``paths`` is accepted for backward compatibility with the previous
    signature but is no longer consulted — the sim/markup flavour is
    resolved at editor load time from on-disk state.
    """
    del paths  # retained for API stability
    if legacy_mode in _DAYLIGHT_LEGACY:
        return "daylight"
    # archilume / hdr / sunlight-sim / sunlight-markup
    return "sunlight"


def migrate_project_toml(project_name: str) -> Optional[str]:
    """Migrate a legacy project.toml in place. Returns the new mode id if the
    project was migrated, or None if no migration was needed / file missing.
    """
    try:
        from archilume.config import get_project_paths
    except ImportError:
        return None

    paths = get_project_paths(project_name)
    toml_path = paths.project_dir / "project.toml"
    if not toml_path.exists():
        return None

    try:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        logger.warning("migrate: could not parse %s: %s", toml_path, e)
        return None

    proj = data.get("project", {}) or {}
    current_mode = proj.get("mode", "")
    if current_mode in NEW_MODES:
        return None  # already migrated
    if not needs_migration(current_mode):
        logger.warning("migrate: %s has unknown mode %r — leaving untouched", toml_path, current_mode)
        return None

    new_mode = infer_new_mode(current_mode, paths)

    try:
        _rewrite_toml(toml_path, data, new_mode)
    except Exception as e:
        logger.warning("migrate: rewrite failed for %s: %s", toml_path, e)
        return None

    logger.info("migrated %s: %s -> %s", project_name, current_mode, new_mode)
    return new_mode


def _rewrite_toml(toml_path: Path, data: dict, new_mode: str) -> None:
    """Rewrite project.toml with the new mode, preserving other content and
    stripping the dead ``image_dir = ""`` key if present."""
    proj = dict(data.get("project", {}) or {})
    proj["mode"] = new_mode
    paths_section = dict(data.get("paths", {}) or {})
    # Drop the empty image_dir override — see the Create-Project discussion: this
    # key never carries a meaningful value in practice and confuses newcomers.
    if paths_section.get("image_dir", None) == "":
        paths_section.pop("image_dir", None)

    lines: list[str] = ["[project]"]
    name = proj.pop("name", toml_path.parent.name)
    lines.append(f'name = "{name}"')
    lines.append(f'mode = "{new_mode}"')
    for k, v in proj.items():
        if k == "mode":
            continue
        lines.append(_toml_assign(k, v))

    if paths_section:
        lines.append("")
        lines.append("[paths]")
        for k, v in paths_section.items():
            lines.append(_toml_assign(k, v))

    # Preserve any other top-level sections (defensive — current schema has none
    # beyond [project] and [paths] but future-proof it).
    for section, contents in data.items():
        if section in ("project", "paths"):
            continue
        if not isinstance(contents, dict):
            continue
        lines.append("")
        lines.append(f"[{section}]")
        for k, v in contents.items():
            lines.append(_toml_assign(k, v))

    toml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _toml_assign(key: str, value) -> str:
    """Render a single ``key = value`` line for toml. Handles str, int, bool,
    float, and list-of-strings — the types that project.toml actually uses."""
    if isinstance(value, bool):
        return f"{key} = {'true' if value else 'false'}"
    if isinstance(value, (int, float)):
        return f"{key} = {value}"
    if isinstance(value, list):
        rendered = ", ".join(_quote(str(v)) for v in value)
        return f"{key} = [{rendered}]"
    return f"{key} = {_quote(str(value))}"


def _quote(s: str) -> str:
    # Use basic double-quoted strings; escape embedded double quotes & backslashes.
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
