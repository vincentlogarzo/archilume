"""gcp_vm_manager.py — minimal GCP VM lifecycle for Archilume.

Creates an LSSD VM running Container-Optimized OS, with the engine container
launched by `cos_startup.sh`. Four actions: setup, delete, tunnel, restart.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from archilume.config import GCLOUD_EXECUTABLE

SSH_KEY_PATH = Path.home() / ".ssh" / "google_cloud_vm_key"
SSH_CONFIG_PATH = Path.home() / ".ssh" / "config"
SSH_HOST_ALIAS = "gcp-vm"
VM_NAME_PREFIX = "archilume-vm"
ENGINE_IMAGE = "vlogarzo/archilume-engine:latest"
ENGINE_PORT = 8100
LSSD_MOUNT = "/mnt/disks/localssd"
REMOTE_PROJECTS = f"{LSSD_MOUNT}/projects"
STARTUP_SCRIPT_PATH = Path(__file__).parent / "cos_startup.sh"
LEGACY_CONFIG_PATH = Path.home() / ".archilume_gcp_config.json"

DEFAULT_ZONE = "australia-southeast1-a"
MACHINE_TYPES: tuple[str, ...] = (
    "c4d-standard-64-lssd",
    "c4d-standard-96-lssd",
    "c4d-standard-192-lssd",
    "c4-standard-288-lssd",
    "c4d-standard-384-lssd",
)
DEFAULT_MACHINE_TYPE = "c4d-standard-96-lssd"

# Engine image is x86_64-only; guardrail blocks arm64 prefixes (c4a/n4a/t2a).
_X86_LSSD_PREFIXES = ("c4d-", "c4-", "c3d-", "c3-", "h4d-", "z3-")
assert all(m.startswith(_X86_LSSD_PREFIXES) for m in MACHINE_TYPES), (
    f"MACHINE_TYPES contains a non-x86_64 LSSD prefix: {MACHINE_TYPES}"
)


def _resolve_gcloud() -> str:
    if Path(GCLOUD_EXECUTABLE).is_file():
        return str(GCLOUD_EXECUTABLE)
    found = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if found:
        return found
    raise RuntimeError(
        f"gcloud not found at {GCLOUD_EXECUTABLE} or on PATH. "
        "Install: https://cloud.google.com/sdk/docs/install"
    )


class GCPVMManager:
    def __init__(self, project_name=None, project=None, zone=DEFAULT_ZONE):
        self.archilume_project = project_name
        self._gcloud_bin = _resolve_gcloud()
        self.zone = zone
        if LEGACY_CONFIG_PATH.exists():
            print(f"Note: {LEGACY_CONFIG_PATH} is no longer used; pass --project or `gcloud config set project <id>`.")
        if project:
            self.project = project
        else:
            out, code = self._gcloud(["config", "get-value", "project"], capture=True)
            if code != 0 or not out or out == "(unset)":
                raise RuntimeError("No GCP project set. Pass --project or run `gcloud config set project <id>`.")
            self.project = out
        self._ensure_authenticated()

    # ----- gcloud / ssh wrappers -----

    def _gcloud(self, args, capture=False):
        cmd = [self._gcloud_bin, *args]
        if capture:
            r = subprocess.run(cmd, capture_output=True, text=True)
            return r.stdout.strip(), r.returncode
        r = subprocess.run(cmd)
        if r.returncode != 0:
            raise RuntimeError(f"gcloud {' '.join(args)} failed (exit {r.returncode})")
        return "", 0

    def _zp(self):
        return [f"--zone={self.zone}", f"--project={self.project}"]

    def _ensure_authenticated(self):
        out, _ = self._gcloud(["auth", "list", "--filter=status:ACTIVE", "--format=value(account)"], capture=True)
        if out:
            return
        if not sys.stdin.isatty():
            raise RuntimeError(
                "No active gcloud account and stdin is not a TTY. "
                "In a backend/container, activate a service account with "
                "`gcloud auth activate-service-account --key-file=$GOOGLE_APPLICATION_CREDENTIALS`."
            )
        print("No active gcloud account; running `gcloud auth login --no-launch-browser`...")
        self._gcloud(["auth", "login", "--no-launch-browser"])

    def _username(self):
        out, _ = self._gcloud(["config", "get-value", "account"], capture=True)
        return out.split("@")[0]

    def _ssh(self, vm_name, command, capture=False):
        return self._gcloud(["compute", "ssh", vm_name, *self._zp(), "--command", command], capture=capture)

    def _describe(self, vm_name, fmt):
        return self._gcloud(["compute", "instances", "describe", vm_name, *self._zp(), f"--format=get({fmt})"], capture=True)

    def _get_vm_ip(self, vm_name):
        out, _ = self._describe(vm_name, "networkInterfaces[0].accessConfigs[0].natIP")
        return out

    def _get_vm_status(self, vm_name):
        out, code = self._describe(vm_name, "status")
        return out if code == 0 else "UNKNOWN"

    def list_vms(self):
        out, code = self._gcloud(
            ["compute", "instances", "list", f"--project={self.project}",
             f"--filter=name~'^{VM_NAME_PREFIX}'",
             "--format=csv[no-heading](name,status,zone,networkInterfaces[0].accessConfigs[0].natIP)"],
            capture=True,
        )
        if code != 0 or not out:
            return []
        return [tuple((line.split(",") + [""])[:4]) for line in out.splitlines() if line]

    # ----- SSH key + config -----

    def _ensure_ssh_key(self):
        if SSH_KEY_PATH.exists():
            return
        SSH_KEY_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            subprocess.run(["ssh-keygen", "-t", "rsa", "-b", "4096", "-f", str(SSH_KEY_PATH), "-N", "", "-q"], check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"ssh-keygen failed: {e}. Try `chmod 700 ~/.ssh` and re-run.") from e

    def _update_ssh_config(self, ip, username):
        block = (
            f"Host {SSH_HOST_ALIAS}\n"
            f"    HostName {ip}\n"
            f"    User {username}\n"
            f"    IdentityFile {SSH_KEY_PATH}\n"
            f"    StrictHostKeyChecking accept-new\n"
            f"    ConnectTimeout 30\n"
            f"    ServerAliveInterval 60\n"
        )
        SSH_CONFIG_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        existing = SSH_CONFIG_PATH.read_text() if SSH_CONFIG_PATH.exists() else ""
        out_lines, skip, found = [], False, False
        for line in existing.splitlines(keepends=True):
            if line.strip() == f"Host {SSH_HOST_ALIAS}":
                skip, found = True, True
                out_lines.append(block)
                continue
            if skip and line.startswith("Host "):
                skip = False
            if not skip:
                out_lines.append(line)
        if not found:
            if out_lines and not out_lines[-1].endswith("\n"):
                out_lines.append("\n")
            out_lines.append("\n" + block)
        SSH_CONFIG_PATH.write_text("".join(out_lines))
        print(f"  SSH config: Host {SSH_HOST_ALIAS} → {ip}")

    def _wait(self, predicate, label, attempts, interval):
        for _ in range(attempts):
            if predicate():
                return
            time.sleep(interval)
        raise RuntimeError(f"{label} not ready after {attempts*interval}s")

    # ----- actions -----

    def setup(self, machine_type=None, vm_name=None):
        machine_type = machine_type or DEFAULT_MACHINE_TYPE
        if machine_type not in MACHINE_TYPES:
            raise ValueError(f"Unknown machine type {machine_type!r}. Choices: {', '.join(MACHINE_TYPES)}")
        if not STARTUP_SCRIPT_PATH.exists():
            raise RuntimeError(f"Startup script missing: {STARTUP_SCRIPT_PATH}")
        vm_name = vm_name or f"{VM_NAME_PREFIX}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        print(f"--- Creating VM {vm_name} ({machine_type}) ---")
        self._ensure_ssh_key()
        username = self._username()
        pubkey = SSH_KEY_PATH.with_suffix(".pub").read_text().strip()
        self._gcloud([
            "compute", "instances", "create", vm_name, *self._zp(),
            f"--machine-type={machine_type}",
            "--image-family=cos-stable", "--image-project=cos-cloud",
            "--boot-disk-size=20GB", "--boot-disk-type=hyperdisk-balanced",
            "--labels=archilume-managed=true",
            f"--metadata=ssh-keys={username}:{pubkey}",
            f"--metadata-from-file=startup-script={STARTUP_SCRIPT_PATH}",
        ])
        self._wait(lambda: self._get_vm_status(vm_name) == "RUNNING", f"VM {vm_name}", 40, 5)
        self._wait(lambda: self._ssh(vm_name, "echo ok", capture=True)[1] == 0, f"SSH on {vm_name}", 30, 10)
        ip = self._get_vm_ip(vm_name)
        self._update_ssh_config(ip, username)
        print(f"\n=== VM ready: {vm_name} | IP: {ip} ===")
        print(f"  ssh {SSH_HOST_ALIAS}")
        print(f"  Tunnel: ssh -N -L {ENGINE_PORT}:localhost:{ENGINE_PORT} {SSH_HOST_ALIAS}")
        print("  Engine container is starting (first pull ~3-5 min); poll /health to confirm.")
        return vm_name

    def delete(self, vm_name):
        if not vm_name:
            raise ValueError("vm_name is required")
        self._gcloud(["compute", "instances", "delete", vm_name, *self._zp(), "--quiet"])
        print(f"  Deleted {vm_name}")

    def tunnel(self, vm_name=None):
        if vm_name is None:
            running = [(n, ip) for n, s, _, ip in self.list_vms() if s == "RUNNING"]
            if not running:
                raise RuntimeError("No RUNNING archilume VMs to tunnel into.")
            vm_name, ip = running[0]
        else:
            ip = self._get_vm_ip(vm_name)
        self._update_ssh_config(ip, self._username())
        print(f"  Tunneling {ENGINE_PORT}:localhost:{ENGINE_PORT} via {SSH_HOST_ALIAS} (Ctrl-C to stop)")
        try:
            subprocess.run(["ssh", "-N", "-L", f"{ENGINE_PORT}:localhost:{ENGINE_PORT}", SSH_HOST_ALIAS], check=False)
        except KeyboardInterrupt:
            print("\n  Tunnel closed.")

    def restart(self, vm_name):
        if not vm_name:
            raise ValueError("vm_name is required")
        self._ssh(vm_name, f"docker pull {ENGINE_IMAGE}")
        self._ssh(vm_name,
            f"docker rm -f archilume-engine 2>/dev/null; "
            f"docker run -d --restart=unless-stopped --name archilume-engine "
            f"-p {ENGINE_PORT}:{ENGINE_PORT} -v {REMOTE_PROJECTS}:/app/projects "
            f"-e ARCHILUME_DEPLOYMENT_MODE=hosted -e ARCHILUME_HOST_PROJECTS_DIR=/app/projects "
            f"{ENGINE_IMAGE}",
        )
        print(f"  Engine restarted on {vm_name}")

    def run(self, action="setup", **kwargs):
        actions = {"setup": self.setup, "delete": self.delete, "tunnel": self.tunnel, "restart": self.restart}
        if action not in actions:
            raise ValueError(f"Unknown action {action!r}. Choices: {', '.join(actions)}")
        return actions[action](**kwargs)
