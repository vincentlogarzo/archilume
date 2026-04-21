"""Tests for top-level workflow orchestrators.

These tests verify the call sequence of the two public workflows
(``SunlightAccessWorkflow`` and ``IESVEDaylightWorkflow``) without actually
running any Radiance binary or doing real rendering. Heavy collaborators
(``Objs2Octree``, ``SkyGenerator``, ``ViewGenerator``, ``SunlightRenderer``,
``DaylightRenderer``, ``Hdr2Wpd``) are patched at the module boundary.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from archilume.workflows import (
    iesve_daylight_workflow as idw,
    sunlight_access_workflow as saw,
)


# =========================================================================
# Shared helpers
# =========================================================================


class _Recorder:
    """Collects sequenced calls to collaborators for assertion order."""

    def __init__(self):
        self.calls: list[str] = []

    def factory(self, label: str):
        recorder = self

        class _Stub:
            def __init__(self, *a, **kw):
                recorder.calls.append(f"{label}.__init__")
                self.view_files = []
                self.view_horizontal = 5.0
                for k, v in kw.items():
                    setattr(self, k, v)

            def __getattr__(self, name):
                if name.startswith("_"):
                    raise AttributeError(name)

                def _method(*a, **kw):
                    recorder.calls.append(f"{label}.{name}")
                    return True

                return _method

        return _Stub


# =========================================================================
# SunlightAccessWorkflow
# =========================================================================


class TestSunlightAccessWorkflow:
    def test_runs_phases_in_order(self, tmp_path, monkeypatch):
        rec = _Recorder()

        # Patch all heavy collaborators to stubs.
        monkeypatch.setattr(saw, "Objs2Octree", rec.factory("Octree"))
        monkeypatch.setattr(saw, "SkyGenerator", rec.factory("Sky"))
        monkeypatch.setattr(saw, "ViewGenerator", rec.factory("View"))
        monkeypatch.setattr(saw, "SunlightRenderer", rec.factory("Renderer"))

        # Patch get_project_paths to return something that looks right.
        paths_stub = SimpleNamespace(
            octree_dir=tmp_path / "octree", rad_dir=tmp_path / "rad",
            sky_dir=tmp_path / "sky", view_dir=tmp_path / "views",
            aoi_dir=tmp_path / "aoi", image_dir=tmp_path / "image",
            wpd_dir=tmp_path / "wpd", outputs_dir=tmp_path,
            create_dirs=lambda: None,
        )
        monkeypatch.setattr(saw.config, "get_project_paths",
                            lambda name: paths_stub)
        monkeypatch.setattr(saw, "clear_outputs_folder", lambda p: None)

        saw.SunlightAccessWorkflow().run(
            building_latitude=-33.9,
            month=6, day=21, start_hour=9, end_hour=15,
            timestep_min=30,
            ffl_offset_mm=850,
            grid_resolution_mm=100,
            aoi_inputs_dir=tmp_path / "aoi_in",
            obj_paths=[tmp_path / "scene.obj"],
            project="test",
        )
        # First collaborator must be Objs2Octree; last must be Renderer.
        assert rec.calls[0] == "Octree.__init__"
        assert any(c.startswith("Renderer.") for c in rec.calls)
        # Sky generation precedes renderer.
        sky_idx = next(i for i, c in enumerate(rec.calls) if c.startswith("Sky."))
        render_idx = next(i for i, c in enumerate(rec.calls)
                          if c.startswith("Renderer."))
        assert sky_idx < render_idx

    def test_clear_outputs_runs_first(self, tmp_path, monkeypatch):
        order = []
        monkeypatch.setattr(saw, "Objs2Octree", lambda **kw: SimpleNamespace(
            create_skyless_octree_for_analysis=lambda: order.append("octree"),
            skyless_octree_path=tmp_path / "scene.oct",
        ))
        monkeypatch.setattr(saw, "SkyGenerator", lambda **kw: SimpleNamespace(
            generate_sunny_sky_series=lambda **k: order.append("sky"),
        ))
        monkeypatch.setattr(saw, "ViewGenerator", lambda **kw: SimpleNamespace(
            create_plan_view_files=lambda: order.append("view"),
            view_files=[], view_horizontal=5.0,
        ))
        monkeypatch.setattr(saw, "SunlightRenderer", lambda **kw: SimpleNamespace(
            sun_only_rendering_pipeline=lambda: order.append("render"),
        ))
        paths_stub = SimpleNamespace(
            octree_dir=tmp_path, rad_dir=tmp_path,
            sky_dir=tmp_path, view_dir=tmp_path,
            aoi_dir=tmp_path, image_dir=tmp_path, wpd_dir=tmp_path,
            outputs_dir=tmp_path,
            create_dirs=lambda: order.append("create_dirs"),
        )
        monkeypatch.setattr(saw.config, "get_project_paths", lambda n: paths_stub)
        monkeypatch.setattr(saw, "clear_outputs_folder",
                            lambda p: order.append("clear_outputs"))

        saw.SunlightAccessWorkflow().run(
            building_latitude=0, month=1, day=1,
            start_hour=9, end_hour=10, timestep_min=60,
            ffl_offset_mm=0, grid_resolution_mm=100,
            aoi_inputs_dir=tmp_path, obj_paths=[tmp_path / "s.obj"],
            project="p",
        )
        # Cleanup before any render-ish step.
        assert order.index("clear_outputs") < order.index("render")


# =========================================================================
# IESVEDaylightWorkflow
# =========================================================================


class TestIESVEDaylightWorkflow:
    def test_runs_view_then_render_then_post(self, tmp_path, monkeypatch):
        order = []

        # Stub ViewGenerator.
        def _vg(*a, **kw):
            order.append("vg.init")
            return SimpleNamespace(
                create_plan_view_files=lambda: order.append("vg.views"),
                create_aoi_files=lambda coordinate_map=None: order.append("vg.aoi"),
                view_files=[],
            )

        monkeypatch.setattr(idw, "ViewGenerator", _vg)

        # Stub DaylightRenderer.
        def _dr(*a, **kw):
            order.append("dr.init")
            return SimpleNamespace(
                daylight_rendering_pipeline=lambda: order.append("dr.render"),
            )

        monkeypatch.setattr(idw, "DaylightRenderer", _dr)

        # Stub utility functions used by the workflow.
        monkeypatch.setattr(
            idw.utils, "iesve_aoi_to_room_boundaries_csv",
            lambda **kw: tmp_path / "rb.csv",
        )
        monkeypatch.setattr(
            idw.utils, "compute_pixel_to_world_map",
            lambda p: SimpleNamespace(image_width=100, image_height=100),
        )

        paths_stub = SimpleNamespace(
            aoi_dir=tmp_path / "aoi", view_dir=tmp_path / "views",
            image_dir=tmp_path / "image", wpd_dir=tmp_path / "wpd",
            outputs_dir=tmp_path,
            create_dirs=lambda: order.append("paths.create_dirs"),
        )
        monkeypatch.setattr(idw.config, "get_project_paths",
                            lambda name: paths_stub)

        # Patch Hdr2Wpd if used in later phases.
        import archilume.post.hdr2wpd as hw
        monkeypatch.setattr(
            hw, "Hdr2Wpd",
            lambda **kw: SimpleNamespace(
                daylight_wpd_extraction=lambda *a, **k: None,
                _generate_daylight_excel_report=lambda *a, **k: None,
            ),
        )

        idw.IESVEDaylightWorkflow().run(
            octree_path=tmp_path / "scene.oct",
            rendering_params=tmp_path / "params.rdp",
            iesve_room_data=tmp_path / "rooms.csv",
            project="p",
            image_resolution=128,
            ffl_offset=0.0,
            use_ambient_file=False,
            n_cpus=1,
        )

        # Phases in order: ViewGenerator → DaylightRenderer → AOI files.
        assert order.index("vg.views") < order.index("dr.render")
        assert order.index("dr.render") < order.index("vg.aoi")
