"""Unit tests for the shared per-view warmup+render helper and its callers.

Covers:
- Linux path emits ``rtpict -n``, Windows path emits ``rpict -w``.
- Warmup is skipped when the ambient file already exists.
- SunlightRenderer overcast HDRs use the ``__{sky}.hdr`` naming convention;
  DaylightRenderer HDRs use ``{octree}_{view}.hdr``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from archilume.core import rendering_pipelines as rp
from archilume.core.rendering_pipelines import (
    DaylightRenderer,
    SunlightRenderer,
    render_view_with_warmup,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _touch(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


@pytest.fixture
def captured_cmds():
    cmds: list[str] = []

    def fake_exec(cmd, number_of_workers=1):
        if isinstance(cmd, list):
            cmds.extend(cmd)
        else:
            cmds.append(cmd)

    with patch.object(rp.utils, "execute_new_radiance_commands", side_effect=fake_exec):
        yield cmds


# ---------------------------------------------------------------------------
# render_view_with_warmup
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("is_linux,expected_prefix", [
    (True, "rtpict -n"),
    (False, "rpict -w"),
])
def test_platform_branch_selects_correct_binary(tmp_path: Path, captured_cmds, is_linux, expected_prefix):
    octree = _touch(tmp_path / "m.oct")
    view = _touch(tmp_path / "v.vp")
    hdr = tmp_path / "out.hdr"
    amb = tmp_path / "out.amb"  # does not exist -> warmup runs

    with patch.object(rp, "IS_LINUX", is_linux):
        render_view_with_warmup(
            octree_path=octree,
            view_file=view,
            output_hdr_path=hdr,
            ambient_file_path=amb,
            render_x=128,
            render_y=128,
            render_params="-aa 0.1 -ab 3",
        )

    assert len(captured_cmds) == 2, "expected warmup + render"
    assert all(c.startswith(expected_prefix) for c in captured_cmds)


def test_warmup_skipped_when_amb_file_exists(tmp_path: Path, captured_cmds):
    octree = _touch(tmp_path / "m.oct")
    view = _touch(tmp_path / "v.vp")
    hdr = tmp_path / "out.hdr"
    amb = _touch(tmp_path / "out.amb", "cached")

    render_view_with_warmup(
        octree_path=octree,
        view_file=view,
        output_hdr_path=hdr,
        ambient_file_path=amb,
        render_x=256,
        render_y=256,
        render_params="-aa 0.1 -ab 3",
    )

    assert len(captured_cmds) == 1, "warmup must be skipped when .amb exists"
    assert f"-x 256 -y 256" in captured_cmds[0]
    assert f"-af {amb}" in captured_cmds[0]


def test_irradiance_flag_toggle(tmp_path: Path, captured_cmds):
    octree = _touch(tmp_path / "m.oct")
    view = _touch(tmp_path / "v.vp")
    hdr = tmp_path / "out.hdr"

    render_view_with_warmup(
        octree_path=octree,
        view_file=view,
        output_hdr_path=hdr,
        ambient_file_path=None,
        render_x=64,
        render_y=64,
        render_params="-aa 0.1",
        use_ambient_file=False,
        irradiance=False,
    )

    assert len(captured_cmds) == 1
    assert " -i " not in f" {captured_cmds[0]} "


# ---------------------------------------------------------------------------
# DaylightRenderer naming
# ---------------------------------------------------------------------------


def test_daylight_renderer_output_naming(tmp_path: Path, captured_cmds):
    octree = _touch(tmp_path / "model.oct")
    rdp = _touch(tmp_path / "std.rdp", "-ab 4")
    view = _touch(tmp_path / "room01.vp", "rvu -vtv -vp 0 0 0")

    renderer = DaylightRenderer(
        octree_path=octree,
        rdp_path=rdp,
        x_res=256,
        view_files=[view],
        image_dir=tmp_path / "out",
    )
    renderer._render_single_view(view, view_idx=1, total=1, octree_base_name="model")

    assert captured_cmds, "expected at least one radiance command"
    assert f"{tmp_path / 'out' / 'model_room01.hdr'}" in captured_cmds[-1]
    assert f"@{rdp}" in captured_cmds[-1]


# ---------------------------------------------------------------------------
# SunlightRenderer overcast naming + platform branch
# ---------------------------------------------------------------------------


def _make_sunlight_renderer(tmp_path: Path) -> SunlightRenderer:
    skyless = _touch(tmp_path / "model_skyless.oct")
    skies = tmp_path / "skies"
    views = tmp_path / "views"
    image_dir = tmp_path / "image"
    overcast = _touch(skies / "TenK_cie_overcast.sky")
    _touch(views / "room01.vp", "rvu -vtv -vp 0 0 0")

    return SunlightRenderer(
        skyless_octree_path=skyless,
        x_res=128,
        y_res=128,
        skies_dir=skies,
        views_dir=views,
        image_dir=image_dir,
        overcast_sky_file_path=overcast,
    )


def test_generate_overcast_returns_oconv_and_param_strings(tmp_path: Path):
    renderer = _make_sunlight_renderer(tmp_path)
    oconv_cmd, warmup_params, render_params = (
        renderer._generate_overcast_sky_rendering_commands()
    )

    assert oconv_cmd.startswith("oconv -i ")
    assert "-ad 2048" in warmup_params and "-ad 4096" in render_params
    assert "-as 512" in warmup_params and "-as 1024" in render_params
    # param strings are tuning flags only — helper appends -i / -af / octree
    assert "-af" not in warmup_params and "-af" not in render_params
    assert "-i " not in warmup_params and "-i " not in render_params


@pytest.mark.parametrize("is_linux,expected_prefix", [
    (True, "rtpict -n"),
    (False, "rpict -w"),
])
def test_overcast_cpu_uses_platform_binary_and_overcast_naming(
    tmp_path: Path, captured_cmds, is_linux, expected_prefix
):
    renderer = _make_sunlight_renderer(tmp_path)
    renderer.overcast_octree_cmd, renderer.overcast_warmup_params, renderer.overcast_render_params = (
        renderer._generate_overcast_sky_rendering_commands()
    )

    with patch.object(rp, "IS_LINUX", is_linux):
        _, future = renderer._render_overcast_cpu(
            octree_base_name="model",
            overcast_sky_name="TenK_cie_overcast",
        )
        future.result()

    assert captured_cmds, "expected warmup + render commands to have run"
    assert all(c.startswith(expected_prefix) for c in captured_cmds)
    expected_hdr = tmp_path / "image" / "model_room01__TenK_cie_overcast.hdr"
    render_cmd = [c for c in captured_cmds if str(expected_hdr) in c]
    assert render_cmd, f"no render cmd wrote to expected HDR {expected_hdr}"


def test_overcast_cpu_skips_when_existing_hdrs_valid(tmp_path: Path, captured_cmds):
    renderer = _make_sunlight_renderer(tmp_path)
    renderer.overcast_octree_cmd, renderer.overcast_warmup_params, renderer.overcast_render_params = (
        renderer._generate_overcast_sky_rendering_commands()
    )
    # Pre-seed a valid-sized HDR so the skip-shortcut triggers.
    hdr = renderer.image_dir / "model_room01__TenK_cie_overcast.hdr"
    _touch(hdr, "x" * (SunlightRenderer.MIN_VALID_HDR_BYTES + 1))

    _, future = renderer._render_overcast_cpu(
        octree_base_name="model",
        overcast_sky_name="TenK_cie_overcast",
    )
    future.result()

    assert captured_cmds == [], "no radiance commands should run when HDRs already valid"
