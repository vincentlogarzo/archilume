#!/bin/bash
set -e

echo "🚀 Setting up Archilume development environment..."

# Install system dependencies
echo "📦 Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y libgl1 libgomp1 libglib2.0-0 git-lfs

# Initialize Git LFS
echo "🔧 Initializing Git LFS..."
git lfs install

# Install Radiance
echo "🌟 Installing Radiance..."

cd /tmp
# Use local file instead of downloading (force overwrite if exists)
unzip -o -q /workspaces/archilume/.devcontainer/radiance.zip
tar -xzf radiance-*.tar.gz
sudo cp -r radiance-*/usr/local/radiance /usr/local/
sudo chmod -R 755 /usr/local/radiance
rm -rf radiance-*

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
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

# Ensure uv is in PATH
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

# Return to project directory for Python operations
cd /workspaces/archilume

# Sync Python dependencies
uv sync --link-mode=copy

# Install archilume package in editable mode
echo "📦 Installing archilume package..."
python -m pip install -e /workspaces/archilume

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

# Verify archilume installation
echo "✅ Verifying archilume installation..."
if python -c "import archilume" 2>/dev/null; then
    echo "✅ Archilume package installed successfully!"
else
    echo "⚠️  Warning: Archilume may not be properly installed"
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
