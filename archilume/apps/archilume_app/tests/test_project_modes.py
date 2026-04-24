"""Tests for archilume_app.lib.project_modes — the two-mode taxonomy.

The current model exposes only two workflow modes (``sunlight`` and
``daylight``). Sunlight requires a building-geometry slot (the thing being
analysed); everything else — site geometry, HDR results, room data — is
optional. Daylight has no required fields today.
"""

from __future__ import annotations

import pytest

from archilume_app.lib import project_modes as pm


# ---------------------------------------------------------------------------
# Mode registry shape
# ---------------------------------------------------------------------------

class TestModeRegistry:
    def test_two_modes_present(self):
        assert set(pm.MODES.keys()) == {"sunlight", "daylight"}

    def test_default_mode_is_registered(self):
        assert pm.DEFAULT_MODE in pm.MODES

    def test_default_mode_is_sunlight(self):
        assert pm.DEFAULT_MODE == "sunlight"

    @pytest.mark.parametrize("mode_id", pm.MODE_IDS)
    def test_all_modes_have_pdf(self, mode_id: str):
        ids = [f.id for f in pm.MODES[mode_id].fields]
        assert "pdf" in ids, f"{mode_id} missing pdf"


class TestFieldShape:
    """Each mode exposes all plausible inputs as optional slots."""

    def test_sunlight_fields(self):
        ids = [f.id for f in pm.MODES["sunlight"].fields]
        assert ids == [
            "pdf",
            "geometry_building",
            "geometry_site",
            "hdr_results",
            "room_data",
            "aoi_files",
        ]

    def test_daylight_fields(self):
        ids = [f.id for f in pm.MODES["daylight"].fields]
        assert ids == ["pdf", "oct", "rdp", "pic_results", "aoi_files", "room_data"]

    def test_sunlight_building_is_required(self):
        """Building geometry is the single mandatory sunlight input."""
        f = pm.field_by_id("sunlight", "geometry_building")
        assert f is not None
        assert f.required is True

    def test_sunlight_site_is_optional(self):
        f = pm.field_by_id("sunlight", "geometry_site")
        assert f is not None
        assert f.required is False

    def test_daylight_fields_all_optional(self):
        """Daylight mode keeps the previous 'everything optional' shape."""
        for f in pm.MODES["daylight"].fields:
            assert f.required is False, f"daylight.{f.id} is unexpectedly required"

    @pytest.mark.parametrize("mode_id", pm.MODE_IDS)
    def test_no_one_of_groups(self, mode_id: str):
        """With everything optional there is no need for mutual substitution."""
        for f in pm.MODES[mode_id].fields:
            assert f.one_of is None, f"{mode_id}.{f.id} still has one_of={f.one_of}"


# ---------------------------------------------------------------------------
# missing_required / one-of logic
# ---------------------------------------------------------------------------

class TestMissingRequired:
    """Sunlight requires the building geometry slot; everything else is optional."""

    def _ok(self, name: str = "any.bin") -> dict:
        return {"path": "/tmp/x", "name": name, "ok": True, "error": ""}

    def test_sunlight_empty_reports_building_missing(self):
        missing = pm.missing_required("sunlight", {})
        assert missing == ["Building geometry (.obj + .mtl)"]

    def test_sunlight_building_staged_reports_nothing_missing(self):
        staged = {"geometry_building": [self._ok("bld.obj")]}
        assert pm.missing_required("sunlight", staged) == []

    def test_daylight_empty_reports_nothing_missing(self):
        assert pm.missing_required("daylight", {}) == []

    def test_daylight_partial_reports_nothing_missing(self):
        staged = {"pdf": [self._ok("plan.pdf")]}
        assert pm.missing_required("daylight", staged) == []

    @pytest.mark.parametrize("mode_id", pm.MODE_IDS)
    def test_no_one_of_groups_reported(self, mode_id: str):
        assert pm.mode_one_of_groups(mode_id) == {}


# ---------------------------------------------------------------------------
# Field lookup helpers
# ---------------------------------------------------------------------------

class TestFieldLookup:
    def test_field_by_id_present(self):
        f = pm.field_by_id("sunlight", "pdf")
        assert f is not None
        assert f.dest_attr == "plans_dir"

    def test_field_by_id_geometry_only_sunlight(self):
        assert pm.field_by_id("sunlight", "geometry_building") is not None
        assert pm.field_by_id("sunlight", "geometry_site") is not None
        assert pm.field_by_id("daylight", "geometry_building") is None
        assert pm.field_by_id("daylight", "geometry_site") is None

    def test_field_by_id_oct_only_daylight(self):
        assert pm.field_by_id("daylight", "oct") is not None
        assert pm.field_by_id("sunlight", "oct") is None

    def test_field_by_id_hdr_only_sunlight(self):
        assert pm.field_by_id("sunlight", "hdr_results") is not None
        assert pm.field_by_id("daylight", "hdr_results") is None

    def test_field_by_id_pic_only_daylight(self):
        assert pm.field_by_id("daylight", "pic_results") is not None
        assert pm.field_by_id("sunlight", "pic_results") is None

    def test_field_by_id_unknown_mode(self):
        assert pm.field_by_id("not-a-mode", "pdf") is None

    def test_aoi_files_dest_is_aoi_inputs(self):
        for mode_id in pm.MODE_IDS:
            f = pm.field_by_id(mode_id, "aoi_files")
            assert f is not None
            assert f.dest_attr == "aoi_inputs_dir"
