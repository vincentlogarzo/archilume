"""Archilume – lazy top-level package imports.

Heavy submodules (pyvista, ifcopenshell, cv2, scipy …) are imported on
first access rather than at package-load time, cutting startup cost for
lightweight consumers such as the HDR editor.
"""

from . import utils, config

# Eagerly re-export the lightweight helpers that many callers expect at
# package level without triggering the heavy submodules.
from .utils import smart_cleanup, clear_outputs_folder, PhaseTimer

# ---------------------------------------------------------------------------
# Lazy attribute access for heavy submodule classes
# ---------------------------------------------------------------------------

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "Apng2Mp4":                (".post.apng2mp4",           "Apng2Mp4"),
    "GCPVMManager":            (".infra.gcp_vm_manager",    "GCPVMManager"),
    "IfcStrip":                (".geo.ifc_strip",           "IfcStrip"),
    "Hdr2Wpd":                 (".post.hdr2wpd",            "Hdr2Wpd"),
    "MtlConverter":            (".core.mtl_converter",      "MtlConverter"),
    "Objs2Octree":             (".core.objs2octree",        "Objs2Octree"),
    "SunlightRenderer":        (".core.rendering_pipelines","SunlightRenderer"),
    "DaylightRenderer":        (".core.rendering_pipelines","DaylightRenderer"),
    "Tiff2Animation":          (".post.tiff2animation",     "Tiff2Animation"),
    "SkyGenerator":            (".core.sky_generator",      "SkyGenerator"),
    "ViewGenerator":           (".core.view_generator",     "ViewGenerator"),
    "SunlightAccessWorkflow":  (".workflows",               "SunlightAccessWorkflow"),
    "IESVEDaylightWorkflow":   (".workflows",               "IESVEDaylightWorkflow"),
}

__all__ = [
    "config", "utils",
    "smart_cleanup", "clear_outputs_folder", "PhaseTimer",
    *_LAZY_IMPORTS,
]


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        import importlib
        mod = importlib.import_module(module_path, __name__)
        val = getattr(mod, attr)
        # Cache on the module so __getattr__ is not called again.
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
