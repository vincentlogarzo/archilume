# syntax=docker/dockerfile:1.7

# Stages:
#   base-slim ──┬── py-build-app ─────┐
#               │                      ├── frontend-builder ── archilume-frontend (Caddy static)
#               │                      └── archilume-backend (Reflex backend-only)
#               ├── py-build-engine ──┐
#               │                      └── archilume-engine
#               ├── radiance-extract ─┘
#               └── archilume-dev (VS Code devcontainer — full engine+desktop+dev env)

# All commands below are run from the repo root.

# Build all three images in parallel (recommended — BuildKit fans out independent targets):
#   docker buildx bake --load -f docker/docker-bake.hcl

# Build without cache:
#   docker buildx bake --load --no-cache -f docker/docker-bake.hcl

# Build + push to Docker Hub:
#   docker login
#   docker buildx bake --push --provenance=false -f docker/docker-bake.hcl

# Cloud frontend build (bake a public URL into the JS bundle):
#   REFLEX_API_URL=https://archilume.example.com docker buildx bake --load -f docker/docker-bake.hcl archilume-frontend

# Run the app:
#   docker compose -f docker/docker-compose-archilume.yml up -d
#   Then open http://localhost:3000


# ── base-slim ─────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base-slim

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl tini \
        libglib2.0-0 libjpeg62-turbo libpng16-16 libtiff6 libwebp7 \
        libexpat1 libxml2 libxslt1.1 libffi8

RUN groupadd -g 1000 app && useradd -u 1000 -g 1000 -m -s /bin/bash app \
    && mkdir -p /app /app/projects /opt/venv \
    && chown -R 1000:1000 /app /opt/venv

ENV PYTHONPATH=/app \
    PATH=/opt/venv/bin:/root/.local/bin:${PATH} \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app
VOLUME ["/app/projects"]


# ── py-build-app ──────────────────────────────────────────────────────────────
FROM base-slim AS py-build-app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ pkg-config libffi-dev libxml2-dev libxslt1-dev python3-dev

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-default-groups --group app


# ── py-build-engine ───────────────────────────────────────────────────────────
FROM base-slim AS py-build-engine

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ pkg-config libffi-dev libxml2-dev libxslt1-dev python3-dev

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-default-groups --group engine


# ── radiance-extract ──────────────────────────────────────────────────────────
FROM alpine:3.20 AS radiance-extract

COPY .devcontainer/Radiance_5085332d_Linux/radiance-6.1.5085332d6e-Linux.tar.gz /tmp/r.tgz
RUN mkdir -p /out/usr/local && cd /tmp \
    && mkdir extract && tar -xzf r.tgz -C extract \
    && cp -r extract/*/usr/local/radiance /out/usr/local/radiance \
    && chmod -R 755 /out/usr/local/radiance


# ── frontend-builder ──────────────────────────────────────────────────────────
FROM py-build-app AS frontend-builder

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends nodejs npm unzip

RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/root/.bun/bin:${PATH}"

# Same-origin deploy: Caddy on :3000 proxies /_event, /_upload, /ping to the
# backend. Default baked URL targets Caddy (not the backend directly), matching
# Reflex's simple-one-port docker-example. For cloud deploys, override at build
# time: --build-arg REFLEX_API_URL=https://archilume.example.com
ARG REFLEX_API_URL=http://localhost:3000
ENV API_URL=${REFLEX_API_URL}

COPY archilume/apps/archilume_app/ /app/archilume_app/
WORKDIR /app/archilume_app
RUN reflex export --frontend-only --no-zip


# ── archilume-frontend ────────────────────────────────────────────────────────
FROM caddy:2-alpine AS archilume-frontend

LABEL org.opencontainers.image.title="Archilume Frontend"
LABEL org.opencontainers.image.description="Caddy serving exported Reflex static build + reverse proxy to backend on :3000"

COPY --from=frontend-builder /app/archilume_app/.web/build/client /srv
COPY docker/Caddyfile /etc/caddy/Caddyfile

EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:3000/ping-frontend >/dev/null 2>&1 || exit 1


# ── archilume-backend ─────────────────────────────────────────────────────────
FROM base-slim AS archilume-backend

LABEL org.opencontainers.image.title="Archilume Backend"
LABEL org.opencontainers.image.description="Reflex backend-only (state, websocket, engine client) on :8000"

# Radiance runtime .so deps + DejaVu fonts for annotated-overlay glyph coverage
# (superscript ² and ≥ symbols used in DF annotations). fonts-dejavu-core is
# ~3 MB and PIL's freetype short-name lookup picks it up automatically.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 libxrender1 libxext6 libice6 libsm6 libx11-6 \
        fonts-dejavu-core

# Radiance binaries expect libtiff.so.5 but Debian 13 ships .so.6 only.
RUN ln -sf /usr/lib/x86_64-linux-gnu/libtiff.so.6 \
           /usr/lib/x86_64-linux-gnu/libtiff.so.5

COPY --from=py-build-app --chown=1000:1000 /opt/venv /opt/venv
COPY --from=radiance-extract /out/usr/local/radiance /usr/local/radiance
COPY --chown=1000:1000 archilume/apps/archilume_app/ /app/archilume_app/
COPY --chown=1000:1000 \
    archilume/__init__.py \
    archilume/config.py \
    archilume/utils.py \
    archilume/project.py \
    archilume/_template_dataclass.py \
    /app/archilume/
COPY --chown=1000:1000 archilume/post/__init__.py archilume/post/hdr_visualisation.py /app/archilume/post/

ENV PATH=/opt/venv/bin:/usr/local/radiance/bin:${PATH} \
    RAYPATH=/usr/local/radiance/lib \
    RADIANCE_ROOT=/usr/local/radiance

WORKDIR /app/archilume_app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/ping || exit 1
ENTRYPOINT ["tini", "--"]
CMD ["reflex", "run", "--env", "prod", "--backend-only", "--backend-host", "0.0.0.0"]


# ── archilume-app (deprecated alias) ──────────────────────────────────────────
# Back-compat alias so any lingering `--target archilume-app` builds still resolve.
# Remove after callers migrate to archilume-frontend / archilume-backend.
FROM archilume-backend AS archilume-app


# ── archilume-engine ──────────────────────────────────────────────────────────
FROM base-slim AS archilume-engine

LABEL org.opencontainers.image.title="Archilume Engine"
LABEL org.opencontainers.image.description="Archilume FastAPI engine — Radiance-based daylight/sunlight compute service on :8100"

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 libxrender1 libxext6 libice6 libsm6 libx11-6

RUN ln -sf /usr/lib/x86_64-linux-gnu/libtiff.so.6 \
           /usr/lib/x86_64-linux-gnu/libtiff.so.5

COPY --from=py-build-engine --chown=1000:1000 /opt/venv /opt/venv
COPY --from=radiance-extract /out/usr/local/radiance /usr/local/radiance
COPY --chown=1000:1000 archilume/ /app/archilume/

ENV PATH=/opt/venv/bin:/usr/local/radiance/bin:${PATH} \
    RAYPATH=/usr/local/radiance/lib \
    RADIANCE_ROOT=/usr/local/radiance

WORKDIR /app
USER app
EXPOSE 8100
HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8100/health || exit 1
ENTRYPOINT ["tini", "--"]
CMD ["python", "-m", "archilume.api.run"]


# ── archilume-dev ─────────────────────────────────────────────────────────────
# VS Code devcontainer target. Full dev environment: engine + desktop + dev
# dep groups, native Radiance, Google Cloud SDK (for GCPVMManager workflows),
# build tools for C-extension packages (pyvista/vtk/cairosvg/geos/proj).
# Accelerad is intentionally excluded — local-only per project notes.
FROM base-slim AS archilume-dev

LABEL org.opencontainers.image.title="Archilume Dev Container"
LABEL org.opencontainers.image.description="Linux dev environment for Archilume — Radiance, Python 3.12, uv, GCloud SDK"

USER root

# Dev-time system libs + build tools. Mirrors what setup.sh used to install
# plus X11/OpenGL libs shared with archilume-engine for desktop visualisation.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        sudo git openssh-client \
        build-essential cmake pkg-config python3-dev \
        gcc g++ libffi-dev libxml2-dev libxslt1-dev \
        libgl1 libgomp1 libxrender1 libxext6 libice6 libsm6 libx11-6 \
        libgeos-dev libproj-dev libcairo2-dev \
        libtiff-tools xfonts-base \
    && ln -sf /usr/lib/x86_64-linux-gnu/libtiff.so.6 \
              /usr/lib/x86_64-linux-gnu/libtiff.so.5

# Native Radiance (reuse extract stage — same tarball as archilume-engine).
COPY --from=radiance-extract /out/usr/local/radiance /usr/local/radiance

# Google Cloud SDK — used by archilume.infra.GCPVMManager for VM lifecycle.
RUN curl -sSL https://sdk.cloud.google.com | bash -s -- \
        --disable-prompts --install-dir=/opt \
    && ln -sf /opt/google-cloud-sdk/bin/gcloud /usr/local/bin/gcloud \
    && ln -sf /opt/google-cloud-sdk/bin/gsutil /usr/local/bin/gsutil \
    && ln -sf /opt/google-cloud-sdk/bin/bq /usr/local/bin/bq

# uv (same source as other stages).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install all default dep groups (app + engine + desktop + dev) into /opt/venv.
# --no-install-project: the project is bind-mounted at runtime; postCreateCommand
# runs `uv sync --frozen` again to install the project editably on top.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project \
    && chown -R 1000:1000 /opt/venv

# vscode user at UID 1001 (app is UID 1000 in base-slim — keep distinct).
# Primary group 0 (root) matches Microsoft devcontainer convention for bind
# mount compatibility across arbitrary host UIDs.
RUN useradd --uid 1001 --gid 0 --create-home --shell /bin/bash vscode \
    && echo "vscode ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/vscode \
    && chmod 0440 /etc/sudoers.d/vscode \
    && chown -R 1001:0 /opt/venv /home/vscode

ENV PATH=/opt/venv/bin:/usr/local/radiance/bin:/opt/google-cloud-sdk/bin:/home/vscode/.local/bin:${PATH} \
    RAYPATH=/usr/local/radiance/lib \
    RADIANCE_ROOT=/usr/local/radiance \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

USER vscode
WORKDIR /workspaces/archilume
