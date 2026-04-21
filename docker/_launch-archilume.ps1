#Requires -Version 5.1
<#
.SYNOPSIS
  Launches the Archilume local stack (Docker Compose) and opens the frontend in the browser.

.DESCRIPTION
  This script is shipped inside archilume.zip alongside docker-compose-archilume.yml and a
  projects/ folder. Unzip anywhere, then run this script. It will:
    1. Locate Docker Desktop (prompting once if not found; the hint is persisted).
    2. Start Docker Desktop if it isn't running.
    3. Tear down any previous 'archilume' compose stack for a fresh launch.
    4. Resolve port 3000 conflicts (prompting before killing foreign processes).
    5. Bring the stack up (compose pulls any missing images automatically).
    6. Wait for the frontend to become healthy, then open the browser.

  All paths are resolved relative to this script, so the zip can be unzipped anywhere.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ComposeProject = 'archilume'
$FrontendPort   = 3000
$FrontendUrl    = "http://localhost:$FrontendPort"
$HealthPath     = '/ping-frontend'
$DockerHintFile = Join-Path $PSScriptRoot '.docker-path.txt'
$ComposeFile    = Join-Path $PSScriptRoot 'docker-compose-archilume.yml'
$EnvFile        = Join-Path $PSScriptRoot '.env'
$ProjectsDir    = Join-Path $PSScriptRoot 'projects'

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Info([string]$Message) {
    Write-Host "    $Message" -ForegroundColor Gray
}

function Write-Warn2([string]$Message) {
    Write-Host "    $Message" -ForegroundColor Yellow
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to close"
    exit 1
}

function Test-DockerEngine {
    # Returns $true if the Docker Engine is reachable via CLI.
    $null = & docker info --format '{{.ServerVersion}}' 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Find-DockerDesktopExe {
    $candidates = @(
        (Join-Path $env:ProgramFiles         'Docker\Docker\Docker Desktop.exe'),
        (Join-Path ${env:ProgramFiles(x86)}  'Docker\Docker\Docker Desktop.exe')
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    # Registry lookup (Docker Desktop writes AppPath here on install).
    try {
        $reg = Get-ItemProperty -Path 'HKLM:\SOFTWARE\Docker Inc.\Docker\Desktop' -ErrorAction Stop
        if ($reg -and $reg.AppPath) {
            $exe = Join-Path $reg.AppPath 'Docker Desktop.exe'
            if (Test-Path -LiteralPath $exe) { return $exe }
        }
    } catch { }
    # Persisted user hint from a prior run.
    if (Test-Path -LiteralPath $DockerHintFile) {
        $hint = (Get-Content -LiteralPath $DockerHintFile -Raw).Trim()
        if ($hint -and (Test-Path -LiteralPath $hint)) { return $hint }
    }
    return $null
}

function Prompt-ForDockerExe {
    Write-Host ""
    Write-Warn2 "Docker Desktop was not found in the usual locations."
    Write-Warn2 "Expected: ${env:ProgramFiles}\Docker\Docker\Docker Desktop.exe"
    Write-Host ""
    $entered = Read-Host "Enter the full path to 'Docker Desktop.exe' (or leave blank to cancel)"
    if ([string]::IsNullOrWhiteSpace($entered)) {
        Fail "Docker Desktop location not provided. Install Docker Desktop or rerun and supply the path."
    }
    $entered = $entered.Trim('"').Trim()
    if (-not (Test-Path -LiteralPath $entered)) {
        Fail "Path does not exist: $entered"
    }
    Set-Content -LiteralPath $DockerHintFile -Value $entered -Encoding UTF8
    Write-Info "Saved Docker Desktop location hint to $DockerHintFile"
    return $entered
}

function Start-DockerDesktop([string]$Exe) {
    Write-Info "Starting Docker Desktop: $Exe"
    Start-Process -FilePath $Exe | Out-Null
    $deadline = (Get-Date).AddSeconds(120)
    while ((Get-Date) -lt $deadline) {
        if (Test-DockerEngine) {
            Write-Info "Docker Engine is ready."
            return
        }
        Start-Sleep -Seconds 2
        Write-Host "." -NoNewline
    }
    Write-Host ""
    Fail "Docker Desktop did not become ready within 120 seconds. Open it manually and rerun this script."
}

function Get-ListenerPid([int]$Port) {
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
                Select-Object -First 1
        return [int]$conn.OwningProcess
    } catch {
        return $null
    }
}

function Resolve-PortConflict([int]$Port) {
    $listenerPid = Get-ListenerPid -Port $Port
    if (-not $listenerPid) { return }
    # Docker Desktop (and its vpnkit/backend helpers) proxy published ports. Our compose
    # down should already have released port 3000 by this point; if something is still
    # listening, it's foreign.
    $proc = $null
    try { $proc = Get-Process -Id $listenerPid -ErrorAction Stop } catch { }
    $procName = if ($proc) { $proc.ProcessName } else { '<unknown>' }
    Write-Warn2 "Port $Port is held by '$procName' (PID $listenerPid)."
    $answer = Read-Host "Stop this process to launch Archilume? [y/N]"
    if ($answer -match '^(?i:y(es)?)$') {
        try {
            Stop-Process -Id $listenerPid -Force -ErrorAction Stop
            Start-Sleep -Seconds 1
            if (Get-ListenerPid -Port $Port) {
                Fail "Port $Port is still held after attempting to stop PID $listenerPid."
            }
            Write-Info "Released port $Port."
        } catch {
            Fail "Failed to stop PID $listenerPid : $($_.Exception.Message)"
        }
    } else {
        Fail "Port $Port is in use. Free it and rerun this script."
    }
}

function Invoke-Compose([string[]]$Arguments) {
    # Runs `docker compose [--env-file .env] -f <file> -p <project> <args...>`.
    # Fails fast on non-zero exit.
    #
    # --env-file is passed explicitly when .env is present so that compose
    # variable substitution (e.g. ARCHILUME_VERSION in image tags) resolves
    # regardless of the caller's current working directory — compose's default
    # .env lookup is cwd-relative, not compose-file-relative.
    $prefix = @('compose')
    if (Test-Path -LiteralPath $EnvFile) {
        $prefix += @('--env-file', $EnvFile)
    }
    $all = $prefix + @('-f', $ComposeFile, '-p', $ComposeProject) + $Arguments
    & docker @all
    if ($LASTEXITCODE -ne 0) {
        Fail "Command failed: docker $($all -join ' ')"
    }
}

function Wait-FrontendReady {
    $url = "$FrontendUrl$HealthPath"
    Write-Info "Polling $url (up to 180 s)..."
    $deadline = (Get-Date).AddSeconds(180)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($r.StatusCode -eq 200) {
                Write-Host ""
                Write-Info "Frontend is healthy."
                return
            }
        } catch { }
        Start-Sleep -Seconds 2
        Write-Host "." -NoNewline
    }
    Write-Host ""
    # Surface container status to aid debugging.
    Invoke-Compose @('ps')
    Fail "Frontend did not become healthy within 180 seconds. See container status above."
}

# --------------------------------------------------------------------------- #
# Stage A — Environment check                                                  #
# --------------------------------------------------------------------------- #

Write-Step "Archilume launcher"
Write-Info "Script location : $PSScriptRoot"
Write-Info "Compose file    : $ComposeFile"
Write-Info "Projects dir    : $ProjectsDir"

if (-not (Test-Path -LiteralPath $ComposeFile)) {
    Fail "docker-compose-archilume.yml not found next to this script. Re-extract archilume.zip and try again."
}
if (-not (Test-Path -LiteralPath $ProjectsDir)) {
    Fail "projects/ folder not found next to this script. Re-extract archilume.zip and try again."
}

$dockerCli = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCli) {
    Fail "'docker' CLI not on PATH. Install Docker Desktop (which bundles the CLI) and rerun."
}

# --------------------------------------------------------------------------- #
# Stage B — Docker Desktop up                                                  #
# --------------------------------------------------------------------------- #

Write-Step "Checking Docker Engine"
if (Test-DockerEngine) {
    Write-Info "Docker Engine is already running."
} else {
    $exe = Find-DockerDesktopExe
    if (-not $exe) { $exe = Prompt-ForDockerExe }
    Start-DockerDesktop -Exe $exe
}

# --------------------------------------------------------------------------- #
# Stage C — Stale-instance cleanup                                             #
# --------------------------------------------------------------------------- #

Write-Step "Tearing down any previous '$ComposeProject' stack"
Invoke-Compose @('down', '--remove-orphans')

Write-Step "Checking port $FrontendPort"
Resolve-PortConflict -Port $FrontendPort

# --------------------------------------------------------------------------- #
# Stage D — Start stack                                                        #
# --------------------------------------------------------------------------- #
#
# Compose's default pull_policy is `missing` — it pulls from the registry only
# when an image isn't present locally, and reuses the cached image otherwise.
# We deliberately do NOT run `docker compose pull` here because (a) it forces
# a remote fetch that fails in offline / not-yet-published scenarios, and
# (b) users who want to refresh can run `docker compose pull` manually.

$env:ARCHILUME_PROJECTS_DIR = $ProjectsDir
Write-Info "ARCHILUME_PROJECTS_DIR = $ProjectsDir"

Write-Step "Starting stack"
Invoke-Compose @('up', '-d')

# --------------------------------------------------------------------------- #
# Stage E — Readiness wait                                                     #
# --------------------------------------------------------------------------- #

Write-Step "Waiting for frontend to become healthy"
Wait-FrontendReady

# --------------------------------------------------------------------------- #
# Stage F — Launch browser                                                     #
# --------------------------------------------------------------------------- #

Write-Step "Opening $FrontendUrl"
Start-Process $FrontendUrl | Out-Null

Write-Host ""
Write-Host "Archilume is running." -ForegroundColor Green
Write-Host "  URL  : $FrontendUrl"
Write-Host "  Stop : re-run this script, or:"
Write-Host "         docker compose -f `"$ComposeFile`" -p $ComposeProject down"
Write-Host ""
