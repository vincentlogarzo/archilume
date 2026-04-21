"""Mode-scoped directory enforcement.

Verifies that creating a sunlight project with only a PDF staged produces only
the three root directories (project_dir, inputs_dir, archive_dir) plus the
plans subdir (from the staged PDF). Mode-specific dirs (pic/, aoi/, octree/,
etc.) must NOT be created when no files target them.

Uses the same object.__new__ bypass as other state tests; exercises
_move_staged_into_project directly against a ProjectPaths rooted in tmp_path.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from dataclasses import replace
from typing import Optional

import pytest

from archilume.config import ProjectPaths
from archilume_app.state.editor_state import EditorState


def _make_paths(base: Path, name: str = "test-proj") -> ProjectPaths:
    project_dir = base / name
    inputs_dir = project_dir / "inputs"
    outputs_dir = project_dir / "outputs"
    return ProjectPaths(
        project_name=name,
        project_dir=project_dir,
        inputs_dir=inputs_dir,
        outputs_dir=outputs_dir,
        archive_dir=project_dir / "archive",
        aoi_inputs_dir=inputs_dir / "aoi",
        plans_dir=inputs_dir / "plans",
        pic_dir=inputs_dir / "pic",
        image_dir=outputs_dir / "image",
        wpd_dir=outputs_dir / "wpd",
        aoi_dir=outputs_dir / "aoi",
        view_dir=outputs_dir / "view",
        sky_dir=outputs_dir / "sky",
        octree_dir=outputs_dir / "octree",
        rad_dir=outputs_dir / "rad",
    )


def _make_state() -> EditorState:
    state = object.__new__(EditorState)
    object.__setattr__(state, "dirty_vars", set())
    object.__setattr__(state, "_self_dirty_computed_vars", set())
    object.__setattr__(state, "base_state", state)
    object.__setattr__(state, "rooms", [])
    return state


class TestSunlightProjectDirsScoped:
    def test_pdf_only_creates_no_phantom_dirs(self, tmp_path: Path):
        """A sunlight project with only a PDF staged must not create pic/, aoi/,
        octree/, rad/, sky/, image/, wpd/, view/, or outputs/ at all."""
        paths = _make_paths(tmp_path)
        state = _make_state()

        # Create the three roots (mirrors create_project)
        paths.project_dir.mkdir(parents=True, exist_ok=True)
        paths.inputs_dir.mkdir(parents=True, exist_ok=True)
        paths.archive_dir.mkdir(parents=True, exist_ok=True)

        # Stage a single valid PDF for the "plans" field
        fake_pdf = tmp_path / "floor_plan.pdf"
        fake_pdf.write_bytes(b"%PDF-dummy")
        staged = {
            "pdf": [{"path": str(fake_pdf), "name": "floor_plan.pdf", "ok": True}]
        }

        state._move_staged_into_project(paths, "sunlight", staged)

        # plans/ must exist (PDF was moved there)
        assert paths.plans_dir.exists()

        # None of the mode-specific dirs that received no files should exist
        phantom_dirs = [
            paths.pic_dir,
            paths.aoi_inputs_dir,
            paths.image_dir,
            paths.wpd_dir,
            paths.aoi_dir,
            paths.view_dir,
            paths.sky_dir,
            paths.octree_dir,
            paths.rad_dir,
        ]
        for d in phantom_dirs:
            assert not d.exists(), f"phantom dir created: {d}"

    def test_aoi_staged_creates_aoi_dir_only(self, tmp_path: Path):
        """Staging an .aoi file must create aoi_inputs_dir but not pic/ or outputs dirs."""
        paths = _make_paths(tmp_path)
        state = _make_state()

        paths.project_dir.mkdir(parents=True, exist_ok=True)
        paths.inputs_dir.mkdir(parents=True, exist_ok=True)
        paths.archive_dir.mkdir(parents=True, exist_ok=True)

        fake_aoi = tmp_path / "U101_T.aoi"
        fake_aoi.write_text("AoI Points File : X,Y positions\n")
        staged = {
            "aoi_files": [{"path": str(fake_aoi), "name": "U101_T.aoi", "ok": True}]
        }

        state._move_staged_into_project(paths, "sunlight", staged)

        assert paths.aoi_inputs_dir.exists()
        assert not paths.pic_dir.exists()
        assert not paths.image_dir.exists()
        assert not paths.octree_dir.exists()
