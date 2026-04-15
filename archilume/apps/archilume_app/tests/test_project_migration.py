"""Tests for archilume_app.lib.project_migration — legacy mode upgrades.

Uses monkeypatched get_project_paths / PROJECTS_DIR so migrations run against a
tmp_path scratch area rather than the real projects/ directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from archilume_app.lib import project_migration as pm


@dataclass
class _FakePaths:
    project_dir: Path
    inputs_dir: Path
    outputs_dir: Path
    octree_dir: Path
    image_dir: Path
    pic_dir: Path


def _make_project(tmp_path: Path, name: str, toml_body: str,
                  *, make_oct: bool = False, make_rdp: bool = False) -> Path:
    """Create a mock project tree under tmp_path/projects/<name>/ and return
    the project root."""
    root = tmp_path / "projects" / name
    (root / "inputs" / "pic").mkdir(parents=True)
    (root / "inputs" / "plans").mkdir(parents=True)
    (root / "inputs" / "aoi").mkdir(parents=True)
    (root / "outputs" / "image").mkdir(parents=True)
    (root / "outputs" / "octree").mkdir(parents=True)
    (root / "project.toml").write_text(toml_body, encoding="utf-8")
    if make_oct:
        (root / "outputs" / "octree" / "scene.oct").write_bytes(b"\x00\x01\x02")
    if make_rdp:
        (root / "inputs" / "standard.rdp").write_text("-ab 5 -aa 0.1\n")
    return root


def _patched_get_project_paths(tmp_path: Path, name: str):
    root = tmp_path / "projects" / name
    return _FakePaths(
        project_dir=root,
        inputs_dir=root / "inputs",
        outputs_dir=root / "outputs",
        octree_dir=root / "outputs" / "octree",
        image_dir=root / "outputs" / "image",
        pic_dir=root / "inputs" / "pic",
    )


@pytest.fixture
def with_patched_config(monkeypatch, tmp_path):
    """Redirect ``archilume.config.get_project_paths`` to our tmp_path tree."""
    import archilume.config as cfg
    monkeypatch.setattr(cfg, "get_project_paths",
                        lambda name: _patched_get_project_paths(tmp_path, name))
    return tmp_path


# ---------------------------------------------------------------------------
# needs_migration / infer_new_mode
# ---------------------------------------------------------------------------

class TestPredicate:
    @pytest.mark.parametrize("m", ["archilume", "hdr", "iesve"])
    def test_legacy_needs_migration(self, m):
        assert pm.needs_migration(m)

    @pytest.mark.parametrize("m", ["sunlight-sim", "sunlight-markup",
                                    "daylight-sim", "daylight-markup"])
    def test_new_does_not_need_migration(self, m):
        assert not pm.needs_migration(m)

    def test_unknown_does_not_need_migration(self):
        assert not pm.needs_migration("nonsense")


class TestInferNewMode:
    def test_iesve_with_sim_inputs(self, with_patched_config, tmp_path):
        _make_project(tmp_path, "p", '[project]\nname="p"\nmode="iesve"\n',
                      make_oct=True, make_rdp=True)
        paths = _patched_get_project_paths(tmp_path, "p")
        assert pm.infer_new_mode("iesve", paths) == "daylight-sim"

    def test_iesve_without_sim_inputs(self, with_patched_config, tmp_path):
        _make_project(tmp_path, "p", '[project]\nname="p"\nmode="iesve"\n')
        paths = _patched_get_project_paths(tmp_path, "p")
        assert pm.infer_new_mode("iesve", paths) == "daylight-markup"

    def test_hdr_with_sim_inputs(self, with_patched_config, tmp_path):
        _make_project(tmp_path, "p", '[project]\nname="p"\nmode="hdr"\n',
                      make_oct=True, make_rdp=True)
        paths = _patched_get_project_paths(tmp_path, "p")
        assert pm.infer_new_mode("hdr", paths) == "sunlight-sim"

    def test_hdr_without_sim_inputs(self, with_patched_config, tmp_path):
        _make_project(tmp_path, "p", '[project]\nname="p"\nmode="hdr"\n')
        paths = _patched_get_project_paths(tmp_path, "p")
        assert pm.infer_new_mode("hdr", paths) == "sunlight-markup"

    def test_archilume_alias_behaves_like_hdr(self, with_patched_config, tmp_path):
        _make_project(tmp_path, "p", '[project]\nname="p"\nmode="archilume"\n')
        paths = _patched_get_project_paths(tmp_path, "p")
        assert pm.infer_new_mode("archilume", paths) == "sunlight-markup"


# ---------------------------------------------------------------------------
# migrate_project_toml — end-to-end
# ---------------------------------------------------------------------------

class TestMigrateProjectToml:
    def _read_toml(self, root: Path) -> dict:
        import tomllib
        with open(root / "project.toml", "rb") as f:
            return tomllib.load(f)

    def test_iesve_markup_rewrites_toml(self, with_patched_config, tmp_path):
        root = _make_project(
            tmp_path, "p1",
            '[project]\nname = "p1"\nmode = "iesve"\n\n'
            '[paths]\npdf_path = "plans/a.pdf"\nimage_dir = ""\n'
            'iesve_room_data = "aoi/iesve_room_data.csv"\n'
            'octree = ""\nrdp = ""\n',
        )
        new_mode = pm.migrate_project_toml("p1")
        assert new_mode == "daylight-markup"
        data = self._read_toml(root)
        assert data["project"]["mode"] == "daylight-markup"
        assert data["project"]["name"] == "p1"
        # Dead image_dir = "" should be dropped
        assert "image_dir" not in data["paths"]
        # Non-dead keys preserved
        assert data["paths"]["pdf_path"] == "plans/a.pdf"
        assert data["paths"]["iesve_room_data"] == "aoi/iesve_room_data.csv"

    def test_hdr_sim_detection(self, with_patched_config, tmp_path):
        _make_project(tmp_path, "p2",
                      '[project]\nname="p2"\nmode="hdr"\n',
                      make_oct=True, make_rdp=True)
        new_mode = pm.migrate_project_toml("p2")
        assert new_mode == "sunlight-sim"

    def test_already_new_mode_is_noop(self, with_patched_config, tmp_path):
        root = _make_project(tmp_path, "p3",
                             '[project]\nname="p3"\nmode="sunlight-markup"\n')
        before = (root / "project.toml").read_text()
        result = pm.migrate_project_toml("p3")
        after = (root / "project.toml").read_text()
        assert result is None
        assert before == after

    def test_idempotent_second_call(self, with_patched_config, tmp_path):
        _make_project(tmp_path, "p4",
                      '[project]\nname="p4"\nmode="iesve"\n')
        first = pm.migrate_project_toml("p4")
        second = pm.migrate_project_toml("p4")
        assert first == "daylight-markup"
        assert second is None  # already migrated

    def test_missing_toml_returns_none(self, with_patched_config, tmp_path):
        # Create the project dir but no toml
        (tmp_path / "projects" / "p5" / "inputs" / "pic").mkdir(parents=True)
        (tmp_path / "projects" / "p5" / "outputs" / "octree").mkdir(parents=True)
        assert pm.migrate_project_toml("p5") is None

    def test_unknown_legacy_mode_is_untouched(self, with_patched_config, tmp_path):
        root = _make_project(tmp_path, "p6",
                             '[project]\nname="p6"\nmode="weirdmode"\n')
        result = pm.migrate_project_toml("p6")
        assert result is None
        # Should not have rewritten
        assert 'weirdmode' in (root / "project.toml").read_text()
