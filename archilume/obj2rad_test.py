import subprocess
import os
from pathlib import Path
from archilume.utils import run_commands_parallel


def obj2rad(obj_paths: Path) -> None:
    """Convert OBJ file to Radiance format using obj2rad.exe.
    obj2rad "c:\\Projects\\archilume\\inputs\\87cowles_BLD_noWindows.obj" > "c:\\Projects\\archilume\\intermediates\\rad\\87cowles_BLD_noWindows.rad"
    """

    for obj_path in obj_paths:
        output_file_path = Path(__file__).parent.parent / "intermediates" / "rad" / obj_path.with_suffix('.rad').name
        command = f'obj2rad {obj_path} > {output_file_path}'
        run_commands_parallel([command],number_of_workers=1)

def run_with_os_system():
    exe_path = r"C:/Radiance/bin/obj2rad.exe"
    input_file = r"C:/Projects/archilume/inputs/87cowles_BLD_noWindows.obj"
    
    
    # Build the command string
    command = f"{exe_path} {input_file}"
    
    print(f"Running: {command}")
    # FIXME: testing this function, using claude, to determine alternatives ways to run this command without using subprocess. 
    # Execute the command - returns exit code
    exit_code = os.system(command)
    #TODO: capture this output somehow and pipe it to a utf-8 format text file. to avoid possible secutirty issues or compatability issues with subprocess running obj2rad. 
    if exit_code == 0:
        print("Command executed successfully")
    else:
        print(f"Command failed with exit code: {exit_code}")
    
    return exit_code


if __name__ == "__main__":
    obj_paths = [
        Path(__file__).parent.parent / "inputs" / "87cowles_BLD_noWindows.obj",
        Path(__file__).parent.parent / "inputs" / "87cowles_site.obj"
        ]
    
    # obj2rad(obj_paths)

    run_with_os_system()

    #TODO determine how to integrate this into the winter_solstice_sunlight file to move on. 
    
