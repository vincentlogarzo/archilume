# =============================================================================
# Archilume — Multi-stage Dockerfile
#
# Stages and their purpose:
#
#   base                   — Shared foundation: python:3.12, system libs, uv, bun
#   archilume-app-builder  — Intermediate: compiles React/Vite frontend (discarded)
#   archilume-app          — Reflex web UI only, pre-built frontend, no node_modules
#   archilume-engine       — Full simulation engine (Radiance, heavy Python libs)
#   archilume-dev          — VS Code dev container (MS base, Radiance + Accelerad,
#                            vscode user, X11 forwarding). Used by .devcontainer/.
#
# ── Build a specific image ────────────────────────────────────────────────
#   docker build --target archilume-app     -t archilume-app .
#   docker build --target archilume-engine -t archilume-engine .
#   docker build --target archilume-dev    -t archilume-dev .
#
# ── Run ───────────────────────────────────────────────────────────────────
#   UI:
#     docker run -p 3000:3000 -p 8000:8000 \
#                -v /host/projects:/app/projects archilume-app
#
#   Engine:
#     docker run --gpus all \
#                -v /host/projects:/app/projects archilume-engine
#
#   Dev container:  managed by VS Code via .devcontainer/devcontainer.json
#
# ── Maintainer (push dev image) ───────────────────────────────────────────
#   docker build --target archilume-dev --no-cache -t archilume-dev .
#   docker tag archilume-dev vlogarzo/archilume-dev:latest
#   docker push vlogarzo/archilume-dev:latest
# =============================================================================


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1 — base
# Shared foundation inherited by archilume-app and archilume-engine.
# Note: archilume-dev uses its own MS base and does NOT inherit from here.
#
# nodejs, npm, and bun are NOT installed here — they are only needed in the
# archilume-app-builder stage and would waste ~560 MB in every other image.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12 AS base

# Runtime system packages needed by both UI and engine:
#   libcairo2-dev      : cairosvg
#   libgl1             : OpenCV headless (libGL.so.1)
#   libglib2.0-0       : OpenCV (libgthread)
#   libjpeg / libpng   : Pillow image codecs
#   libtiff5-dev       : scikit-image TIFF support
#   libwebp-dev        : Pillow WebP support
#   libxml2 / libxslt  : lxml
#   libffi-dev         : cffi / cairosvg
#   curl               : uv installer
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        libcairo2-dev \
        libgl1 \
        libglib2.0-0 \
        libjpeg-dev \
        libpng-dev \
        libtiff5-dev \
        libwebp-dev \
        libxml2-dev \
        libxslt1-dev \
        libffi-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# uv — Python package manager
RUN curl -Ls https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# Copy only the archilume modules the UI and engine actually import at runtime.
# Excludes apps/, core/, geo/, infra/, post/, workflows/ from the UI image.
# The engine stage adds its own full COPY after this base.
COPY archilume/__init__.py         /app/archilume/__init__.py
COPY archilume/__main__.py         /app/archilume/__main__.py
COPY archilume/_template_dataclass.py /app/archilume/_template_dataclass.py
COPY archilume/config.py           /app/archilume/config.py
COPY archilume/project.py          /app/archilume/project.py
COPY archilume/utils.py            /app/archilume/utils.py

RUN mkdir -p /app/projects
VOLUME ["/app/projects"]

ENV PYTHONPATH="/app"


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2 — archilume-app-builder  (intermediate, not a deliverable image)
# Installs Node/bun/Reflex and compiles the React/Vite frontend.
# node_modules (~500 MB), bun (~99 MB), and npm stay here and are never
# copied into the final image.
# ─────────────────────────────────────────────────────────────────────────────
FROM base AS archilume-app-builder

# Node.js + npm + bun: only needed to compile the frontend, not at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/root/.bun/bin:${PATH}"

RUN uv pip install --system \
        "reflex>=0.8.28.post1" \
        "pillow>=11.3.0" \
        "numpy>=2.3.2" \
        "pymupdf>=1.24.0" \
        "opencv-python-headless>=4.11.0.86" \
        "scikit-image>=0.25.2" \
        "cairosvg>=2.8.2" \
        "svglib>=1.6.0" \
        "svgpathtools>=1.7.2" \
        "lxml>=6.0.2" \
        "psutil>=7.0.0" \
        "pandas>=2.3.1" \
        "plotly>=6.6.0"

COPY archilume/apps/archilume_ui/ /app/archilume_ui_app/

WORKDIR /app/archilume_ui_app

# Compile the React/Vite frontend into static assets.
# node_modules is created here but discarded — only .web/build is carried over.
RUN reflex export --no-zip 2>/dev/null || (reflex init && reflex export --no-zip)


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 3 — archilume-app  (final deliverable)
# Reflex web application: AOI editor, project browser, DF analysis viewer.
# Receives only the compiled frontend assets from the builder — no node_modules,
# no bun cache, no npm.
#
# Excluded (engine only): pyvista, vtk, ifcopenshell, pyradiance, selenium,
#   openpyxl, svg2png
# ─────────────────────────────────────────────────────────────────────────────
FROM base AS archilume-app

LABEL org.opencontainers.image.title="Archilume App"
LABEL org.opencontainers.image.description="Archilume web UI — open http://localhost:3000 after starting"

# Python packages only — no Node tooling needed at runtime
RUN uv pip install --system \
        "reflex>=0.8.28.post1" \
        "pillow>=11.3.0" \
        "numpy>=2.3.2" \
        "pymupdf>=1.24.0" \
        "opencv-python-headless>=4.11.0.86" \
        "scikit-image>=0.25.2" \
        "cairosvg>=2.8.2" \
        "svglib>=1.6.0" \
        "svgpathtools>=1.7.2" \
        "lxml>=6.0.2" \
        "psutil>=7.0.0" \
        "pandas>=2.3.1" \
        "plotly>=6.6.0" \
    && uv cache clean

# Copy the Python app source
COPY archilume/apps/archilume_ui/ /app/archilume_ui_app/

# Copy only the compiled frontend build — leaves node_modules behind in builder
COPY --from=archilume-app-builder /app/archilume_ui_app/.web/build \
                                  /app/archilume_ui_app/.web/build

WORKDIR /app/archilume_ui_app

# 3000 : Reflex frontend (React, served by Reflex in prod mode)
# 8000 : Reflex backend  (Python WebSocket + REST API, Reflex default)
EXPOSE 3000 8000

CMD ["reflex", "run", "--env", "prod", "--backend-host", "0.0.0.0"]


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 4 — archilume-engine
# Full simulation engine: Radiance pipelines, geometry processing, reporting.
#
# Radiance and Accelerad binaries are bundled from the repo's .devcontainer/
# directory — the same binaries used in local development.
#
# GPU rendering (AcceleradRT) requires:  docker run --gpus all ...
# Override tool paths via env vars:  RADIANCE_ROOT, ACCELERAD_ROOT
# ─────────────────────────────────────────────────────────────────────────────
FROM base AS archilume-engine

# Additional system packages needed by the engine (not required by UI)
RUN apt-get update && apt-get install -y --no-install-recommends \
        # pyvista / vtk headless rendering
        libgomp1 \
        libxrender1 \
        libxext6 \
        # Radiance ra_tiff compiled against libtiff5; Ubuntu ships libtiff6
        libtiff6 \
        libtiff-tools \
        # build tools (some Python packages compile C extensions)
        build-essential \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

# libtiff compatibility symlink (same fix as in the dev container)
RUN ln -sf /usr/lib/x86_64-linux-gnu/libtiff.so.6 \
           /usr/lib/x86_64-linux-gnu/libtiff.so.5

# Install Radiance (Linux binaries from .devcontainer/)
COPY .devcontainer/Radiance_5085332d_Linux/radiance-6.1.5085332d6e-Linux.tar.gz \
     /tmp/radiance.tar.gz
RUN cd /tmp \
    && mkdir radiance-extract \
    && tar -xzf radiance.tar.gz -C radiance-extract \
    && cp -r radiance-extract/*/usr/local/radiance /usr/local/ \
    && chmod -R 755 /usr/local/radiance \
    && rm -rf radiance.tar.gz radiance-extract

# Install Accelerad (Linux binaries from .devcontainer/)
COPY .devcontainer/accelerad_07_beta_linux/usr/local/accelerad /usr/local/accelerad
RUN chmod +x /usr/local/accelerad/bin/*

ENV PATH="${PATH}:/usr/local/radiance/bin:/usr/local/accelerad/bin" \
    RAYPATH="/usr/local/accelerad/lib:/usr/local/radiance/lib" \
    ACCELERAD_ROOT="/usr/local/accelerad" \
    RADIANCE_ROOT="/usr/local/radiance"

# Engine needs the full archilume package — override the surgical base copy
COPY archilume/ /app/archilume/

# Full engine Python dependencies
RUN uv pip install --system \
        "pillow>=11.3.0" \
        "numpy>=2.3.2" \
        "pymupdf>=1.24.0" \
        "opencv-python-headless>=4.11.0.86" \
        "scikit-image>=0.25.2" \
        "cairosvg>=2.8.2" \
        "svglib>=1.6.0" \
        "svgpathtools>=1.7.2" \
        "svg2png>=1.2" \
        "lxml>=6.0.2" \
        "psutil>=7.0.0" \
        "pandas>=2.3.1" \
        "plotly>=6.6.0" \
        "openpyxl>=3.1.5" \
        "pyradiance>=1.2.0" \
        "pyvista>=0.46.4" \
        "vtk>=9.6.0" \
        "ifcopenshell>=0.8.3.post1" \
        "selenium>=4.41.0" \
    && uv cache clean

WORKDIR /app

# Run a workflow script passed via CMD override, e.g.:
#   docker run archilume-engine python examples/sunlight_access_workflow.py
CMD ["python", "-c", "import archilume; print('Archilume engine ready.')"]


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 5 — archilume-dev
# VS Code dev container. Used exclusively by .devcontainer/devcontainer.json.
#
# Differences from the other stages:
#   - Based on mcr.microsoft.com/devcontainers/python:3.12 (includes git,
#     sudo, and the non-root "vscode" user that VS Code expects)
#   - Does NOT inherit from base (different parent image)
#   - Installs the full project via uv sync --frozen (editable, with dev deps)
#   - X11 forwarding support for GUI tools on Windows via VcXsrv
#   - Radiance + Accelerad installed identically to archilume-engine
#
# Setup (one-time, Windows):
#   1. Install Docker Desktop
#   2. Install VcXsrv: https://sourceforge.net/projects/vcxsrv/
#      Launch with "Disable access control" checked
#   3. Open repo in VS Code → "Reopen in Container"
# ─────────────────────────────────────────────────────────────────────────────
FROM mcr.microsoft.com/devcontainers/python:3.12 AS archilume-dev

LABEL org.opencontainers.image.title="Archilume Dev Environment"
LABEL org.opencontainers.image.description="Python 3.12 + Radiance 6.1 + Accelerad for architectural daylight simulation"
LABEL org.opencontainers.image.source="https://github.com/vincentlogarzo/archilume.git"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

ENV PATH="${PATH}:/usr/local/radiance/bin:/usr/local/accelerad/bin" \
    RAYPATH="/usr/local/accelerad/lib:/usr/local/radiance/lib" \
    ACCELERAD_ROOT="/usr/local/accelerad"

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

# libtiff compatibility symlink
RUN ln -sf /usr/lib/x86_64-linux-gnu/libtiff.so.6 \
           /usr/lib/x86_64-linux-gnu/libtiff.so.5

# Install Radiance
COPY .devcontainer/Radiance_5085332d_Linux/radiance-6.1.5085332d6e-Linux.tar.gz \
     /tmp/radiance.tar.gz
RUN cd /tmp \
    && mkdir radiance-extract \
    && tar -xzf radiance.tar.gz -C radiance-extract \
    && cp -r radiance-extract/*/usr/local/radiance /usr/local/ \
    && chmod -R 755 /usr/local/radiance \
    && rm -rf radiance.tar.gz radiance-extract

# Install Accelerad
COPY .devcontainer/accelerad_07_beta_linux/usr/local/accelerad /usr/local/accelerad
RUN chmod +x /usr/local/accelerad/bin/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | \
    env HOME=/root sh -s -- --no-modify-path \
    && mv /root/.local/bin/uv /usr/local/bin/uv \
    && mv /root/.local/bin/uvx /usr/local/bin/uvx

# Install Python dependencies via uv sync (pinned via uv.lock)
# pyproject.toml + uv.lock copied first for layer caching
WORKDIR /workspace

COPY pyproject.toml uv.lock /workspace/
COPY archilume/ /workspace/archilume/
RUN uv sync --frozen

# Copy remaining source (examples, tests, etc.)
# Changes here don't bust the dependency install layer above
COPY . /workspace/

ENV PATH="/workspace/.venv/bin:${PATH}"

USER vscode

CMD ["python", "-m", "archilume"]
