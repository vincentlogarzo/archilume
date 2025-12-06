# Archilume

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> A Python library for Radiance-based daylight analysis, providing streamlined tools for architectural lighting simulation and environmental performance assessment.

## Features

- **3D Model Conversion** - Convert OBJ/MTL building models to Radiance octree format with automatic material processing
- **Sky Generation** - Create physically accurate sky models for any date, time, and geographic location
- **View Setup** - Generate camera view parameters for interior and exterior analysis
- **GPU Acceleration** - Optional Accelerad integration for 10-50x faster rendering with NVIDIA GPUs
- **Image Processing** - Advanced rendering pipelines with automated post-processing capabilities
- **Parallel Execution** - Multi-core processing support for computationally intensive simulations
- **Seasonal Analysis** - Pre-configured workflows for solstice studies and annual daylight assessments

## Limitations

⚠️ **This repository is not appropriate for use with large buildings containing many curved surfaces.** The current implementation is optimized for smaller to medium-sized buildings with primarily planar geometry. Complex curved geometries may result in:
- Excessive computation times
- High memory usage
- Reduced accuracy in mesh conversion and rendering

For projects with extensive curved surfaces or very large building models, consider using specialized Radiance workflows or simplified geometric representations.

## Quick Start

### Prerequisites

- **Python 3.12+** - [Download Python](https://www.python.org/downloads/)
- **Radiance** - [Install Radiance](https://www.radiance-online.org/)
- **Accelerad** (Optional) - [Install Accelerad](https://nljones.github.io/Accelerad/) for GPU-accelerated rendering

#### Windows Installation

**Radiance Setup**

Radiance must be installed to `C:\Radiance\bin\`. If you encounter "Warning! PATH too long" during installation, manually set environment variables:

```cmd
setx PATH "%PATH%;C:\Radiance\bin"
setx RAYPATH "C:\Radiance\lib"
```

**Accelerad Setup (Optional - GPU Rendering)**

For GPU-accelerated rendering, install Accelerad to `C:\Program Files\Accelerad\`. After installation, update the RAYPATH environment variable to include both Radiance and Accelerad libraries:

```cmd
setx RAYPATH "C:\Radiance\lib;C:\Program Files\Accelerad\lib"
```

**Important**: Accelerad requires NVIDIA GPU with CUDA support. Verify your system meets these requirements:
- NVIDIA GPU with compute capability 5.0 or higher
- NVIDIA display drivers with CUDA support (12.0+)
- OptiX 6.x or higher (usually included with display drivers)

To verify Accelerad installation, run:
```cmd
accelerad_rpict -version
```

### Installation

```bash
# Clone the repository
git clone https://github.com/vincentlogarzo/archilume.git
cd archilume

# Install in development mode
pip install -e .

# Optional: Install with development tools
pip install -e ".[dev]"
```

### Basic Usage

```python
from archilume.obj_to_octree import ObjToOctree
from archilume.sky_generator import SkyGenerator

# Convert 3D model to Radiance format
octree = ObjToOctree(['building.obj'], ['building.mtl'])
octree.create_skyless_octree_for_sunlight_analysis()

# Generate sky files for analysis
sky_gen = SkyGenerator(lat=-37.8136)  # Melbourne
sky_gen.generate_sunny_sky_series(
    month=6, day=21,  # Winter solstice
    start_hour_24hr_format=9,
    end_hour_24hr_format=17
)
```

## Project Structure

```
archilume/
├── archilume/                       # Core package
│   ├── obj_to_octree.py            # 3D model → Radiance conversion
│   ├── sky_generator.py            # Sky condition generation
│   ├── view_generator.py           # Camera view setup
│   ├── rendering_pipelines.py      # Rendering workflows
│   ├── image_processor.py          # Post-processing utilities
│   ├── geometry_utils.py           # Geometric calculations
│   └── utils.py                    # Helper functions & parallel processing
│
├── examples/                        # Example workflows
│   ├── sunlight_exposure_analysis.py
│   └── summer_solstice_solar_gains.py
│
├── tests/                           # Test suite
│
└── intermediates/                   # Generated files (gitignored)
    ├── octrees/                    # Radiance scene files
    ├── sky/                        # Sky condition files
    └── views/                      # Camera parameters
```

## API Reference

### ObjToOctree

Converts 3D building models from OBJ format to Radiance octree format.

```python
from archilume.obj_to_octree import ObjToOctree

octree_generator = ObjToOctree(
    obj_file_paths=['building.obj'],
    mtl_file_paths=['building.mtl']
)
octree_generator.create_skyless_octree_for_sunlight_analysis()
```

### SkyGenerator

Generates Radiance sky files for specific dates, times, and geographic locations.

```python
from archilume.sky_generator import SkyGenerator

sky_generator = SkyGenerator(lat=-37.8136)  # Latitude in decimal degrees

sky_generator.generate_sunny_sky_series(
    month=6, day=21,                    # Date for analysis
    start_hour_24hr_format=9,           # Start time (24hr)
    end_hour_24hr_format=17,            # End time (24hr)
    minute_increment=60                 # Time step (default: 5 minutes)
)
```

### ViewGenerator

Creates view parameter files for rendering analysis points.

```python
from archilume.view_generator import ViewGenerator

view_generator = ViewGenerator(
    room_boundaries_csv_path='rooms.csv',
    output_dir='intermediates/views'
)
view_generator.create_aoi_and_view_files()
```

## Examples

See the [examples](examples/) directory for complete workflows:

- **[sunlight_exposure_analysis.py](examples/sunlight_exposure_analysis.py)** - Comprehensive sunlight analysis with hourly sky generation
- **[summer_solstice_solar_gains.py](examples/summer_solstice_solar_gains.py)** - Solar heat gain calculations for peak summer conditions

### Basic Workflow

```python
from archilume.obj_to_octree import ObjToOctree
from archilume.sky_generator import SkyGenerator
from archilume.view_generator import ViewGenerator

# 1. Convert building geometry
octree = ObjToOctree(['building.obj'], ['building.mtl'])
octree.create_skyless_octree_for_sunlight_analysis()

# 2. Generate sky conditions (Melbourne, winter solstice)
sky = SkyGenerator(lat=-37.8136)
sky.generate_sunny_sky_series(
    month=6, day=21,
    start_hour_24hr_format=9,
    end_hour_24hr_format=17,
    minute_increment=60
)

# 3. Create analysis views
views = ViewGenerator(
    room_boundaries_csv_path='rooms.csv',
    output_dir='intermediates/views'
)
views.create_aoi_and_view_files()
```

## GPU Rendering with Accelerad

Archilume supports GPU-accelerated rendering through Accelerad, providing significant performance improvements for overcast daylight simulations. GPU rendering can be **10-50x faster** than CPU rendering depending on scene complexity and GPU hardware.

### Overview

The GPU rendering pipeline replaces both the overture (ambient file warming) and medium quality rendering steps with a single accelerated batch process. This provides:

- **Faster rendering**: GPU parallelization dramatically reduces render times
- **Ambient file caching**: Reuses pre-computed ambient files across rendering sessions
- **Quality presets**: Six built-in quality configurations from preview to production
- **Automatic fallback**: Seamlessly falls back to CPU rendering if GPU unavailable

### Requirements

**Hardware:**
- NVIDIA GPU with compute capability 5.0+ (Maxwell architecture or newer)
- Minimum 2GB VRAM (4GB+ recommended for high-resolution renders)
- Compatible GPUs: GTX 900 series, RTX series, Quadro/RTX professional cards

**Software:**
- Accelerad installed to `C:\Program Files\Accelerad\`
- NVIDIA display drivers with CUDA 12.0+ support
- OptiX 6.8+ (included with recent NVIDIA drivers)
- RAYPATH environment variable configured correctly

### RAYPATH Configuration

The RAYPATH environment variable must include both Radiance and Accelerad library paths. Accelerad searches RAYPATH for required PTX (CUDA compiled kernel) files.

**Verify RAYPATH is set correctly:**

```cmd
echo %RAYPATH%
```

Expected output:
```
C:\Radiance\lib;C:\Program Files\Accelerad\lib
```

If RAYPATH is incorrect or missing Accelerad libraries, you'll see errors like:
```
accelerad_rpict: system - File rpict.ptx not found in RAYPATH.
```

**Fix RAYPATH issues:**

```cmd
setx RAYPATH "C:\Radiance\lib;C:\Program Files\Accelerad\lib"
```

**Note**: After setting environment variables, restart your terminal/IDE for changes to take effect.

### Usage

Enable GPU rendering by setting `render_mode='gpu'` in the `sunlight_rendering_pipeline()` method:

```python
from archilume.rendering_pipelines import RenderingPipelines

renderer = RenderingPipelines(
    skyless_octree_path=octree_path,
    overcast_sky_file_path=overcast_sky_path,
    skies_dir=sky_files_dir,
    views_dir=view_files_dir,
    x_res=1024,
    y_res=1024
)

# GPU rendering with medium quality preset
timings = renderer.sunlight_rendering_pipeline(
    render_mode='gpu',
    gpu_quality='med'
)
```

### Quality Presets

Six quality presets are available, balancing speed vs accuracy:

| Preset | Use Case | AA | AB | AD | AS | AR | Speed | Quality |
|--------|----------|----|----|----|----|-------|-------|---------|
| `fast` | Quick preview | 0.07 | 3 | 1024 | 256 | 124 | ⚡⚡⚡⚡ | ⭐ |
| `med` | Standard analysis | 0.05 | 3 | 1024 | 256 | 512 | ⚡⚡⚡ | ⭐⭐ |
| `high` | High quality | 0.01 | 3 | 1024 | 512 | 512 | ⚡⚡ | ⭐⭐⭐ |
| `detailed` | Maximum quality | 0 | 1 | 2048 | 1024 | 124 | ⚡ | ⭐⭐⭐⭐ |
| `test` | Testing/debugging | 0.05 | 8 | 1024 | 256 | 512 | ⚡⚡⚡ | ⭐⭐ |
| `ark` | Architecture grade | 0.01 | 8 | 4096 | 1024 | 1024 | ⚡ | ⭐⭐⭐⭐⭐ |

**Parameter definitions:**
- **AA** (Ambient Accuracy): Lower = more accurate indirect lighting (0-1)
- **AB** (Ambient Bounces): Number of indirect light bounces (0-10)
- **AD** (Ambient Divisions): Ray sampling density (512-4096)
- **AS** (Ambient Super-samples): Additional samples for accuracy (128-1024)
- **AR** (Ambient Resolution): Spatial resolution of ambient cache (32-1024)

### Complete GPU Rendering Example

```python
from pathlib import Path
from archilume.obj_to_octree import ObjToOctree
from archilume.sky_generator import SkyGenerator
from archilume.view_generator import ViewGenerator
from archilume.rendering_pipelines import RenderingPipelines

# 1. Setup geometry
octree_generator = ObjToOctree(['building.obj', 'site.obj'])
octree_generator.create_skyless_octree_for_analysis()

# 2. Generate sky conditions
sky_generator = SkyGenerator(lat=-37.8136)
sky_generator.generate_TenK_cie_overcast_skyfile()
sky_generator.generate_sunny_sky_series(
    month=6, day=21,
    start_hour_24hr_format=9,
    end_hour_24hr_format=15,
    minute_increment=10
)

# 3. Create views
view_generator = ViewGenerator(
    room_boundaries_csv_path='rooms.csv',
    ffl_offset=1.0
)
view_generator.create_plan_view_files()

# 4. GPU-accelerated rendering
renderer = RenderingPipelines(
    skyless_octree_path=octree_generator.skyless_octree_path,
    overcast_sky_file_path=sky_generator.TenK_cie_overcast_sky_file_path,
    skies_dir=sky_generator.sky_file_dir,
    views_dir=view_generator.view_file_dir,
    x_res=1024,
    y_res=1024
)

# Render with GPU using 'fast' preset for quick preview
phase_timings = renderer.sunlight_rendering_pipeline(
    render_mode='gpu',
    gpu_quality='fast'
)

print(f"GPU rendering completed in {phase_timings['    Ambient file warming & rendering (GPU)']:.1f}s")
```

### Performance Considerations

**Ambient File Reuse**

GPU rendering generates `.amb` files that cache indirect lighting calculations. These files are automatically reused in subsequent renders with matching:
- Octree geometry
- View parameters
- Sky conditions
- Quality settings

**Benefits:**
- First render: Full overture + rendering (~2-5 minutes per view)
- Subsequent renders: Skip overture, reuse `.amb` files (~30-60 seconds per view)

**Storage:** Ambient files are stored in `outputs/images/` and typically range from 1-50MB depending on scene complexity.

**When to Clear Ambient Files:**

Use the `scrub_outputs.py` utility to manage ambient file caching:

```python
# Clear all outputs including ambient files (fresh start)
from examples.scrub_outputs import clear_outputs_folder
clear_outputs_folder(retain_amb_files=False)

# Clear outputs but keep ambient files (faster re-rendering)
clear_outputs_folder(retain_amb_files=True)
```

**Resolution Guidelines**

Higher resolutions require more VRAM and processing time:

| Resolution | VRAM Usage | Render Time (per view) | Recommended For |
|------------|------------|------------------------|-----------------|
| 512px | ~1GB | 30-60s | Quick previews |
| 1024px | ~2GB | 1-3min | Standard analysis |
| 2048px | ~4GB | 4-8min | High-quality output |
| 4096px | ~8GB+ | 10-20min | Publication quality |

**Multi-View Rendering**

The GPU batch renderer processes all views sequentially. For projects with many views:
- Total time = (number of views) × (time per view)
- Example: 10 views at 1024px with 'fast' preset = ~10-30 minutes total

### Troubleshooting

**Error: "File rpict.ptx not found in RAYPATH"**

The RAYPATH environment variable doesn't include Accelerad's library path.

**Solution:**
```cmd
setx RAYPATH "C:\Radiance\lib;C:\Program Files\Accelerad\lib"
```

Restart your terminal/IDE after setting the environment variable.

**Error: "No CUDA-capable device detected"**

Accelerad cannot find a compatible NVIDIA GPU.

**Solutions:**
1. Verify NVIDIA GPU is installed: `nvidia-smi`
2. Update NVIDIA drivers to latest version
3. Check GPU compute capability: Must be 5.0 or higher
4. Fallback to CPU rendering: `render_mode='cpu'`

**Warning: "unknown object type 'specpict'"**

This warning can be safely ignored. It indicates Accelerad encountered a Radiance primitive type that doesn't affect rendering results.

**Render appears too dark/bright**

Adjust the quality preset or rendering parameters:
- Darker images: Increase AB (ambient bounces) or AS (super-samples)
- Brighter images: Decrease AD (ambient divisions) or increase AR (ambient resolution)
- Try different presets: `fast` → `med` → `high` → `detailed`

**GPU rendering slower than expected**

Possible causes:
1. First render (generating ambient files): Expected, subsequent renders will be faster
2. Low VRAM: Reduce resolution or use simpler geometry
3. Thermal throttling: Ensure adequate GPU cooling
4. Other GPU processes: Close GPU-intensive applications

### CPU vs GPU Rendering Comparison

| Aspect | CPU (rpict) | GPU (Accelerad) |
|--------|-------------|-----------------|
| **Speed** | Baseline | 10-50x faster |
| **Quality** | Identical | Identical |
| **Hardware** | Any CPU | NVIDIA GPU required |
| **Ambient files** | Separate overture pass | Combined overture + render |
| **Multi-view** | Parallel processing | Sequential batching |
| **Memory** | RAM-limited | VRAM-limited |
| **Best for** | Parallel multi-scene | Single-scene high-res |

**Recommendation**: Use GPU rendering for iterative design workflows where you render the same views repeatedly. Use CPU rendering for one-off analyses or when GPU hardware is unavailable.

## Troubleshooting

### First-Time Setup Verification

After installation, verify your setup is working correctly:

```bash
# Quick verification
python -c "import archilume; print('✓ Archilume installed')"
python -c "import PIL; print(f'✓ Pillow {PIL.__version__}')"
oconv -version
```

### Common Issues and Solutions

#### Installation Issues

| Issue | Symptoms | Solution |
|-------|----------|----------|
| **Python version too old** | `SyntaxError` or import errors | Install Python 3.12+ from [python.org](https://www.python.org/downloads/) |
| **Pillow not installed** | `ModuleNotFoundError: No module named 'PIL'` | Run: `pip install -e .` in project root |
| **Missing dependencies** | Import errors for numpy, pandas, etc. | Run: `pip install -e .` to install all dependencies |
| **Permission denied** | `PermissionError` during installation | Run terminal as administrator (Windows) or use `sudo` (Linux/Mac) |
| **pip not found** | `'pip' is not recognized` | Install pip: `python -m ensurepip --upgrade` |

#### Radiance/Accelerad Issues

| Issue | Symptoms | Solution |
|-------|----------|----------|
| **Radiance not found** | `FileNotFoundError: 'oconv' not found` | 1. Install from [radiance-online.org](https://www.radiance-online.org/)<br>2. Add to PATH or set `RADIANCE_ROOT` env var<br>3. Verify: `oconv -version` |
| **RAYPATH not set** | `system - cannot find file` errors | **Windows:** `setx RAYPATH "C:\Radiance\lib"`<br>**Linux/Mac:** Add to `.bashrc`: `export RAYPATH=/usr/local/radiance/lib`<br>Restart terminal after setting |
| **Accelerad PTX errors** | `File rpict.ptx not found in RAYPATH` | Add Accelerad lib to RAYPATH:<br>`setx RAYPATH "C:\Radiance\lib;C:\Program Files\Accelerad\lib"`<br>Restart terminal/IDE |
| **No CUDA device** | `No CUDA-capable device detected` | 1. Verify NVIDIA GPU: `nvidia-smi`<br>2. Update drivers from [nvidia.com](https://www.nvidia.com/drivers)<br>3. Fallback to CPU mode: `render_mode='cpu'` |
| **Accelerad not found** | GPU rendering fails | 1. Install from [nljones.github.io/Accelerad](https://nljones.github.io/Accelerad/)<br>2. Or use CPU rendering: `render_mode='cpu'` |

#### Runtime Issues

| Issue | Symptoms | Solution |
|-------|----------|----------|
| **Paths with spaces fail** | Command execution errors | Ensure no spaces in: project path, input files, Radiance installation path |
| **OBJ file in millimeters** | Validation error: "model in MILLIMETERS" | Re-export OBJ files from CAD with units set to **meters** |
| **Missing .mtl file** | `Missing .mtl file` error | Ensure each `.obj` has matching `.mtl` file in same directory |
| **CSV not found** | `room_boundaries_csv not found` | 1. Create CSV file with room boundaries<br>2. Place in `inputs/` directory<br>3. Update path in workflow script |
| **Resolution too high** | Out of memory errors | Reduce `image_resolution` to 1024 or 512 in workflow script |
| **Render appears dark** | Very dark output images | 1. Check sky file generation<br>2. Increase ambient bounces in quality preset<br>3. Verify geometry units (must be meters) |

#### Environment Variable Setup

**Windows (PowerShell):**
```powershell
# Set Radiance paths
setx RADIANCE_ROOT "C:\Radiance"
setx RAYPATH "C:\Radiance\lib"

# With Accelerad:
setx RAYPATH "C:\Radiance\lib;C:\Program Files\Accelerad\lib"
```

**Windows (Command Prompt):**
```cmd
setx RADIANCE_ROOT "C:\Radiance"
setx RAYPATH "C:\Radiance\lib"
```

**Linux/macOS:**
```bash
# Add to ~/.bashrc or ~/.zshrc
export RADIANCE_ROOT="/usr/local/radiance"
export RAYPATH="/usr/local/radiance/lib"
export PATH="$PATH:$RADIANCE_ROOT/bin"

# Apply changes
source ~/.bashrc
```

**After setting environment variables, restart your terminal/IDE for changes to take effect.**

#### Platform-Specific Notes

**Windows:**
- Install Radiance to `C:\Radiance\` (default expected location)
- Use PowerShell or Command Prompt (not Git Bash) for environment variables
- Check Windows Defender isn't blocking executable files

**Linux:**
- May need to install system dependencies: `sudo apt-get install libgl1-mesa-glx`
- Ensure executable permissions: `chmod +x /usr/local/radiance/bin/*`

**macOS:**
- May need to install Xcode Command Line Tools: `xcode-select --install`
- Allow executables in System Preferences > Security & Privacy

### Getting Help

If you encounter issues not covered here:

1. **Check existing issues**: [GitHub Issues](https://github.com/vincentlogarzo/archilume/issues)
2. **Verify installation**:
   ```python
   # Run diagnostic script
   python -c "from archilume import config; print(f'Radiance: {config.RADIANCE_ROOT}')"
   ```
3. **Create new issue** with:
   - Operating system and version
   - Python version (`python --version`)
   - Full error message
   - Steps to reproduce

## Testing

Archilume uses pytest for comprehensive testing across unit, integration, and end-to-end levels.

### Quick Start

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run all tests
pytest tests/

# Run only fast unit tests
pytest tests/ -m "not slow and not integration"

# Run with coverage
pytest tests/ --cov=archilume --cov-report=html
coverage report

# Run specific test file
pytest tests/test_sky_generator.py -v
```

### Test Organization

```
tests/
├── test_sky_generator.py           # Sky file generation (✓ Complete)
├── test_geometric_calculations.py  # Geometry utilities (✓ Complete)
├── test_material_parsing.py        # MTL conversion
├── test_config.py                  # Configuration & validation (TODO)
├── test_view_generator.py          # View generation (TODO)
├── test_rendering_pipelines.py     # Rendering workflows (TODO)
└── integration/                    # End-to-end tests (TODO)
```

### Coverage Goals

| Module | Current Coverage | Target |
|--------|-----------------|--------|
| `sky_generator.py` | ~90% | 90%+ |
| `utils.py` (geometry) | ~85% | 85%+ |
| Other modules | ~20% | 80%+ |

**For comprehensive testing guidelines, test templates, and coverage strategies, see [TESTING_GUIDE.md](TESTING_GUIDE.md).**

## Dependencies

Archilume requires the following Python packages (automatically installed):

- [pyradiance](https://github.com/LBNL-ETA/pyradiance) ≥1.1.5 - Python interface to Radiance
- [open3d](https://open3d.org/) ≥0.19.0 - 3D data processing
- [opencv-python](https://opencv.org/) ≥4.11.0 - Computer vision and image processing
- [ifcopenshell](https://ifcopenshell.org/) ≥0.8.3 - IFC/BIM file support
- [numpy](https://numpy.org/) ≥2.3.2 - Numerical computing
- [pandas](https://pandas.pydata.org/) ≥2.3.1 - Data manipulation
- [pillow](https://pillow.readthedocs.io/) ≥11.3.0 - Image processing

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes and add tests
4. Run the test suite: `pytest tests/`
5. Commit your changes: `git commit -m 'Add new feature'`
6. Push to your branch: `git push origin feature/your-feature`
7. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built on [Radiance](https://www.radiance-online.org/), the industry-standard lighting simulation software
- Uses [PyRadiance](https://github.com/LBNL-ETA/pyradiance) for Python-Radiance integration
- Special thanks to [@MrBlenny](https://github.com/MrBlenny) for bringing life to a sick project.

## Support

- **Issues**: Report bugs or request features via [GitHub Issues](https://github.com/vincentlogarzo/archilume/issues)
- **Examples**: See the [examples](examples/) directory for usage patterns
- **Documentation**: Explore the codebase and docstrings for detailed API information

---

**Archilume** - Streamlined architectural lighting analysis with Radiance