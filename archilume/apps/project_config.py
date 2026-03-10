"""
project_config.py — helpers for reading and writing project.toml files.

Each project stores a TOML config at:
    projects/<project_name>/project.toml

Schema:
    [project]
    name = "527DP"
    mode = "hdr"          # "hdr" or "iesve"

    [paths]
    pdf_path        = "plans/SK01.09-PLAN.pdf"   # relative to inputs/, optional
    image_dir       = ""                          # relative to inputs/ (iesve) or blank (hdr)
    iesve_room_data = ""                          # relative to inputs/, optional
    octree          = "527DP.oct"                 # relative to inputs/, Archilume only
    rdp             = "527DP.rdp"                 # relative to inputs/, Archilume only
"""

# fmt: off
# autopep8: off

import tomllib
from pathlib import Path

from archilume import config


def _toml_path(project_name: str) -> Path:
    return config.PROJECTS_DIR / project_name / "project.toml"


def load_project_toml(project_name: str) -> dict:
    """Return parsed TOML dict for *project_name*.

    If the project directory exists but has no project.toml, a default one
    is created so the project can be opened and configured immediately.
    Returns {} only when the project directory itself does not exist.
    """
    path = _toml_path(project_name)
    if not path.exists():
        project_dir = config.PROJECTS_DIR / project_name
        if not project_dir.exists():
            return {}
        # Initialise a default project.toml for this existing directory
        default_cfg = {
            "project": {"name": project_name, "mode": "hdr"},
            "paths":   {"pdf_path": "", "image_dir": "", "iesve_room_data": ""},
        }
        save_project_toml(project_name, default_cfg)
        return default_cfg
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def save_project_toml(project_name: str, cfg: dict) -> None:
    """Write *cfg* as TOML to projects/<project_name>/project.toml.

    The file is written using a hand-built TOML string so that no extra
    dependency (tomli_w) is required.  Only the fixed schema fields are
    written.
    """
    path = _toml_path(project_name)
    path.parent.mkdir(parents=True, exist_ok=True)

    proj = cfg.get("project", {})
    paths = cfg.get("paths", {})

    def _str(val):
        return Path(val).as_posix() if val else ""

    lines = [
        "[project]",
        f'name = "{_str(proj.get("name", project_name))}"',
        f'mode = "{_str(proj.get("mode", "hdr"))}"',
        "",
        "[paths]",
        f'pdf_path        = "{_str(paths.get("pdf_path", ""))}"',
        f'image_dir       = "{_str(paths.get("image_dir", ""))}"',
        f'iesve_room_data = "{_str(paths.get("iesve_room_data", ""))}"',
        f'octree          = "{_str(paths.get("octree", ""))}"',
        f'rdp             = "{_str(paths.get("rdp", ""))}"',
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def list_projects() -> list:
    """Return sorted list of project names found under PROJECTS_DIR.

    Includes any subdirectory that contains a project.toml *or* an inputs/
    directory (i.e. projects scaffolded but not yet configured).  Hidden
    directories and the _blank placeholder are excluded.
    """
    if not config.PROJECTS_DIR.exists():
        return []
    return sorted(
        d.name
        for d in config.PROJECTS_DIR.iterdir()
        if d.is_dir()
        and not d.name.startswith("_")
        and not d.name.startswith(".")
        and ((d / "project.toml").exists() or (d / "inputs").exists())
    )


def get_last_project() -> str:
    """Read the last used project name from .last_project file."""
    last_file = config.PROJECTS_DIR / ".last_project"
    if last_file.exists():
        try:
            return last_file.read_text().strip()
        except Exception:
            pass
    return ""


def set_last_project(project_name: str) -> None:
    """Store the current project name in .last_project file."""
    if not project_name:
        return
    try:
        (config.PROJECTS_DIR / ".last_project").write_text(project_name)
    except Exception:
        pass