"""Sunlight ``room_boundaries.csv`` parser + v2 ``.aoi`` generator.

Schema (three columns, one row per room)::

    Room Name, z_FFL(m), Vertex Coordinates (X:Y)
    U101_T,   93.260,    0.0:0.0 10.0:0.0 10.0:5.0 0.0:5.0

- ``Room Name`` becomes the ``.aoi`` filestem (sanitised).
- ``z_FFL(m)`` is a single floor-finish level height in metres.
- ``Vertex Coordinates (X:Y)`` packs vertices into one cell. Vertices are
  whitespace-separated; the ``X`` and ``Y`` components of each vertex are
  joined by ``:`` so the cell requires no CSV quoting.

Coordinates are in metres. The :meth:`EditorState._seed_rooms_from_modern_aoi`
seeder consumes the generated ``.aoi`` files exactly as if the user had
uploaded them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Tuple

import pandas as pd

from . import aoi_io


ROOM_NAME_COL = "room name"
FFL_COL = "z_ffl(m)"
VERTEX_COL = "vertex coordinates (x:y)"
REQUIRED_COLS = (ROOM_NAME_COL, FFL_COL, VERTEX_COL)


class SunlightCsvError(ValueError):
    """Raised when ``room_boundaries.csv`` cannot be parsed."""


@dataclass(frozen=True)
class RoomBoundary:
    name: str
    ffl_m: float
    vertices: Tuple[Tuple[float, float], ...]


def _normalize_columns(df: pd.DataFrame) -> dict[str, str]:
    """Map normalized column name -> actual column name in df.

    Normalisation is case-insensitive and trims whitespace.
    """
    return {str(c).strip().lower(): str(c) for c in df.columns}


def _parse_vertex_cell(cell: str, row_index: Any, room_name: str) -> Tuple[Tuple[float, float], ...]:
    if not isinstance(cell, str) or not cell.strip():
        raise SunlightCsvError(
            f"Row {row_index} ({room_name!r}): vertex cell is empty"
        )
    tokens = cell.split()
    vertices: list[tuple[float, float]] = []
    for tok in tokens:
        if ":" not in tok:
            raise SunlightCsvError(
                f"Row {row_index} ({room_name!r}): vertex token {tok!r} "
                "missing ':' separator — expected X:Y"
            )
        x_str, y_str = tok.split(":", 1)
        try:
            vertices.append((float(x_str), float(y_str)))
        except ValueError as e:
            raise SunlightCsvError(
                f"Row {row_index} ({room_name!r}): cannot parse vertex {tok!r}: {e}"
            ) from e
    if len(vertices) < 3:
        raise SunlightCsvError(
            f"Row {row_index} ({room_name!r}): need at least 3 vertices, got {len(vertices)}"
        )
    return tuple(vertices)


def parse_room_boundaries_csv(path: Path) -> list[RoomBoundary]:
    """Parse a sunlight ``room_boundaries.csv``.

    Raises :class:`SunlightCsvError` on any structural issue.
    """
    try:
        df = pd.read_csv(path, skipinitialspace=True)
    except Exception as e:
        raise SunlightCsvError(f"Could not read csv {path.name}: {e}") from e

    if df.empty:
        raise SunlightCsvError("room_boundaries.csv has no data rows")

    col_map = _normalize_columns(df)
    missing = [c for c in REQUIRED_COLS if c not in col_map]
    if missing:
        raise SunlightCsvError(
            "room_boundaries.csv missing required column(s): "
            + ", ".join(missing)
            + f". Found: {list(df.columns)}"
        )

    name_col = col_map[ROOM_NAME_COL]
    ffl_col = col_map[FFL_COL]
    vx_col = col_map[VERTEX_COL]

    rooms: list[RoomBoundary] = []
    seen: set[str] = set()
    for idx, row in df.iterrows():
        raw_name = row[name_col]
        if pd.isna(raw_name) or str(raw_name).strip() == "":
            raise SunlightCsvError(f"Row {idx}: empty Room Name")
        name = str(raw_name).strip()
        if name in seen:
            raise SunlightCsvError(f"Row {idx}: duplicate Room Name {name!r}")
        seen.add(name)

        try:
            ffl = float(row[ffl_col])
        except (TypeError, ValueError) as e:
            raise SunlightCsvError(
                f"Row {idx} ({name!r}): cannot parse z_FFL(m) = {row[ffl_col]!r}: {e}"
            ) from e

        vertices = _parse_vertex_cell(row[vx_col], idx, name)
        rooms.append(RoomBoundary(name=name, ffl_m=ffl, vertices=vertices))

    return rooms


def convert_csv_to_aoi_files(csv_path: Path, dest_dir: Path) -> list[Path]:
    """Parse ``csv_path`` and write one v2 ``.aoi`` per row into ``dest_dir``.

    Returns the list of written paths in CSV row order. Raises
    :class:`SunlightCsvError` if parsing fails before any files are written.
    """
    rooms = parse_room_boundaries_csv(csv_path)
    dest_dir.mkdir(parents=True, exist_ok=True)
    return [
        aoi_io.write_v2_aoi(dest_dir, r.name, r.ffl_m, r.vertices)
        for r in rooms
    ]
