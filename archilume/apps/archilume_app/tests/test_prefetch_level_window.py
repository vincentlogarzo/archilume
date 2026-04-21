"""Tests for the +/-1 adjacent-level PNG prefetch target selection.

``_select_level_prefetch_targets`` is the pure helper that
``EditorState.prefetch_level_window`` delegates to under its state lock.
Exercising the helper directly avoids spinning up a Reflex event loop while
still covering every branch that decides which Paths get warmed into the
image LRU.
"""

from __future__ import annotations

from pathlib import Path

from archilume_app.state.editor_state import _select_level_prefetch_targets


def _sunlight_group(view_name: str) -> dict:
    return {
        "view_name": view_name,
        "view_prefix": f"octree_{view_name}",
        "frames": [
            {
                "hdr_path": f"/tmp/{view_name}_t0.hdr",
                "png_path": f"/tmp/{view_name}_t0.png",
                "sky_name": "t0",
                "hdr_stem": f"{view_name}_t0",
                "frame_label": "t0",
            }
        ],
    }


def _hdr_info(name: str, *, variants: list[str] | None = None) -> dict:
    return {
        "name": name,
        "hdr_path": f"/tmp/{name}.hdr",
        "tiff_paths": variants or [],
        "legend_map": {},
    }


# ---------------------------------------------------------------------------
# Sunlight mode
# ---------------------------------------------------------------------------


def test_sunlight_middle_view_picks_both_neighbours() -> None:
    groups = [_sunlight_group("L1"), _sunlight_group("L2"), _sunlight_group("L3")]
    targets = _select_level_prefetch_targets(
        project_mode="sunlight",
        view_groups=groups,
        current_view_idx=1,
        hdr_files=[],
        current_hdr_idx=0,
        current_variant_idx=0,
    )
    assert targets == [Path("/tmp/L1_t0.png"), Path("/tmp/L3_t0.png")]


def test_sunlight_first_view_picks_only_forward() -> None:
    groups = [_sunlight_group("L1"), _sunlight_group("L2"), _sunlight_group("L3")]
    targets = _select_level_prefetch_targets(
        project_mode="sunlight",
        view_groups=groups,
        current_view_idx=0,
        hdr_files=[],
        current_hdr_idx=0,
        current_variant_idx=0,
    )
    assert targets == [Path("/tmp/L2_t0.png")]


def test_sunlight_last_view_picks_only_backward() -> None:
    groups = [_sunlight_group("L1"), _sunlight_group("L2"), _sunlight_group("L3")]
    targets = _select_level_prefetch_targets(
        project_mode="sunlight",
        view_groups=groups,
        current_view_idx=2,
        hdr_files=[],
        current_hdr_idx=0,
        current_variant_idx=0,
    )
    assert targets == [Path("/tmp/L2_t0.png")]


def test_sunlight_single_view_returns_empty() -> None:
    groups = [_sunlight_group("L1")]
    targets = _select_level_prefetch_targets(
        project_mode="sunlight",
        view_groups=groups,
        current_view_idx=0,
        hdr_files=[],
        current_hdr_idx=0,
        current_variant_idx=0,
    )
    assert targets == []


def test_sunlight_no_view_groups_returns_empty() -> None:
    targets = _select_level_prefetch_targets(
        project_mode="sunlight",
        view_groups=[],
        current_view_idx=0,
        hdr_files=[],
        current_hdr_idx=0,
        current_variant_idx=0,
    )
    assert targets == []


def test_sunlight_skips_neighbour_with_empty_frames() -> None:
    groups = [
        _sunlight_group("L1"),
        {"view_name": "L2", "view_prefix": "octree_L2", "frames": []},
        _sunlight_group("L3"),
    ]
    targets = _select_level_prefetch_targets(
        project_mode="sunlight",
        view_groups=groups,
        current_view_idx=0,
        hdr_files=[],
        current_hdr_idx=0,
        current_variant_idx=0,
    )
    assert targets == []


# ---------------------------------------------------------------------------
# Daylight mode
# ---------------------------------------------------------------------------


def test_daylight_middle_hdr_picks_variant_from_each_neighbour() -> None:
    hdr_files = [
        _hdr_info("h1", variants=["/tmp/h1_df.tiff", "/tmp/h1_cntr.tiff"]),
        _hdr_info("h2", variants=["/tmp/h2_df.tiff", "/tmp/h2_cntr.tiff"]),
        _hdr_info("h3", variants=["/tmp/h3_df.tiff", "/tmp/h3_cntr.tiff"]),
    ]
    targets = _select_level_prefetch_targets(
        project_mode="daylight",
        view_groups=[],
        current_view_idx=0,
        hdr_files=hdr_files,
        current_hdr_idx=1,
        current_variant_idx=1,
    )
    assert targets == [Path("/tmp/h1_cntr.tiff"), Path("/tmp/h3_cntr.tiff")]


def test_daylight_variant_idx_clamps_to_neighbour_variants() -> None:
    hdr_files = [
        _hdr_info("h1", variants=["/tmp/h1_df.tiff"]),
        _hdr_info("h2", variants=["/tmp/h2_df.tiff", "/tmp/h2_cntr.tiff"]),
        _hdr_info("h3", variants=["/tmp/h3_df.tiff"]),
    ]
    # current_variant_idx=1 exists for h2 but not for h1/h3 — clamp to 0.
    targets = _select_level_prefetch_targets(
        project_mode="daylight",
        view_groups=[],
        current_view_idx=0,
        hdr_files=hdr_files,
        current_hdr_idx=1,
        current_variant_idx=1,
    )
    assert targets == [Path("/tmp/h1_df.tiff"), Path("/tmp/h3_df.tiff")]


def test_daylight_falls_back_to_hdr_when_no_variants() -> None:
    hdr_files = [_hdr_info("h1"), _hdr_info("h2"), _hdr_info("h3")]
    targets = _select_level_prefetch_targets(
        project_mode="daylight",
        view_groups=[],
        current_view_idx=0,
        hdr_files=hdr_files,
        current_hdr_idx=1,
        current_variant_idx=0,
    )
    assert targets == [Path("/tmp/h1.hdr"), Path("/tmp/h3.hdr")]


def test_daylight_first_hdr_picks_only_forward() -> None:
    hdr_files = [_hdr_info("h1"), _hdr_info("h2"), _hdr_info("h3")]
    targets = _select_level_prefetch_targets(
        project_mode="daylight",
        view_groups=[],
        current_view_idx=0,
        hdr_files=hdr_files,
        current_hdr_idx=0,
        current_variant_idx=0,
    )
    assert targets == [Path("/tmp/h2.hdr")]


def test_daylight_last_hdr_picks_only_backward() -> None:
    hdr_files = [_hdr_info("h1"), _hdr_info("h2"), _hdr_info("h3")]
    targets = _select_level_prefetch_targets(
        project_mode="daylight",
        view_groups=[],
        current_view_idx=0,
        hdr_files=hdr_files,
        current_hdr_idx=2,
        current_variant_idx=0,
    )
    assert targets == [Path("/tmp/h2.hdr")]


def test_daylight_empty_hdr_files_returns_empty() -> None:
    targets = _select_level_prefetch_targets(
        project_mode="daylight",
        view_groups=[],
        current_view_idx=0,
        hdr_files=[],
        current_hdr_idx=0,
        current_variant_idx=0,
    )
    assert targets == []


def test_current_level_never_in_target_list() -> None:
    """Primary contract: never warm the level the user is already on."""
    groups = [_sunlight_group("L1"), _sunlight_group("L2"), _sunlight_group("L3")]
    targets = _select_level_prefetch_targets(
        project_mode="sunlight",
        view_groups=groups,
        current_view_idx=1,
        hdr_files=[],
        current_hdr_idx=0,
        current_variant_idx=0,
    )
    assert Path("/tmp/L2_t0.png") not in targets
