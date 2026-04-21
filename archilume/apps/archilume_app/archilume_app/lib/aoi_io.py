"""v2 ``.aoi`` file writer/mover/remover.

Single source of truth for the minimal v2 ``.aoi`` format used by
``aoi_inputs_dir``:

    AoI Points File : X,Y positions
    FFL z height(m): <ffl_m>
    POINTS <N>
    <x1> <y1>
    <x2> <y2>
    ...

The header regex that :meth:`EditorState._seed_rooms_from_modern_aoi`
matches is ``^AO?I Points File\\s*:`` so the leading ``AoI`` spelling is
mandatory. Vertex rows are world metres, one pair per line.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

_SANITIZE_DROP = re.compile(r"[^\w\s-]")
_SANITIZE_GAPS = re.compile(r"[-\s]+")


def sanitize_stem(name: str) -> str:
    """Return a filesystem-safe ``.aoi`` filestem derived from a room name.

    Mirrors the convention used by ``ViewGenerator.create_aoi_files`` at
    ``core/view_generator.py:401-402`` so filenames produced here are
    interchangeable with pipeline outputs.
    """
    cleaned = _SANITIZE_DROP.sub("", str(name)).strip()
    cleaned = _SANITIZE_GAPS.sub("_", cleaned)
    return cleaned or "room"


def aoi_path(dest_dir: Path, name: str) -> Path:
    """Resolve the absolute ``.aoi`` path for a room name."""
    return dest_dir / f"{sanitize_stem(name)}.aoi"


def write_v2_aoi(
    dest_dir: Path,
    name: str,
    ffl_m: float,
    world_vertices: Sequence[tuple[float, float]],
) -> Path:
    """Write a v2 ``.aoi`` file for ``name`` into ``dest_dir``.

    Overwrites any existing file atomically. Returns the written path.
    Raises ``ValueError`` if fewer than three vertices are supplied.
    """
    verts = [(float(x), float(y)) for x, y in world_vertices]
    if len(verts) < 3:
        raise ValueError(
            f"v2 .aoi requires at least 3 vertices, got {len(verts)} for {name!r}"
        )
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = aoi_path(dest_dir, name)

    lines = [
        "AoI Points File : X,Y positions",
        f"FFL z height(m): {float(ffl_m):.4f}",
        f"POINTS {len(verts)}",
    ]
    lines.extend(f"{x:.4f} {y:.4f}" for x, y in verts)
    content = "\n".join(lines) + "\n"

    tmp = target.with_suffix(".aoi.tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(target)
    return target


def delete_aoi(dest_dir: Path, name: str) -> bool:
    """Delete the ``.aoi`` for ``name`` if it exists.

    Returns True if a file was removed, False if none was present.
    Missing files are a no-op — callers may invoke this defensively.
    """
    target = aoi_path(dest_dir, name)
    if not target.exists():
        return False
    target.unlink()
    return True


def rename_aoi(dest_dir: Path, old_name: str, new_name: str) -> bool:
    """Rename the ``.aoi`` for ``old_name`` to ``new_name``.

    Returns True on success, False if the source file is absent.
    Overwrites any existing file at the destination.
    """
    src = aoi_path(dest_dir, old_name)
    dst = aoi_path(dest_dir, new_name)
    if src == dst:
        return src.exists()
    if not src.exists():
        return False
    src.replace(dst)
    return True
