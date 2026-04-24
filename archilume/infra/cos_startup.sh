#!/bin/bash
# GCP VM startup script for Container-Optimized OS.
# Runs on first boot (and every boot) via instance metadata.
# Idempotent — safe to re-execute.
#
# Steps:
#   1. Format local SSD if blank (ext4)
#   2. Persist mount via systemd .mount unit (COS fstab is not writable)
#   3. Relocate Docker data-root to LSSD via systemd drop-in
#   4. Pull and run archilume-engine container on port 8100
#   5. Touch readiness marker
set -euo pipefail

LSSD=/dev/nvme0n1
MNT=/mnt/disks/localssd
ENGINE_IMAGE=vlogarzo/archilume-engine:latest
ENGINE_PORT=8100
READY_MARKER=/var/run/archilume-ready

log() { echo "[archilume-startup] $*"; }

# ----- 1. Format LSSD if blank ------------------------------------------------
if ! blkid -s TYPE -o value "$LSSD" | grep -q ext4; then
  log "Formatting $LSSD as ext4..."
  mkfs.ext4 -m 0 -E lazy_itable_init=0,lazy_journal_init=0,discard "$LSSD"
else
  log "$LSSD already ext4 — skipping format"
fi
mkdir -p "$MNT"

# ----- 2. Persistent mount via systemd ----------------------------------------
UUID=$(blkid -s UUID -o value "$LSSD")
log "LSSD UUID: $UUID"

cat > /etc/systemd/system/mnt-disks-localssd.mount <<EOF
[Unit]
Description=Archilume local SSD
Before=docker.service

[Mount]
What=UUID=$UUID
Where=$MNT
Type=ext4
Options=discard,defaults,nofail

[Install]
WantedBy=local-fs.target
EOF

systemctl daemon-reload
systemctl enable --now mnt-disks-localssd.mount
mkdir -p "$MNT/projects" "$MNT/docker"
chmod -R a+rwx "$MNT"

# ----- 3. Relocate Docker data-root to LSSD -----------------------------------
# COS does not persist /etc/docker/daemon.json across reboots; use a
# systemd drop-in instead so the override survives stateful_partition resets.
mkdir -p /etc/systemd/system/docker.service.d
cat > /etc/systemd/system/docker.service.d/data-root.conf <<EOF
[Service]
ExecStart=
ExecStart=/usr/bin/dockerd --host=fd:// --data-root=$MNT/docker --containerd=/run/containerd/containerd.sock
EOF

systemctl daemon-reload
systemctl restart docker

# ----- 4. Pull + run engine ---------------------------------------------------
log "Pulling $ENGINE_IMAGE..."
docker pull "$ENGINE_IMAGE"

log "Starting archilume-engine container..."
docker rm -f archilume-engine 2>/dev/null || true
docker run -d --restart=unless-stopped --name archilume-engine \
  -p ${ENGINE_PORT}:${ENGINE_PORT} \
  -v "$MNT/projects:/app/projects" \
  -e ARCHILUME_DEPLOYMENT_MODE=hosted \
  -e ARCHILUME_HOST_PROJECTS_DIR=/app/projects \
  "$ENGINE_IMAGE"

# ----- 5. Readiness marker ----------------------------------------------------
touch "$READY_MARKER"
log "Setup complete. Engine listening on :${ENGINE_PORT}."
