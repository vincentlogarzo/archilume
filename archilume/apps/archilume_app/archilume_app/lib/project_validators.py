"""Per-file content validators used by Create/Settings project modals.

Each validator returns ``(ok: bool, message: str)`` and is a thin wrapper over
existing archilume utilities. The goal is to catch malformed uploads before they
land in the canonical project directories, so a user can't accidentally create a
project with a broken HDR, the wrong xlsx schema, or an empty rdp.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Tuple

ValidationResult = Tuple[bool, str]


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def validate_pdf(path: Path) -> ValidationResult:
    """PDF must open with PyMuPDF and report at least one page."""
    try:
        from .image_loader import get_pdf_page_count
        count = get_pdf_page_count(path)
    except Exception as e:
        return False, f"Could not open PDF: {e}"
    if count <= 0:
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
    try:
        import pandas as pd
    except ImportError:
        return False, "pandas not available"

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
# Geometry (.obj)
# ---------------------------------------------------------------------------

def validate_obj(path: Path) -> ValidationResult:
    """Minimal OBJ validity — must contain vertices or faces.

    We don't block on missing ``.mtl`` siblings because users may supply them in
    a follow-up upload; that's surfaced as a warning at create time.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                stripped = line.lstrip()
                if (
                    stripped.startswith("v ")
                    or stripped.startswith("f ")
                    or stripped.startswith("vn ")
                    or stripped.startswith("vt ")
                ):
                    return True, ""
    except OSError as e:
        return False, f"Could not read obj: {e}"
    return False, "No OBJ vertex/face lines found"


def validate_mtl(path: Path) -> ValidationResult:
    """Minimal MTL validity — must declare at least one ``newmtl`` material."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        return False, f"Could not read mtl: {e}"
    if "newmtl " not in text:
        return False, "No 'newmtl' declarations found"
    return True, ""


# ---------------------------------------------------------------------------
# AOI
# ---------------------------------------------------------------------------

def validate_aoi(path: Path) -> ValidationResult:
    """AOI file must have the 5-line header plus ≥3 parseable coordinate rows.

    Format (see archilume/core/view_generator.py ``create_aoi_files``):
        Line 1: "AOI Points File: ..."
        Line 2: "ASSOCIATED VIEW FILE: ..."
        Line 3: "FFL z height(m): ..."
        Line 4: "CENTRAL x,y: ..."
        Line 5: "NO. PERIMETER POINTS N: ..."
        Lines 6+: "x y [pixel_x pixel_y]"
    """
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError as e:
        return False, f"Could not read aoi: {e}"
    if len(lines) < 8:
        return False, f"Too few lines ({len(lines)}); expected header + ≥3 points"
    if not lines[0].lstrip().startswith("AOI Points File"):
        return False, "Missing 'AOI Points File' header"
    coord_rows = 0
    for line in lines[5:]:
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
