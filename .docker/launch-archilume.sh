#!/usr/bin/env bash
# Archilume launcher (macOS/Linux).
#
# Shipped inside archilume.zip alongside docker-compose-archilume.yml and
# projects/. Unzip anywhere, then run this script. Mirrors the Windows
# _launch-archilume.ps1 six-stage flow:
#   A. Environment check (compose file, projects/, docker CLI)
#   B. Docker Engine up (autostart Docker Desktop on macOS; hint on Linux)
#   C. Stale-instance cleanup + port-3000 conflict prompt
#   D. compose up -d (pull_policy=missing; no forced remote pull)
#   E. Wait for frontend /ping-frontend
#   F. Open browser
#
# All paths resolve relative to this script, so the zip can be unzipped anywhere.

set -euo pipefail

# --------------------------------------------------------------------------- #
# Constants                                                                    #
# --------------------------------------------------------------------------- #

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd -P )"
COMPOSE_PROJECT='archilume'
FRONTEND_PORT=3000
FRONTEND_URL="http://localhost:${FRONTEND_PORT}"
HEALTH_PATH='/ping-frontend'
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose-archilume.yml"
PROJECTS_DIR="${SCRIPT_DIR}/projects"
ENV_FILE="${SCRIPT_DIR}/.env"
DOCKER_READY_TIMEOUT=120
FRONTEND_READY_TIMEOUT=180

case "$(uname -s)" in
    Darwin*) OS='macos' ;;
    Linux*)  OS='linux' ;;
    *)       OS='other' ;;
esac

# --------------------------------------------------------------------------- #
# Output helpers                                                               #
# --------------------------------------------------------------------------- #

if [[ -t 1 ]]; then
    C_CYAN=$'\033[36m'; C_GRAY=$'\033[90m'; C_YELLOW=$'\033[33m'
    C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_RESET=$'\033[0m'
else
    C_CYAN=''; C_GRAY=''; C_YELLOW=''; C_RED=''; C_GREEN=''; C_RESET=''
fi

step() { printf '\n%s==> %s%s\n' "$C_CYAN" "$1" "$C_RESET"; }
info() { printf '    %s%s%s\n' "$C_GRAY" "$1" "$C_RESET"; }
warn() { printf '    %s%s%s\n' "$C_YELLOW" "$1" "$C_RESET"; }

fail() {
    printf '\n%sERROR: %s%s\n\n' "$C_RED" "$1" "$C_RESET" >&2
    # When launched by double-click on macOS (.command) the parent Terminal
    # stays open; on Linux the user runs from a terminal anyway. No pause needed.
    exit 1
}

# --------------------------------------------------------------------------- #
# Docker helpers                                                               #
# --------------------------------------------------------------------------- #

docker_engine_ready() {
    docker info --format '{{.ServerVersion}}' >/dev/null 2>&1
}

start_docker_macos() {
    if [[ -d '/Applications/Docker.app' ]]; then
        info 'Starting Docker Desktop (open -a Docker)...'
        open -a Docker || fail "Failed to start Docker Desktop."
    else
        fail "Docker Desktop not found at /Applications/Docker.app. Install from https://www.docker.com/products/docker-desktop/"
    fi
}

start_docker_linux() {
    # Docker Desktop for Linux ships as `docker-desktop`; many users instead run
    # the Docker Engine systemd service. We try Desktop first, else print a
    # clear hint rather than invoking sudo on the user's behalf.
    if command -v docker-desktop >/dev/null 2>&1; then
        info 'Starting Docker Desktop (systemctl --user start docker-desktop)...'
        systemctl --user start docker-desktop 2>/dev/null \
            || docker-desktop &  # best-effort fallback
    else
        fail "Docker Engine is not running. Start it with:
    sudo systemctl start docker
  or launch Docker Desktop / Rancher Desktop / OrbStack / Colima manually."
    fi
}

wait_docker_engine() {
    local deadline=$(( $(date +%s) + DOCKER_READY_TIMEOUT ))
    while (( $(date +%s) < deadline )); do
        if docker_engine_ready; then
            info 'Docker Engine is ready.'
            return 0
        fi
        sleep 2
        printf '.'
    done
    printf '\n'
    fail "Docker Engine did not become ready within ${DOCKER_READY_TIMEOUT} seconds. Start Docker manually and rerun."
}

# --------------------------------------------------------------------------- #
# Port helpers                                                                 #
# --------------------------------------------------------------------------- #

port_listener_pid() {
    # Prints the PID holding $1 as a TCP listener on localhost, or nothing.
    local port="$1"
    if command -v lsof >/dev/null 2>&1; then
        lsof -nP -iTCP:"${port}" -sTCP:LISTEN -t 2>/dev/null | head -n 1
    elif command -v ss >/dev/null 2>&1; then
        ss -ltnpH "sport = :${port}" 2>/dev/null \
            | sed -nE 's/.*pid=([0-9]+).*/\1/p' | head -n 1
    fi
}

resolve_port_conflict() {
    local port="$1"
    local pid
    pid="$(port_listener_pid "$port")"
    [[ -z "$pid" ]] && return 0

    local pname='<unknown>'
    if command -v ps >/dev/null 2>&1; then
        pname="$(ps -p "$pid" -o comm= 2>/dev/null | tr -d '\n' || true)"
        [[ -z "$pname" ]] && pname='<unknown>'
    fi
    warn "Port ${port} is held by '${pname}' (PID ${pid})."
    read -r -p "    Stop this process to launch Archilume? [y/N] " answer
    case "$answer" in
        y|Y|yes|YES|Yes)
            kill "$pid" 2>/dev/null || true
            sleep 1
            if [[ -n "$(port_listener_pid "$port")" ]]; then
                kill -9 "$pid" 2>/dev/null || true
                sleep 1
            fi
            [[ -n "$(port_listener_pid "$port")" ]] \
                && fail "Port ${port} is still held after attempting to stop PID ${pid}."
            info "Released port ${port}."
            ;;
        *)
            fail "Port ${port} is in use. Free it and rerun this script."
            ;;
    esac
}

# --------------------------------------------------------------------------- #
# Compose wrapper                                                              #
# --------------------------------------------------------------------------- #

compose() {
    local args=(compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT")
    if [[ -f "$ENV_FILE" ]]; then
        args=(compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT")
    fi
    docker "${args[@]}" "$@" \
        || fail "Command failed: docker ${args[*]} $*"
}

# --------------------------------------------------------------------------- #
# Readiness                                                                    #
# --------------------------------------------------------------------------- #

wait_frontend_ready() {
    local url="${FRONTEND_URL}${HEALTH_PATH}"
    info "Polling ${url} (up to ${FRONTEND_READY_TIMEOUT} s)..."
    local deadline=$(( $(date +%s) + FRONTEND_READY_TIMEOUT ))
    while (( $(date +%s) < deadline )); do
        if curl -sf -o /dev/null --max-time 2 "$url"; then
            printf '\n'
            info 'Frontend is healthy.'
            return 0
        fi
        sleep 2
        printf '.'
    done
    printf '\n'
    docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" ps || true
    fail "Frontend did not become healthy within ${FRONTEND_READY_TIMEOUT} seconds. See container status above."
}

# --------------------------------------------------------------------------- #
# Browser                                                                      #
# --------------------------------------------------------------------------- #

open_browser() {
    case "$OS" in
        macos) open "$FRONTEND_URL" >/dev/null 2>&1 || true ;;
        linux)
            if command -v xdg-open >/dev/null 2>&1; then
                xdg-open "$FRONTEND_URL" >/dev/null 2>&1 &
            else
                info "Open your browser at ${FRONTEND_URL}"
            fi
            ;;
        *) info "Open your browser at ${FRONTEND_URL}" ;;
    esac
}

# =========================================================================== #
# Stage A — Environment check                                                  #
# =========================================================================== #

step 'Archilume launcher'
info "Script location : ${SCRIPT_DIR}"
info "Compose file    : ${COMPOSE_FILE}"
info "Projects dir    : ${PROJECTS_DIR}"
info "Detected OS     : ${OS}"

[[ -f "$COMPOSE_FILE" ]] \
    || fail "docker-compose-archilume.yml not found next to this script. Re-extract archilume.zip and try again."
[[ -d "$PROJECTS_DIR" ]] \
    || fail "projects/ folder not found next to this script. Re-extract archilume.zip and try again."

command -v docker >/dev/null 2>&1 \
    || fail "'docker' CLI not on PATH. Install Docker Desktop (or Colima/OrbStack/Rancher Desktop) and rerun."
command -v curl >/dev/null 2>&1 \
    || fail "'curl' not on PATH. Install curl and rerun (apt/brew install curl)."

# =========================================================================== #
# Stage B — Docker Engine up                                                   #
# =========================================================================== #

step 'Checking Docker Engine'
if docker_engine_ready; then
    info 'Docker Engine is already running.'
else
    case "$OS" in
        macos) start_docker_macos ;;
        linux) start_docker_linux ;;
        *)     fail "Unsupported OS. Start Docker manually and rerun." ;;
    esac
    wait_docker_engine
fi

# =========================================================================== #
# Stage C — Stale-instance cleanup                                             #
# =========================================================================== #

step "Tearing down any previous '${COMPOSE_PROJECT}' stack"
compose down --remove-orphans

step "Checking port ${FRONTEND_PORT}"
resolve_port_conflict "$FRONTEND_PORT"

# =========================================================================== #
# Stage D — Start stack                                                        #
# =========================================================================== #
#
# Compose's default pull_policy is `missing` — it pulls from the registry only
# when an image isn't present locally. We deliberately do NOT `compose pull`
# here because that forces a remote fetch which fails offline. Users who want
# to refresh can run `docker compose pull` manually.

export ARCHILUME_PROJECTS_DIR="$PROJECTS_DIR"
info "ARCHILUME_PROJECTS_DIR = ${ARCHILUME_PROJECTS_DIR}"

step 'Starting stack'
compose up -d

# =========================================================================== #
# Stage E — Readiness wait                                                     #
# =========================================================================== #

step 'Waiting for frontend to become healthy'
wait_frontend_ready

# =========================================================================== #
# Stage F — Launch browser                                                     #
# =========================================================================== #

step "Opening ${FRONTEND_URL}"
open_browser

printf '\n%sArchilume is running.%s\n' "$C_GREEN" "$C_RESET"
printf '  URL  : %s\n' "$FRONTEND_URL"
printf '  Stop : re-run this script, or:\n'
printf '         docker compose -f "%s" -p %s down\n\n' "$COMPOSE_FILE" "$COMPOSE_PROJECT"
