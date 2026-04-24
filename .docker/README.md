# Archilume — Docker distribution

This directory packages Archilume for end users via Docker Compose. For local
development inside VS Code, see [`../.devcontainer/README.md`](../.devcontainer/README.md) —
the dev container reuses `base-slim` and `radiance-extract` stages from this
Dockerfile via the `archilume-dev` target.

## Requirements

Any Docker runtime with Compose v2:

- [Docker Desktop](https://www.docker.com/products/docker-desktop) on Windows 10/11, macOS, or Linux (note Docker Desktop's [subscription terms](https://www.docker.com/pricing/) for larger organisations)
- [Rancher Desktop](https://rancherdesktop.io/), [OrbStack](https://orbstack.dev/) (macOS), [Colima](https://github.com/abiosoft/colima) (macOS/Linux), or the standalone Docker Engine on Linux are drop-in free alternatives

## Quick start

1. Unzip `archilume.zip` anywhere (any drive, any folder, spaces in the path are fine).
2. Launch using the one-action entry point for your OS:

   | Platform | Action |
   | --- | --- |
   | **Windows** | Double-click `launch-archilume.cmd`. |
   | **macOS** | Double-click `launch-archilume.command` in Finder. First time only, right-click the file and choose **Open** to approve Gatekeeper. |
   | **Linux** | From a terminal in the unzipped folder, run `./launch-archilume.sh` (make it executable once with `chmod +x launch-archilume.sh` if your unzip tool dropped the bit). |

3. Wait until the launcher reports "Archilume is running" and opens your browser on <http://localhost:3000>.

Each launcher follows the same six stages:

1. Verify the compose file and `projects/` folder are next to it.
2. Check the Docker Engine is reachable. On Windows, find and start Docker Desktop if needed. On macOS, `open -a Docker`. On Linux, print a hint if the daemon is not running.
3. Tear down any previous `archilume` compose stack.
4. Check port 3000 for conflicts and prompt before stopping a foreign process.
5. `docker compose up -d` — pulls any missing images automatically, reuses cached ones.
6. Poll `http://localhost:3000/ping-frontend` until healthy, then open the browser.

Your project data lives in the `projects/` folder next to the compose file. Anything saved from the app writes back to that folder on your host.

## Version pinning

The shipped `.env` sets `ARCHILUME_VERSION` to the release tag, so the zip resolves to a specific image triple on Docker Hub (`vlogarzo/archilume-frontend|backend|engine:<tag>`). To track the newest published image instead, edit `.env` to `ARCHILUME_VERSION=latest` and run `docker compose -f docker-compose-archilume.yml -p archilume pull` before relaunching.

## Stopping Archilume

- **Any platform:** rerun the launcher (it tears down the previous stack before starting a fresh one).
- **Docker Desktop GUI:** click the `archilume` stack → **Stop**.
- **CLI fallback:** `docker compose -f docker-compose-archilume.yml -p archilume down`.

## Troubleshooting

### All platforms

- **"Port 3000 is held by …"** — another app is using 3000. The launcher prompts before stopping it.
- **Get a newer image** — run `docker compose -f docker-compose-archilume.yml -p archilume pull` from the unzipped folder, then relaunch. To always track latest, also edit `.env` as described above.
- **"Frontend did not become healthy"** — the launcher prints `docker compose ps` output. Check that all three containers show `running` / `healthy`; if not, `docker compose -f docker-compose-archilume.yml -p archilume logs <service>` names the failure.

### Windows

- **Window closes instantly with no message** — you ran `_launch-archilume.ps1` directly instead of double-clicking `launch-archilume.cmd`. The `.cmd` wrapper keeps the window open on exit.
- **"Docker Desktop was not found"** — enter the full path to `Docker Desktop.exe` when prompted. It is remembered for next time in `.docker-path.txt`.

### macOS

- **"launch-archilume.command can't be opened because it is from an unidentified developer"** — Gatekeeper blocks the first run. Right-click the file in Finder → **Open** → **Open** in the confirmation dialog. macOS remembers the approval for subsequent double-clicks.
- **Terminal opens then closes instantly** — open Terminal.app → Preferences → Profiles → Shell → "When the shell exits" → **Don't close the window**. Or run `./launch-archilume.sh` from an existing terminal.
- **Docker Desktop alternatives**: launcher also works with OrbStack or Colima. Start them manually before double-clicking. On Colima, first run `colima start` once; the launcher's `open -a Docker` will no-op and `docker info` will succeed.

### Linux

- **"permission denied" when running `./launch-archilume.sh`** — `chmod +x launch-archilume.sh` once, then retry. Some archive tools drop the execute bit on unzip.
- **"Docker Engine is not running"** — start it with your distribution's service manager: `sudo systemctl start docker`, or `colima start`, or open Rancher Desktop / Docker Desktop for Linux.
- **Rootless Docker** — the launcher respects `DOCKER_HOST`; set it in the shell before running `./launch-archilume.sh`.
- **"xdg-open: not found"** — the launcher still brings the stack up; open <http://localhost:3000> manually or `sudo apt install xdg-utils`.
