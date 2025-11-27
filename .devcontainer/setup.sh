#!/bin/bash
set -e

echo "🚀 Setting up Archilume development environment..."

# Install system dependencies
echo "📦 Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y libgl1 libgomp1 libglib2.0-0

# Install Radiance
echo "🌟 Installing Radiance..."

cd /tmp
# Use local file instead of downloading
unzip -q /workspaces/archilume/.devcontainer/radiance.zip
tar -xzf radiance-*.tar.gz
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
    echo 'export PATH=$PATH:/usr/local/radiance/bin' >> ~/.bashrc
    echo 'export RAYPATH=/usr/local/radiance/lib' >> ~/.bashrc
    echo 'export UV_LINK_MODE=copy' >> ~/.bashrc
fi

# Install Python dependencies using uv
echo "🐍 Installing Python dependencies..."
if ! command -v uv &> /dev/null; then
    echo "📥 Installing uv package manager..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"

    # Add uv to PATH permanently
    if ! grep -q ".cargo/bin" ~/.bashrc; then
        echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
    fi
fi

# Ensure uv is in PATH for this session
export PATH="$HOME/.cargo/bin:$PATH"

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

echo "🎉 Setup complete! Archilume development environment is ready."
echo ""
echo "Available commands:"
echo "  - oconv: Convert scenes to octree format"
echo "  - rpict: Render pictures from octrees"
echo "  - gensky: Generate sky conditions"
echo "  - obj2rad: Convert OBJ files to Radiance format"
echo ""
echo "Run 'python examples/sunlight_exposure_analysis.py' to test!"
