"""Tests for archilume_app.lib.project_modes — required-field graph for each
of the four workflow modes.
"""

from __future__ import annotations

import pytest

from archilume_app.lib import project_modes as pm


# ---------------------------------------------------------------------------
# Mode registry shape
# ---------------------------------------------------------------------------

class TestModeRegistry:
    def test_four_modes_present(self):
        assert set(pm.MODES.keys()) == {
            "sunlight-sim", "sunlight-markup",
            "daylight-sim", "daylight-markup",
        }

    def test_default_mode_is_registered(self):
        assert pm.DEFAULT_MODE in pm.MODES

    @pytest.mark.parametrize("mode_id", pm.MODE_IDS)
    def test_all_modes_have_pdf(self, mode_id: str):
        ids = [f.id for f in pm.MODES[mode_id].fields]
        assert "pdf" in ids, f"{mode_id} missing pdf"


class TestRequiredFieldShape:
    """Verify the table from the plan: each mode declares the right field set."""

    def test_sunlight_sim_required(self):
        ids = [f.id for f in pm.MODES["sunlight-sim"].fields]
        assert ids == ["pdf", "geometry", "room_data"]

    def test_sunlight_markup_required(self):
        ids = [f.id for f in pm.MODES["sunlight-markup"].fields]
        assert ids == ["pdf", "hdr_results", "room_data", "aoi_files"]

    def test_daylight_sim_required(self):
        ids = [f.id for f in pm.MODES["daylight-sim"].fields]
        assert ids == ["pdf", "oct", "rdp", "aoi_files"]

    def test_daylight_markup_required(self):
        ids = [f.id for f in pm.MODES["daylight-markup"].fields]
        assert ids == ["pdf", "pic_results", "aoi_files", "room_data"]


# ---------------------------------------------------------------------------
# missing_required logic
# ---------------------------------------------------------------------------

class TestMissingRequired:
    def _ok(self, name: str = "any.bin") -> dict:
        return {"path": "/tmp/x", "name": name, "ok": True, "error": ""}

    def _bad(self, name: str = "bad.bin") -> dict:
        return {"path": "/tmp/x", "name": name, "ok": False, "error": "fail"}

    def test_empty_staging_reports_all_required(self):
        missing = pm.missing_required("sunlight-sim", {})
        assert "PDF floor plan" in missing
        assert any("Geometry" in m for m in missing)
        assert any("room_boundaries" in m for m in missing)

    def test_satisfied_field_not_reported(self):
        staged = {"pdf": [self._ok("plan.pdf")]}
        missing = pm.missing_required("sunlight-sim", staged)
        assert "PDF floor plan" not in missing
        # Still missing geometry + room_data
        assert any("Geometry" in m for m in missing)

    def test_invalid_file_does_not_satisfy(self):
        staged = {"pdf": [self._bad("plan.pdf")]}
        missing = pm.missing_required("sunlight-sim", staged)
        assert "PDF floor plan" in missing

    def test_one_of_group_satisfied_by_room_data(self):
        """sunlight-markup accepts EITHER room csv OR aoi files."""
        staged = {
            "pdf":         [self._ok("plan.pdf")],
            "hdr_results": [self._ok("img.hdr")],
            "room_data":   [self._ok("rooms.csv")],
            # No aoi_files staged — but room_data satisfies the one_of group
        }
        missing = pm.missing_required("sunlight-markup", staged)
        assert missing == []

    def test_one_of_group_satisfied_by_aoi(self):
        staged = {
            "pdf":         [self._ok("plan.pdf")],
            "hdr_results": [self._ok("img.hdr")],
            "aoi_files":   [self._ok("a.aoi")],
            # No room_data — but aoi_files satisfies the one_of group
        }
        missing = pm.missing_required("sunlight-markup", staged)
        assert missing == []

    def test_one_of_group_unsatisfied(self):
        staged = {
            "pdf":         [self._ok("plan.pdf")],
            "hdr_results": [self._ok("img.hdr")],
            # Neither room_data nor aoi_files staged
        }
        missing = pm.missing_required("sunlight-markup", staged)
        assert any("room_boundaries" in m or ".aoi" in m for m in missing)

    def test_daylight_sim_complete(self):
        staged = {
            "pdf":       [self._ok("plan.pdf")],
            "oct":       [self._ok("scene.oct")],
            "rdp":       [self._ok("standard.rdp")],
            "aoi_files": [self._ok("a.aoi")],
        }
        missing = pm.missing_required("daylight-sim", staged)
        assert missing == []


# ---------------------------------------------------------------------------
# Field lookup helpers
# ---------------------------------------------------------------------------

class TestFieldLookup:
    def test_field_by_id_present(self):
        f = pm.field_by_id("sunlight-sim", "pdf")
        assert f is not None
        assert f.dest_attr == "plans_dir"

    def test_field_by_id_absent(self):
        # daylight-sim has no hdr_results field
        assert pm.field_by_id("daylight-sim", "hdr_results") is None

    def test_field_by_id_unknown_mode(self):
        assert pm.field_by_id("not-a-mode", "pdf") is None
