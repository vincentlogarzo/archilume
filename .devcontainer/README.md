# Archilume Dev Container

This directory contains the development container configuration for Archilume.

## What's Included

- **Python 3.12** development environment
- **Radiance 6.1** (build 5085332d) - Lighting simulation tools
- **OpenGL libraries** - Required for Open3D visualization
- **Git & GitHub CLI** - Version control tools
- **uv** - Fast Python package installer
- **VSCode Extensions** - Python, Pylance, Black formatter

## Environment Variables

The following environment variables are automatically configured:

- `PATH` - Includes `/usr/local/radiance/bin` for Radiance tools and `~/.cargo/bin` for uv
- `RAYPATH` - Set to `/usr/local/radiance/lib` for Radiance libraries
- `UV_LINK_MODE=copy` - Suppresses UV hardlink warnings in containers

## How to Use

### Opening in DevContainer (VS Code Desktop)

1. Open this project in VS Code
2. Press `F1` or `Ctrl+Shift+P`
3. Type "Dev Containers: Reopen in Container"
4. Wait for container to build (first time: ~5-10 minutes)
5. Verify setup:
   ```bash
   uv --version
   python --version
   oconv 2>&1 | head -1
   ```

### For GitHub Codespaces

1. When you open this repository in GitHub Codespaces, the devcontainer will automatically:
   - Install all system dependencies
   - Install Radiance lighting simulation software
   - Install uv package manager
   - Set up Python environment with all dependencies
   - Configure environment variables

2. Wait for the setup to complete (usually 2-3 minutes)

3. Verify installation:
   ```bash
   uv --version
   which oconv rpict gensky
   python examples/sunlight_exposure_analysis.py
   ```

### Rebuilding the Container

If you modify `.devcontainer/` files:

1. Open Command Palette (Ctrl+Shift+P / Cmd+Shift+P)
2. Type "Rebuild Container" and select **"Dev Containers: Rebuild Container"**
3. Wait for the rebuild to complete

### Manual Setup

If you need to run the setup script manually:

```bash
bash .devcontainer/setup.sh
source ~/.bashrc
```

## Radiance Tools Available

After setup, these Radiance commands are available:

- `oconv` - Convert scenes to octree format
- `rpict` - Render pictures from octrees
- `gensky` - Generate sky conditions
- `obj2rad` - Convert OBJ files to Radiance format
- `pcomb` - Combine/process HDR images
- `ra_tiff` - Convert Radiance HDR to TIFF

## Troubleshooting

### Radiance commands not found

If Radiance commands aren't available, ensure environment variables are loaded:

```bash
source ~/.bashrc
# Or manually export:
export PATH=$PATH:/usr/local/radiance/bin
export RAYPATH=/usr/local/radiance/lib
```

### UV link mode warnings

The devcontainer automatically sets `UV_LINK_MODE=copy` to suppress hardlink warnings. If you still see them, run:

```bash
export UV_LINK_MODE=copy
```

### Python dependencies not installed

Run the sync command:

```bash
uv sync --link-mode=copy
```

### uv command not found

If `uv` isn't available after setup:

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# Or add to PATH manually
export PATH="$HOME/.cargo/bin:$PATH"
```

## Using uv Package Manager

Inside the devcontainer, use `uv` for all package management:

```bash
# Install a package
uv pip install <package-name>

# Install multiple packages
uv pip install package1 package2

# Install from requirements file
uv pip install -r requirements.txt

# Sync all dependencies from pyproject.toml
uv sync

# List installed packages
uv pip list

# Show package details
uv pip show <package-name>

# Uninstall a package
uv pip uninstall <package-name>

# Freeze current packages
uv pip freeze > requirements.txt
```

**Why uv?**
- ⚡ 10-100x faster than pip
- 🔒 Better dependency resolution
- 💾 Efficient caching
- 🎯 Compatible with pip workflows

## Architecture

- **devcontainer.json** - Container configuration and VSCode settings
- **setup.sh** - Automated installation script
- **README.md** - This file

## License

This devcontainer configuration is part of the Archilume project (MIT License).
