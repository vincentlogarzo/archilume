# Working with Large OBJ Files in Boundary Editor

Quick reference guide for handling large building models efficiently.

## Quick Start

### Is Your OBJ File "Large"?

Check your file's complexity:

```bash
# Count cells in OBJ file (approximate)
grep -c "^f " your_model.obj
```

| Face Count | Category | Recommended Settings |
|------------|----------|---------------------|
| < 10,000 | Small | Use defaults |
| 10K - 50K | Medium | Use defaults (already optimized) |
| 50K - 200K | Large | Use `simplify_ratio=0.5` |
| > 200K | Very Large | Use aggressive settings below |

---

## Recommended Settings by File Size

### Small to Medium OBJ (< 50K cells) - DEFAULT

```python
from archilume.obj_boundary_editor import BoundaryEditor

# Just use defaults - already optimized!
editor = BoundaryEditor(obj_paths=["model.obj"])
editor.launch()
```

**Performance**: Instant loading, smooth interaction

---

### Large OBJ (50K - 200K cells)

```python
editor = BoundaryEditor(
    obj_paths=["large_building.obj"],
    simplify_ratio=0.5,        # Reduce to 50% of cells
    max_vertex_display=3000,   # Downsample display
)
editor.launch()
```

**What this does**:
- Reduces mesh complexity by half
- Limits vertex display for UI responsiveness
- Maintains full accuracy for boundary drawing

**Performance**: 3-8 second loading, smooth interaction

---

### Very Large OBJ (> 200K cells)

```python
editor = BoundaryEditor(
    obj_paths=["huge_complex.obj"],
    simplify_ratio=0.3,        # Keep only 30% of cells
    detect_floors=False,       # Skip automatic floor detection
    max_vertex_display=2000,   # Aggressive display downsampling
)
editor.launch()

# Manually set floor levels if needed
# editor.slicer.floor_levels = [0.0, 3.5, 7.0, 10.5]  # meters
```

**What this does**:
- Aggressive mesh reduction (70% fewer cells)
- Skips time-consuming floor detection
- Heavily downsamples vertex display

**Performance**: 5-15 second loading, responsive interaction

---

## Understanding the Parameters

### `simplify_ratio` - Mesh Decimation

**What it does**: Reduces polygon count using PyVista's decimation algorithm

**Values**:
- `None` (default): No simplification
- `0.8`: Keep 80% of cells (subtle reduction)
- `0.5`: Keep 50% of cells (balanced)
- `0.3`: Keep 30% of cells (aggressive)
- `0.1`: Keep 10% of cells (extreme, may lose detail)

**Trade-offs**:
- ✅ Faster loading, slicing, and rendering
- ✅ Lower memory usage
- ⚠️ May lose fine geometric details in complex curved surcells
- ✅ Does NOT affect boundary drawing accuracy (just visualization)

**Recommended**:
- Start with `0.5` for large files
- Increase to `0.7` if detail is lost
- Decrease to `0.3` if still slow

---

### `detect_floors` - Automatic Floor Detection

**What it does**: Analyzes mesh to find horizontal floor surcells

**Values**:
- `True` (default): Auto-detect floors on load
- `False`: Skip detection (faster loading)

**When to disable**:
- Very large meshes (>200K cells) where detection is slow
- Buildings with complex geometry (detection may be inaccurate)
- When you already know floor heights

**How to manually set floors** (if disabled):
```python
editor = BoundaryEditor(obj_paths=paths, detect_floors=False)
editor.launch()

# After launch, set manually (before using [ ] navigation)
editor.slicer.floor_levels = [0.0, 3.5, 7.0, 10.5, 14.0]  # in meters
editor.slicer.precache_floor_slices()  # Optional: pre-cache for speed
```

---

### `max_vertex_display` - Vertex Rendering Limit

**What it does**: Limits how many snap points are rendered as blue dots

**Values**:
- `5000` (default): Good balance
- `10000`: More detail, may slow rendering on dense slices
- `2000`: Faster rendering, fewer visible snap points
- `1000`: Very fast, minimal visual clutter

**Important**: This only affects *display*. Snapping still uses ALL vertices via KD-tree.

---

## Performance Optimization Checklist

If boundary editor is slow, try in this order:

1. ✅ **Add mesh simplification**
   ```python
   simplify_ratio=0.5
   ```

2. ✅ **Reduce vertex display threshold**
   ```python
   max_vertex_display=2000
   ```

3. ✅ **Skip floor detection**
   ```python
   detect_floors=False
   ```

4. ✅ **Close other applications** (free up RAM)

5. ✅ **Simplify OBJ in external tool** before importing
   - Use Blender's decimate modifier
   - Use MeshLab's quadric edge collapse

---

## Troubleshooting

### "Out of memory" errors

**Solution**: Increase `simplify_ratio` aggressively
```python
simplify_ratio=0.2  # Keep only 20% of cells
```

### Loading takes > 30 seconds

**Solutions**:
1. Enable simplification: `simplify_ratio=0.5`
2. Disable floor detection: `detect_floors=False`
3. Check if multiple large OBJs are being merged

### UI freezes when moving Z-slider

**Solutions**:
1. Slider is already debounced (200ms delay)
2. Reduce vertex display: `max_vertex_display=2000`
3. Increase simplification: `simplify_ratio=0.3`

### Floor detection finds wrong levels

**Solution**: Disable and set manually
```python
editor = BoundaryEditor(obj_paths=paths, detect_floors=False)
editor.launch()
editor.slicer.floor_levels = [0.0, 3.0, 6.0]  # Your known heights
```

### Slicing is slow even with optimizations

**Check**:
1. Are slices being cached? (Should see instant return on 2nd visit)
2. Is mesh simplified? (Check console output during load)
3. Try more aggressive simplification: `simplify_ratio=0.3`

---

## Advanced: Multi-Stage Workflow for Huge Models

For buildings too large even with all optimizations:

### Option 1: Split by Floor Range

```python
# Annotate floors 1-5
editor = BoundaryEditor(
    obj_paths=["building.obj"],
    simplify_ratio=0.5,
)
editor.launch()
# Draw rooms on floors 1-5, export, close

# Then floors 6-10
editor = BoundaryEditor(
    obj_paths=["building.obj"],
    simplify_ratio=0.5,
)
editor.launch()
# Manually adjust Z-slider to upper floors
# Draw rooms, export
```

### Option 2: Pre-process in Blender

```python
# 1. Open OBJ in Blender
# 2. Select mesh → Modifiers → Add Modifier → Decimate
# 3. Set Ratio to 0.5, Apply
# 4. File → Export → Wavefront (.obj)
# 5. Use simplified OBJ in boundary editor
```

### Option 3: Split OBJ by Building Section

If OBJ contains multiple buildings or zones:
1. Use Blender/MeshLab to separate into multiple OBJs
2. Annotate each section independently
3. Merge exported CSVs if needed

---

## Best Practices

### ✅ DO

- Start with default settings, only optimize if slow
- Use `simplify_ratio=0.5` as first optimization
- Pre-cache floor slices if you'll navigate between them frequently
- Save sessions often (Shift+S) - optimizations don't affect sessions

### ❌ DON'T

- Set `simplify_ratio` below 0.2 (too much detail loss)
- Disable vertex snapping to improve performance (KD-tree is already fast)
- Manually re-slice same Z heights (cache handles this automatically)

---

## Performance Monitoring

Watch the console output during launch:

```
Loading OBJ mesh(es)...
Simplifying mesh from 150,234 cells to 75,117 cells...  ← Simplification active
Mesh simplified to 75,117 cells (50.0% of original)
Mesh loaded: 75,117 cells, Z range [0.00, 42.50]m
Detecting floor levels...  ← May be slow if >100K cells
Detected 8 floor levels: ['0.00m', '3.50m', ...]
Pre-caching slices at 8 floor levels...  ← Preparing for instant navigation
Pre-cached 8 floor slices
```

**Good signs**:
- Load time < 10 seconds
- "Pre-cached N floor slices" appears
- Slider dragging is smooth

**Bad signs**:
- Load time > 30 seconds → increase `simplify_ratio`
- No "Simplifying mesh" message → add `simplify_ratio`
- "Detecting floor levels" hangs → set `detect_floors=False`

---

## Summary Table

| Optimization | When to Use | Impact |
|-------------|-------------|--------|
| `simplify_ratio=0.5` | >50K cells | 4-10x faster load |
| `simplify_ratio=0.3` | >200K cells | 10-30x faster load |
| `detect_floors=False` | >200K cells, complex geometry | 5-30s faster load |
| `max_vertex_display=2000` | Dense slices, UI lag | Smooth rendering |

**Default behavior** (no parameters): Already optimized with caching, KD-tree, and debouncing!
