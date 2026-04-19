"""Tests for archilume_app.lib.project_modes — the two-mode taxonomy.

The current model exposes only two workflow modes (``sunlight`` and
``daylight``). Every field inside a mode is optional: a project can be
created with just a name + mode, and inputs are added later via the
Project Settings modal or by dropping files directly into the project
directories.
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
        assert ids == ["pdf", "geometry", "hdr_results", "room_data", "aoi_files"]

    def test_daylight_fields(self):
        ids = [f.id for f in pm.MODES["daylight"].fields]
        assert ids == ["pdf", "oct", "rdp", "pic_results", "aoi_files", "room_data"]

    @pytest.mark.parametrize("mode_id", pm.MODE_IDS)
    def test_no_field_is_required(self, mode_id: str):
        """Fields are always optional — the user decides what to supply."""
        for f in pm.MODES[mode_id].fields:
            assert f.required is False, f"{mode_id}.{f.id} is marked required"

    @pytest.mark.parametrize("mode_id", pm.MODE_IDS)
    def test_no_one_of_groups(self, mode_id: str):
        """With everything optional there is no need for mutual substitution."""
        for f in pm.MODES[mode_id].fields:
            assert f.one_of is None, f"{mode_id}.{f.id} still has one_of={f.one_of}"


# ---------------------------------------------------------------------------
# missing_required / one-of logic
# ---------------------------------------------------------------------------

class TestMissingRequired:
    """With nothing marked required, the helper always returns an empty list."""

    def _ok(self, name: str = "any.bin") -> dict:
        return {"path": "/tmp/x", "name": name, "ok": True, "error": ""}

    @pytest.mark.parametrize("mode_id", pm.MODE_IDS)
    def test_empty_staging_reports_nothing_missing(self, mode_id: str):
        assert pm.missing_required(mode_id, {}) == []

    @pytest.mark.parametrize("mode_id", pm.MODE_IDS)
    def test_partial_staging_reports_nothing_missing(self, mode_id: str):
        staged = {"pdf": [self._ok("plan.pdf")]}
        assert pm.missing_required(mode_id, staged) == []

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
        assert pm.field_by_id("sunlight", "geometry") is not None
        assert pm.field_by_id("daylight", "geometry") is None

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
