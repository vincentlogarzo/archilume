# =============================================================================
# Archilume Development Image
# =============================================================================
#
# SETUP (one-time):
#   1. Install Docker Desktop: https://www.docker.com/products/docker-desktop
#   2. Install VcXsrv (X server for GUI): https://sourceforge.net/projects/vcxsrv/
#   3. Create a local projects folder:
#        mkdir C:\Users\%USERPROFILE%\archilume-projects
#
# RUN:
#   1. Launch VcXsrv using xlaunch.exe with "Disable access control" checked
#   2. Run:
# docker run --rm -it -e DISPLAY=host.docker.internal:0.0 -v "C:\Users\VincentLogarzo\archilume-projects:/workspace/projects" vlogarzo/archilume-dev:latest
#
#   Your project files are saved to %USERPROFILE%\archilume-projects and
#   persist even if the container is stopped or deleted.
#
# MAINTAINER COMMANDS (not needed by end users):
# docker build --load --no-cache -t archilume-dev -f .devcontainer/Dockerfile .
# docker tag archilume-dev vlogarzo/archilume-dev:latest
# docker push vlogarzo/archilume-dev:latest

# =============================================================================


# -----------------------------------------------------------------------------
# BASE IMAGE
# -----------------------------------------------------------------------------
# Microsoft's devcontainer base for Python 3.12. Includes git, curl, sudo,
# and a non-root "vscode" user that VS Code expects.
# -----------------------------------------------------------------------------
FROM mcr.microsoft.com/devcontainers/python:3.12


# -----------------------------------------------------------------------------
# METADATA (optional but good practice)
# -----------------------------------------------------------------------------
#
# LABEL adds key=value metadata to the image. Useful for:
#   - Identifying images in a registry
#   - Automation tools that filter by label
#   - Documentation
# -----------------------------------------------------------------------------
LABEL org.opencontainers.image.title="Archilume Dev Environment"
LABEL org.opencontainers.image.description="Python 3.12 + Radiance 6.1 + Accelerad for architectural daylight simulation"
LABEL org.opencontainers.image.source="https://github.com/vincentlogarzo/archilume.git"


# -----------------------------------------------------------------------------
# ENVIRONMENT VARIABLES
# -----------------------------------------------------------------------------
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

# Tool paths — baked into the image so they're always available.
# ACCELERAD_ROOT is read by config.py (line 43) to locate Accelerad binaries.
# Note: AcceleradRT.exe is Windows-only and not available in this Linux image.
ENV PATH="${PATH}:/usr/local/radiance/bin:/usr/local/accelerad/bin" \
    RAYPATH="/usr/local/accelerad/lib:/usr/local/radiance/lib" \
    ACCELERAD_ROOT="/usr/local/accelerad"


# -----------------------------------------------------------------------------
# SYSTEM DEPENDENCIES
# -----------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libgomp1 \
    libglib2.0-0 \
    libtiff6 \
    libtiff-tools \
    xfonts-base \
    libgeos-dev \
    libproj-dev \
    python3-dev \
    build-essential \
    libcairo2-dev \
    pkg-config \
    git \
    cmake \
    libx11-dev \
    tcl-dev \
    tk-dev \
    python3-tk \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Compatibility symlink: Radiance's ra_tiff was compiled against libtiff5,
# but Ubuntu 22.04+ ships libtiff6. This symlink bridges the gap.
RUN ln -sf /usr/lib/x86_64-linux-gnu/libtiff.so.6 \
           /usr/lib/x86_64-linux-gnu/libtiff.so.5


# -----------------------------------------------------------------------------
# INSTALL RADIANCE
# -----------------------------------------------------------------------------
COPY .devcontainer/Radiance_5085332d_Linux/radiance-6.1.5085332d6e-Linux.tar.gz \
     /tmp/radiance.tar.gz

RUN cd /tmp \
    && mkdir radiance-extract \
    && tar -xzf radiance.tar.gz -C radiance-extract \
    && cp -r radiance-extract/*/usr/local/radiance /usr/local/ \
    && chmod -R 755 /usr/local/radiance \
    && rm -rf radiance.tar.gz radiance-extract


# -----------------------------------------------------------------------------
# INSTALL ACCELERAD
# -----------------------------------------------------------------------------
# FIX #2: Pre-built binaries have 644 permissions — must chmod +x.
COPY .devcontainer/accelerad_07_beta_linux/usr/local/accelerad /usr/local/accelerad
RUN chmod +x /usr/local/accelerad/bin/*


# -----------------------------------------------------------------------------
# INSTALL UV PACKAGE MANAGER
# -----------------------------------------------------------------------------
RUN curl -LsSf https://astral.sh/uv/install.sh | \
    env HOME=/root sh -s -- --no-modify-path \
    && mv /root/.local/bin/uv /usr/local/bin/uv \
    && mv /root/.local/bin/uvx /usr/local/bin/uvx


# -----------------------------------------------------------------------------
# INSTALL PYTHON DEPENDENCIES
# -----------------------------------------------------------------------------
# FIX #1: Copy source code AND lock file before uv sync so that:
#   - uv.lock pins exact versions (reproducible builds)
#   - archilume/ package is present for the editable install
# pyproject.toml + uv.lock copied first for layer caching — if only app code
# changes, the dependency install layer is still cached.
WORKDIR /workspace

COPY pyproject.toml uv.lock /workspace/
COPY archilume/ /workspace/archilume/

RUN uv sync --frozen


# -----------------------------------------------------------------------------
# COPY APPLICATION SOURCE
# -----------------------------------------------------------------------------
# Copy remaining files (examples, tests, etc.) — changes here don't
# invalidate the dependency install layer above.
COPY . /workspace/


# -----------------------------------------------------------------------------
# USER
# -----------------------------------------------------------------------------
USER vscode


# -----------------------------------------------------------------------------
# PYTHON PATH
# -----------------------------------------------------------------------------
ENV PATH="/workspace/.venv/bin:${PATH}"


# -----------------------------------------------------------------------------
# DEFAULT COMMAND
# -----------------------------------------------------------------------------
# Launch the Archilume GUI on container start.
# Requires DISPLAY to be set (X11 forwarding via VcXsrv on Windows).
# Override with `docker run archilume-dev bash` to get a shell instead.
# FIX #3: Use python -m (guaranteed) instead of uv run archilume (no console_scripts entry).
# -----------------------------------------------------------------------------
CMD ["python", "-m", "archilume"]
