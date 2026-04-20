"""Tests for sunlight view-group parser in image_loader."""

from pathlib import Path

from archilume_app.lib.image_loader import (
    _extract_view_name,
    scan_sunlight_view_groups,
)


def _touch(path: Path, content: bytes = b"") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content or b"#?RADIANCE\n\n-Y 1 +X 1\n")


def test_extract_view_name_strips_longest_matching_sky():
    stem = "527DP_level1_Jun_21_10-00"
    sky_stems = ["Jun_21_10-00", "Jun_21", "Dec_21_12-00"]
    assert _extract_view_name(stem, sky_stems) == ("527DP_level1", "Jun_21_10-00")


def test_extract_view_name_falls_back_when_no_match():
    stem = "unknown_image"
    assert _extract_view_name(stem, ["Jun_21_10-00"]) == ("unknown_image", "")


def test_sunlight_grouping_multi_view_multi_sky(tmp_path: Path):
    image_dir = tmp_path / "outputs" / "image"
    sky_stems = ["Jun_21_10-00", "Jun_21_10-30"]

    # Two views × two timesteps = four HDRs
    for view in ("level1", "level2"):
        for sky in sky_stems:
            _touch(image_dir / f"527DP_{view}_{sky}.hdr")

    groups = scan_sunlight_view_groups(image_dir, sky_stems)
    assert len(groups) == 2
    assert {g["view_name"] for g in groups} == {"level1", "level2"}
    for g in groups:
        assert len(g["frames"]) == 2
        # Frames sorted by sky name (lexical)
        sky_names = [f["sky_name"] for f in g["frames"]]
        assert sky_names == sorted(sky_names)


def test_sunlight_grouping_single_timestep_per_view(tmp_path: Path):
    """Simulation with only one timestep — each view is a single-frame group."""
    image_dir = tmp_path / "outputs" / "image"
    sky_stems = ["Jun_21_12-00"]

    for view in ("livingroom", "kitchen"):
        _touch(image_dir / f"527DP_{view}_Jun_21_12-00.hdr")

    groups = scan_sunlight_view_groups(image_dir, sky_stems)
    assert len(groups) == 2
    for g in groups:
        assert len(g["frames"]) == 1
        assert g["frames"][0]["sky_name"] == "Jun_21_12-00"


def test_sunlight_grouping_no_sky_dir_fallback(tmp_path: Path):
    """Markup-only project with no sky files falls back to per-HDR groups."""
    image_dir = tmp_path / "outputs" / "image"
    _touch(image_dir / "room_a.hdr")
    _touch(image_dir / "room_b.hdr")

    groups = scan_sunlight_view_groups(image_dir, [])
    assert len(groups) == 2
    assert {g["view_name"] for g in groups} == {"room_a", "room_b"}
    for g in groups:
        assert len(g["frames"]) == 1


def test_sunlight_grouping_strips_common_prefix(tmp_path: Path):
    """Common ``{octree_base}_`` prefix is stripped from the displayed view_name."""
    image_dir = tmp_path / "outputs" / "image"
    sky_stems = ["t1"]

    _touch(image_dir / "526_block_A_level1_t1.hdr")
    _touch(image_dir / "526_block_A_level2_t1.hdr")

    groups = scan_sunlight_view_groups(image_dir, sky_stems)
    names = {g["view_name"] for g in groups}
    assert names == {"level1", "level2"}


def test_sunlight_grouping_keeps_ffl_qualifier_on_digit_tail(tmp_path: Path):
    """When the only distinguishing token is digits-only (e.g. FFL in mm),
    the prior qualifier token rides along so labels read ``ffl_090000``
    instead of a bare ``090000``."""
    image_dir = tmp_path / "outputs" / "image"
    sky_stems = ["SS_0621_0900", "SS_0621_0915"]
    for ffl in ("090000", "093260", "103180"):
        for sky in sky_stems:
            _touch(image_dir / f"87Cowles_BLD_with_plan_ffl_{ffl}_{sky}.hdr")

    groups = scan_sunlight_view_groups(image_dir, sky_stems)
    names = sorted(g["view_name"] for g in groups)
    assert names == ["ffl_090000", "ffl_093260", "ffl_103180"]
    # Full prefix is exposed for the tooltip
    for g in groups:
        assert g["view_prefix"].endswith(g["view_name"])


def test_sunlight_grouping_empty_dir_returns_empty(tmp_path: Path):
    assert scan_sunlight_view_groups(tmp_path / "nope", ["Jun_21"]) == []
    empty_dir = tmp_path / "outputs" / "image"
    empty_dir.mkdir(parents=True)
    assert scan_sunlight_view_groups(empty_dir, ["Jun_21"]) == []
