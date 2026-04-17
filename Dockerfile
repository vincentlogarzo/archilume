# Stages: base → archilume-app-builder → archilume-app
#                base →                   archilume-engine
#
# Build:
#   docker build --target archilume-app    -t archilume-app .
#   docker build --target archilume-engine -t archilume-engine .
# Push:
#   docker tag archilume-app vlogarzo/archilume-app:latest && docker push vlogarzo/archilume-app:latest
#   docker tag archilume-engine vlogarzo/archilume-engine:latest && docker push vlogarzo/archilume-engine:latest


# ── base ──────────────────────────────────────────────────────────────────────
FROM python:3.12 AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl libcairo2-dev libgl1 libglib2.0-0 \
        libjpeg-dev libpng-dev libtiff5-dev libwebp-dev \
        libxml2-dev libxslt1-dev libffi-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN curl -Ls https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app
COPY archilume/__init__.py archilume/__main__.py archilume/_template_dataclass.py \
     archilume/config.py archilume/project.py archilume/utils.py \
     /app/archilume/

RUN mkdir -p /app/projects
VOLUME ["/app/projects"]
ENV PYTHONPATH="/app"


# ── archilume-app-builder (intermediate) ──────────────────────────────────────
FROM base AS archilume-app-builder

RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/root/.bun/bin:${PATH}"

RUN uv pip install --system \
        "reflex>=0.8.28.post1" "pillow>=11.3.0" "numpy>=2.3.2" \
        "pymupdf>=1.24.0" "opencv-python-headless>=4.11.0.86" \
        "scikit-image>=0.25.2" "cairosvg>=2.8.2" "svglib>=1.6.0" \
        "svgpathtools>=1.7.2" "lxml>=6.0.2" "psutil>=7.0.0" \
        "pandas>=2.3.1" "plotly>=6.6.0"

COPY archilume/apps/archilume_app/ /app/archilume_app/
WORKDIR /app/archilume_app
RUN reflex export --no-zip 2>/dev/null || (reflex init && reflex export --no-zip)


# ── archilume-app ──────────────────────────────────────────────────────────────
FROM base AS archilume-app

LABEL org.opencontainers.image.title="Archilume App"
LABEL org.opencontainers.image.description="Archilume web UI — open http://localhost:3000 after starting"

RUN uv pip install --system \
        "reflex>=0.8.28.post1" "pillow>=11.3.0" "numpy>=2.3.2" \
        "pymupdf>=1.24.0" "opencv-python-headless>=4.11.0.86" \
        "scikit-image>=0.25.2" "cairosvg>=2.8.2" "svglib>=1.6.0" \
        "svgpathtools>=1.7.2" "lxml>=6.0.2" "psutil>=7.0.0" \
        "pandas>=2.3.1" "plotly>=6.6.0" \
    && uv cache clean

COPY archilume/apps/archilume_app/ /app/archilume_app/
COPY --from=archilume-app-builder /app/archilume_app/.web/build \
                                  /app/archilume_app/.web/build
WORKDIR /app/archilume_app

EXPOSE 3000 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:3000/ || exit 1
CMD ["reflex", "run", "--env", "prod", "--backend-host", "0.0.0.0"]


# ── archilume-engine ──────────────────────────────────────────────────────────
FROM base AS archilume-engine

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 libxrender1 libxext6 libtiff6 libtiff-tools \
        build-essential python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/lib/x86_64-linux-gnu/libtiff.so.6 \
           /usr/lib/x86_64-linux-gnu/libtiff.so.5

COPY .devcontainer/Radiance_5085332d_Linux/radiance-6.1.5085332d6e-Linux.tar.gz /tmp/radiance.tar.gz
RUN cd /tmp && mkdir radiance-extract \
    && tar -xzf radiance.tar.gz -C radiance-extract \
    && cp -r radiance-extract/*/usr/local/radiance /usr/local/ \
    && chmod -R 755 /usr/local/radiance \
    && rm -rf radiance.tar.gz radiance-extract

COPY .devcontainer/accelerad_07_beta_linux/usr/local/accelerad /usr/local/accelerad
RUN chmod +x /usr/local/accelerad/bin/*

ENV PATH="${PATH}:/usr/local/radiance/bin:/usr/local/accelerad/bin" \
    RAYPATH="/usr/local/accelerad/lib:/usr/local/radiance/lib" \
    ACCELERAD_ROOT="/usr/local/accelerad" \
    RADIANCE_ROOT="/usr/local/radiance"

COPY archilume/ /app/archilume/

RUN uv pip install --system \
        "pillow>=11.3.0" "numpy>=2.3.2" "pymupdf>=1.24.0" \
        "opencv-python-headless>=4.11.0.86" "scikit-image>=0.25.2" \
        "cairosvg>=2.8.2" "svglib>=1.6.0" "svgpathtools>=1.7.2" \
        "svg2png>=1.2" "lxml>=6.0.2" "psutil>=7.0.0" "pandas>=2.3.1" \
        "plotly>=6.6.0" "openpyxl>=3.1.5" "pyradiance>=1.2.0" \
        "pyvista>=0.46.4" "vtk>=9.6.0" "ifcopenshell>=0.8.3.post1" \
        "selenium>=4.41.0" \
        "fastapi>=0.135.3" "uvicorn>=0.34.0" \
    && uv cache clean

WORKDIR /app
EXPOSE 8100
HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8100/health || exit 1
CMD ["python", "-m", "archilume.api.run"]
