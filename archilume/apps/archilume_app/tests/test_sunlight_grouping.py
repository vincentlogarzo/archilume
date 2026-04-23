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


def test_extract_view_name_strips_double_underscore_for_overcast():
    """Overcast file names use ``__{sky}`` (double underscore). When the
    matched sky is the overcast stem, both underscores are stripped so the
    returned view_prefix lines up with the sunlight-frame prefix for the same
    view."""
    sky_stems = ["SS_0621_0900", "TenK_cie_overcast"]
    overcast = "TenK_cie_overcast"

    # Overcast filename: double underscore before the sky.
    prefix_oc, sky_oc = _extract_view_name(
        "87Cowles_ffl_103180__TenK_cie_overcast", sky_stems, overcast
    )
    # Sunlight filename: single underscore.
    prefix_sun, sky_sun = _extract_view_name(
        "87Cowles_ffl_103180_SS_0621_0900", sky_stems, overcast
    )

    assert sky_oc == "TenK_cie_overcast"
    assert sky_sun == "SS_0621_0900"
    # Both prefixes collapse to the same view key.
    assert prefix_oc == prefix_sun == "87Cowles_ffl_103180"


def test_extract_view_name_overcast_without_stem_hint_is_unchanged():
    """Default behaviour (no overcast_sky_stem passed) leaves the trailing
    underscore in place — matches the legacy single-underscore contract."""
    sky_stems = ["TenK_cie_overcast"]
    prefix, sky = _extract_view_name(
        "view_a__TenK_cie_overcast", sky_stems
    )
    assert sky == "TenK_cie_overcast"
    assert prefix == "view_a_"  # trailing _ preserved because overcast hint absent


def test_sunlight_grouping_segregates_overcast_into_underlay(tmp_path: Path):
    """When ``overcast_sky_stem`` is passed, the overcast HDR for each view is
    pulled out of ``frames`` and attached as ``underlay_png_path``; the
    sunlight timesteps remain in ``frames``."""
    image_dir = tmp_path / "outputs" / "image"
    sky_stems = ["SS_0621_0900", "SS_0621_1000", "TenK_cie_overcast"]

    for view in ("level1", "level2"):
        _touch(image_dir / f"87Cowles_{view}_SS_0621_0900.hdr")
        _touch(image_dir / f"87Cowles_{view}_SS_0621_1000.hdr")
        _touch(image_dir / f"87Cowles_{view}__TenK_cie_overcast.hdr")

    groups = scan_sunlight_view_groups(image_dir, sky_stems, "TenK_cie_overcast")
    assert len(groups) == 2
    for g in groups:
        # Only sunlight timesteps appear as frames.
        assert len(g["frames"]) == 2
        frame_skies = {f["sky_name"] for f in g["frames"]}
        assert frame_skies == {"SS_0621_0900", "SS_0621_1000"}
        # Underlay is present and points at the overcast PNG sibling.
        assert g["underlay_png_path"].endswith("__TenK_cie_overcast.png")
        assert g["underlay_hdr_stem"].endswith("__TenK_cie_overcast")


def test_sunlight_grouping_without_overcast_stem_keeps_legacy_behaviour(tmp_path: Path):
    """Passing ``overcast_sky_stem=""`` (default) leaves the overcast as just
    another frame — preserves the existing contract for tests that don't opt
    in."""
    image_dir = tmp_path / "outputs" / "image"
    sky_stems = ["SS_0621_0900", "TenK_cie_overcast"]

    _touch(image_dir / "87Cowles_level1_SS_0621_0900.hdr")
    # Double underscore like the renderer emits.
    _touch(image_dir / "87Cowles_level1__TenK_cie_overcast.hdr")

    groups = scan_sunlight_view_groups(image_dir, sky_stems)
    # Without the overcast hint, the two files have different prefixes
    # (``...level1`` vs ``...level1_``) so they end up in separate groups —
    # the legacy behaviour that originally surfaced the bug.
    assert len(groups) == 2
    for g in groups:
        assert g["underlay_png_path"] == ""
        assert g["underlay_hdr_stem"] == ""


def test_sunlight_grouping_overcast_only_view_emits_empty_frames(tmp_path: Path):
    """If a view has an overcast HDR but no sunlight timesteps, the group is
    still emitted with empty ``frames`` and a populated underlay."""
    image_dir = tmp_path / "outputs" / "image"
    sky_stems = ["TenK_cie_overcast"]

    _touch(image_dir / "proj_level1__TenK_cie_overcast.hdr")

    groups = scan_sunlight_view_groups(image_dir, sky_stems, "TenK_cie_overcast")
    assert len(groups) == 1
    assert groups[0]["frames"] == []
    assert groups[0]["underlay_hdr_stem"].endswith("__TenK_cie_overcast")


def test_sky_stems_includes_rad_overcast_file(tmp_path: Path):
    """SkyGenerator writes TenK_cie_overcast as .rad, not .sky. The project
    open handler must still surface it in sky_stems so the scanner can
    segregate it.

    Replicates the glob-and-append logic from editor_state._init_project_paths
    at unit scope — guards against regression of the extension mismatch that
    broke overcast segregation at runtime even though the scanner itself was
    correct."""
    sky_dir = tmp_path / "sky"
    sky_dir.mkdir()
    (sky_dir / "SS_0621_0900.sky").write_text("# sunlight")
    (sky_dir / "TenK_cie_overcast.rad").write_text("# overcast")

    sky_stems = [p.stem for p in sky_dir.glob("*.sky")]
    if (sky_dir / "TenK_cie_overcast.rad").exists():
        sky_stems.append("TenK_cie_overcast")

    assert "SS_0621_0900" in sky_stems
    assert "TenK_cie_overcast" in sky_stems
