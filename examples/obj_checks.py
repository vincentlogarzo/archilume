import os
from pathlib import Path


filepath = Path(r"C:\Projects\archilume\inputs\22041_AR_T01_BLD.obj")

# Get file size
file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
print(f"File size: {file_size_mb:.2f} MB\n")

# Count different element types
vertices = 0
faces = 0
normals = 0
textures = 0
objects = 0
groups = 0
materials = 0
lines_total = 0

object_faces = {}
current_object = "unnamed"

with open(filepath, "r") as f:
    for line in f:
        lines_total += 1
        if line.startswith("v "):
            vertices += 1
        elif line.startswith("f "):
            faces += 1
            object_faces[current_object] = object_faces.get(current_object, 0) + 1
        elif line.startswith("vn "):
            normals += 1
        elif line.startswith("vt "):
            textures += 1
        elif line.startswith("o "):
            objects += 1
            current_object = line.strip()[2:]
            if current_object not in object_faces:
                object_faces[current_object] = 0
        elif line.startswith("g "):
            groups += 1
        elif line.startswith("usemtl "):
            materials += 1

print(f"Total lines: {lines_total:,}")
print(f"Vertices: {vertices:,}")
print(f"Faces: {faces:,}")
print(f"Normals: {normals:,}")
print(f"Texture coords: {textures:,}")
print(f"Objects: {objects:,}")
print(f"Groups: {groups:,}")
print(f"Material switches: {materials:,}\n")

# Top objects by face count
print("Top 20 objects by face count:")
sorted_objects = sorted(object_faces.items(), key=lambda x: x[1], reverse=True)
for obj_name, count in sorted_objects[:20]:
    pct = (count / faces * 100) if faces > 0 else 0
    print(f"{count:8,} faces ({pct:5.1f}%): {obj_name}")