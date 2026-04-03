# =============================================================================
# Archilume Reflex UI – Production Dockerfile
# =============================================================================
#
# Builds and runs the Reflex web UI with correct WebSocket port forwarding.
#
# Reflex requires TWO ports:
#   - 3000: Frontend (static Vite build served by Reflex)
#   - 8000: Backend (FastAPI/uvicorn, all UI state via WebSocket at /_event)
#
# The backend URL (api_url) is baked into the frontend JS at build time.
# It MUST be reachable from the browser, not from inside the container.
#
# BUILD (local machine – browser on same machine as Docker):
#   docker build -t archilume-ui .
#   docker run -p 3000:3000 -p 8000:8000 archilume-ui
#
# BUILD (remote VM / server – browser on a different machine):
#   docker build --build-arg API_URL=http://<server-ip>:8000 -t archilume-ui .
#   docker run -p 3000:3000 -p 8000:8000 archilume-ui
#
# =============================================================================


# -----------------------------------------------------------------------------
# BASE IMAGE
# -----------------------------------------------------------------------------
FROM python:3.12

WORKDIR /app


# -----------------------------------------------------------------------------
# SYSTEM DEPENDENCIES
# -----------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*


# -----------------------------------------------------------------------------
# INSTALL UV PACKAGE MANAGER
# -----------------------------------------------------------------------------
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv \
    && mv /root/.local/bin/uvx /usr/local/bin/uvx


# -----------------------------------------------------------------------------
# INSTALL PYTHON DEPENDENCIES
# -----------------------------------------------------------------------------
# Copy dependency files first for layer caching – if only app code changes,
# the dependency install layer is still cached.
COPY pyproject.toml uv.lock /app/
COPY archilume/ /app/archilume/

RUN uv sync --frozen


# -----------------------------------------------------------------------------
# COPY REMAINING APPLICATION SOURCE
# -----------------------------------------------------------------------------
COPY . /app/


# -----------------------------------------------------------------------------
# INITIALIZE REFLEX
# -----------------------------------------------------------------------------
# Must run from the Reflex app directory where rxconfig.py lives.
WORKDIR /app/archilume/apps/archilume_ui
RUN uv run reflex init


# -----------------------------------------------------------------------------
# BUILD FRONTEND WITH BAKED-IN API_URL
# -----------------------------------------------------------------------------
# api_url is the URL the BROWSER uses to reach the backend WebSocket.
#   - For local Docker:  http://localhost:8000  (default)
#   - For remote server:  http://<server-ip>:8000
#   - For domain + proxy: https://<domain.com>
#
# Override at build time:
#   docker build --build-arg API_URL=http://<your-host>:8000 -t archilume-ui .
#
# IMPORTANT: Changing API_URL at `docker run` time has NO effect on the
# compiled frontend JS. You must rebuild the image.
ARG API_URL=http://localhost:8000
ENV API_URL=${API_URL}
RUN uv run reflex export --frontend-only --no-zip


# -----------------------------------------------------------------------------
# EXPOSE PORTS
# -----------------------------------------------------------------------------
# 3000 = Frontend (HTTP)
# 8000 = Backend (WebSocket at /_event)
EXPOSE 3000 8000


# -----------------------------------------------------------------------------
# RUN
# -----------------------------------------------------------------------------
# reflex run --env prod binds the backend to 0.0.0.0:8000 by default.
# This is required for Docker port mapping to work.
# Never override with --host 127.0.0.1 (traffic would be unreachable).
CMD ["uv", "run", "reflex", "run", "--env", "prod"]
