"""Archilume – top-level package exports.

Heavy engine modules (pyradiance, ifcopenshell, opencv, matplotlib, etc.)
are lazy-loaded via PEP 562 __getattr__. This lets lightweight Docker
stages (archilume-frontend, archilume-backend) import archilume.config and
archilume.utils without requiring the engine dep group.
"""

from typing import TYPE_CHECKING

from . import config, utils
from .utils import clear_outputs_folder, PhaseTimer

# Static-analysis shim: Pylance/Pyright/Ruff read this block as real
# imports, preserving Ctrl+click Go-to-Definition, hover types, and
# auto-import suggestions. Python skips it at runtime (TYPE_CHECKING is
# False), so the heavy modules are only loaded on first attribute access
# via __getattr__ below.
if TYPE_CHECKING:
    from .core.mtl_converter import MtlConverter
    from .core.objs2octree import Objs2Octree
    from .core.sky_generator import SkyGenerator
    from .core.view_generator import ViewGenerator
    from .core.rendering_pipelines import SunlightRenderer, DaylightRenderer
    from .post.apng2mp4 import Apng2Mp4
    from .post.hdr2wpd import Hdr2Wpd
    from .post.tiff2animation import Tiff2Animation
    from .geo.ifc_strip import IfcStrip
    from .infra.gcp_vm_manager import GCPVMManager
    from .workflows import SunlightAccessWorkflow, IESVEDaylightWorkflow


_LAZY_ATTRS: dict[str, str] = {
    "MtlConverter":           ".core.mtl_converter",
    "Objs2Octree":            ".core.objs2octree",
    "SkyGenerator":           ".core.sky_generator",
    "ViewGenerator":          ".core.view_generator",
    "SunlightRenderer":       ".core.rendering_pipelines",
    "DaylightRenderer":       ".core.rendering_pipelines",
    "Apng2Mp4":               ".post.apng2mp4",
    "Hdr2Wpd":                ".post.hdr2wpd",
    "Tiff2Animation":         ".post.tiff2animation",
    "IfcStrip":               ".geo.ifc_strip",
    "GCPVMManager":           ".infra.gcp_vm_manager",
    "SunlightAccessWorkflow": ".workflows",
    "IESVEDaylightWorkflow":  ".workflows",
}


def __getattr__(name: str):
    try:
        module_path = _LAZY_ATTRS[name]
    except KeyError:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from None
    from importlib import import_module
    value = getattr(import_module(module_path, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY_ATTRS})


__all__ = [
    "config",
    "utils",
    "clear_outputs_folder",
    "PhaseTimer",
    *_LAZY_ATTRS.keys(),
]
