"""Tests for archilume_app.lib.session_io — session persistence.

All tests use tmp_path (pytest fixture) — no permanent files created.
Regression strategy: when a serialisation or load bug is found, add a test here.
"""

import json
from pathlib import Path

import pytest

from archilume_app.lib.session_io import (
    _prepare_for_json,
    build_session_dict,
    load_session,
    save_session,
)

# ===========================================================================
# _prepare_for_json
# ===========================================================================

class TestPrepareForJson:
    def test_tuple_becomes_list(self):
        result = _prepare_for_json((1, 2, 3))
        assert result == [1, 2, 3]
        assert isinstance(result, list)

    def test_nested_tuple_in_dict(self):
        result = _prepare_for_json({"key": (1.0, 2.0)})
        assert result["key"] == [1.0, 2.0]

    def test_path_becomes_string(self):
        p = Path("/some/path/to/file.json")
        result = _prepare_for_json(p)
        assert isinstance(result, str)
        assert "file.json" in result

    def test_nested_path_in_list(self):
        result = _prepare_for_json([Path("/a"), Path("/b")])
        assert all(isinstance(r, str) for r in result)

    def test_primitives_unchanged(self):
        assert _prepare_for_json(42) == 42
        assert _prepare_for_json(3.14) == 3.14
        assert _prepare_for_json("hello") == "hello"
        assert _prepare_for_json(True) is True
        assert _prepare_for_json(None) is None

    def test_list_preserved(self):
        result = _prepare_for_json([1, 2, 3])
        assert result == [1, 2, 3]

    def test_deeply_nested(self):
        data = {"rooms": [{"vertices": [(1, 2), (3, 4)], "path": Path("/x")}]}
        result = _prepare_for_json(data)
        assert result["rooms"][0]["vertices"] == [[1, 2], [3, 4]]
        assert isinstance(result["rooms"][0]["path"], str)

    def test_empty_dict(self):
        assert _prepare_for_json({}) == {}

    def test_empty_list(self):
        assert _prepare_for_json([]) == []

    def test_mixed_nested_types(self):
        """Tuple inside list inside dict with Path — all converted."""
        data = {"stamps": [((1, 2), Path("/img.hdr"))]}
        result = _prepare_for_json(data)
        assert result["stamps"][0][0] == [1, 2]
        assert isinstance(result["stamps"][0][1], str)
        assert "img.hdr" in result["stamps"][0][1]

    def test_result_is_json_serializable(self):
        data = {
            "rooms": [{"vertices": [(1, 2)], "path": Path("/x")}],
            "stamps": ((10, 20),),
        }
        result = _prepare_for_json(data)
        # Must not raise
        json.dumps(result)


# ===========================================================================
# build_session_dict
# ===========================================================================

class TestBuildSessionDict:
    def test_returns_dict_with_all_keys(self):
        d = build_session_dict(rooms=[], df_stamps={}, overlay_transforms={})
        expected_keys = {
            "rooms", "df_stamps", "overlay_transforms", "transform_version",
            "current_hdr_idx", "current_variant_idx", "selected_parent",
            "annotation_scale", "overlay_dpi", "overlay_visible",
            "overlay_alpha", "overlay_page_idx",
            "overlay_img_width", "overlay_img_height",
            "falsecolour_settings", "contour_settings", "last_generated",
        }
        assert expected_keys == set(d.keys())

    def test_defaults_are_sane(self):
        d = build_session_dict(rooms=[], df_stamps={}, overlay_transforms={})
        assert d["current_hdr_idx"] == 0
        assert d["current_variant_idx"] == 0
        assert d["selected_parent"] == ""
        assert d["annotation_scale"] == 1.0
        assert d["overlay_dpi"] == 200
        assert d["overlay_visible"] is False
        assert d["overlay_alpha"] == 0.6
        assert d["overlay_page_idx"] == 0
        assert d["transform_version"] == 5

    def test_custom_values_preserved(self):
        d = build_session_dict(
            rooms=[{"name": "Kitchen"}],
            df_stamps={"img.hdr": [(1, 2)]},
            overlay_transforms={"img.hdr": {"x": 10}},
            current_hdr_idx=3,
            overlay_dpi=300,
            overlay_visible=True,
            overlay_alpha=0.8,
        )
        assert d["rooms"] == [{"name": "Kitchen"}]
        assert d["current_hdr_idx"] == 3
        assert d["overlay_dpi"] == 300
        assert d["overlay_visible"] is True
        assert d["overlay_alpha"] == 0.8

    def test_output_is_json_serializable(self):
        """build_session_dict output should survive json.dumps via _prepare_for_json."""
        d = build_session_dict(
            rooms=[{"name": "R", "vertices": [[0.0, 0.0]]}],
            df_stamps={"a.hdr": [(1, 2)]},
            overlay_transforms={},
        )
        serialized = _prepare_for_json(d)
        json.dumps(serialized)  # must not raise


# ===========================================================================
# save_session / load_session — round-trip
# ===========================================================================

class TestSaveLoadRoundTrip:
    def test_round_trip_basic(self, tmp_path: Path):
        path = tmp_path / "aoi_session.json"
        data = build_session_dict(
            rooms=[{"name": "Living", "vertices": [[0, 0], [100, 0], [100, 80], [0, 80]]}],
            df_stamps={},
            overlay_transforms={},
        )
        assert save_session(path, data) is True
        loaded = load_session(path)
        assert loaded is not None
        assert loaded["rooms"][0]["name"] == "Living"

    def test_round_trip_tuples_in_df_stamps(self, tmp_path: Path):
        """Tuples in df_stamps must round-trip to tuples (load normalises them)."""
        path = tmp_path / "session.json"
        data = build_session_dict(
            rooms=[],
            df_stamps={"img.hdr": [(10, 20), (30, 40)]},
            overlay_transforms={},
        )
        save_session(path, data)
        loaded = load_session(path)
        assert loaded is not None
        stamps = loaded["df_stamps"]["img.hdr"]
        assert stamps == [(10, 20), (30, 40)]
        assert all(isinstance(s, tuple) for s in stamps)

    def test_round_trip_empty_df_stamps_list(self, tmp_path: Path):
        """Empty stamp list for an HDR should survive round-trip."""
        path = tmp_path / "session.json"
        data = build_session_dict(rooms=[], df_stamps={"img.hdr": []}, overlay_transforms={})
        save_session(path, data)
        loaded = load_session(path)
        assert loaded is not None
        assert loaded["df_stamps"]["img.hdr"] == []

    def test_file_is_valid_json(self, tmp_path: Path):
        path = tmp_path / "session.json"
        data = build_session_dict(rooms=[], df_stamps={}, overlay_transforms={})
        save_session(path, data)
        raw = path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_save_returns_false_on_unwritable_path(self, tmp_path: Path):
        # Use a file as a parent component — mkdir will fail (file exists, not a dir).
        blocker = tmp_path / "blocker"
        blocker.write_text("x")
        bad_path = blocker / "session.json"
        result = save_session(bad_path, {})
        assert result is False

    def test_load_returns_none_for_missing_file(self, tmp_path: Path):
        assert load_session(tmp_path / "ghost.json") is None

    def test_load_returns_none_for_corrupt_json(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("{ not valid json }", encoding="utf-8")
        assert load_session(path) is None

    def test_load_returns_none_for_empty_file(self, tmp_path: Path):
        path = tmp_path / "empty.json"
        path.write_text("", encoding="utf-8")
        assert load_session(path) is None

    def test_atomic_write_does_not_leave_tmp_file(self, tmp_path: Path):
        path = tmp_path / "session.json"
        data = build_session_dict(rooms=[], df_stamps={}, overlay_transforms={})
        save_session(path, data)
        assert not path.with_suffix(".json.tmp").exists()

    def test_overwrite_existing_session(self, tmp_path: Path):
        path = tmp_path / "session.json"
        save_session(path, build_session_dict(rooms=[], df_stamps={}, overlay_transforms={}, current_hdr_idx=0))
        save_session(path, build_session_dict(rooms=[], df_stamps={}, overlay_transforms={}, current_hdr_idx=5))
        loaded = load_session(path)
        assert loaded is not None
        assert loaded["current_hdr_idx"] == 5

    def test_large_session_round_trips(self, tmp_path: Path):
        """Regression: large room lists must not truncate."""
        rooms = [
            {"name": f"Room_{i}", "vertices": [[i, 0], [i + 1, 0], [i + 1, 1], [i, 1]]}
            for i in range(200)
        ]
        path = tmp_path / "session.json"
        data = build_session_dict(rooms=rooms, df_stamps={}, overlay_transforms={})
        save_session(path, data)
        loaded = load_session(path)
        assert loaded is not None
        assert len(loaded["rooms"]) == 200
        assert loaded["rooms"][199]["name"] == "Room_199"

    def test_save_non_serializable_uses_str_fallback(self, tmp_path: Path):
        """The default=str fallback in json.dump should handle odd types."""
        path = tmp_path / "session.json"
        data = {"key": Path("/some/path")}
        assert save_session(path, data) is True
        loaded = load_session(path)
        assert loaded is not None
        assert "path" in loaded["key"]
