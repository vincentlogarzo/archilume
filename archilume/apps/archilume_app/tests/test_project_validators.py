"""Tests for archilume_app.lib.project_validators — content validators used by
the Create New Project and Project Settings modals.

All tests use tmp_path; no permanent files created.
"""

from pathlib import Path

import pytest

from archilume_app.lib import project_validators as V


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

class TestValidatePdf:
    @staticmethod
    def _write_clean_pdf(path: Path, pages: int = 1) -> None:
        import pymupdf as fitz
        doc = fitz.open()
        for _ in range(pages):
            doc.new_page()
        doc.save(str(path))
        doc.close()

    @staticmethod
    def _write_encrypted_pdf(path: Path) -> None:
        import pymupdf as fitz
        doc = fitz.open()
        doc.new_page()
        # AES-256 with both owner and user passwords — pdf.js (and PyMuPDF
        # without the password) cannot read either page-count or pixmap.
        doc.save(
            str(path),
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw="o",
            user_pw="u",
        )
        doc.close()

    def test_valid_unencrypted_pdf(self, tmp_path: Path):
        p = tmp_path / "ok.pdf"
        self._write_clean_pdf(p, pages=2)
        ok, msg = V.validate_pdf(p)
        assert ok, msg

    def test_rejects_encrypted_pdf_with_specific_message(self, tmp_path: Path):
        p = tmp_path / "locked.pdf"
        self._write_encrypted_pdf(p)
        ok, msg = V.validate_pdf(p)
        assert not ok
        # Exact user-facing message — surfaced verbatim by both the create-
        # project popout and the in-editor "Attach Floor Plan" flow.
        assert msg == V.ENCRYPTED_PDF_MESSAGE

    def test_rejects_missing_pdf(self, tmp_path: Path):
        ok, msg = V.validate_pdf(tmp_path / "absent.pdf")
        assert not ok
        # No pages in a non-existent file → "PDF has no pages" branch.
        assert "no pages" in msg.lower()


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

def _write_cube_obj(
    path: Path,
    *,
    side_m: float = 5.0,
    include_faces: bool = True,
) -> None:
    """Write a minimal axis-aligned cube OBJ with ``side_m`` edge length.

    ``include_faces=False`` produces a vertices-only file, used to exercise
    the faces-required branch of ``validate_obj``.
    """
    s = side_m
    verts = [
        (0, 0, 0), (s, 0, 0), (s, s, 0), (0, s, 0),
        (0, 0, s), (s, 0, s), (s, s, s), (0, s, s),
    ]
    lines = [f"v {x} {y} {z}" for (x, y, z) in verts]
    if include_faces:
        # Two triangles per face × 6 faces = 12 triangles.
        lines += [
            "f 1 2 3", "f 1 3 4",  # -Z
            "f 5 6 7", "f 5 7 8",  # +Z
            "f 1 2 6", "f 1 6 5",  # -Y
            "f 4 3 7", "f 4 7 8",  # +Y
            "f 1 4 8", "f 1 8 5",  # -X
            "f 2 3 7", "f 2 7 6",  # +X
        ]
    path.write_text("\n".join(lines) + "\n")


class TestValidateObj:
    def test_valid_metres_cube_with_faces(self, tmp_path: Path):
        """A 5-metre cube (diagonal ≈ 8.66 m) should pass all checks."""
        p = tmp_path / "cube.obj"
        _write_cube_obj(p, side_m=5.0)
        ok, msg = V.validate_obj(p)
        assert ok, msg

    def test_rejects_vertices_only_obj(self, tmp_path: Path):
        """Vertices without faces builds an empty octree — must reject."""
        p = tmp_path / "verts_only.obj"
        _write_cube_obj(p, side_m=5.0, include_faces=False)
        ok, msg = V.validate_obj(p)
        assert not ok
        assert "faces" in msg.lower()

    def test_rejects_empty_obj(self, tmp_path: Path):
        p = tmp_path / "empty.obj"
        p.write_text("# only comments\n# nothing else\n")
        ok, msg = V.validate_obj(p)
        assert not ok

    def test_rejects_submetre_model_as_wrong_units(self, tmp_path: Path):
        """A cube < 1 m across is almost certainly unit-scaled wrong."""
        p = tmp_path / "tiny.obj"
        _write_cube_obj(p, side_m=0.1)  # diagonal ≈ 0.17 m
        ok, msg = V.validate_obj(p)
        assert not ok
        assert "units" in msg.lower() or "metres" in msg.lower()

    def test_rejects_millimetre_model_as_wrong_units(self, tmp_path: Path):
        """A 'cube' 50 000 m across is almost certainly millimetres."""
        p = tmp_path / "mm.obj"
        _write_cube_obj(p, side_m=50_000.0)  # diagonal ≈ 86 km
        ok, msg = V.validate_obj(p)
        assert not ok
        assert "units" in msg.lower() or "millimetres" in msg.lower()


# First 20 lines of projects/cowles/inputs/87Cowles_BLD_withWindows.mtl.
# Captures the Autodesk ATF export pattern: header comment, blank line between
# material blocks, names prefixed with ``*`` and ``_``, three-line blocks.
COWLES_MTL_SAMPLE = """# WaveFront *.mtl file (generated by Autodesk ATF)

newmtl CF02_Ribbed
Kd 0.752941 0.752941 0.752941
d 1.000000

newmtl AF01
Kd 0.752941 0.752941 0.752941
d 1.000000

newmtl CF01
Kd 0.752941 0.752941 0.752941
d 1.000000

newmtl Default
Kd 1.000000 1.000000 1.000000
d 1.000000

newmtl *BK01_Masonry_-Brick_-_Beige
Kd 0.650980 0.600000 0.556863
d 1.000000
"""


class TestValidateMtl:
    def test_accepts_real_cowles_autodesk_atf_export(self, tmp_path: Path):
        """Real Revit/Autodesk ATF export pattern must validate."""
        p = tmp_path / "cowles.mtl"
        p.write_text(COWLES_MTL_SAMPLE)
        ok, msg = V.validate_mtl(p)
        assert ok, msg

    def test_accepts_minimal_single_material(self, tmp_path: Path):
        p = tmp_path / "ok.mtl"
        p.write_text("newmtl plaster\nKa 1 1 1\n")
        ok, msg = V.validate_mtl(p)
        assert ok, msg

    def test_accepts_tab_separated_newmtl(self, tmp_path: Path):
        """``newmtl\\tname`` is legal per the OBJ/MTL spec and is produced by
        some exporters. The old substring check falsely rejected this."""
        p = tmp_path / "tabs.mtl"
        p.write_text("newmtl\tmaterial_01\nKd 0.5 0.5 0.5\n")
        ok, msg = V.validate_mtl(p)
        assert ok, msg

    def test_rejects_empty_mtl(self, tmp_path: Path):
        p = tmp_path / "bad.mtl"
        p.write_text("# header only\n")
        ok, msg = V.validate_mtl(p)
        assert not ok
        assert "newmtl" in msg.lower()

    def test_rejects_newmtl_only_in_comment(self, tmp_path: Path):
        """A commented-out ``# newmtl`` line doesn't count as a declaration."""
        p = tmp_path / "comment.mtl"
        p.write_text("# newmtl example\nKd 1 1 1\n")
        ok, msg = V.validate_mtl(p)
        assert not ok


class TestValidateGeometryPair:
    def test_accepts_matching_stems(self):
        ok, msg = V.validate_geometry_pair(Path("foo.obj"), Path("foo.mtl"))
        assert ok, msg

    def test_rejects_different_stems(self):
        ok, msg = V.validate_geometry_pair(Path("foo.obj"), Path("bar.mtl"))
        assert not ok
        assert "stems" in msg.lower()

    def test_rejects_missing_mtl(self):
        ok, msg = V.validate_geometry_pair(Path("foo.obj"), None)
        assert not ok
        assert "foo.mtl" in msg


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
