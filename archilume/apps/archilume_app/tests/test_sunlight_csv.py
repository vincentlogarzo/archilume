"""Tests for archilume_app.lib.sunlight_csv — CSV parser + CSV→AOI converter."""

from __future__ import annotations

from pathlib import Path

import pytest

from archilume_app.lib import sunlight_csv as sc


_SAMPLE_HEADER = "Room Name, z_FFL(m), Vertex Coordinates (X:Y)"
_SAMPLE_ROW = "U101_T, 93.260, 0.0:0.0 10.0:0.0 10.0:5.0 0.0:5.0"


def _write_csv(path: Path, *rows: str) -> Path:
    path.write_text("\n".join([_SAMPLE_HEADER, *rows]) + "\n", encoding="utf-8")
    return path


class TestParseHappyPath:
    def test_single_row(self, tmp_path: Path):
        csv = _write_csv(tmp_path / "rooms.csv", _SAMPLE_ROW)
        rooms = sc.parse_room_boundaries_csv(csv)
        assert len(rooms) == 1
        r = rooms[0]
        assert r.name == "U101_T"
        assert r.ffl_m == pytest.approx(93.26)
        assert r.vertices == ((0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0))

    def test_multiple_rows(self, tmp_path: Path):
        csv = _write_csv(
            tmp_path / "rooms.csv",
            _SAMPLE_ROW,
            "U102_T, 93.260, 12.0:0.0 22.0:0.0 22.0:5.0 12.0:5.0",
        )
        rooms = sc.parse_room_boundaries_csv(csv)
        assert [r.name for r in rooms] == ["U101_T", "U102_T"]

    def test_case_insensitive_headers(self, tmp_path: Path):
        csv = tmp_path / "rooms.csv"
        csv.write_text(
            "ROOM NAME, Z_FFL(M), vertex coordinates (x:y)\n"
            + _SAMPLE_ROW + "\n",
            encoding="utf-8",
        )
        rooms = sc.parse_room_boundaries_csv(csv)
        assert rooms[0].name == "U101_T"


class TestParseUnhappyPath:
    def test_missing_columns(self, tmp_path: Path):
        csv = tmp_path / "rooms.csv"
        csv.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
        with pytest.raises(sc.SunlightCsvError, match="missing required column"):
            sc.parse_room_boundaries_csv(csv)

    def test_empty_file(self, tmp_path: Path):
        csv = tmp_path / "rooms.csv"
        csv.write_text(_SAMPLE_HEADER + "\n", encoding="utf-8")
        with pytest.raises(sc.SunlightCsvError, match="no data rows"):
            sc.parse_room_boundaries_csv(csv)

    def test_duplicate_names(self, tmp_path: Path):
        csv = _write_csv(tmp_path / "rooms.csv", _SAMPLE_ROW, _SAMPLE_ROW)
        with pytest.raises(sc.SunlightCsvError, match="duplicate Room Name"):
            sc.parse_room_boundaries_csv(csv)

    def test_fewer_than_three_vertices(self, tmp_path: Path):
        csv = _write_csv(tmp_path / "rooms.csv", "R1, 0.0, 0.0:0.0 1.0:0.0")
        with pytest.raises(sc.SunlightCsvError, match="at least 3 vertices"):
            sc.parse_room_boundaries_csv(csv)

    def test_malformed_vertex_token(self, tmp_path: Path):
        csv = _write_csv(tmp_path / "rooms.csv", "R1, 0.0, 0.0,0.0 1.0:0.0 1.0:1.0")
        with pytest.raises(sc.SunlightCsvError, match="missing ':'"):
            sc.parse_room_boundaries_csv(csv)

    def test_non_numeric_coord(self, tmp_path: Path):
        csv = _write_csv(tmp_path / "rooms.csv", "R1, 0.0, a:b c:d e:f")
        with pytest.raises(sc.SunlightCsvError):
            sc.parse_room_boundaries_csv(csv)

    def test_non_numeric_ffl(self, tmp_path: Path):
        csv = _write_csv(tmp_path / "rooms.csv", "R1, high, 0:0 1:0 1:1")
        with pytest.raises(sc.SunlightCsvError, match="z_FFL"):
            sc.parse_room_boundaries_csv(csv)


class TestConvertCsvToAoiFiles:
    def test_writes_one_aoi_per_row(self, tmp_path: Path):
        csv = _write_csv(
            tmp_path / "rooms.csv",
            _SAMPLE_ROW,
            "U102_T, 93.260, 12.0:0.0 22.0:0.0 22.0:5.0 12.0:5.0",
        )
        dest = tmp_path / "aoi"
        written = sc.convert_csv_to_aoi_files(csv, dest)
        assert len(written) == 2
        assert {p.name for p in written} == {"U101_T.aoi", "U102_T.aoi"}
        first = (dest / "U101_T.aoi").read_text(encoding="utf-8")
        assert first.startswith("AoI Points File : X,Y positions")
        assert "POINTS 4" in first

    def test_seeder_regex_matches_generated_output(self, tmp_path: Path):
        """The v2 header we emit must match the regex used by
        EditorState._seed_rooms_from_modern_aoi at editor_state.py:3546."""
        import re
        csv = _write_csv(tmp_path / "rooms.csv", _SAMPLE_ROW)
        dest = tmp_path / "aoi"
        written = sc.convert_csv_to_aoi_files(csv, dest)
        header = written[0].read_text(encoding="utf-8").splitlines()[0]
        assert re.match(r"AO?I Points File\s*:", header, re.IGNORECASE)

    def test_sanitized_filename(self, tmp_path: Path):
        csv = _write_csv(tmp_path / "rooms.csv", "3 BED, 0.0, 0:0 1:0 1:1")
        dest = tmp_path / "aoi"
        written = sc.convert_csv_to_aoi_files(csv, dest)
        assert written[0].name == "3_BED.aoi"
