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


if __name__ == "__main__":
    project = "527DP"
    paths   = config.get_project_paths(project)
    octree  = paths.inputs_dir / "527DP.oct"
    view_octree(octree)
