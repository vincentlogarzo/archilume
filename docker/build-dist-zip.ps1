#Requires -Version 5.1
<#
.SYNOPSIS
  Builds dist\archilume.zip for team distribution.

.DESCRIPTION
  Stages:
    - docker\launch-archilume.cmd    (Windows double-click entry point)
    - docker\_launch-archilume.ps1   (PowerShell implementation, hidden via `_` prefix)
    - docker\launch-archilume.sh     (Linux entry point)
    - docker\launch-archilume.command (macOS Finder double-click entry point)
    - docker\docker-compose-archilume.yml
    - docker\.env                    (ARCHILUME_VERSION pin for image tags)
    - docker\README.md
    - docker\demos\demo-sunlight\  -> projects\demo-sunlight\
    - docker\demos\demo-daylight\  -> projects\demo-daylight\
  into a temp folder, then Compress-Archive into docker\dist\archilume.zip,
  then patches the zip's central directory so that launch-archilume.sh and
  launch-archilume.command carry Unix file mode 0755 (rwxr-xr-x).

  Compress-Archive on Windows writes VersionMadeBy=DOS and zero Unix mode bits.
  macOS unzip / ditto then extract shell scripts as 0644 (no exec bit), causing
  Finder to refuse to run .command on double-click. The patch below rewrites two
  fields per entry in the central directory — VersionMadeBy and ExternalAttributes
  — to carry the Unix exec bit. Compressed data is untouched.

  Demo content is curated in-tree under docker\demos\ so the shipped payload is
  reviewable in git and stays small. To update a demo, edit the files under
  docker\demos\ directly.
#>

[CmdletBinding()]
param(
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# --------------------------------------------------------------------------- #
# Zip central-directory patcher                                                #
# --------------------------------------------------------------------------- #
#
# Patches a zip file so nominated entries are stamped with Unix file mode 0755.
# Works by locating the End of Central Directory Record (EOCD), walking every
# Central Directory File Header (CDFH), and rewriting two fields in-place for
# each matching entry:
#
#   Offset  Size  Field                   Before (DOS)       After (Unix)
#   ------  ----  -----                   ------------       ------------
#   +4      2     VersionMadeBy           0x0014 (DOS 2.0)   0x0314 (Unix 2.0)
#   +38     4     ExternalAttributes      0x00000020 (arch)  0x81ED0000 (0755)
#
# VersionMadeBy upper byte = 0x03 signals Unix host; macOS unzip / ditto then
# honour the Unix mode stored in the high 16 bits of ExternalAttributes.
# 0x81ED = S_IFREG (0x8000) | 0755 (0x01ED).  Compressed data is not touched.
#
function Set-ZipEntryUnixExec {
    param(
        [Parameter(Mandatory)][string]   $ZipPath,
        [Parameter(Mandatory)][string[]] $EntryNames  # forward-slash paths as stored in zip
    )

    # Constants
    $SIG_CDFH = [uint32]0x02014b50
    # VersionMadeBy: upper byte 0x03 = Unix, lower byte 0x14 = PKZIP 2.0
    $VERMADE_UNIX = [byte[]]@(0x14, 0x03)
    # ExternalAttributes: S_IFREG | 0755 in high 16 bits.
    # 0x81ED0000 little-endian = bytes [0x00, 0x00, 0xED, 0x81].
    # Written as a literal byte array to avoid PS 5.1 signed-Int32 overflow on
    # the hex literal (0x81ED0000 > Int32.MaxValue, so PS 5.1 makes it negative).
    $EXT_ATTR_EXEC = [byte[]]@(0x00, 0x00, 0xED, 0x81)

    function Read-Exact([System.IO.Stream]$s, [int]$count) {
        $buf  = [byte[]]::new($count)
        $pos  = 0
        while ($pos -lt $count) {
            $n = $s.Read($buf, $pos, $count - $pos)
            if ($n -eq 0) { throw "Unexpected EOF reading $count bytes." }
            $pos += $n
        }
        return $buf
    }

    $stream = [System.IO.File]::Open(
        $ZipPath,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::ReadWrite
    )
    try {
        # ------------------------------------------------------------------- #
        # 1. Locate EOCD: scan backward through the last 65 557 bytes         #
        #    (22-byte fixed EOCD + max 65 535-byte comment).                  #
        # ------------------------------------------------------------------- #
        $tailLen = [long][Math]::Min(65557, $stream.Length)
        [void]$stream.Seek(-$tailLen, [System.IO.SeekOrigin]::End)
        $tail = Read-Exact $stream $tailLen

        $eocdPos = -1L
        for ($i = $tailLen - 22; $i -ge 0; $i--) {
            if ($tail[$i]   -eq 0x50 -and $tail[$i+1] -eq 0x4b -and
                $tail[$i+2] -eq 0x05 -and $tail[$i+3] -eq 0x06) {
                $eocdPos = $stream.Length - $tailLen + $i
                break
            }
        }
        if ($eocdPos -lt 0) { throw "EOCD signature not found in: $ZipPath" }

        # ------------------------------------------------------------------- #
        # 2. Read CD size + offset from EOCD (bytes 12-19).                   #
        # ------------------------------------------------------------------- #
        [void]$stream.Seek($eocdPos + 12, [System.IO.SeekOrigin]::Begin)
        $eocdFields = Read-Exact $stream 8
        $cdSize   = [BitConverter]::ToUInt32($eocdFields, 0)
        $cdOffset = [BitConverter]::ToUInt32($eocdFields, 4)

        # ------------------------------------------------------------------- #
        # 3. Walk Central Directory and patch matching entries.                #
        # ------------------------------------------------------------------- #
        $wanted  = [System.Collections.Generic.HashSet[string]]::new($EntryNames)
        $patched = [System.Collections.Generic.HashSet[string]]::new()
        $cursor  = [long]$cdOffset

        while ($cursor -lt ($cdOffset + $cdSize)) {
            [void]$stream.Seek($cursor, [System.IO.SeekOrigin]::Begin)
            $hdr = Read-Exact $stream 46

            $sig = [BitConverter]::ToUInt32($hdr, 0)
            if ($sig -ne $SIG_CDFH) {
                throw "CDFH signature mismatch at offset $cursor (got 0x{0:X8})." -f $sig
            }

            $nameLen  = [BitConverter]::ToUInt16($hdr, 28)
            $extraLen = [BitConverter]::ToUInt16($hdr, 30)
            $cmntLen  = [BitConverter]::ToUInt16($hdr, 32)

            $nameBytes = Read-Exact $stream $nameLen
            $name = [System.Text.Encoding]::UTF8.GetString($nameBytes)

            if ($wanted.Contains($name)) {
                # Patch VersionMadeBy at cursor+4
                [void]$stream.Seek($cursor + 4, [System.IO.SeekOrigin]::Begin)
                $stream.Write($VERMADE_UNIX, 0, 2)
                # Patch ExternalAttributes at cursor+38
                [void]$stream.Seek($cursor + 38, [System.IO.SeekOrigin]::Begin)
                $stream.Write($EXT_ATTR_EXEC, 0, 4)
                [void]$patched.Add($name)
            }

            $cursor += 46 + $nameLen + $extraLen + $cmntLen
        }

        foreach ($n in $EntryNames) {
            if (-not $patched.Contains($n)) {
                Write-Warning "Entry not found in zip (exec bit not set): $n"
            }
        }
    } finally {
        $stream.Dispose()
    }
}

$DistDir = Join-Path $PSScriptRoot 'dist'
if (-not $OutputPath) { $OutputPath = Join-Path $DistDir 'archilume.zip' }

$LauncherCmd     = Join-Path $PSScriptRoot 'launch-archilume.cmd'
$LauncherPs1     = Join-Path $PSScriptRoot '_launch-archilume.ps1'
$LauncherSh      = Join-Path $PSScriptRoot 'launch-archilume.sh'
$LauncherCommand = Join-Path $PSScriptRoot 'launch-archilume.command'
$ReadmeMd        = Join-Path $PSScriptRoot 'README.md'
$ComposeYml      = Join-Path $PSScriptRoot 'docker-compose-archilume.yml'
$EnvFile         = Join-Path $PSScriptRoot '.env'

$DemosRoot   = Join-Path $PSScriptRoot 'demos'
$SunlightSrc = Join-Path $DemosRoot    'demo-sunlight'
$DaylightSrc = Join-Path $DemosRoot    'demo-daylight'

$required = @(
    $LauncherCmd, $LauncherPs1, $LauncherSh, $LauncherCommand,
    $ReadmeMd, $ComposeYml, $EnvFile,
    $SunlightSrc, $DaylightSrc
)
foreach ($path in $required) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing expected file or folder: $path"
    }
}

# Staging area inside system temp so the working copy never lands in the repo.
$Staging = Join-Path ([System.IO.Path]::GetTempPath()) ("archilume-zip-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Staging | Out-Null

try {
    Write-Host "Staging at $Staging" -ForegroundColor Cyan

    Copy-Item -LiteralPath $LauncherCmd     -Destination $Staging
    Copy-Item -LiteralPath $LauncherPs1     -Destination $Staging
    Copy-Item -LiteralPath $LauncherSh      -Destination $Staging
    Copy-Item -LiteralPath $LauncherCommand -Destination $Staging
    Copy-Item -LiteralPath $ReadmeMd        -Destination $Staging
    Copy-Item -LiteralPath $ComposeYml      -Destination $Staging
    Copy-Item -LiteralPath $EnvFile         -Destination $Staging

    $stagedProjects = Join-Path $Staging 'projects'
    New-Item -ItemType Directory -Path $stagedProjects | Out-Null

    Write-Host "  + demo-sunlight  (from docker\demos\demo-sunlight)" -ForegroundColor Gray
    Copy-Item -LiteralPath $SunlightSrc -Destination (Join-Path $stagedProjects 'demo-sunlight') -Recurse

    Write-Host "  + demo-daylight  (from docker\demos\demo-daylight)" -ForegroundColor Gray
    Copy-Item -LiteralPath $DaylightSrc -Destination (Join-Path $stagedProjects 'demo-daylight') -Recurse

    # Prepare output path.
    $outDir = Split-Path -Parent $OutputPath
    if (-not (Test-Path -LiteralPath $outDir)) {
        New-Item -ItemType Directory -Path $outDir -Force | Out-Null
    }
    if (Test-Path -LiteralPath $OutputPath) {
        Remove-Item -LiteralPath $OutputPath -Force
    }

    Write-Host "Compressing -> $OutputPath" -ForegroundColor Cyan
    Compress-Archive -Path (Join-Path $Staging '*') -DestinationPath $OutputPath -CompressionLevel Optimal

    Write-Host "Patching Unix exec bits (launch-archilume.sh, launch-archilume.command)..." -ForegroundColor Cyan
    Set-ZipEntryUnixExec -ZipPath $OutputPath -EntryNames @(
        'launch-archilume.sh',
        'launch-archilume.command'
    )

    $size = (Get-Item -LiteralPath $OutputPath).Length
    $sizeMb = [Math]::Round($size / 1MB, 2)
    Write-Host ""
    Write-Host "Built archilume.zip ($sizeMb MB)" -ForegroundColor Green
    Write-Host "  Path: $OutputPath"
} finally {
    if (Test-Path -LiteralPath $Staging) {
        Remove-Item -LiteralPath $Staging -Recurse -Force -ErrorAction SilentlyContinue
    }
}
