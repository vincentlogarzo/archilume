"""
IFC file stripping utility for removing unwanted elements before daylight simulation.

This module contains:
- IfcStrip: Removes IFC elements by class, name pattern, or type pattern, with an
  optional tkinter tree viewer showing the class hierarchy and instance counts.

Strip unwanted elements from an IFC file.

See archilume/ifc_strip.py for full documentation.
Usage: python strip_ifc.py [input.ifc [output.ifc]]
       If no arguments are given, a file picker window opens.
"""

# Standard library imports
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# Third-party imports
import ifcopenshell
import ifcopenshell.ifcopenshell_wrapper as ifc_wrapper


from archilume import config


# Defaults
DEFAULT_CLASSES_TO_REMOVE = [
    "IfcDoor",
    "IfcOpeningElement",
    "IfcSpace",
    "IfcAnnotation",
    "IfcGrid",
    "IfcBuildingElementProxy",
    "IfcFurnishingElement",
    "IfcFurniture",
    "IfcDistributionElement",
]

DEFAULT_NAME_PATTERNS = [
    "demolish",
    "temp",
    "temporary",
    "existing",
]

DEFAULT_TYPE_PATTERNS = [
    "demo",
    "scaffold",
]

# Classes whose detailed FacetedBrep geometry will be replaced with a convex hull.
# These are elements that need to exist in the model for validity but whose exact
# surface geometry does not affect daylight simulation results.
DEFAULT_SIMPLIFY_CLASSES = [
    "IfcMember",
    "IfcPlate",
]


@dataclass
class IfcStrip:
    """
    Strips unwanted elements from an IFC file and saves a cleaned copy.

    Attributes:
        input_path (Path): Path to the source IFC file.
        output_path (Path): Path to write the stripped IFC file.
        classes_to_remove (List[str]): IFC class names to remove entirely.
        name_patterns (List[str]): Case-insensitive name substrings to match for removal.
        type_patterns (List[str]): Case-insensitive type name substrings to match for removal.

    Example:
        >>> s = IfcStrip(input_path=Path("model.ifc"))
        >>> s.run()
    """

    input_path: Path
    output_path: Optional[Path] = None
    classes_to_remove: List[str] = field(default_factory=lambda: list(DEFAULT_CLASSES_TO_REMOVE))
    name_patterns: List[str] = field(default_factory=lambda: list(DEFAULT_NAME_PATTERNS))
    type_patterns: List[str] = field(default_factory=lambda: list(DEFAULT_TYPE_PATTERNS))
    simplify_classes: List[str] = field(default_factory=lambda: list(DEFAULT_SIMPLIFY_CLASSES))
    simplify_deflection: float = 0.3  # mesher-linear-deflection: larger = coarser (fewer faces), smaller = finer

    # Internal state
    _ifc: object = field(init=False, repr=False, default=None)
    _total_removed: int = field(init=False, default=0)

    def __post_init__(self):
        self.input_path = Path(self.input_path)
        if not self.input_path.exists():
            raise FileNotFoundError(f"IFC file not found: {self.input_path}")
        if self.output_path is None:
            p = self.input_path
            self.output_path = p.with_name(p.stem + "_stripped" + p.suffix)
        self.output_path = Path(self.output_path)

    def load(self) -> None:
        """Open the IFC file."""
        self._ifc = ifcopenshell.open(str(self.input_path))

    def show_class_tree(self, run_fn=None) -> None:
        """Open a tkinter window showing the IFC class hierarchy with instance counts.

        Args:
            run_fn: Optional callable to execute in a background thread while the
                    window is open. Its return value is shown in the status bar when done.
        """
        import threading
        import tkinter as tk
        from tkinter import ttk

        if self._ifc is None:
            self.load()

        ifc_file = self._ifc
        schema = ifc_wrapper.schema_by_name(ifc_file.schema)

        counts = {}
        for entity in schema.declarations():
            if not hasattr(entity, 'supertype'):
                continue
            name = entity.name()
            try:
                counts[name] = len(ifc_file.by_type(name, include_subtypes=False))
            except Exception:
                counts[name] = 0

        def total_count(name):
            try:
                return len(ifc_file.by_type(name, include_subtypes=True))
            except Exception:
                return 0

        # Build subtypes map for fast child lookup
        subtypes_map: dict = {}
        for entity in schema.declarations():
            if not hasattr(entity, 'supertype'):
                continue
            sup = entity.supertype()
            parent_name = sup.name() if sup else None
            subtypes_map.setdefault(parent_name, []).append(entity.name())

        # Parse raw file: per-entity byte size and per-class totals
        # Also build entity_id -> owning product class for geometry attribution
        entity_bytes: dict = {}   # entity id (int) -> line byte size
        class_bytes: dict = {}    # UPPER class name -> total bytes (all instances)
        total_file_bytes: int = 0
        entity_refs: dict = {}    # entity id -> list of referenced entity ids (from raw parse)

        import re as _re
        _ref_pattern = _re.compile(rb"#(\d+)")

        with open(str(self.input_path), "rb") as _f:
            for _line in _f:
                total_file_bytes += len(_line)
                if not _line.startswith(b"#"):
                    continue
                _eq = _line.find(b"=")
                _paren = _line.find(b"(", _eq) if _eq != -1 else -1
                if _paren == -1:
                    continue
                try:
                    _eid = int(_line[1:_eq].strip())
                except ValueError:
                    continue
                _cls = _line[_eq + 1:_paren].decode("ascii", errors="ignore").strip().upper()
                _sz = len(_line)
                entity_bytes[_eid] = _sz
                class_bytes[_cls] = class_bytes.get(_cls, 0) + _sz
                # Parse references from the argument portion
                _args = _line[_paren:]
                entity_refs[_eid] = [int(m) for m in _ref_pattern.findall(_args)]

        total_file_mb = total_file_bytes / 1_000_000

        # Attribution computed in background thread after UI is shown
        _product_class_geo_bytes: dict = {}      # product class name -> total attributed bytes

        # Face counts computed lazily in a background thread after UI is shown
        import ifcopenshell.geom as _geom
        _tess = _geom.settings()
        _tess.set("mesher-linear-deflection", 0.3)
        _tess.set("mesher-angular-deflection", 0.15)
        _tess.set("use-world-coords", False)

        _face_cache: dict = {}       # class name -> avg face count (int)

        root = tk.Tk()
        root.title(f"IFC Strip — {self.input_path.name}")
        root.geometry("1300x800")

        # --- toolbar ---
        toolbar = tk.Frame(root)
        toolbar.pack(fill=tk.X, padx=8, pady=(8, 0))

        show_empty_var = tk.BooleanVar(value=False)
        # File size label — right-aligned in toolbar
        tk.Label(toolbar, text=f"File size: {total_file_mb:.1f} MB",
                 font=("TkDefaultFont", 9, "bold"), fg="#333").pack(side=tk.RIGHT, padx=8)

        # --- main area: tree left, filters right ---
        main = tk.Frame(root)
        main.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # Tree panel
        tree_frame = tk.Frame(main)
        tree_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tree = ttk.Treeview(tree_frame, columns=("direct", "total", "mb", "faces"), show="tree headings")
        tree.heading("#0", text="Class")
        tree.heading("direct", text="Direct")
        tree.heading("total", text="Total (inc. subtypes)")
        tree.heading("mb", text="MB in file")
        tree.heading("faces", text="Avg faces")
        tree.column("#0", width=260)
        tree.column("direct", width=55, anchor="center")
        tree.column("total", width=120, anchor="center")
        tree.column("mb", width=80, anchor="center")
        tree.column("faces", width=80, anchor="center")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Filter panel (right side) — scrollable canvas so all sections are reachable
        filter_outer = tk.Frame(main, width=340)
        filter_outer.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 0))
        filter_outer.pack_propagate(False)

        filter_canvas = tk.Canvas(filter_outer, width=320, highlightthickness=0)
        filter_scrollbar = ttk.Scrollbar(filter_outer, orient="vertical", command=filter_canvas.yview)
        filter_canvas.configure(yscrollcommand=filter_scrollbar.set)
        filter_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        filter_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        filter_frame = tk.LabelFrame(filter_canvas, text="Strip Filters", padx=6, pady=6)
        filter_canvas_window = filter_canvas.create_window((0, 0), window=filter_frame, anchor="nw")

        def _on_filter_configure(event):
            filter_canvas.configure(scrollregion=filter_canvas.bbox("all"))
            filter_canvas.itemconfig(filter_canvas_window, width=filter_canvas.winfo_width())

        filter_frame.bind("<Configure>", _on_filter_configure)
        filter_canvas.bind("<Configure>", lambda e: filter_canvas.itemconfig(
            filter_canvas_window, width=e.width))

        def make_list_editor(parent, label, initial_items):
            """Returns a frame with a labelled listbox + add/remove controls."""
            lf = tk.LabelFrame(parent, text=label, padx=4, pady=4)
            lf.pack(fill=tk.X, pady=(0, 8))

            lb = tk.Listbox(lf, height=5, selectmode=tk.EXTENDED, exportselection=False)
            for item in initial_items:
                lb.insert(tk.END, item)
            lb.pack(fill=tk.X)

            entry_var = tk.StringVar()
            entry = tk.Entry(lf, textvariable=entry_var)
            entry.pack(fill=tk.X, pady=(2, 0))

            btn_row = tk.Frame(lf)
            btn_row.pack(fill=tk.X)

            def add_item():
                val = entry_var.get().strip()
                if val and val not in lb.get(0, tk.END):
                    lb.insert(tk.END, val)
                    entry_var.set("")

            def remove_selected():
                for i in reversed(lb.curselection()):
                    lb.delete(i)

            def add_from_tree():
                sel = tree.selection()
                for item in sel:
                    val = tree.item(item, "text")
                    if val and val not in lb.get(0, tk.END):
                        lb.insert(tk.END, val)

            tk.Button(btn_row, text="Add", command=add_item, width=6).pack(side=tk.LEFT)
            tk.Button(btn_row, text="Remove", command=remove_selected, width=8).pack(side=tk.LEFT)
            if label == "Classes to Remove":
                tk.Button(btn_row, text="← From tree", command=add_from_tree,
                          width=10).pack(side=tk.LEFT)

            return lb

        classes_lb = make_list_editor(filter_frame, "Classes to Remove", self.classes_to_remove)
        # --- Simplify geometry panel ---
        simplify_frame = tk.LabelFrame(filter_frame, text="Simplify Geometry", padx=4, pady=4)
        simplify_frame.pack(fill=tk.X, pady=(0, 8))

        simplify_enabled_var = tk.BooleanVar(value=bool(self.simplify_classes))

        def _toggle_simplify():
            state = tk.NORMAL if simplify_enabled_var.get() else tk.DISABLED
            simplify_lb.config(state=state)
            simplify_entry.config(state=state)
            defl_slider.config(state=state)

        tk.Checkbutton(simplify_frame, text="Enable simplification",
                       variable=simplify_enabled_var, command=_toggle_simplify).pack(anchor=tk.W)

        simplify_lb = tk.Listbox(simplify_frame, height=5, selectmode=tk.EXTENDED, exportselection=False)
        for item in self.simplify_classes:
            simplify_lb.insert(tk.END, item)
        simplify_lb.pack(fill=tk.X)

        simplify_entry_var = tk.StringVar()
        simplify_entry = tk.Entry(simplify_frame, textvariable=simplify_entry_var)
        simplify_entry.pack(fill=tk.X, pady=(2, 0))

        simplify_btn_row = tk.Frame(simplify_frame)
        simplify_btn_row.pack(fill=tk.X)

        def _simplify_add():
            val = simplify_entry_var.get().strip()
            if val and val not in simplify_lb.get(0, tk.END):
                simplify_lb.insert(tk.END, val)
                simplify_entry_var.set("")

        def _simplify_remove():
            for idx in reversed(simplify_lb.curselection()):
                simplify_lb.delete(idx)

        def _simplify_from_tree():
            for item in tree.selection():
                val = tree.item(item, "text")
                if val and val not in simplify_lb.get(0, tk.END):
                    simplify_lb.insert(tk.END, val)

        tk.Button(simplify_btn_row, text="Add", command=_simplify_add, width=6).pack(side=tk.LEFT)
        tk.Button(simplify_btn_row, text="Remove", command=_simplify_remove, width=8).pack(side=tk.LEFT)
        tk.Button(simplify_btn_row, text="← From tree", command=_simplify_from_tree, width=10).pack(side=tk.LEFT)

        # Deflection slider: 0.05 (fine) → 1.0 (coarse)
        defl_row = tk.Frame(simplify_frame)
        defl_row.pack(fill=tk.X, pady=(6, 0))
        tk.Label(defl_row, text="Mesh detail:").pack(side=tk.LEFT)
        tk.Label(defl_row, text="Fine", fg="gray").pack(side=tk.LEFT, padx=(4, 0))
        defl_var = tk.DoubleVar(value=self.simplify_deflection)
        defl_slider = tk.Scale(
            simplify_frame, variable=defl_var,
            from_=0.05, to=1.0, resolution=0.05,
            orient=tk.HORIZONTAL, showvalue=True,
            label="Linear deflection (larger = coarser)",
        )
        defl_slider.pack(fill=tk.X)
        tk.Label(simplify_frame, text="  ← Fine detail          Coarse / boxy →",
                 fg="gray", font=("TkDefaultFont", 8)).pack()

        def read_filters():
            self.classes_to_remove = list(classes_lb.get(0, tk.END))
            if simplify_enabled_var.get():
                self.simplify_classes = list(simplify_lb.get(0, tk.END))
                self.simplify_deflection = defl_var.get()
            else:
                self.simplify_classes = []

        inserted = {}

        def has_any_instances(name):
            if total_count(name) > 0:
                return True
            for child in subtypes_map.get(name, []):
                if has_any_instances(child):
                    return True
            return False

        # Queue of (class_name, node_id) pairs needing face-count computation
        _pending_faces: list = []

        def _subtree_mb(name):
            """Sum raw class-line bytes for this class and all schema subtypes (fast, no geo)."""
            total = class_bytes.get(name.upper(), 0)
            for child in subtypes_map.get(name, []):
                total += _subtree_mb(child)
            return total

        def insert_node(name, parent_id=""):
            if name in inserted:
                return inserted[name]
            d = counts.get(name, 0)
            t = total_count(name)
            # Initial MB from raw class-line bytes only (geo attribution added async)
            mb = _subtree_mb(name) / 1_000_000
            tag = "has_instances" if t > 0 else "empty"
            mb_str = f"{mb:.2f}" if mb >= 0.01 else ""
            node_id = tree.insert(parent_id, "end", text=name,
                                  values=(d if d else "", t if t else "", mb_str, "…" if d > 0 else ""),
                                  tags=(tag,), open=(t > 0))
            inserted[name] = node_id
            if d > 0:
                _pending_faces.append((name, node_id))
            return node_id

        def insert_tree(name, parent_id=""):
            if not show_empty_var.get() and not has_any_instances(name):
                return
            node_id = insert_node(name, parent_id)
            for child in subtypes_map.get(name, []):
                insert_tree(child, node_id)

        _bg_worker_stop = threading.Event()

        def rebuild_tree():
            _bg_worker_stop.set()
            tree.delete(*tree.get_children())
            inserted.clear()
            _pending_faces.clear()
            _bg_worker_stop.clear()
            _product_class_geo_bytes.clear()
            insert_tree("IfcProduct")
            _start_bg_workers()

        def _start_bg_workers():
            """Spawn background threads for face counts and MB attribution."""
            work = list(_pending_faces)      # snapshot current queue

            # --- Face count worker ---
            def _face_worker():
                for class_name, node_id in work:
                    if _bg_worker_stop.is_set():
                        return
                    if class_name in _face_cache:
                        avg = _face_cache[class_name]
                    else:
                        try:
                            elements = ifc_file.by_type(class_name, include_subtypes=False)
                        except RuntimeError:
                            _face_cache[class_name] = 0
                            avg = 0
                        else:
                            sample = elements[:10]
                            totals = []
                            for el in sample:
                                if _bg_worker_stop.is_set():
                                    return
                                try:
                                    shape = _geom.create_shape(_tess, el)
                                    totals.append(len(shape.geometry.faces) // 3)
                                except Exception:
                                    pass
                            avg = int(sum(totals) / len(totals)) if totals else 0
                            _face_cache[class_name] = avg

                    faces_str = str(avg) if avg else "—"
                    _nid = node_id
                    _fs = faces_str
                    def _apply(nid=_nid, fs=_fs):
                        try:
                            vals = list(tree.item(nid, "values"))
                            if len(vals) >= 4:
                                vals[3] = fs
                                tree.item(nid, values=vals)
                        except Exception:
                            pass
                    root.after(0, _apply)

            # --- MB attribution worker: walk entity graph in background ---
            def _mb_worker():
                _claimed: set = set()

                # Collect product element IDs by class
                product_ids_by_class: dict = {}
                try:
                    all_products = ifc_file.by_type("IfcProduct", include_subtypes=True)
                    product_id_set = {el.id() for el in all_products}
                except RuntimeError:
                    product_id_set = set()

                for pclass_name, pclass_count in counts.items():
                    if pclass_count == 0:
                        continue
                    try:
                        elements = ifc_file.by_type(pclass_name, include_subtypes=False)
                    except RuntimeError:
                        continue
                    eids = [el.id() for el in elements if el.id() in product_id_set]
                    if eids:
                        product_ids_by_class[pclass_name] = eids

                def walk_refs(start_eid, collected):
                    stack = [start_eid]
                    while stack:
                        eid = stack.pop()
                        if eid in collected or eid in _claimed:
                            continue
                        collected.add(eid)
                        refs = entity_refs.get(eid)
                        if refs:
                            stack.extend(refs)

                for pclass_name, eids in product_ids_by_class.items():
                    if _bg_worker_stop.is_set():
                        return
                    total_geo = 0
                    for eid in eids:
                        collected: set = set()
                        walk_refs(eid, collected)
                        collected.discard(eid)
                        for ref_id in collected:
                            if ref_id not in _claimed:
                                _claimed.add(ref_id)
                                total_geo += entity_bytes.get(ref_id, 0)
                    _product_class_geo_bytes[pclass_name] = total_geo

                # Recompute MB for all tree nodes and update the MB column
                if _bg_worker_stop.is_set():
                    return

                mb_cache: dict = {}
                def attributed_mb(name):
                    if name in mb_cache:
                        return mb_cache[name]
                    own = class_bytes.get(name.upper(), 0)
                    geo = _product_class_geo_bytes.get(name, 0)
                    total = (own + geo) / 1_000_000
                    for child in subtypes_map.get(name, []):
                        total += attributed_mb(child)
                    mb_cache[name] = total
                    return total

                def _update_mb():
                    for name, node_id in inserted.items():
                        mb = attributed_mb(name)
                        mb_str = f"{mb:.2f}" if mb >= 0.01 else ""
                        try:
                            vals = list(tree.item(node_id, "values"))
                            if len(vals) >= 3:
                                vals[2] = mb_str
                                tree.item(node_id, values=vals)
                        except Exception:
                            pass
                root.after(0, _update_mb)

            threading.Thread(target=_face_worker, daemon=True).start()
            threading.Thread(target=_mb_worker, daemon=True).start()

        rebuild_tree()

        tk.Checkbutton(toolbar, text="Show empty classes", variable=show_empty_var,
                       command=rebuild_tree).pack(side=tk.LEFT)

        tree.tag_configure("has_instances", foreground="green")
        tree.tag_configure("empty", foreground="gray")


        status_var = tk.StringVar(value="Green = has instances  |  Gray = empty  "
                                        "|  Select a tree row then '← From tree' to add to filter")
        tk.Label(root, textvariable=status_var, fg="gray").pack(pady=(0, 2))

        progress_var = tk.DoubleVar(value=0.0)
        progress_bar = ttk.Progressbar(root, variable=progress_var, maximum=100,
                                       mode="determinate", length=400)
        progress_bar.pack(pady=(0, 4))

        if run_fn is not None:
            run_btn = tk.Button(root, text="Run Strip", bg="#d9534f", fg="white",
                                font=("TkDefaultFont", 11, "bold"), pady=6)

            def _on_run():
                read_filters()
                run_btn.config(state=tk.DISABLED, text="Running...")
                progress_var.set(0.0)
                status_var.set("Running strip operation...")

                def _ui(pct: float, msg: str = ""):
                    """Schedule a UI update safely onto the main thread."""
                    def _apply():
                        progress_var.set(pct)
                        if msg:
                            status_var.set(msg)
                    root.after(0, _apply)

                def _worker():
                    try:
                        result = self.run(progress_cb=_ui)
                        root.after(0, lambda: progress_var.set(100.0))
                        root.after(0, lambda: run_btn.config(text="Done"))
                        root.after(0, lambda: status_var.set(
                            f"Done — {result} elements removed. "
                            f"Output: {self.output_path.name}"
                        ))
                    except Exception as exc:
                        msg = f"Error: {exc}"
                        root.after(0, lambda: run_btn.config(state=tk.NORMAL, text="Run Strip"))
                        root.after(0, lambda m=msg: status_var.set(m))

                threading.Thread(target=_worker, daemon=True).start()

            run_btn.config(command=_on_run)
            run_btn.pack(pady=(0, 8))

        root.mainloop()

    def run(self, progress_cb=None) -> int:
        """
        Execute the strip operation and save the output file.

        Args:
            progress_cb: Optional callable(pct: float, msg: str) called during processing.

        Returns:
            int: Total number of elements removed.
        """
        if self._ifc is None:
            self.load()

        def _cb(pct, msg=""):
            if progress_cb:
                progress_cb(pct, msg)

        print("=" * 50)
        print(f"IFC Cleanup: {self.input_path.name}")
        print("=" * 50)

        self._total_removed = 0

        import time as _time

        _cb(0, "Removing by class...")
        print("\n[Phase 1/5] Removing by class...")
        _t0 = _time.monotonic()
        self._total_removed += self._remove_by_classes(progress_cb=progress_cb, pct_start=0, pct_end=40)
        print(f"  Done in {_time.monotonic() - _t0:.1f}s")

        _cb(40, "Removing by name pattern...")
        print("\n[Phase 2/5] Removing by name pattern...")
        _t0 = _time.monotonic()
        self._total_removed += self._remove_by_name_patterns(progress_cb=progress_cb, pct_start=40, pct_end=70)
        print(f"  Done in {_time.monotonic() - _t0:.1f}s")

        _cb(70, "Removing by type pattern...")
        print("\n[Phase 3/5] Removing by type pattern...")
        _t0 = _time.monotonic()
        self._total_removed += self._remove_by_type_patterns(progress_cb=progress_cb, pct_start=70, pct_end=80)
        print(f"  Done in {_time.monotonic() - _t0:.1f}s")

        if self.simplify_classes:
            _cb(80, "Simplifying geometry (mesh re-tessellation)...")
            print("\n[Phase 4/5] Simplifying geometry...")
            _t0 = _time.monotonic()
            simplified = self._simplify_geometry(progress_cb=progress_cb, pct_start=80, pct_end=88)
            print(f"  Simplified {simplified} elements in {_time.monotonic() - _t0:.1f}s")
        else:
            _cb(80, "Simplify: skipped (no classes selected)")
            print("\n[Phase 4/5] Simplify geometry: skipped (no classes selected).")

        _cb(88, "Purging orphaned geometry and materials...")
        print("\n[Phase 5/5] Purging orphaned entities...")
        _t0 = _time.monotonic()
        purged = self._purge_unused()
        print(f"  Purged {purged} entities in {_time.monotonic() - _t0:.1f}s")

        _cb(95, "Writing output file...")
        self._ifc.write(str(self.output_path))
        print(f"Saved to: {self.output_path}")

        print("=" * 50)
        print(f"Total removed: {self._total_removed}")
        print("=" * 50)

        return self._total_removed

    def _remove_by_classes(self, progress_cb=None, pct_start=0, pct_end=40) -> int:
        total = 0
        classes = self.classes_to_remove
        n = len(classes) or 1
        for i, class_name in enumerate(classes):
            pct = pct_start + (pct_end - pct_start) * i / n
            if progress_cb:
                progress_cb(pct, f"Class: {class_name}")
            try:
                elements = self._ifc.by_type(class_name)
            except RuntimeError:
                continue
            count = len(elements)
            for element in elements:
                try:
                    self._ifc.remove(element)
                except Exception:
                    pass
            if count > 0:
                print(f"Removed {count} x {class_name}")
            total += count
        return total

    def _remove_by_name_patterns(self, progress_cb=None, pct_start=40, pct_end=70) -> int:
        count = 0
        if not self.name_patterns:
            print("Name pattern removal: skipped (no patterns)")
            return 0
        print("Scanning remaining products for name patterns...")
        elements = list(self._ifc.by_type("IfcProduct"))
        n = len(elements) or 1
        for i, element in enumerate(elements):
            if i % 500 == 0 and progress_cb:
                pct = pct_start + (pct_end - pct_start) * i / n
                progress_cb(pct, f"Name patterns: {i}/{n} elements")
            if element.Name:
                name_lower = element.Name.lower()
                if any(p.lower() in name_lower for p in self.name_patterns):
                    try:
                        self._ifc.remove(element)
                        count += 1
                    except Exception:
                        pass
        if count > 0:
            print(f"Removed {count} elements matching name patterns")
        return count

    def _remove_by_type_patterns(self, progress_cb=None, pct_start=70, pct_end=80) -> int:
        count = 0
        if not self.type_patterns:
            print("Type pattern removal: skipped (no patterns)")
            return 0
        print("Scanning remaining products for type patterns...")
        elements = list(self._ifc.by_type("IfcProduct"))
        n = len(elements) or 1
        for i, element in enumerate(elements):
            if i % 500 == 0 and progress_cb:
                pct = pct_start + (pct_end - pct_start) * i / n
                progress_cb(pct, f"Type patterns: {i}/{n} elements")
            if hasattr(element, 'IsTypedBy') and element.IsTypedBy:
                for rel in element.IsTypedBy:
                    type_obj = rel.RelatingType
                    if type_obj.Name:
                        type_name_lower = type_obj.Name.lower()
                        if any(p.lower() in type_name_lower for p in self.type_patterns):
                            try:
                                self._ifc.remove(element)
                                count += 1
                                break
                            except Exception:
                                pass
        if count > 0:
            print(f"Removed {count} elements matching type patterns")
        return count

    def _simplify_geometry(self, progress_cb=None, pct_start=80, pct_end=88) -> int:
        """Replace detailed geometry with a re-tessellated mesh at a coarser resolution.

        Uses ifcopenshell.geom.iterator for multithreaded tessellation (the C++
        kernel parallelises across CPU cores), then writes simplified meshes back.

        simplify_deflection controls the linear deflection used during tessellation:
          - 0.05 = fine   (~same as default authoring tools)
          - 0.3  = medium (default, good balance for daylight simulation)
          - 1.0  = coarse (boxy approximation, maximum size reduction)

        Returns:
            int: Number of elements whose geometry was simplified.
        """
        import multiprocessing
        import numpy as np
        import ifcopenshell.geom as geom
        import ifcopenshell.api.geometry

        ifc = self._ifc

        # Build tessellation settings
        tess_settings = geom.settings()
        tess_settings.set("mesher-linear-deflection", self.simplify_deflection)
        tess_settings.set("mesher-angular-deflection", self.simplify_deflection * 0.5)
        tess_settings.set("use-world-coords", False)
        tess_settings.set("weld-vertices", True)

        # Find Body representation context
        context = None
        for ctx in ifc.by_type("IfcGeometricRepresentationSubContext"):
            if getattr(ctx, "ContextIdentifier", None) == "Body":
                context = ctx
                break
        if context is None:
            for ctx in ifc.by_type("IfcGeometricRepresentationContext"):
                if getattr(ctx, "ContextType", None) == "Model":
                    context = ctx
                    break
        if context is None:
            for ctx in ifc.by_type("IfcGeometricRepresentationContext"):
                context = ctx
                break

        all_elements = []
        for cls in self.simplify_classes:
            try:
                all_elements.extend(ifc.by_type(cls, include_subtypes=True))
            except RuntimeError:
                pass

        # Filter to elements that actually have geometry
        all_elements = [
            el for el in all_elements
            if hasattr(el, "Representation") and el.Representation
        ]

        n = len(all_elements) or 1
        simplified = 0

        if not all_elements:
            return 0

        # Phase 1: Parallel tessellation using ifcopenshell.geom.iterator
        # This uses the C++ OCCT kernel across multiple threads.
        if progress_cb:
            progress_cb(pct_start, f"Tessellating {n} elements (parallel)...")

        num_threads = max(1, multiprocessing.cpu_count())
        element_ids = [el.id() for el in all_elements]
        # iterator with include/exclude filter
        it = geom.iterator(tess_settings, ifc, num_threads, include=all_elements)

        # Collect tessellated results: element_id -> (verts, faces)
        tessellated: dict = {}
        if it.initialize():
            done = 0
            while True:
                shape = it.get()
                eid = shape.id
                geo = shape.geometry
                verts_flat = geo.verts
                faces_flat = geo.faces
                if verts_flat and faces_flat:
                    verts = np.array(verts_flat).reshape(-1, 3).tolist()
                    faces = np.array(faces_flat).reshape(-1, 3).tolist()
                    tessellated[eid] = (verts, faces)
                done += 1
                if done % 200 == 0 and progress_cb:
                    pct = pct_start + (pct_end - pct_start) * 0.7 * done / n
                    progress_cb(pct, f"Tessellated: {done}/{n}")
                if not it.next():
                    break

        if progress_cb:
            progress_cb(pct_start + (pct_end - pct_start) * 0.7,
                        f"Tessellated {len(tessellated)}/{n}. Replacing geometry...")

        # Phase 2: Replace geometry (sequential — modifies the IFC model)
        for i, element in enumerate(all_elements):
            eid = element.id()
            if eid not in tessellated:
                continue

            verts, faces = tessellated[eid]

            if i % 200 == 0 and progress_cb:
                pct = pct_start + (pct_end - pct_start) * (0.7 + 0.3 * i / n)
                progress_cb(pct, f"Replacing geometry: {i}/{n}")

            # Remove existing Body representations
            body_reps = [
                rep for rep in element.Representation.Representations
                if getattr(rep, "RepresentationIdentifier", None) == "Body"
            ]
            for rep in body_reps:
                remaining = [r for r in element.Representation.Representations if r != rep]
                element.Representation.Representations = remaining
                try:
                    ifcopenshell.api.geometry.remove_representation(ifc, representation=rep)
                except Exception:
                    pass

            # Write back the simplified mesh
            try:
                new_rep = ifcopenshell.api.geometry.add_mesh_representation(
                    ifc,
                    context=context,
                    vertices=[verts],
                    faces=[faces],
                )
                element.Representation.Representations = (
                    list(element.Representation.Representations) + [new_rep]
                )
                simplified += 1
            except Exception:
                pass

        return simplified

    def _purge_unused(self) -> int:
        """Remove entities that are no longer referenced by anything in the model.

        Targets geometry and material classes that are commonly orphaned after
        element removal: representations, shapes, points, curves, materials, and
        property sets.

        Returns:
            int: Number of entities removed.
        """
        PURGEABLE = {
            "IfcShapeRepresentation",
            "IfcRepresentationMap",
            "IfcFaceBasedSurfaceModel",
            "IfcShellBasedSurfaceModel",
            "IfcGeometricRepresentationItem",
            "IfcMaterial",
            "IfcMaterialList",
            "IfcMaterialLayerSet",
            "IfcMaterialLayer",
            "IfcMaterialConstituentSet",
            "IfcMaterialConstituent",
            "IfcPropertySet",
            "IfcRelDefinesByProperties",
        }
        removed = 0
        for class_name in PURGEABLE:
            try:
                candidates = list(self._ifc.by_type(class_name, include_subtypes=False))
            except RuntimeError:
                continue
            for entity in candidates:
                try:
                    if self._ifc.get_total_inverses(entity) == 0:
                        self._ifc.remove(entity)
                        removed += 1
                except Exception:
                    pass
        return removed

if __name__ == "__main__":
    import sys
    from pathlib import Path

    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
        output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    else:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        selected = filedialog.askopenfilename(
            title="Select IFC file to strip",
            initialdir=config.INPUTS_DIR,
            filetypes=[("IFC files", "*.ifc"), ("All files", "*.*")],
        )
        if not selected:
            print("No file selected.")
            sys.exit(0)
        input_path = Path(selected)
        output_path = None  # IfcStrip will default to _stripped suffix

    stripper = IfcStrip(input_path=input_path, output_path=output_path)
    stripper.load()
    stripper.show_class_tree(run_fn=stripper.run)  # strip runs in background while tree is open


# TODO: determine if output file can be written iteratively, it currently holds it all in memory untill complete and then writes the file at the end.

    # In IFC, doors create holes in walls through IfcOpeningElement entities. The relationship chain is:
    # IfcWall → IfcRelVoidsElement → IfcOpeningElement → IfcRelFillsElement → IfcDoor
    # If you remove only the IfcDoor, the IfcOpeningElement still exists — the wall still has a void/hole, just with nothing filling it. The wall geometry remains voided.

    # If you remove both IfcDoor and IfcOpeningElement (which is the current default — IfcOpeningElement is in DEFAULT_CLASSES_TO_REMOVE), then the IfcRelVoidsElement relationship is orphaned or removed too, and the wall's original solid geometry is restored — no hole.

    # So with your current defaults: walls become solid when doors are removed, because IfcOpeningElement is also stripped. If you were to add IfcDoor to the remove list but keep IfcOpeningElement off it, you'd get empty holes.

    # Please make this change, i would like door to be removed, and its ifcopening element remove instead of it currently being decimated which is taking ages.

