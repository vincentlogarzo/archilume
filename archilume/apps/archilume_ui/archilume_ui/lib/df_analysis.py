"""Daylight Factor (DF%) analysis — compute per-room stats from HDR images."""

import math
from pathlib import Path
from typing import Optional

import numpy as np

# DF% thresholds by room type
DF_THRESHOLDS = {
    "BED": 0.5,
    "LIVING": 1.0,
    "NON-RESI": 2.0,
    "CIRC": None,  # No threshold
}


def compute_room_df(
    df_image: np.ndarray,
    vertices: list[list[float]],
    room_type: str = "BED",
    image_width: int = 0,
    image_height: int = 0,
) -> Optional[dict]:
    """Compute DF% statistics for a room polygon on a DF image.

    Args:
        df_image: 2D array (H, W) of DF% values.
        vertices: Room polygon vertices in pixel coords.
        room_type: Room type for threshold lookup.
        image_width: Image width (for bounds checking).
        image_height: Image height (for bounds checking).

    Returns dict with: mean_df, median_df, pct_above, threshold, pass_status, result_lines
    """
    if df_image is None or len(vertices) < 3:
        return None

    h, w = df_image.shape[:2]
    if image_width <= 0:
        image_width = w
    if image_height <= 0:
        image_height = h

    # Create polygon mask
    mask = _polygon_mask(vertices, w, h)
    if not np.any(mask):
        return None

    values = df_image[mask]
    if values.size == 0:
        return None

    mean_df = float(np.mean(values))
    median_df = float(np.median(values))

    threshold = DF_THRESHOLDS.get(room_type)
    if threshold is not None:
        above = float(np.sum(values >= threshold)) / values.size * 100.0
        if above >= 100.0:
            status = "pass"
        elif above >= 50.0:
            status = "marginal"
        else:
            status = "fail"
    else:
        above = 0.0
        status = "none"

    result_lines = [f"DF avg: {mean_df:.2f}%"]
    if threshold is not None:
        result_lines.append(f"Above {threshold}%: {above:.0f}%")

    return {
        "mean_df": mean_df,
        "median_df": median_df,
        "pct_above": above,
        "threshold": threshold,
        "pass_status": status,
        "result_lines": result_lines,
    }


def _polygon_mask(
    vertices: list[list[float]], width: int, height: int
) -> np.ndarray:
    """Create a boolean mask for pixels inside a polygon."""
    from .geometry import point_in_polygon

    mask = np.zeros((height, width), dtype=bool)

    # Bounding box for efficiency
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    min_x = max(0, int(math.floor(min(xs))))
    max_x = min(width - 1, int(math.ceil(max(xs))))
    min_y = max(0, int(math.floor(min(ys))))
    max_y = min(height - 1, int(math.ceil(max(ys))))

    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            if point_in_polygon(float(x), float(y), vertices):
                mask[y, x] = True

    return mask


def load_df_image(hdr_path: Path) -> Optional[np.ndarray]:
    """Load an HDR file and extract DF% values.

    Returns 2D array (H, W) of DF percentages, or None.
    """
    try:
        from .image_loader import _load_hdr, _read_hdr_dimensions

        w, h = _read_hdr_dimensions(hdr_path)
        if w <= 0 or h <= 0:
            return None

        # Load raw (non-tonemapped) HDR
        arr = _load_hdr_raw(hdr_path)
        if arr is None:
            return None

        # Convert luminance to DF%
        # Luminance from RGB: Y = 0.2126R + 0.7152G + 0.0722B
        luminance = 0.2126 * arr[:, :, 0] + 0.7152 * arr[:, :, 1] + 0.0722 * arr[:, :, 2]

        # DF% = (interior illuminance / exterior illuminance) * 100
        # For daylight factor images, the values are already in DF% representation
        # (illuminance values where exterior = 100 lux reference)
        return luminance
    except Exception:
        return None


def _load_hdr_raw(path: Path) -> Optional[np.ndarray]:
    """Load HDR file as raw float32 values (no tone-mapping)."""
    try:
        from .image_loader import _load_hdr_manual, _load_hdr_pvalue, _read_hdr_dimensions
        import subprocess

        # Try pvalue first for raw extraction
        try:
            from archilume import config
            pvalue = config.RADIANCE_BIN_PATH / "pvalue"
            if pvalue.exists() or pvalue.with_suffix(".exe").exists():
                result = subprocess.run(
                    [str(pvalue), "-h", "-H", "-df", str(path)],
                    capture_output=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    w, h = _read_hdr_dimensions(path)
                    data = np.frombuffer(result.stdout, dtype=np.float32)
                    expected = h * w * 3
                    if data.size >= expected:
                        return data[:expected].reshape(h, w, 3)
        except ImportError:
            pass

        # Fallback to manual RGBE parser (returns non-tonemapped)
        return _load_hdr_manual_raw(path)
    except Exception:
        return None


def _load_hdr_manual_raw(path: Path) -> Optional[np.ndarray]:
    """Load HDR manually without tone-mapping."""
    from .image_loader import _read_hdr_scanline

    try:
        with open(path, "rb") as f:
            while True:
                line = f.readline()
                if not line or line.strip() == b"":
                    break
            res_line = f.readline().decode("ascii", errors="replace").strip()
            parts = res_line.split()
            if len(parts) != 4:
                return None
            height = int(parts[1])
            width = int(parts[3])
            if width <= 0 or height <= 0:
                return None

            img = np.zeros((height, width, 3), dtype=np.float32)
            for y in range(height):
                scanline = _read_hdr_scanline(f, width)
                if scanline is None:
                    return None
                img[y] = scanline
        return img
    except Exception:
        return None


def read_df_at_pixel(
    df_image: np.ndarray, x: float, y: float
) -> Optional[float]:
    """Read DF% value at a specific pixel position."""
    if df_image is None:
        return None
    h, w = df_image.shape[:2]
    ix = int(round(x))
    iy = int(round(y))
    if 0 <= ix < w and 0 <= iy < h:
        return float(df_image[iy, ix])
    return None
