# Archilume Dev Container

Linux development environment for Archilume. Intended to run on a cloud Linux VM (e.g. GCP) via VS Code Remote-SSH, giving you Radiance + Python 3.12 + all project deps without polluting the host.

## What's Included

- **Python 3.12** via `python:3.12-slim` base
- **Radiance 6.1** (build 5085332d) — native Linux binaries at `/usr/local/radiance`
- **uv** — package manager
- **All dep groups** — `app`, `engine`, `desktop`, `dev` installed into `/opt/venv`
- **Google Cloud SDK** — `gcloud`, `gsutil`, `bq` for `GCPVMManager` workflows
- **Build toolchain** — `gcc`, `cmake`, `pkg-config`, plus OpenGL/X11 libs for `pyvista`, `vtk`, `cairosvg`

**Not included:** Accelerad (local-only — runs on Windows/macOS hosts with a GPU, not inside this Linux container).

## Build Source

The container builds from [`../.docker/Dockerfile`](../.docker/Dockerfile), target `archilume-dev`. It reuses the same `base-slim` and `radiance-extract` stages as the distribution engine image, so Python and Radiance versions can't drift between dev and production.

## Environment Variables

Baked into the image (`ENV` in the Dockerfile):

- `PATH` — `/opt/venv/bin:/usr/local/radiance/bin:/opt/google-cloud-sdk/bin:…`
- `RAYPATH` — `/usr/local/radiance/lib`
- `RADIANCE_ROOT` — `/usr/local/radiance`
- `UV_LINK_MODE=copy` — suppresses uv hardlink warnings
- `UV_PROJECT_ENVIRONMENT=/opt/venv` — uv syncs into the baked venv, not `.venv`

Supplied at runtime by [`devcontainer.json`](devcontainer.json) `remoteEnv`:

- `DISPLAY` (for X11 forwarding via VcXsrv)
- `CLAUDE_API_KEY`, `TZ` from host

## How to Use

### Opening in DevContainer (VS Code with Remote-SSH)

1. **Connect to your Linux VM via SSH in VS Code:**
   - Install the "Remote - SSH" extension
   - `F1` → "Remote-SSH: Connect to Host" → enter `user@your-vm-ip`

2. **Open the project in a DevContainer:**
   - Once connected, open the Archilume folder
   - VS Code detects `.devcontainer/devcontainer.json`
   - Click "Reopen in Container" (or `F1` → "Dev Containers: Reopen in Container")

3. **First build: ~5–10 min.** The Dockerfile handles everything: system libs, Radiance extraction, all Python deps, GCloud SDK. `postCreateCommand` just fixes bind-mount ownership and runs a final `uv sync` to install the project editably.

4. **Verify:**

   ```bash
   python --version          # 3.12.x
   uv --version
   oconv 2>&1 | head -1      # Radiance works
   gcloud --version          # GCP SDK present
   pytest --version          # dev group installed
   ```

### Rebuilding

After changing `.devcontainer/devcontainer.json` or `.docker/Dockerfile`:

1. `Ctrl+Shift+P` → "Dev Containers: Rebuild Container"
2. Wait for rebuild (layer cache keeps this fast unless apt/uv layers changed)

### Python Interpreter

VS Code is pre-configured to use `/opt/venv/bin/python`. The venv is built by the image; the project is installed editably at container start by `postCreateCommand`.

## Radiance Tools Available

- `oconv` — Scene → octree
- `rpict` — Render from octree (CPU)
- `rtpict` — Ray-tracing renderer (daylight workflows)
- `rcontrib` — Contribution rendering
- `gensky` — Sky generation
- `obj2rad` — OBJ → Radiance
- `pcomb` — HDR compositing
- `ra_tiff` — HDR → TIFF

## Troubleshooting

### Radiance commands not found

Env vars are set in the image. If they somehow aren't active:

```bash
export PATH=/usr/local/radiance/bin:$PATH
export RAYPATH=/usr/local/radiance/lib
```

### UV link mode warnings

The image sets `UV_LINK_MODE=copy`. If you still see them:

```bash
export UV_LINK_MODE=copy
```

### Python deps missing after rebuild

The image bakes deps into `/opt/venv`. If something's missing after a pull:

```bash
uv sync --frozen
```

### Accelerad / GPU rendering

Not available in this container. Run Accelerad locally on a Windows/macOS host with GPU access, or use the legacy CPU path in Radiance (`rpict`, `rtpict`).

### "Reopen in Container" fails with unknown target

Ensure `.docker/Dockerfile` is on disk and git up to date — the `archilume-dev` target must exist. If the build references `../Dockerfile` (old path), pull latest and rebuild.

## Architecture

- [`devcontainer.json`](devcontainer.json) — VS Code build + runtime config
- [`../.docker/Dockerfile`](../.docker/Dockerfile) — `archilume-dev` target (single source of truth)
- [`README.md`](README.md) — this file
- `Radiance_5085332d_Linux/` — bundled Radiance tarball, extracted into the image

## Using uv

```bash
uv sync                 # install all default dep groups
uv add <package>        # add a new runtime dep
uv add --group dev <p>  # add a dev-only dep
uv run pytest           # run command inside the project venv
uv pip list             # show installed packages
```
