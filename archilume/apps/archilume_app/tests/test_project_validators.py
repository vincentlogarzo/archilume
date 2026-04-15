"""Tests for archilume_app.lib.project_validators — content validators used by
the Create New Project and Project Settings modals.

All tests use tmp_path; no permanent files created.
"""

from pathlib import Path

import pytest

from archilume_app.lib import project_validators as V


# ---------------------------------------------------------------------------
# HDR / PIC
# ---------------------------------------------------------------------------

class TestValidateHdr:
    def _write_minimal_hdr(self, path: Path, height: int = 64, width: int = 128) -> None:
        """Write a Radiance HDR with a parseable header. The pixel data is a
        single line of zeros — get_hdr_resolution only inspects the header."""
        header = b"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n"
        res = f"-Y {height} +X {width}\n".encode("ascii")
        body = b"\x00" * (width * 4)
        path.write_bytes(header + res + body)

    def test_valid_hdr(self, tmp_path: Path):
        p = tmp_path / "ok.hdr"
        self._write_minimal_hdr(p)
        ok, msg = V.validate_hdr(p)
        assert ok, msg

    def test_missing_resolution_line(self, tmp_path: Path):
        p = tmp_path / "bad.hdr"
        p.write_bytes(b"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n" + b"\x00" * 16)
        ok, msg = V.validate_hdr(p)
        assert not ok
        assert "header" in msg.lower() or "could not" in msg.lower()

    def test_pic_alias_uses_same_validator(self):
        assert V.validate_pic is V.validate_hdr


# ---------------------------------------------------------------------------
# RDP
# ---------------------------------------------------------------------------

class TestValidateRdp:
    def test_valid_rdp(self, tmp_path: Path):
        p = tmp_path / "ok.rdp"
        p.write_text("-ab 5 -aa 0.1 -ar 256 -ad 1024\n")
        ok, msg = V.validate_rdp(p)
        assert ok, msg

    def test_empty_rdp(self, tmp_path: Path):
        p = tmp_path / "empty.rdp"
        p.write_text("")
        ok, msg = V.validate_rdp(p)
        assert not ok
        assert "empty" in msg.lower()

    def test_no_known_flags(self, tmp_path: Path):
        p = tmp_path / "junk.rdp"
        p.write_text("hello world this is not rdp content\n")
        ok, msg = V.validate_rdp(p)
        assert not ok
        assert "flag" in msg.lower()


# ---------------------------------------------------------------------------
# OBJ / MTL
# ---------------------------------------------------------------------------

class TestValidateObj:
    def test_valid_obj_with_vertices(self, tmp_path: Path):
        p = tmp_path / "ok.obj"
        p.write_text("# blender export\nv 0.0 0.0 0.0\nv 1.0 0.0 0.0\n")
        ok, msg = V.validate_obj(p)
        assert ok, msg

    def test_valid_obj_with_faces(self, tmp_path: Path):
        p = tmp_path / "ok.obj"
        p.write_text("o cube\nf 1 2 3\n")
        ok, msg = V.validate_obj(p)
        assert ok, msg

    def test_obj_with_no_geometry(self, tmp_path: Path):
        p = tmp_path / "bad.obj"
        p.write_text("# only comments here\n# nothing else\n")
        ok, msg = V.validate_obj(p)
        assert not ok
        assert "vertex" in msg.lower() or "face" in msg.lower()


class TestValidateMtl:
    def test_valid_mtl(self, tmp_path: Path):
        p = tmp_path / "ok.mtl"
        p.write_text("newmtl plaster\nKa 1 1 1\n")
        ok, _ = V.validate_mtl(p)
        assert ok

    def test_mtl_no_newmtl(self, tmp_path: Path):
        p = tmp_path / "bad.mtl"
        p.write_text("# header only\n")
        ok, msg = V.validate_mtl(p)
        assert not ok
        assert "newmtl" in msg.lower()


# ---------------------------------------------------------------------------
# OCT
# ---------------------------------------------------------------------------

class TestValidateOct:
    def test_binary_file_passes(self, tmp_path: Path):
        p = tmp_path / "ok.oct"
        # Write some non-utf8 bytes so the validator's text-decode test fails
        # (that failure is the indicator of a binary file).
        p.write_bytes(b"\x00\x01\x02\xff\xfe\xfdsome more random binary data " * 10)
        ok, msg = V.validate_oct(p)
        assert ok, msg

    def test_empty_file(self, tmp_path: Path):
        p = tmp_path / "empty.oct"
        p.write_bytes(b"")
        ok, msg = V.validate_oct(p)
        assert not ok
        assert "empty" in msg.lower()

    def test_text_file_rejected(self, tmp_path: Path):
        p = tmp_path / "text.oct"
        p.write_text("this is plain text not an octree\n")
        ok, msg = V.validate_oct(p)
        assert not ok
        assert "text" in msg.lower()


# ---------------------------------------------------------------------------
# AOI
# ---------------------------------------------------------------------------

class TestValidateAoi:
    def _write_valid_aoi(self, path: Path) -> None:
        path.write_text(
            "AOI Points File: APT_Living\n"
            "ASSOCIATED VIEW FILE: living.vp\n"
            "FFL z height(m): 0.85\n"
            "CENTRAL x,y: 1.0 2.0\n"
            "NO. PERIMETER POINTS 4: x,y [pixel_x pixel_y]\n"
            "0.0 0.0 [10 20]\n"
            "1.0 0.0 [30 20]\n"
            "1.0 1.0 [30 40]\n"
            "0.0 1.0 [10 40]\n"
        )

    def test_valid_aoi(self, tmp_path: Path):
        p = tmp_path / "ok.aoi"
        self._write_valid_aoi(p)
        ok, msg = V.validate_aoi(p)
        assert ok, msg

    def test_too_few_lines(self, tmp_path: Path):
        p = tmp_path / "bad.aoi"
        p.write_text("AOI Points File: x\nASSOCIATED VIEW FILE: y\n")
        ok, msg = V.validate_aoi(p)
        assert not ok
        assert "too few" in msg.lower() or "missing" in msg.lower()

    def test_missing_header(self, tmp_path: Path):
        p = tmp_path / "bad.aoi"
        p.write_text(
            "Wrong header line\n"
            "ASSOCIATED VIEW FILE: y\n"
            "FFL z height(m): 0\n"
            "CENTRAL x,y: 0 0\n"
            "NO. PERIMETER POINTS 4: x,y\n"
            "0 0\n"
            "1 0\n"
            "1 1\n"
            "0 1\n"
        )
        ok, msg = V.validate_aoi(p)
        assert not ok


# ---------------------------------------------------------------------------
# Room data
# ---------------------------------------------------------------------------

class TestValidateRoomData:
    def test_csv_with_rows(self, tmp_path: Path):
        p = tmp_path / "rooms.csv"
        p.write_text("room_name,vertices\nLiving,\"[[0,0],[1,0],[1,1]]\"\n")
        ok, msg = V.validate_room_data(p)
        assert ok, msg

    def test_empty_csv(self, tmp_path: Path):
        p = tmp_path / "rooms.csv"
        p.write_text("room_name,vertices\n")
        ok, msg = V.validate_room_data(p)
        assert not ok
        assert "no rows" in msg.lower()

    def test_xlsx_missing_columns(self, tmp_path: Path):
        pytest.importorskip("openpyxl")
        import pandas as pd
        p = tmp_path / "rooms.xlsx"
        pd.DataFrame({"random": [1], "cols": [2]}).to_excel(p, index=False)
        ok, msg = V.validate_room_data(p)
        assert not ok
        assert "Space ID" in msg

    def test_xlsx_with_iesve_columns(self, tmp_path: Path):
        pytest.importorskip("openpyxl")
        import pandas as pd
        p = tmp_path / "rooms.xlsx"
        pd.DataFrame({
            "Space ID":            ["S001"],
            "Space Name (Real)":   ["Living"],
            "Min. Height (m) (Real)": [2.7],
        }).to_excel(p, index=False)
        ok, msg = V.validate_room_data(p)
        assert ok, msg

    def test_unsupported_extension(self, tmp_path: Path):
        p = tmp_path / "rooms.txt"
        p.write_text("anything\n")
        ok, msg = V.validate_room_data(p)
        assert not ok
        assert "unsupported" in msg.lower()


# ---------------------------------------------------------------------------
# PDF (smoke test only — fitz handles validation internally)
# ---------------------------------------------------------------------------

class TestValidatePdf:
    def test_invalid_bytes_rejected(self, tmp_path: Path):
        p = tmp_path / "bad.pdf"
        p.write_bytes(b"not really a pdf")
        ok, msg = V.validate_pdf(p)
        assert not ok

    def test_valid_pdf_accepted(self, tmp_path: Path):
        fitz = pytest.importorskip("fitz")
        doc = fitz.open()
        doc.new_page()
        p = tmp_path / "ok.pdf"
        doc.save(p)
        doc.close()
        ok, msg = V.validate_pdf(p)
        assert ok, msg
