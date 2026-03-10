"""Launch AcceleradRT interactive viewer."""

import os
import subprocess

from archilume import config

ACCELERAD_RT = config.ACCELERAD_BIN_PATH / "AcceleradRT.exe"


def view_octree(octree_path, x=900, y=900):
    env = os.environ.copy()
    env["RAYPATH"] = config.RAYPATH
    subprocess.run(
        [str(ACCELERAD_RT), 
         "-x", str(x), 
         "-y", str(y), 
         "-ab", str(1),
         str(octree_path)], 
         env=env
         )


def launch(project):
    """Launch the interactive viewer for a specific project."""
    paths   = config.get_project_paths(project)
    octree  = paths.inputs_dir / f"{project}.oct"
    if not octree.exists():
        # Try generic octree name
        octree = paths.inputs_dir / "scene.oct"
    
    if not octree.exists():
        print(f"Error: Could not find octree for project {project}")
        return

    print(f"Launching viewer for project: {project}")
    view_octree(octree)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AcceleradRT Octree Viewer")
    parser.add_argument("--project", help="Project name")
    args = parser.parse_args()
    
    if args.project:
        launch(args.project)
    else:
        # Default fallback
        project = "527DP"
        launch(project)
