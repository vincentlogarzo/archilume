# Archilume — Docker distribution

This directory packages Archilume for end users via Docker Compose. For local
development inside VS Code, see [`../.devcontainer/README.md`](../.devcontainer/README.md) —
the dev container reuses `base-slim` and `radiance-extract` stages from
this Dockerfile via the `archilume-dev` target.

## Local launcher

## Requirements

- [Docker Desktop](https://www.docker.com/products/docker-desktop)
- Windows 10/11, PowerShell 5.1+

## Quick start

1. Unzip `archilume.zip` anywhere (any drive, any folder, spaces OK).
2. Double-click `launch-archilume.cmd`.

   The `.cmd` opens a PowerShell window with execution policy bypassed, runs
   the launcher, and keeps the window open on exit so you can read progress
   and any error messages. Do not use `launch-archilume.ps1` directly via
   "Run with PowerShell" — that closes the window instantly on any failure,
   hiding errors.

   Terminal alternative:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\launch-archilume.ps1
   ```

3. Wait until your browser opens on <http://localhost:3000>.

Your project data lives next to the script in the `projects\` folder. Anything saved from the app writes back to that folder on your host.

## Stopping Archilume

Shutdown from containers in your docker desktop application

## Troubleshooting

- **Window closes instantly with no message** — you ran `launch-archilume.ps1` directly (for example via "Run with PowerShell"). Use `launch-archilume.cmd` instead.
- **"Port 3000 is held by …"** — another app is using 3000. The script will prompt before stopping it.
- **"Docker Desktop was not found"** — enter the full path to `Docker Desktop.exe` when prompted. It's remembered for next time.
- **Get a newer image** — the launcher reuses images already on your machine. To refresh, run `docker compose -f docker-compose-archilume.yml -p archilume pull` from the unzipped folder.
