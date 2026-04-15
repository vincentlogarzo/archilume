"""One-shot migration of legacy project.toml files to the new mode taxonomy.

The archilume_app create-project flow used to write one of three mode strings
that are no longer valid:

    archilume   — generic HDR mode, synonym for ``hdr``
    hdr         — archilume-rendered or pre-rendered sunlight HDRs
    iesve       — IESVE-derived daylight with .pic images

The new taxonomy (see ``project_modes.py``) replaces these with four explicit
workflow modes:

    sunlight-sim       sunlight-markup
    daylight-sim       daylight-markup

Inference rules (applied only to projects carrying a legacy mode string):

* ``iesve``:
    - has ``.oct`` in ``outputs/octree/`` AND ``.rdp`` in ``inputs/``  → daylight-sim
    - otherwise                                                        → daylight-markup

* ``hdr`` / ``archilume``:
    - has ``.oct`` in ``outputs/octree/`` AND ``.rdp`` in ``inputs/``  → sunlight-sim
    - otherwise                                                        → sunlight-markup

Both paths favour the markup branch when the simulation-specific files are
absent because markup is non-destructive — it just reads existing results.

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


LEGACY_MODES = frozenset({"archilume", "hdr", "iesve"})
NEW_MODES = frozenset({"sunlight-sim", "sunlight-markup", "daylight-sim", "daylight-markup"})


def needs_migration(mode: str) -> bool:
    return mode in LEGACY_MODES


def infer_new_mode(legacy_mode: str, paths) -> str:
    """Map a legacy mode + on-disk state to a new mode id.

    ``paths`` is the :class:`archilume.config.ProjectPaths` for the project.
    """
    has_oct = paths.octree_dir.exists() and any(paths.octree_dir.glob("*.oct"))
    has_rdp = paths.inputs_dir.exists() and any(paths.inputs_dir.glob("*.rdp"))
    simulation = has_oct and has_rdp

    if legacy_mode == "iesve":
        return "daylight-sim" if simulation else "daylight-markup"
    # hdr / archilume
    return "sunlight-sim" if simulation else "sunlight-markup"


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
