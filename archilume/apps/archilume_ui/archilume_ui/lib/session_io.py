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


def build_session_dict(
    rooms: list[dict],
    df_stamps: dict,
    overlay_transforms: dict,
    current_hdr_idx: int = 0,
    current_variant_idx: int = 0,
    selected_parent: str = "",
    annotation_scale: float = 1.0,
    overlay_dpi: int = 150,
    overlay_visible: bool = False,
    overlay_alpha: float = 0.6,
    overlay_pdf_path: str = "",
    overlay_page_idx: int = 0,
    transform_version: int = 4,
    overlay_img_width: int = 0,
    overlay_img_height: int = 0,
) -> dict[str, Any]:
    """Build a session dict ready for saving."""
    return {
        "rooms": rooms,
        "df_stamps": df_stamps,
        "overlay_transforms": overlay_transforms,
        "transform_version": transform_version,
        "current_hdr_idx": current_hdr_idx,
        "current_variant_idx": current_variant_idx,
        "selected_parent": selected_parent,
        "annotation_scale": annotation_scale,
        "overlay_dpi": overlay_dpi,
        "overlay_visible": overlay_visible,
        "overlay_alpha": overlay_alpha,
        "overlay_pdf_path": overlay_pdf_path,
        "overlay_page_idx": overlay_page_idx,
        "overlay_img_width": overlay_img_width,
        "overlay_img_height": overlay_img_height,
    }
