"""Session persistence — load/save aoi_session.json."""

import json
import os
from pathlib import Path
from typing import Any, Optional


def load_session(session_path: Path) -> Optional[dict[str, Any]]:
    """Load session from JSON file.

    Returns session dict or None if file doesn't exist or is invalid.
    """
    if not session_path.exists():
        return None
    try:
        with open(session_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Normalize df_stamps: convert inner lists to tuples for consistency
        if "df_stamps" in data:
            for key, stamps in data["df_stamps"].items():
                data["df_stamps"][key] = [tuple(s) for s in stamps]
        return data
    except Exception:
        return None


def save_session(session_path: Path, data: dict[str, Any]) -> bool:
    """Save session to JSON file with atomic write.

    Returns True on success.
    """
    try:
        # Convert tuples to lists for JSON serialization
        serializable = _prepare_for_json(data)

        session_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = session_path.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, default=str)

        os.replace(str(tmp_path), str(session_path))
        return True
    except Exception:
        return False


def _prepare_for_json(obj: Any) -> Any:
    """Recursively convert tuples and Paths to JSON-serializable types."""
    if isinstance(obj, dict):
        return {k: _prepare_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_prepare_for_json(item) for item in obj]
    if isinstance(obj, Path):
        return str(obj)
    return obj


DEFAULT_FALSECOLOUR_SETTINGS = {"scale": 4.0, "n_levels": 10, "palette": "spec"}
DEFAULT_CONTOUR_SETTINGS     = {"scale": 2.0, "n_levels": 4}
DEFAULT_SUNLIGHT_SETTINGS    = {"exposure": -4.0}


def build_session_dict(
    rooms: list[dict],
    df_stamps: dict,
    overlay_transforms: dict,
    current_hdr_idx: int = 0,
    current_variant_idx: int = 0,
    selected_parent: str = "",
    annotation_scale: float = 1.0,
    overlay_visible: bool = False,
    overlay_alpha: float = 0.6,
    overlay_page_idx: int = 0,
    transform_version: int = 5,
    overlay_img_width: int = 0,
    overlay_img_height: int = 0,
    falsecolour_settings: Optional[dict] = None,
    contour_settings: Optional[dict] = None,
    sunlight_settings: Optional[dict] = None,
    last_generated: Optional[dict] = None,
) -> dict[str, Any]:
    """Build a session dict ready for saving.

    Note: ``overlay_img_width`` / ``overlay_img_height`` were once PNG pixel
    dimensions from the PyMuPDF rasterisation cache. After the pdf.js
    migration they hold the active PDF page's rect width/height in PDF
    points; only the aspect ratio is consumed downstream.
    """
    return {
        "rooms": rooms,
        "df_stamps": df_stamps,
        "overlay_transforms": overlay_transforms,
        "transform_version": transform_version,
        "current_hdr_idx": current_hdr_idx,
        "current_variant_idx": current_variant_idx,
        "selected_parent": selected_parent,
        "annotation_scale": annotation_scale,
        "overlay_visible": overlay_visible,
        "overlay_alpha": overlay_alpha,
        "overlay_page_idx": overlay_page_idx,
        "overlay_img_width": overlay_img_width,
        "overlay_img_height": overlay_img_height,
        "falsecolour_settings": falsecolour_settings or dict(DEFAULT_FALSECOLOUR_SETTINGS),
        "contour_settings":     contour_settings     or dict(DEFAULT_CONTOUR_SETTINGS),
        "sunlight_settings":    sunlight_settings    or dict(DEFAULT_SUNLIGHT_SETTINGS),
        "last_generated":       last_generated       or {},
    }
