# Archilume Dev Container

This directory contains the development container configuration for Archilume.

## What's Included

- **Python 3.12** development environment
- **Radiance 6.1** (build 5085332d) - Lighting simulation tools
- **Accelerad** - GPU-accelerated Radiance (requires NVIDIA GPU for acceleration)
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

### Opening in DevContainer (VS Code with Remote SSH)

This project is designed to work seamlessly with VS Code connecting to a cloud Linux VM via SSH:

1. **Connect to your Linux VM via SSH in VS Code:**
   - Install the "Remote - SSH" extension in VS Code
   - Press `F1` → "Remote-SSH: Connect to Host"
   - Enter your VM's SSH connection string (e.g., `user@your-vm-ip`)

2. **Open this project in a DevContainer:**
   - Once connected, open this project folder
   - VS Code will detect `.devcontainer/devcontainer.json`
   - Click "Reopen in Container" when prompted (or press `F1` → "Dev Containers: Reopen in Container")

3. **Wait for automatic setup (first time: ~5-10 minutes):**
   The devcontainer will automatically:
   - Install all system dependencies (OpenGL, OpenMP, etc.)
   - Extract and install Radiance 6.1 from bundled tarball
   - Install uv package manager
   - Sync all Python dependencies from pyproject.toml
   - Configure environment variables (PATH, RAYPATH)

4. **Verify installation:**
   ```bash
   uv --version
   python --version
   oconv 2>&1 | head -1
   uv run examples/sunlight_access_workflow.py
   ```

### Benefits of DevContainer on Cloud VM

- ✅ **Consistent Environment**: Same setup across all developers
- ✅ **Isolated Dependencies**: No conflicts with system packages
- ✅ **Pre-configured Tools**: Radiance, uv, Python 3.12 ready to go
- ✅ **Easy Scaling**: Use powerful cloud VMs for rendering
- ✅ **VS Code Integration**: Full IDE features with remote development

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

## Radiance & Accelerad Tools Available

After setup, these Radiance/Accelerad commands are available:

- `oconv` - Convert scenes to octree format
- `rpict` - Render pictures from octrees (CPU-based)
- `rcontrib` - Accelerad GPU-accelerated rendering
- `gensky` - Generate sky conditions
- `obj2rad` - Convert OBJ files to Radiance format
- `pcomb` - Combine/process HDR images
- `ra_tiff` - Convert Radiance HDR to TIFF

### GPU Acceleration Notes

Accelerad is installed but **GPU acceleration requires**:
1. NVIDIA GPU on the host machine
2. NVIDIA Docker runtime configured
3. Docker GPU passthrough enabled
4. CUDA toolkit installed

Without GPU access, Accelerad commands will fall back to CPU rendering. See [Accelerad GitHub](https://github.com/nljones/Accelerad) for more details.

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

### Accelerad GPU not working

To enable GPU acceleration in the devcontainer:

1. Install NVIDIA Docker runtime on your host:
   ```bash
   # Ubuntu/Debian
   distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
   curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
   curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
   sudo apt-get update && sudo apt-get install -y nvidia-docker2
   sudo systemctl restart docker
   ```

2. Update `.devcontainer/devcontainer.json` to add:
   ```json
   "runArgs": ["--gpus", "all"]
   ```

3. Rebuild the container

Without GPU, Accelerad will still work in CPU fallback mode.

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
