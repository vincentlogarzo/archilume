"""
Project scaffolding helper
==========================

Creates the standard directory structure for a new Archilume simulation project.

Usage (CLI):
    python -m archilume.project <project_name>

Usage (Python):
    from archilume.project import create_project
    create_project("527DP")
"""

import sys
from archilume.config import PROJECTS_DIR, get_project_paths


def create_project(name: str) -> None:
    """Create all standard subdirectories for a new project under projects/<name>/."""
    paths = get_project_paths(name)

    if paths.project_dir.exists():
        print(f"Project '{name}' already exists at {paths.project_dir}")
        return

    paths.create_dirs()
    print(f"Created project '{name}' at {paths.project_dir}")
    for d in sorted(paths.project_dir.rglob("*")):
        print(f"  {d.relative_to(PROJECTS_DIR)}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m archilume.project <project_name>")
        sys.exit(1)
    create_project(sys.argv[1])
