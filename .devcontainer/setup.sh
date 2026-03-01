#!/bin/bash
set -e

echo "🚀 Setting up Archilume development environment..."

# Install system dependencies
echo "📦 Installing system dependencies..."

# Remove Yarn repository if present (not needed for this project)
sudo rm -f /etc/apt/sources.list.d/yarn.list

sudo apt-get update
sudo apt-get install -y libgl1 libgomp1 libglib2.0-0 libtiff6 libtiff-tools xfonts-base

# Create symlink for ra_tiff compatibility (expects libtiff5, we have libtiff6)
sudo ln -sf /usr/lib/x86_64-linux-gnu/libtiff.so.6 /usr/lib/x86_64-linux-gnu/libtiff.so.5

# Install Radiance
echo "🌟 Installing Radiance..."

cd /tmp
# Detect workspace path: prefer env vars set by Codespaces/devcontainers, else derive from script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DERIVED_PATH="$(dirname "$SCRIPT_DIR")"
# Validate derived path contains expected marker; fall back to known devcontainer mount
if [ -f "$DERIVED_PATH/pyproject.toml" ]; then
    WORKSPACE_PATH="$DERIVED_PATH"
elif [ -f "${CODESPACE_VSCODE_FOLDER:-}/pyproject.toml" ]; then
    WORKSPACE_PATH="$CODESPACE_VSCODE_FOLDER"
elif [ -f "${LOCAL_WORKSPACE_FOLDER:-}/pyproject.toml" ]; then
    WORKSPACE_PATH="$LOCAL_WORKSPACE_FOLDER"
else
    # Last resort: scan /workspaces for the project
    WORKSPACE_PATH="$(find /workspaces -maxdepth 2 -name "pyproject.toml" -exec dirname {} \; 2>/dev/null | head -1)"
fi
echo "📂 Workspace path resolved to: $WORKSPACE_PATH"

# Use bundled Radiance tarball from .devcontainer directory
tar -xzf "$WORKSPACE_PATH/.devcontainer/Radiance_5085332d_Linux/radiance-6.1.5085332d6e-Linux.tar.gz"
sudo cp -r radiance-*/usr/local/radiance /usr/local/
sudo chmod -R 755 /usr/local/radiance
rm -rf radiance-*

# Install Accelerad (GPU-accelerated Radiance)
echo "⚡ Installing Accelerad..."
echo "Note: GPU acceleration requires NVIDIA GPU and proper Docker GPU passthrough"

# Install build dependencies for Accelerad
sudo apt-get install -y build-essential git cmake libx11-dev tcl-dev tk-dev

# Clone Accelerad repository
cd /tmp
if [ ! -d "Accelerad" ]; then
    git clone https://github.com/nljones/Accelerad.git
fi

cd Accelerad

# Build and install Accelerad
# Note: This will build CPU fallback if CUDA is not available
if ./makeall install clean 2>&1 | tee /tmp/accelerad_install.log; then
    echo "✅ Accelerad installed successfully!"
    echo "Note: GPU acceleration requires CUDA toolkit and NVIDIA GPU"
else
    echo "⚠️  Accelerad installation encountered issues - check /tmp/accelerad_install.log"
    echo "Continuing with setup..."
fi

cd /tmp
rm -rf Accelerad

# Add environment variables to bash profile
echo "🔧 Configuring environment variables..."
if ! grep -q "RAYPATH" ~/.bashrc; then
    echo 'export PATH=$PATH:/usr/local/radiance/bin:/usr/local/google-cloud-sdk/bin' >> ~/.bashrc
    echo 'export RAYPATH=/usr/local/radiance/lib' >> ~/.bashrc
    echo 'export UV_LINK_MODE=copy' >> ~/.bashrc
fi

# Install Google Cloud CLI
echo "☁️  Installing Google Cloud CLI..."
curl -sSL https://sdk.cloud.google.com | bash -s -- --disable-prompts --install-dir="$HOME"
sudo ln -sf "$HOME/google-cloud-sdk/bin/gcloud" /usr/local/bin/gcloud
sudo ln -sf "$HOME/google-cloud-sdk/bin/gsutil" /usr/local/bin/gsutil
sudo ln -sf "$HOME/google-cloud-sdk/bin/bq" /usr/local/bin/bq
echo "✅ Google Cloud CLI installed!"

# Install Python dependencies using uv
echo "🐍 Installing Python dependencies..."
if ! command -v uv &> /dev/null; then
    echo "📥 Installing uv package manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # uv installs to ~/.local/bin by default (not ~/.cargo/bin)
    export PATH="$HOME/.local/bin:$PATH"

    # Add uv to PATH permanently
    if ! grep -q ".local/bin" ~/.bashrc; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    fi
fi

# Ensure uv is in PATH for this session
export PATH="$HOME/.local/bin:$PATH"

# Verify uv installation
echo "✅ Verifying uv installation..."
if command -v uv &> /dev/null; then
    uv --version
else
    echo "⚠️  Warning: uv installation may have failed"
    exit 1
fi

# Sync Python dependencies
echo "📦 Syncing Python dependencies with uv..."
cd "$WORKSPACE_PATH"

# Ensure .venv directory exists before syncing
mkdir -p .venv

uv sync --link-mode=copy

# Verify Radiance installation
echo "✅ Verifying Radiance installation..."
export PATH=$PATH:/usr/local/radiance/bin
export RAYPATH=/usr/local/radiance/lib

if command -v oconv &> /dev/null && command -v rpict &> /dev/null; then
    echo "✅ Radiance installed successfully!"
    oconv 2>&1 | head -1 || echo "Radiance version: $(ls /usr/local/radiance/bin/oconv)"
else
    echo "⚠️  Warning: Radiance may not be properly installed"
fi

# Verify Accelerad installation
echo "✅ Verifying Accelerad installation..."
if command -v rcontrib &> /dev/null; then
    echo "✅ Accelerad commands available!"
    # Check if CUDA is available
    if command -v nvidia-smi &> /dev/null; then
        echo "🎮 NVIDIA GPU detected - GPU acceleration available"
        nvidia-smi --query-gpu=name --format=csv,noheader
    else
        echo "⚠️  No NVIDIA GPU detected - Accelerad will run in CPU fallback mode"
        echo "   For GPU acceleration, ensure Docker has GPU passthrough configured"
    fi
else
    echo "⚠️  Accelerad commands not found - may not be properly installed"
fi

# Verify Python venv is set up correctly
echo "✅ Verifying Python environment..."
if [ -f "$WORKSPACE_PATH/.venv/bin/python" ]; then
    echo "✅ Python venv found at .venv/bin/python"
    "$WORKSPACE_PATH/.venv/bin/python" --version
else
    echo "⚠️  Warning: Python venv not found at expected location"
fi

echo "🎉 Setup complete! Archilume development environment is ready."
echo ""
echo "Available commands:"
echo "  - oconv: Convert scenes to octree format"
echo "  - rpict: Render pictures from octrees"
echo "  - gensky: Generate sky conditions"
echo "  - obj2rad: Convert OBJ files to Radiance format"
echo ""
echo "Run 'python examples/sunlight_exposure_analysis.py' to test!"
