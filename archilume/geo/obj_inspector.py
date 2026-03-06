"""
obj_inspect.py — OBJ File Inspector

Parses a Wavefront .obj file and prints a summary:
1. File stats      — Size in MB and total line count.
2. Element counts  — Vertices, faces, normals, texture coords, objects, groups, material switches.
3. Bounding box    — Min/max extents and center point for X, Y, Z.
4. Face distribution — Top 20 named objects by face count with percentage of total.

Usage: Run directly as a script. Target file is set via config.INPUTS_DIR.
"""

import os
from archilume import config


class OBJInspector:
    def __init__(self, filepath):
        self.filepath = filepath
        self.vertices = 0
        self.faces = 0
        self.normals = 0
        self.textures = 0
        self.objects = 0
        self.groups = 0
        self.materials = 0
        self.lines_total = 0
        self.min_x = self.min_y = self.min_z = float("inf")
        self.max_x = self.max_y = self.max_z = float("-inf")
        self.object_faces = {}
        self.object_bytes = {}
        self.class_faces = {}
        self.class_bytes = {}
        self._current_object = "unnamed"
        self._current_class = "unnamed"

    def parse(self):
        with open(self.filepath, "r") as f:
            for line in f:
                self.lines_total += 1
                n = len(line.encode())
                self.object_bytes[self._current_object] = self.object_bytes.get(self._current_object, 0) + n
                self.class_bytes[self._current_class] = self.class_bytes.get(self._current_class, 0) + n
                self._process_line(line)

    def _process_line(self, line):
        if line.startswith("v "):
            self.vertices += 1
            parts = line.split()
            if len(parts) >= 4:
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                self.min_x, self.max_x = min(self.min_x, x), max(self.max_x, x)
                self.min_y, self.max_y = min(self.min_y, y), max(self.max_y, y)
                self.min_z, self.max_z = min(self.min_z, z), max(self.max_z, z)
        elif line.startswith("f "):
            self.faces += 1
            self.object_faces[self._current_object] = self.object_faces.get(self._current_object, 0) + 1
            self.class_faces[self._current_class] = self.class_faces.get(self._current_class, 0) + 1
        elif line.startswith("vn "):
            self.normals += 1
        elif line.startswith("vt "):
            self.textures += 1
        elif line.startswith("o "):
            self.objects += 1
            self._current_object = line.strip()[2:]
            self._current_class = self._current_object.split("/")[0]
            self.object_faces.setdefault(self._current_object, 0)
            self.object_bytes.setdefault(self._current_object, 0)
        elif line.startswith("g "):
            self.groups += 1
            name = line.strip()[2:]
            if name:
                self._current_object = name
                self._current_class = name.split("/")[0]
                self.object_faces.setdefault(self._current_object, 0)
                self.object_bytes.setdefault(self._current_object, 0)
        elif line.startswith("usemtl "):
            self.materials += 1

    def report(self):
        file_size_mb = os.path.getsize(self.filepath) / (1024 * 1024)
        print(f"File size: {file_size_mb:.2f} MB\n")
        print(f"Total lines: {self.lines_total:,}")
        print(f"Vertices:    {self.vertices:,}")
        print(f"Faces:       {self.faces:,}")
        print(f"Normals:     {self.normals:,}")
        print(f"Texture coords: {self.textures:,}")
        print(f"Objects:     {self.objects:,}")
        print(f"Groups:      {self.groups:,}")
        print(f"Material switches: {self.materials:,}\n")

        total_bytes = sum(self.object_bytes.values()) or 1

        print("By IFC class:")
        print(f"  {'Faces':>10}  {'% faces':>7}  {'MB':>8}  {'% size':>7}  Class")
        print(f"  {'-'*10}  {'-'*7}  {'-'*8}  {'-'*7}  {'-'*30}")
        for cls, count in sorted(self.class_faces.items(), key=lambda x: x[1], reverse=True):
            face_pct = (count / self.faces * 100) if self.faces > 0 else 0
            cls_mb = self.class_bytes.get(cls, 0) / (1024 * 1024)
            size_pct = self.class_bytes.get(cls, 0) / total_bytes * 100
            print(f"  {count:>10,}  {face_pct:>6.1f}%  {cls_mb:>8.2f}  {size_pct:>6.1f}%  {cls}")

        if self.vertices > 0:
            print("\nBounding Box:")
            print(f"  X: {self.min_x:.3f} to {self.max_x:.3f} (width: {self.max_x - self.min_x:.3f})")
            print(f"  Y: {self.min_y:.3f} to {self.max_y:.3f} (height: {self.max_y - self.min_y:.3f})")
            print(f"  Z: {self.min_z:.3f} to {self.max_z:.3f} (depth: {self.max_z - self.min_z:.3f})")
            cx = (self.min_x + self.max_x) / 2
            cy = (self.min_y + self.max_y) / 2
            cz = (self.min_z + self.max_z) / 2
            print(f"  Center: ({cx:.3f}, {cy:.3f}, {cz:.3f})")

        print(f"\nTop 100 groups by face count:")
        print(f"  {'Faces':>10}  {'% faces':>7}  {'MB':>8}  {'% size':>7}  Name")
        print(f"  {'-'*10}  {'-'*7}  {'-'*8}  {'-'*7}  {'-'*50}")
        for name, count in sorted(self.object_faces.items(), key=lambda x: x[1], reverse=True)[:100]:
            face_pct = (count / self.faces * 100) if self.faces > 0 else 0
            obj_mb = self.object_bytes.get(name, 0) / (1024 * 1024)
            size_pct = self.object_bytes.get(name, 0) / total_bytes * 100
            print(f"  {count:>10,}  {face_pct:>6.1f}%  {obj_mb:>8.2f}  {size_pct:>6.1f}%  {name}")


if __name__ == "__main__":
    filepath = config.INPUTS_DIR / "527DM" /"223181_AR_LOFTUS_BTR_cleaned_stripped_cleaned.obj"
    inspector = OBJInspector(filepath)
    inspector.parse()
    inspector.report()
