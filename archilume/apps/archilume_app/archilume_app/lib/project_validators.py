"""Per-file content validators used by Create/Settings project modals.

Each validator returns ``(ok: bool, message: str)`` and is a thin wrapper over
existing archilume utilities. The goal is to catch malformed uploads before they
land in the canonical project directories, so a user can't accidentally create a
project with a broken HDR, the wrong xlsx schema, or an empty rdp.
"""

from __future__ import annotations

import logging
import math
import re
from pathlib import Path
from typing import Callable, Tuple

import pandas as pd

ValidationResult = Tuple[bool, str]

# Radiance works in metres. Reject obvious unit mismatches — models under 1 m
# across are almost certainly unit-scaled incorrectly, models over 10 km are
# almost certainly exported in millimetres or a similar sub-metre unit.
_MIN_BBOX_DIAGONAL_M = 1.0
_MAX_BBOX_DIAGONAL_M = 10_000.0


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

ENCRYPTED_PDF_MESSAGE = (
    "This PDF is encrypted or password-protected. "
    "Please unlock the PDF before attaching it."
)


def validate_pdf(path: Path) -> ValidationResult:
    """PDF must open with PyMuPDF, be unencrypted, and report at least one page.

    Encryption is detected without unlocking — pdf.js cannot render password-
    protected PDFs and the underlay would silently fail to draw, so we reject
    upstream with an explicit user-facing message.
    """
    try:
        from .image_loader import get_pdf_info
        info = get_pdf_info(path)
    except Exception as e:
        return False, f"Could not open PDF: {e}"
    if info.is_encrypted:
        return False, ENCRYPTED_PDF_MESSAGE
    if info.page_count <= 0:
        return False, "PDF has no pages"
    return True, ""


# ---------------------------------------------------------------------------
# HDR / PIC (Radiance)
# ---------------------------------------------------------------------------

def validate_hdr(path: Path) -> ValidationResult:
    """Radiance HDR/PIC must expose a parseable ``-Y <h> +X <w>`` resolution line."""
    try:
        from archilume.utils import get_hdr_resolution
        w, h = get_hdr_resolution(path)
    except FileNotFoundError:
        return False, "File not found"
    except ValueError as e:
        return False, f"Invalid Radiance header: {e}"
    except Exception as e:
        return False, f"Could not read HDR: {e}"
    if w <= 0 or h <= 0:
        return False, f"Invalid resolution {w}x{h}"
    return True, ""


# Alias — .pic files use the same Radiance container format as .hdr.
validate_pic = validate_hdr


# ---------------------------------------------------------------------------
# Room data (iesve_room_data.xlsx OR room_boundaries.csv)
# ---------------------------------------------------------------------------

_IESVE_COLUMNS = ("Space ID", "Space Name (Real)", "Min. Height (m) (Real)")


def validate_room_data(path: Path) -> ValidationResult:
    """Accept either IESVE xlsx (with known columns) or a room_boundaries csv.

    IESVE xlsx is detected by ``.xlsx`` extension; anything else is treated as a
    room_boundaries csv and must be readable with ``pandas`` and have at least
    one row.
    """
    suffix = path.suffix.lower()

    if suffix == ".xlsx":
        try:
            df = pd.read_excel(path)
        except Exception as e:
            return False, f"Could not read xlsx: {e}"
        missing = [c for c in _IESVE_COLUMNS if c not in df.columns]
        if missing:
            return False, f"Missing IESVE columns: {', '.join(missing)}"
        if df.empty:
            return False, "IESVE room data has no rows"
        return True, ""

    if suffix == ".csv":
        try:
            df = pd.read_csv(path)
        except Exception as e:
            return False, f"Could not read csv: {e}"
        if df.empty:
            return False, "Room boundaries csv has no rows"
        return True, ""

    return False, f"Unsupported room-data extension: {suffix}"


def validate_sunlight_room_csv(path: Path) -> ValidationResult:
    """Strict validator for the sunlight ``room_boundaries.csv`` schema.

    Accepts only ``.csv`` with the three required columns (``Room Name``,
    ``z_FFL(m)``, ``Vertex Coordinates (X:Y)``) and at least one parseable row.
    Parse errors from :func:`sunlight_csv.parse_room_boundaries_csv` are
    surfaced verbatim so the user can correct the file.
    """
    if path.suffix.lower() != ".csv":
        return False, f"Sunlight room data must be a .csv (got {path.suffix})"
    from .sunlight_csv import SunlightCsvError, parse_room_boundaries_csv
    try:
        rooms = parse_room_boundaries_csv(path)
    except SunlightCsvError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Could not parse room_boundaries.csv: {e}"
    if not rooms:
        return False, "room_boundaries.csv has no rows"
    return True, ""


# ---------------------------------------------------------------------------
# Octree (.oct)
# ---------------------------------------------------------------------------

def validate_oct(path: Path) -> ValidationResult:
    """Basic sanity check — file exists, non-zero size, appears binary.

    Radiance octree format has no stable magic bytes we can check against, so
    this validator only rules out obviously-wrong uploads (empty files,
    text-encoded junk).
    """
    try:
        size = path.stat().st_size
    except OSError as e:
        return False, f"Could not stat file: {e}"
    if size <= 0:
        return False, "File is empty"
    # Read a small prefix — if it decodes cleanly as UTF-8 text, it's almost
    # certainly not an octree (which is binary).
    try:
        with open(path, "rb") as f:
            head = f.read(256)
    except OSError as e:
        return False, f"Could not read file: {e}"
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        return True, ""  # Binary — good sign for an octree
    return False, "File looks like text, not a binary octree"


# ---------------------------------------------------------------------------
# Render params (.rdp)
# ---------------------------------------------------------------------------

_KNOWN_RDP_FLAGS = (
    "-ab", "-aa", "-ar", "-ad", "-as", "-ps", "-pt", "-pj", "-dj", "-lw",
    "-dc", "-dp", "-dr", "-ds", "-dt", "-lr", "-ss", "-st",
)


def validate_rdp(path: Path) -> ValidationResult:
    """Non-empty text file containing at least one known Radiance render flag."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        return False, f"Could not read rdp: {e}"
    if not text.strip():
        return False, "rdp is empty"
    if not any(flag in text for flag in _KNOWN_RDP_FLAGS):
        return False, "No recognised Radiance flags found"
    return True, ""


# ---------------------------------------------------------------------------
# Geometry (.obj / .mtl)
# ---------------------------------------------------------------------------

# Regex for a well-formed MTL material declaration: ``newmtl <name>`` with any
# run of whitespace (space, tab) between the directive and the material name,
# and a non-empty name token. Anchored to line start to reject matches inside
# comments like ``# newmtl foo``.
_NEWMTL_RE = re.compile(r"(?m)^\s*newmtl\s+\S+")


def _parse_obj_with_pywavefront(path: Path):
    """Parse ``path`` with pywavefront in tolerant mode, suppressing its noisy
    per-line warnings. Returns the ``Wavefront`` scene, or raises whatever
    pywavefront raised (caller wraps into ``ValidationResult``).
    """
    import pywavefront

    # pywavefront logs one warning per unsupported directive (``g``, ``s``, …).
    # Real Revit/Blender exports are dense with these and the console floods;
    # the validator only cares whether parsing succeeded.
    prior_level = pywavefront.logger.level
    pywavefront.logger.setLevel(logging.ERROR)
    try:
        return pywavefront.Wavefront(
            str(path),
            strict=False,
            create_materials=True,
            collect_faces=True,
        )
    finally:
        pywavefront.logger.setLevel(prior_level)


def _bbox_diagonal(vertices) -> float:
    """Euclidean diagonal of the axis-aligned bbox over ``vertices``.

    ``vertices`` is pywavefront's ``scene.vertices`` — a list of ``(x, y, z)``
    tuples. Returns ``0.0`` for an empty list rather than raising.
    """
    if not vertices:
        return 0.0
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    zs = [v[2] for v in vertices]
    return math.sqrt(
        (max(xs) - min(xs)) ** 2
        + (max(ys) - min(ys)) ** 2
        + (max(zs) - min(zs)) ** 2
    )


def validate_obj(path: Path) -> ValidationResult:
    """Structural + unit-of-measure validation of a Wavefront ``.obj`` file.

    Parses the file with :mod:`pywavefront` in tolerant mode, then:

    1. Requires at least one face — a vertices-only export (normals/UVs only)
       produces an empty octree downstream.
    2. Checks the axis-aligned bbox diagonal against a metres-based sanity
       range (1 m ≤ d ≤ 10 km) so SketchUp-inches or Revit-millimetres
       exports fail fast instead of silently producing wrong sun angles.
    """
    try:
        from pywavefront import PywavefrontException
    except ImportError as e:
        return False, f"pywavefront not installed: {e}"

    try:
        scene = _parse_obj_with_pywavefront(path)
    except FileNotFoundError:
        return False, "File not found"
    except PywavefrontException as e:
        return False, f"OBJ parse failed: {e}"
    except Exception as e:
        return False, f"Could not read obj: {e}"

    face_count = sum(len(m.faces) for m in scene.mesh_list)
    if face_count == 0:
        return False, (
            "OBJ has no faces. Archilume needs triangulated faces to build an "
            "octree — re-export with 'Triangulate faces' enabled."
        )

    diagonal = _bbox_diagonal(scene.vertices)
    if diagonal < _MIN_BBOX_DIAGONAL_M:
        return False, (
            f"Model is only {diagonal:.3f} m across. Units look wrong — "
            "archilume expects metres. Re-export in metres."
        )
    if diagonal > _MAX_BBOX_DIAGONAL_M:
        return False, (
            f"Model is {diagonal:.0f} m across (> 10 km). Units look wrong "
            "(likely millimetres). Re-export in metres."
        )
    return True, ""


def validate_mtl(path: Path) -> ValidationResult:
    """Accept any ``.mtl`` with ≥1 ``newmtl <name>`` declaration, regardless
    of the whitespace (space / tab) between directive and name."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        return False, f"Could not read mtl: {e}"
    if not _NEWMTL_RE.search(text):
        return False, (
            "MTL file has no 'newmtl <name>' material definitions. "
            "Export materials alongside the .obj."
        )
    return True, ""


def validate_geometry_pair(
    obj_path: Path, mtl_path: Path | None
) -> ValidationResult:
    """Confirm that an uploaded ``.obj`` has a stem-matched ``.mtl`` sibling.

    Returns ``(False, msg)`` when ``mtl_path`` is missing or has a different
    stem — downstream ``Objs2Octree`` resolves MTL paths via
    ``obj_path.with_suffix('.mtl')`` so a mismatched stem causes every
    material to default to grey plastic.
    """
    if mtl_path is None:
        return False, (
            f"OBJ '{obj_path.name}' has no matching MTL. "
            f"Upload '{obj_path.stem}.mtl'."
        )
    if obj_path.stem != mtl_path.stem:
        return False, (
            f"OBJ '{obj_path.name}' and MTL '{mtl_path.name}' have different "
            f"stems. Rename the MTL to '{obj_path.stem}.mtl'."
        )
    return True, ""


# ---------------------------------------------------------------------------
# AOI
# ---------------------------------------------------------------------------

def validate_aoi(path: Path) -> ValidationResult:
    """AOI file must carry an ``AOI Points File`` header, an ``FFL z height(m)``
    line, a ``POINTS`` / ``NO. PERIMETER POINTS`` data-start sentinel, and ≥3
    parseable coordinate rows below it.

    Accepts both v2 minimal format::

        AoI Points File : X,Y positions
        FFL z height(m): 93.260
        POINTS 13
        <x y rows>

    and legacy v1 format with PARENT/CHILD/CENTRAL header lines.
    """
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError as e:
        return False, f"Could not read aoi: {e}"

    has_header = any(l.lstrip().lower().startswith("aoi points file") for l in lines[:2])
    if not has_header:
        return False, "Missing 'AOI Points File' header"

    ffl_ok = any(l.strip().startswith("FFL z height(m):") for l in lines)
    if not ffl_ok:
        return False, "Missing 'FFL z height(m)' line"

    vertex_start: int | None = None
    for i, line in enumerate(lines):
        upper = line.strip().upper()
        if upper.startswith("POINTS ") or upper.startswith("NO. PERIMETER POINTS"):
            vertex_start = i + 1
            break
    if vertex_start is None:
        return False, "Missing 'POINTS' / 'NO. PERIMETER POINTS' header"

    coord_rows = 0
    for line in lines[vertex_start:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            float(parts[0]); float(parts[1])
            coord_rows += 1
        except ValueError:
            continue
    if coord_rows < 3:
        return False, f"Only {coord_rows} valid coordinate rows; need ≥3"
    return True, ""


# ---------------------------------------------------------------------------
# Public lookup
# ---------------------------------------------------------------------------

VALIDATORS: dict[str, Callable[[Path], ValidationResult]] = {
    "pdf":       validate_pdf,
    "hdr":       validate_hdr,
    "pic":       validate_pic,
    "room_data": validate_room_data,
    "oct":       validate_oct,
    "rdp":       validate_rdp,
    "obj":       validate_obj,
    "mtl":       validate_mtl,
    "aoi":       validate_aoi,
}
