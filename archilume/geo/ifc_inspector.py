"""
ifc_inspector.py — IFC File Inspector

Parses an IFC file and prints a summary with schema-aware size attribution.
Size is attributed by walking each product element's full forward-reference
graph (geometry, materials, properties) and rolling bytes up through the IFC
schema inheritance hierarchy.

Sections:
1. File stats      — Size, line count, entity count, product count.
2. By IFC class    — IfcProduct subtypes sorted by attributed MB.
3. Unattributed    — Non-product entities whose bytes were not claimed by any product.
4. Top 100 largest — Biggest raw entity lines in the file.

Usage: Run directly as a script. Target file is set via config.INPUTS_DIR.
"""

import os
import re
from pathlib import Path

import ifcopenshell
import ifcopenshell.ifcopenshell_wrapper as ifc_wrapper

from archilume import config


class IFCInspector:
    def __init__(self, filepath):
        self.filepath = Path(filepath)
        self.ifc = None

        # Raw scan — all keyed by lowercase class name for consistency
        self.lines_total = 0
        self.total_entities = 0
        self.entity_bytes = {}   # eid (int) -> raw line byte size
        self.entity_refs = {}    # eid -> [referenced eids] (forward refs only)
        self.entity_class = {}   # eid -> class name (lowercase, matches ifc.is_a())

        # Schema
        self.subtypes_map = {}   # class name -> [direct subtype names]

        # Attribution
        self.direct_counts = {}          # class name -> direct instance count
        self.product_attr_bytes = {}     # class name -> attributed bytes (own + claimed refs)
        self.unclaimed_bytes = {}        # class name -> bytes not claimed by any product
        self.instance_names = {}         # eid -> Name string

    # ------------------------------------------------------------------
    # Phase 1: raw byte scan
    # ------------------------------------------------------------------
    def _raw_scan(self):
        # Match lines like: #123=IFCWALL(...)
        _eid_cls = re.compile(rb"^#(\d+)\s*=\s*([A-Z][A-Z0-9_]*)\s*\(")
        _ref_pat = re.compile(rb"#(\d+)")
        with open(self.filepath, "rb") as f:
            for line in f:
                self.lines_total += 1
                m = _eid_cls.match(line)
                if not m:
                    continue
                self.total_entities += 1
                eid = int(m.group(1))
                # IFC files use uppercase class names; ifcopenshell .is_a() returns mixed case.
                # Store as-parsed uppercase so we can normalise later via ifcopenshell.
                cls_upper = m.group(2).decode("ascii")
                sz = len(line)
                self.entity_bytes[eid] = sz
                self.entity_class[eid] = cls_upper  # temporary; replaced in _load_ifc
                # Extract forward references from the argument body only (after the opening '(')
                args_start = m.end() - 1  # position of '('
                refs = [int(r) for r in _ref_pat.findall(line, args_start)]
                self.entity_refs[eid] = refs

    # ------------------------------------------------------------------
    # Phase 2: ifcopenshell load — get canonical class names + Name attrs
    # ------------------------------------------------------------------
    def _load_ifc(self):
        self.ifc = ifcopenshell.open(str(self.filepath))
        # Replace uppercase raw class names with ifcopenshell canonical casing
        for eid in list(self.entity_class.keys()):
            try:
                el = self.ifc.by_id(eid)
                if el is not None:
                    self.entity_class[eid] = el.is_a()
                    name = getattr(el, "Name", None)
                    if name:
                        self.instance_names[eid] = name
            except Exception:
                pass

        # Count direct instances per class
        seen_classes = set(self.entity_class.values())
        for cls in seen_classes:
            try:
                self.direct_counts[cls] = len(self.ifc.by_type(cls, include_subtypes=False))
            except RuntimeError:
                self.direct_counts[cls] = 0

    # ------------------------------------------------------------------
    # Phase 3: build schema subtype map (canonical casing from schema)
    # ------------------------------------------------------------------
    def _build_schema(self):
        schema = ifc_wrapper.schema_by_name(self.ifc.schema)
        for entity in schema.declarations():
            if not hasattr(entity, "supertype"):
                continue
            sup = entity.supertype()
            parent = sup.name() if sup else None
            self.subtypes_map.setdefault(parent, []).append(entity.name())

    # ------------------------------------------------------------------
    # Phase 4: attribute bytes via reference-graph walk
    # ------------------------------------------------------------------
    def _attribute_bytes(self):
        try:
            all_products = self.ifc.by_type("IfcProduct", include_subtypes=True)
        except RuntimeError:
            return

        product_id_set = {el.id() for el in all_products}

        # Group product IDs by exact class
        products_by_class = {}
        for el in all_products:
            cls = el.is_a()
            products_by_class.setdefault(cls, []).append(el.id())

        # Walk forward refs from a product, collecting all reachable non-product entities.
        # Each entity is claimed by the first product that reaches it (no double-counting).
        claimed = set()

        def walk(start_eid):
            """Return set of non-product entity IDs reachable from start_eid (excl. self)."""
            collected = set()
            stack = list(self.entity_refs.get(start_eid, []))
            while stack:
                eid = stack.pop()
                if eid in collected or eid in claimed or eid in product_id_set:
                    continue
                collected.add(eid)
                refs = self.entity_refs.get(eid)
                if refs:
                    stack.extend(refs)
            return collected

        for cls, eids in products_by_class.items():
            own_bytes = sum(self.entity_bytes.get(eid, 0) for eid in eids)
            ref_bytes = 0
            for eid in eids:
                reachable = walk(eid)
                for ref_id in reachable:
                    claimed.add(ref_id)
                    ref_bytes += self.entity_bytes.get(ref_id, 0)
            self.product_attr_bytes[cls] = own_bytes + ref_bytes

        # Anything not claimed (and not a product itself) is "unattributed"
        for eid, sz in self.entity_bytes.items():
            if eid not in claimed and eid not in product_id_set:
                cls = self.entity_class.get(eid, "unknown")
                self.unclaimed_bytes[cls] = self.unclaimed_bytes.get(cls, 0) + sz

    # ------------------------------------------------------------------
    # Schema helpers
    # ------------------------------------------------------------------
    def _all_subtypes(self, root, result=None):
        if result is None:
            result = set()
        result.add(root)
        for child in self.subtypes_map.get(root, []):
            self._all_subtypes(child, result)
        return result

    # ------------------------------------------------------------------
    # Schema helpers — rolled-up totals
    # ------------------------------------------------------------------
    def _subtree_bytes(self, name, cache=None):
        """Sum attributed bytes for a class and all its schema descendants."""
        if cache is None:
            cache = {}
        if name in cache:
            return cache[name]
        total = self.product_attr_bytes.get(name, 0)
        for child in self.subtypes_map.get(name, []):
            total += self._subtree_bytes(child, cache)
        cache[name] = total
        return total

    def _subtree_count(self, name, cache=None):
        """Sum direct instance counts for a class and all its schema descendants."""
        if cache is None:
            cache = {}
        if name in cache:
            return cache[name]
        total = self.direct_counts.get(name, 0)
        for child in self.subtypes_map.get(name, []):
            total += self._subtree_count(child, cache)
        cache[name] = total
        return total

    def _has_any_data(self, name):
        """True if this class or any descendant has instances or attributed bytes."""
        if self.direct_counts.get(name, 0) > 0 or self.product_attr_bytes.get(name, 0) > 0:
            return True
        return any(self._has_any_data(c) for c in self.subtypes_map.get(name, []))

    # ------------------------------------------------------------------
    # Parse + Report
    # ------------------------------------------------------------------
    def parse(self):
        self._raw_scan()
        self._load_ifc()
        self._build_schema()
        self._attribute_bytes()

    def report(self, depth=3):
        """Print the inspection report.

        Args:
            depth: How many levels below IfcProduct to expand in the class tree.
                   depth=1 → only IfcProduct total
                   depth=2 → IfcElement, IfcAnnotation, IfcSpatialStructureElement …
                   depth=3 → IfcBuildingElement, IfcWall, IfcMember … (default)
                   depth=4 → IfcWallStandardCase, leaf classes
        """
        file_size_mb = os.path.getsize(self.filepath) / (1024 * 1024)
        total_bytes = sum(self.entity_bytes.values()) or 1

        print(f"File: {self.filepath.name}")
        print(f"File size:      {file_size_mb:.2f} MB")
        print(f"Total lines:    {self.lines_total:,}")
        print(f"Total entities: {self.total_entities:,}")

        try:
            total_products = len(self.ifc.by_type("IfcProduct", include_subtypes=True))
        except RuntimeError:
            total_products = 0
        print(f"Total products: {total_products:,}\n")

        # --- Hierarchical class table, depth-limited ---
        bytes_cache = {}
        count_cache = {}

        print(f"By IFC class (depth={depth}, attributed MB — own lines + referenced geometry/properties):")
        print(f"  {'Count':>8}  {'% count':>7}  {'MB':>8}  {'% size':>7}  Class")
        print(f"  {'-'*8}  {'-'*7}  {'-'*8}  {'-'*7}  {'-'*40}")

        def print_tree(name, level, current_depth):
            if not self._has_any_data(name):
                return
            indent = "  " * level
            if current_depth >= depth:
                # At the depth limit: roll up all descendants into this row
                rolled_bytes = self._subtree_bytes(name, bytes_cache)
                rolled_count = self._subtree_count(name, count_cache)
                if rolled_bytes == 0 and rolled_count == 0:
                    return
                cls_mb = rolled_bytes / (1024 * 1024)
                pct_count = rolled_count / total_products * 100 if total_products else 0
                pct_size = rolled_bytes / total_bytes * 100
                # Mark rolled-up rows with '+' if they have hidden children
                has_children = bool(self.subtypes_map.get(name))
                marker = "+" if has_children and current_depth == depth else " "
                print(f"  {rolled_count:>8,}  {pct_count:>6.1f}%  {cls_mb:>8.2f}  {pct_size:>6.1f}%  {indent}{marker}{name}")
            else:
                # Intermediate node: show rolled-up totals then recurse into children
                rolled_bytes = self._subtree_bytes(name, bytes_cache)
                rolled_count = self._subtree_count(name, count_cache)
                children = [c for c in self.subtypes_map.get(name, []) if self._has_any_data(c)]
                direct_count = self.direct_counts.get(name, 0)
                direct_bytes = self.product_attr_bytes.get(name, 0)
                # Only print this node if it has direct instances or multiple children to show
                if rolled_bytes > 0 or rolled_count > 0:
                    cls_mb = rolled_bytes / (1024 * 1024)
                    pct_count = rolled_count / total_products * 100 if total_products else 0
                    pct_size = rolled_bytes / total_bytes * 100
                    marker = "v" if children else " "
                    print(f"  {rolled_count:>8,}  {pct_count:>6.1f}%  {cls_mb:>8.2f}  {pct_size:>6.1f}%  {indent}{marker}{name}")
                for child in sorted(children, key=lambda c: self._subtree_bytes(c, bytes_cache), reverse=True):
                    print_tree(child, level + 1, current_depth + 1)

        print_tree("IfcProduct", 0, 1)

        # --- Unattributed (not claimed by any product) ---
        total_unclaimed_mb = sum(self.unclaimed_bytes.values()) / (1024 * 1024)
        print(f"\nUnattributed entities (shared / not reachable from any product): {total_unclaimed_mb:.2f} MB")
        print(f"  {'Count':>8}  {'MB':>8}  {'% size':>7}  Class")
        print(f"  {'-'*8}  {'-'*8}  {'-'*7}  {'-'*35}")
        for cls, b in sorted(self.unclaimed_bytes.items(), key=lambda x: x[1], reverse=True)[:30]:
            count = self.direct_counts.get(cls, 0)
            cls_mb = b / (1024 * 1024)
            pct_size = b / total_bytes * 100
            print(f"  {count:>8,}  {cls_mb:>8.2f}  {pct_size:>6.1f}%  {cls}")

        # --- Top 100 largest individual entity lines ---
        print(f"\nTop 100 largest individual entities by line size:")
        print(f"  {'Bytes':>8}  {'ID':>8}  {'Class':<40}  Name")
        print(f"  {'-'*8}  {'-'*8}  {'-'*40}  {'-'*30}")
        for eid, nbytes in sorted(self.entity_bytes.items(), key=lambda x: x[1], reverse=True)[:100]:
            cls = self.entity_class.get(eid, "?")
            name = self.instance_names.get(eid, "")
            print(f"  {nbytes:>8,}  #{eid:<8}  {cls:<40}  {name}")


if __name__ == "__main__":
    FILEPATH = config.INPUTS_DIR / "527DM" / "223181_AR_LOFTUS_BTR.ifc"
    DEPTH = 4  # 1=IfcProduct only  2=major groups  3=element classes  4=leaf classes


    inspector = IFCInspector(FILEPATH)
    inspector.parse()
    inspector.report(depth=DEPTH)
