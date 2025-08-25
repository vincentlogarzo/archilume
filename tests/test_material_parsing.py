"""
Test script to reproduce and verify the material parsing bug fix.
"""

def test_material_parsing_bug():
    """Test that demonstrates the material parsing issue."""
    
    # Simulate the problematic converted content that causes the bug
    problematic_content = """# Third line parameters: R G B Sp Rg

# 00_MF01
void plastic 00_MF01
0
0
5 0.753 0.753 0.753 0.000 0.005

# Glass
void glass Glass
0
0
3 0.588 0.686 0.784"""
    
    # Simulate the buggy parsing logic from lines 200-219
    lines = problematic_content.split('\n')
    all_converted_content = ["#Combined Radiance Material file:"]
    processed_materials = set()
    current_section = []
    
    print("=== Testing Current (Buggy) Logic ===")
    for line in lines:
        print(f"Processing line: '{line}'")
        if line.strip().startswith('void plastic ') or line.strip().startswith('void glass '):
            material_name = line.strip().split()[-1]
            print(f"Found material: {material_name}")
            if material_name not in processed_materials:
                processed_materials.add(material_name)
                current_section.append(line)
                print(f"Added to current_section: {line}")
            else:
                print(f"Skipping duplicate material: {material_name}")
                current_section = []
        elif current_section or (line.strip() and not line.startswith('#')):
            current_section.append(line)
            print(f"Added to current_section: {line}")
        elif current_section:
            all_converted_content.extend(current_section)
            print(f"Completed section: {current_section}")
            current_section = []
    
    # Add any remaining content
    if current_section:
        all_converted_content.extend(current_section)
        print(f"Final section: {current_section}")
    
    print("\n=== Result ===")
    result = "\n".join(all_converted_content)
    print(result)
    
    # Check if the bug occurs
    lines_result = result.split('\n')
    for i, line in enumerate(lines_result):
        if '00_MF01' in line:
            # Check the following lines for the material definition
            material_lines = []
            for j in range(i, min(i+10, len(lines_result))):
                if lines_result[j].strip():
                    material_lines.append(lines_result[j])
                if j > i and (lines_result[j].startswith('void ') or lines_result[j].startswith('#')):
                    break
            
            print(f"\n=== 00_MF01 Material Definition ===")
            for line in material_lines:
                print(line)
            
            # Count non-comment, non-void lines in the material definition
            param_lines = [l for l in material_lines if not l.startswith('#') and not l.startswith('void')]
            if len(param_lines) > 3:  # Should only be: 0, 0, "5 ..."
                print(f"\n❌ BUG DETECTED: Material has {len(param_lines)} parameter lines, expected 3")
                print("Extra lines:", param_lines[3:])
                return False
            break
    
    print("\n✅ No bug detected in this test case")
    return True

if __name__ == "__main__":
    test_material_parsing_bug()