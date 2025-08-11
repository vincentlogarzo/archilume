from pathlib import Path

import archilume.generate_view_files as vg

# --- 1. generate views to be rendered (including axonometric and plan views of the building you are analysing)


script_dir = Path(__file__).parent  # Get the directory containing this script
csv_path = script_dir.parent / "inputs" / "RL_dyn_script_output_room_boundaries.csv"
vg.GenerateViewFiles(room_boundaries_csv_path_input=csv_path)



# --- 2. 


# --- 3. 




