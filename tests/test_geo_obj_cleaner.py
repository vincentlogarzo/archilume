"""Tests for :mod:`archilume.geo.obj_cleaner`."""

from __future__ import annotations

from pathlib import Path

from archilume.geo.obj_cleaner import clean_obj_for_radiance


def _messy_obj() -> str:
    """A contrived OBJ with everything the cleaner should either keep or strip."""
    return (
        "# A comment that should be stripped\n"
        "mtllib some.mtl\n"
        "o Wall/ExteriorBricks\n"
        "v 0.0 0.0 0.0\n"
        "v 1.0 0.0 0.0\n"
        "v 1.0 1.0 0.0\n"
        "v 0.0 1.0 0.0\n"
        "vn 0.0 0.0 1.0\n"
        "vt 0.0 0.0\n"
        "usemtl brick\n"
        "s 1\n"
        "f 1/1/1 2/2/1 3/3/1 4/4/1\n"
        "g Group42\n"
        "f 1 2 3\n"
    )


class TestCleanObjForRadiance:
    def test_writes_cleaned_file_next_to_input(self, tmp_path):
        src = tmp_path / "scene.obj"
        src.write_text(_messy_obj())
        out = clean_obj_for_radiance(src, verbose=False)
        assert out == tmp_path / "scene_cleaned.obj"
        assert out.exists()

    def test_strips_vertex_normals_and_texcoords(self, tmp_path):
        src = tmp_path / "scene.obj"
        src.write_text(_messy_obj())
        out = clean_obj_for_radiance(src, verbose=False)
        text = out.read_text()
        assert "vn " not in text
        assert "vt " not in text
        # "mtllib" is also dropped (not in the keep set).
        assert "mtllib" not in text
        # "s 1" smoothing group dropped.
        assert "\ns 1" not in text

    def test_keeps_vertices_faces_objects_groups_materials(self, tmp_path):
        src = tmp_path / "scene.obj"
        src.write_text(_messy_obj())
        out = clean_obj_for_radiance(src, verbose=False)
        text = out.read_text()
        # 4 vertex lines survived.
        assert text.count("\nv ") == 4
        # At least one face survived — and face indices lost their /ref/ref suffixes.
        assert "\nf 1 2 3 4" in text  # quad simplified to pure vertex indices
        assert "\nf 1 2 3" in text
        assert "\no " in text
        assert "\ng " in text
        assert "\nusemtl " in text

    def test_custom_output_path_honoured(self, tmp_path):
        src = tmp_path / "s.obj"
        src.write_text(_messy_obj())
        dest = tmp_path / "nested" / "out.obj"
        out = clean_obj_for_radiance(src, output_path=dest, verbose=False)
        assert out == dest
        assert dest.exists()
        # Parent directory was auto-created.
        assert dest.parent.is_dir()
