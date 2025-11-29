"""
Debug script to test the _obj_files_to_rad function specifically
"""
import os
from pathlib import Path
from archilume.objs2octree import Objs2Octree

def debug_obj_files_to_rad():
    """Test the _obj_files_to_rad function with debug output"""
    
    # Use only the second file that we know works
    test_obj_files = ["C:/Projects/archilume/inputs/87cowles_site.obj"]
    test_mtl_files = ["C:/Projects/archilume/inputs/87cowles_site.mtl"]
    
    print("=== DEBUGGING _obj_files_to_rad FUNCTION ===")
    print(f"Input OBJ file: {test_obj_files[0]}")
    print(f"Input MTL file: {test_mtl_files[0]}")
    print(f"File exists check: {os.path.exists(test_obj_files[0])}")
    print()
    
    # Create the octree generator
    octree_generator = Objs2Octree(
        obj_file_paths=test_obj_files,
        mtl_file_paths=test_mtl_files
    )
    
    print(f"Output directory: {octree_generator.output_dir}")
    print(f"Directory exists: {os.path.exists(octree_generator.output_dir)}")
    print()
    
    # Clear any existing RAD files
    output_dir = Path(octree_generator.output_dir)
    if output_dir.exists():
        for rad_file in output_dir.glob("*.rad"):
            rad_file.unlink()
            print(f"Removed existing: {rad_file}")
    
    print("=== STARTING _obj_files_to_rad EXECUTION ===")
    
    try:
        # Call the function we want to debug
        octree_generator._obj_files_to_rad()
        
        print("=== EXECUTION COMPLETED SUCCESSFULLY ===")
        print(f"Combined RAD paths: {octree_generator.combined_rad_paths}")
        
        # Check output files
        for rad_path in octree_generator.combined_rad_paths:
            if os.path.exists(rad_path):
                file_size = os.path.getsize(rad_path)
                print(f"✅ Created: {rad_path} ({file_size} bytes)")
                
                # Show first few lines of content
                with open(rad_path, 'r') as f:
                    first_lines = [f.readline().strip() for _ in range(3)]
                print(f"   Content preview: {first_lines}")
            else:
                print(f"❌ Missing: {rad_path}")
        
    except Exception as e:
        print(f"❌ ERROR in _obj_files_to_rad: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_obj_files_to_rad()