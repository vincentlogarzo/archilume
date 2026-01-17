# Archilume

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A Python library for Radiance-based daylight analysis, providing streamlined tools for architectural lighting simulation and environmental performance assessment.

## Overview

Archilume simplifies the workflow of creating physically accurate daylight simulations by bridging the gap between 3D modeling software and Radiance rendering. It automates the conversion of building geometry, generates sky conditions for any location and time, and provides GPU-accelerated rendering capabilities.

### Key Features

- **3D Model Conversion**: Convert OBJ/MTL building models to Radiance octree format
- **Sky Generation**: Create physically accurate sky models for any date, time, and location
- **View Management**: Generate camera view parameters for interior and exterior analysis
- **GPU Acceleration**: Optional Accelerad integration for 10-50x faster rendering
- **Parallel Processing**: Multi-core support for computationally intensive simulations
- **Automated Workflows**: Pre-configured pipelines for seasonal and annual daylight studies

### Limitations

⚠️ **Not suitable for large buildings with extensive curved surfaces.** The current implementation is optimized for small to medium-sized buildings with primarily planar geometry. Complex curved geometries may result in excessive computation times, high memory usage, and reduced accuracy.

---

## Table of Contents

- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Basic Installation](#basic-installation)
  - [Dev Container Setup](#dev-container-setup)
- [Quick Start](#quick-start)
- [Core Modules](#core-modules)
- [GPU Rendering](#gpu-rendering)
- [Examples](#examples)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

---

## Installation

### Prerequisites

**Required:**
- Python 3.12 or higher
- [Radiance](https://www.radiance-online.org/) lighting simulation software

**Optional:**
- [Accelerad](https://nljones.github.io/Accelerad/) for GPU-accelerated rendering (requires NVIDIA GPU)

### Basic Installation

```bash
# Clone the repository
git clone https://github.com/vincentlogarzo/archilume.git
cd archilume

# Install the package
pip install -e .

# Verify installation
python -c "import archilume; print('Archilume installed successfully')"
```

### Dev Container Setup

This repository includes a preconfigured development container for VS Code with all dependencies pre-installed.

**Requirements:**
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [VS Code](https://code.visualstudio.com/) with [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

**Setup Steps:**

1. **Set Claude API Key** (if using Claude Code):

   **Windows (PowerShell):**
   ```powershell
   [System.Environment]::SetEnvironmentVariable('CLAUDE_API_KEY', 'your-api-key-here', 'User')
   ```

   **Linux/macOS:**
   ```bash
   echo 'export CLAUDE_API_KEY="your-api-key-here"' >> ~/.bashrc
   source ~/.bashrc
   ```

2. **Open in Container:**
   - Open the project folder in VS Code
   - Click "Reopen in Container" when prompted
   - Or use `Ctrl+Shift+P` → "Dev Containers: Reopen in Container"

3. **Verify Setup:**
   ```bash
   python -c "import archilume; print('Ready!')"
   ```

**Note:** After setting environment variables, restart VS Code for changes to take effect.

---

## Quick Start

Here's a minimal example to perform a sunlight analysis:

```python
from archilume.objs2octree import ObjToOctree
from archilume.sky_generator import SkyGenerator
from archilume.view_generator import ViewGenerator
from archilume.rendering_pipelines import RenderingPipelines

# 1. Convert building geometry to Radiance format
octree = ObjToOctree(
    obj_file_paths=['building.obj'],
    mtl_file_paths=['building.mtl']
)
octree.create_skyless_octree_for_sunlight_analysis()

# 2. Generate sky conditions (Melbourne, winter solstice)
sky = SkyGenerator(lat=-37.8136)
sky.generate_sunny_sky_series(
    month=6, day=21,
    start_hour_24hr_format=9,
    end_hour_24hr_format=17,
    minute_increment=60
)

# 3. Create analysis views from room boundaries
views = ViewGenerator(
    room_boundaries_csv_path='inputs/rooms.csv',
    output_dir='intermediates/views'
)
views.create_aoi_and_view_files()

# 4. Render the analysis
renderer = RenderingPipelines(
    skyless_octree_path=octree.skyless_octree_path,
    skies_dir=sky.sky_file_dir,
    views_dir=views.view_file_dir,
    x_res=1024,
    y_res=1024
)
renderer.sunlight_rendering_pipeline(render_mode='cpu')
```

---

## Core Modules

### ObjToOctree

Converts 3D building models from OBJ format to Radiance octree format.

```python
from archilume.objs2octree import ObjToOctree

converter = ObjToOctree(
    obj_file_paths=['building.obj', 'site.obj'],
    mtl_file_paths=['building.mtl', 'site.mtl']
)
converter.create_skyless_octree_for_sunlight_analysis()
```

**Key Methods:**
- `create_skyless_octree_for_sunlight_analysis()`: Creates octree for direct sun analysis
- `create_skyless_octree_for_analysis()`: Creates octree for general daylight analysis

### SkyGenerator

Generates Radiance sky files for specific dates, times, and geographic locations.

```python
from archilume.sky_generator import SkyGenerator

sky = SkyGenerator(lat=-37.8136, lon=144.9631)  # Melbourne coordinates

# Generate hourly sky conditions for winter solstice
sky.generate_sunny_sky_series(
    month=6, day=21,
    start_hour_24hr_format=9,
    end_hour_24hr_format=17,
    minute_increment=60
)

# Generate overcast sky for glare analysis
sky.generate_TenK_cie_overcast_skyfile()
```

**Key Methods:**
- `generate_sunny_sky_series()`: Creates sun-only sky files for a time range
- `generate_TenK_cie_overcast_skyfile()`: Creates CIE overcast sky at 10,000 lux

### ViewGenerator

Creates view parameter files for rendering analysis points.

```python
from archilume.view_generator import ViewGenerator

views = ViewGenerator(
    room_boundaries_csv_path='inputs/rooms.csv',
    output_dir='intermediates/views',
    ffl_offset=1.0  # Height above floor (meters)
)

# Generate plan views for all rooms
views.create_plan_view_files()

# Generate area-of-interest views
views.create_aoi_and_view_files()
```

**CSV Format:** The room boundaries CSV should contain room geometry definitions. See [examples](examples/) for templates.

### RenderingPipelines

Manages rendering workflows with CPU or GPU acceleration.

```python
from archilume.rendering_pipelines import RenderingPipelines

renderer = RenderingPipelines(
    skyless_octree_path='intermediates/octrees/scene.oct',
    skies_dir='intermediates/sky/',
    views_dir='intermediates/views/',
    x_res=1024,
    y_res=1024
)

# CPU rendering
timings = renderer.sunlight_rendering_pipeline(render_mode='cpu')

# GPU rendering (requires Accelerad)
timings = renderer.sunlight_rendering_pipeline(
    render_mode='gpu',
    gpu_quality='med'
)
```

---

## GPU Rendering

Archilume supports GPU-accelerated rendering through Accelerad, providing 10-50x performance improvements.

### Requirements

**Hardware:**
- NVIDIA GPU with compute capability 5.0+ (GTX 900 series, RTX series, or newer)
- Minimum 2GB VRAM (4GB+ recommended)

**Software:**
- Accelerad installed to `C:\Program Files\Accelerad\` (Windows) or `/usr/local/accelerad/` (Linux)
- NVIDIA drivers with CUDA 12.0+ support
- Correct RAYPATH configuration

### Installation

**Windows:**
```cmd
# Install Accelerad from https://nljones.github.io/Accelerad/

# Set environment variables
setx RAYPATH "C:\Radiance\lib;C:\Program Files\Accelerad\lib"
setx PATH "%PATH%;C:\Program Files\Accelerad\bin"

# Verify installation
accelerad_rpict -version
```

**Linux:**
```bash
# Add to ~/.bashrc
export RAYPATH="/usr/local/radiance/lib:/usr/local/accelerad/lib"
export PATH="$PATH:/usr/local/accelerad/bin"

# Apply changes
source ~/.bashrc

# Verify installation
accelerad_rpict -version
```

### Usage

```python
from archilume.rendering_pipelines import RenderingPipelines

renderer = RenderingPipelines(
    skyless_octree_path=octree_path,
    skies_dir=sky_dir,
    views_dir=view_dir,
    x_res=1024,
    y_res=1024
)

# Render with GPU acceleration
timings = renderer.sunlight_rendering_pipeline(
    render_mode='gpu',
    gpu_quality='med'  # Options: fast, med, high, detailed, ark
)
```

### Quality Presets

| Preset | Speed | Quality | Use Case |
|--------|-------|---------|----------|
| `fast` | ⚡⚡⚡⚡ | ⭐ | Quick previews |
| `med` | ⚡⚡⚡ | ⭐⭐ | Standard analysis |
| `high` | ⚡⚡ | ⭐⭐⭐ | High-quality output |
| `detailed` | ⚡ | ⭐⭐⭐⭐ | Maximum quality |
| `ark` | ⚡ | ⭐⭐⭐⭐⭐ | Publication grade |

### Performance Tips

**Ambient File Caching**: GPU rendering generates `.amb` files that cache indirect lighting calculations. These files are automatically reused for matching scene/view/quality settings, significantly speeding up subsequent renders.

**Resolution Guidelines**:
- 512px: Quick previews (~1GB VRAM)
- 1024px: Standard analysis (~2GB VRAM)
- 2048px: High-quality output (~4GB VRAM)
- 4096px: Publication quality (~8GB+ VRAM)

**Troubleshooting**: See the [Troubleshooting](#troubleshooting) section for common GPU rendering issues.

---

## Examples

Complete example workflows are available in the [examples](examples/) directory:

### Sunlight Access Workflow

A comprehensive example demonstrating the full analysis pipeline:

```python
# See: examples/sunlight_access_workflow.py
from archilume import (
    ObjToOctree,
    SkyGenerator,
    ViewGenerator,
    RenderingPipelines
)

# Full workflow with geometry conversion, sky generation,
# view setup, and GPU-accelerated rendering
```

**What it demonstrates:**
- OBJ/MTL conversion to Radiance octree
- Sunny sky series generation for solstice analysis
- View generation from room boundaries
- GPU rendering with quality presets
- Timing and performance tracking

### Custom Workflows

You can adapt the workflow for specific needs:

```python
# Summer solstice solar heat gain analysis
sky.generate_sunny_sky_series(
    month=12, day=21,  # Summer solstice (Southern Hemisphere)
    start_hour_24hr_format=6,
    end_hour_24hr_format=20,
    minute_increment=30
)

# Annual daylight analysis with monthly samples
for month in range(1, 13):
    sky.generate_sunny_sky_series(
        month=month, day=21,
        start_hour_24hr_format=9,
        end_hour_24hr_format=17
    )
```

---

## Project Structure

```
archilume/
├── archilume/                      # Core package
│   ├── objs2octree.py             # 3D model → Radiance conversion
│   ├── sky_generator.py           # Sky condition generation
│   ├── view_generator.py          # Camera view setup
│   ├── rendering_pipelines.py     # Rendering workflows
│   ├── hdr2wpd.py                 # HDR to work plane daylight processing
│   ├── mtl_converter.py           # Material file conversion
│   ├── tiff2animation.py          # Animation generation
│   ├── utils.py                   # Utilities & parallel processing
│   ├── config.py                  # Configuration & validation
│   └── accelerad_rpict.py         # GPU rendering interface
│
├── examples/                       # Example workflows
│   └── sunlight_access_workflow.py
│
├── tests/                          # Test suite
│   ├── test_sky_generator.py
│   ├── test_geometric_calculations.py
│   └── ...
│
├── inputs/                         # Input files (OBJ, MTL, CSV)
├── intermediates/                  # Generated files
│   ├── octrees/                   # Radiance scene files
│   ├── sky/                       # Sky condition files
│   └── views/                     # Camera parameters
└── outputs/                        # Rendered images and results
```

---

## Testing

Archilume uses pytest for testing. To run the test suite:

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run all tests
pytest tests/

# Run only fast tests (skip slow integration tests)
pytest tests/ -m "not slow and not integration"

# Run with coverage report
pytest tests/ --cov=archilume --cov-report=html

# Run specific test file
pytest tests/test_sky_generator.py -v
```

**Coverage Status:**
- `sky_generator.py`: ~90%
- `utils.py` (geometry): ~85%
- Other modules: In progress

For comprehensive testing guidelines, see [TESTING_GUIDE.md](TESTING_GUIDE.md).

---

## Troubleshooting

### Common Issues

#### Radiance Not Found

**Error:** `FileNotFoundError: 'oconv' not found`

**Solution:**
1. Install Radiance from [radiance-online.org](https://www.radiance-online.org/)
2. Add to PATH or set `RADIANCE_ROOT` environment variable
3. Verify: `oconv -version`

**Windows:**
```cmd
setx RADIANCE_ROOT "C:\Radiance"
setx PATH "%PATH%;C:\Radiance\bin"
setx RAYPATH "C:\Radiance\lib"
```

**Linux/macOS:**
```bash
export RADIANCE_ROOT="/usr/local/radiance"
export PATH="$PATH:$RADIANCE_ROOT/bin"
export RAYPATH="$RADIANCE_ROOT/lib"
```

#### GPU Rendering Errors

**Error:** `File rpict.ptx not found in RAYPATH`

**Solution:** Update RAYPATH to include Accelerad libraries:

```cmd
setx RAYPATH "C:\Radiance\lib;C:\Program Files\Accelerad\lib"
```

Restart your terminal/IDE after setting environment variables.

**Error:** `No CUDA-capable device detected`

**Solution:**
1. Verify NVIDIA GPU is installed: `nvidia-smi`
2. Update NVIDIA drivers from [nvidia.com/drivers](https://www.nvidia.com/drivers)
3. Fall back to CPU rendering: `render_mode='cpu'`

#### Model Validation Errors

**Error:** `Validation error: model in MILLIMETERS`

**Solution:** Re-export OBJ files from your CAD software with units set to **meters**. Radiance requires metric units.

**Error:** `Missing .mtl file`

**Solution:** Ensure each `.obj` file has a matching `.mtl` file in the same directory with the same base name.

#### Runtime Issues

**Issue:** Render appears too dark

**Solution:**
1. Verify sky file generation completed successfully
2. Check geometry units (must be meters)
3. Increase quality preset: `gpu_quality='high'`
4. Increase ambient bounces in custom quality settings

**Issue:** Out of memory errors

**Solution:**
1. Reduce image resolution: `x_res=512, y_res=512`
2. Use simpler geometry or lower quality preset
3. Close other GPU-intensive applications

### Platform-Specific Notes

**Windows:**
- Install Radiance to `C:\Radiance\` (default location)
- Use PowerShell or Command Prompt (not Git Bash) for environment variables
- Check Windows Defender isn't blocking executable files

**Linux:**
- May need system dependencies: `sudo apt-get install libgl1-mesa-glx`
- Ensure executable permissions: `chmod +x /usr/local/radiance/bin/*`

**macOS:**
- May need Xcode Command Line Tools: `xcode-select --install`
- Allow executables in System Preferences → Security & Privacy

### Getting Help

If you encounter issues not covered here:

1. Check [existing issues](https://github.com/vincentlogarzo/archilume/issues)
2. Run diagnostic script:
   ```python
   from archilume import config
   print(f'Radiance: {config.RADIANCE_ROOT}')
   print(f'RAYPATH: {config.RAYPATH}')
   ```
3. Create a [new issue](https://github.com/vincentlogarzo/archilume/issues/new) with:
   - Operating system and version
   - Python version: `python --version`
   - Full error message
   - Steps to reproduce

---

## Contributing

Contributions are welcome! To contribute:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes and add tests
4. Run the test suite: `pytest tests/`
5. Commit: `git commit -m 'Add new feature'`
6. Push: `git push origin feature/your-feature`
7. Open a Pull Request

Please ensure:
- Code follows existing style conventions
- Tests pass and coverage is maintained
- Documentation is updated for new features

---

## Dependencies

Archilume automatically installs these Python packages:

- **pyradiance** ≥1.1.5 - Python interface to Radiance
- **open3d** ≥0.19.0 - 3D data processing
- **opencv-python** ≥4.11.0 - Image processing
- **ifcopenshell** ≥0.8.3 - IFC/BIM file support
- **numpy** ≥2.3.2 - Numerical computing
- **pandas** ≥2.3.1 - Data manipulation
- **pillow** ≥11.3.0 - Image processing

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## Acknowledgments

- Built on [Radiance](https://www.radiance-online.org/), the industry-standard lighting simulation software
- Uses [PyRadiance](https://github.com/LBNL-ETA/pyradiance) for Python-Radiance integration
- GPU acceleration powered by [Accelerad](https://nljones.github.io/Accelerad/)
- Special thanks to [@MrBlenny](https://github.com/MrBlenny) for revitalizing this project

---

**Archilume** - Streamlined architectural lighting analysis with Radiance
