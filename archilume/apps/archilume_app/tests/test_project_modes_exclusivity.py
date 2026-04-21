"""Tests for project_modes.invalid_combinations — sunlight CSV-vs-AOI XOR."""

from __future__ import annotations

import pytest

from archilume_app.lib import project_modes as pm


def _ok(name: str) -> dict:
    return {"path": f"/tmp/{name}", "name": name, "ok": True, "error": ""}


def _bad(name: str) -> dict:
    return {"path": f"/tmp/{name}", "name": name, "ok": False, "error": "nope"}


class TestInvalidCombinationsSunlight:
    def test_neither_is_ok(self):
        assert pm.invalid_combinations("sunlight", {}) == []

    def test_csv_only_is_ok(self):
        staged = {"room_data": [_ok("room_boundaries.csv")]}
        assert pm.invalid_combinations("sunlight", staged) == []

    def test_aoi_only_is_ok(self):
        staged = {"aoi_files": [_ok("U101_T.aoi")]}
        assert pm.invalid_combinations("sunlight", staged) == []

    def test_both_staged_rejected(self):
        staged = {
            "room_data": [_ok("room_boundaries.csv")],
            "aoi_files": [_ok("U101_T.aoi")],
        }
        errs = pm.invalid_combinations("sunlight", staged)
        assert len(errs) == 1
        assert "room_boundaries.csv" in errs[0]
        assert ".aoi" in errs[0]

    def test_invalid_entries_do_not_count(self):
        staged = {
            "room_data": [_bad("room_boundaries.csv")],
            "aoi_files": [_ok("U101_T.aoi")],
        }
        # CSV is invalid so not "staged" in the field_ok sense → no conflict.
        assert pm.invalid_combinations("sunlight", staged) == []


class TestInvalidCombinationsDaylight:
    def test_daylight_ignores_csv_and_aoi(self):
        staged = {
            "room_data": [_ok("iesve_room_data.xlsx")],
            "aoi_files": [_ok("U101_T.aoi")],
        }
        assert pm.invalid_combinations("daylight", staged) == []
