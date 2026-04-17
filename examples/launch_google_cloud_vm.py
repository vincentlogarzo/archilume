"""
Archilume Google Cloud Platform (GCP) Virtual Machine (VM) Manager (entry point)

Usage:
    python examples/gcp_launch_vm.py
"""

from archilume import config
from archilume.infra.gcp_vm_manager import GCPVMManager


def _select_project() -> str:
    projects_dir = config.PROJECTS_DIR
    projects = sorted(p.name for p in projects_dir.iterdir() if p.is_dir())
    if not projects:
        raise RuntimeError(f"No projects found in {projects_dir}")

    print("\nAvailable projects:")
    for i, name in enumerate(projects, 1):
        print(f"  {i}. {name}")

    try:
        idx = int(input("\nSelect project number: ").strip()) - 1
        return projects[idx]
    except (ValueError, IndexError):
        raise RuntimeError("Invalid project selection.")


if __name__ == "__main__":
    project_name = _select_project()
    GCPVMManager(project_name=project_name).run()
