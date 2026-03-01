"""
gcp_vm_manager.py — GCP VM lifecycle manager for Archilume.

Handles creation, setup, connection, and deletion of GCP VMs.
Config is saved to ~/.archilume_gcp_config.json.
SSH key is stored at ~/.ssh/google_cloud_vm_key.
"""

import json
import subprocess
import time
import urllib.request
from datetime import datetime
from pathlib import Path


CONFIG_PATH = Path.home() / ".archilume_gcp_config.json"
SSH_KEY_PATH = Path.home() / ".ssh" / "google_cloud_vm_key"
SSH_CONFIG_PATH = Path.home() / ".ssh" / "config"
SSH_HOST_ALIAS = "gcp-vm"
REMOTE_WORKSPACE = "/mnt/disks/localssd/workspace/archilume"
VM_NAME_PREFIX = "archilume-vm"
MIN_VCPUS = 64
# GCP Compute Engine billing service ID (stable)
_GCP_BILLING_SERVICE = "6F81-5844-456A"


class GCPVMManager:
    def __init__(self):
        if subprocess.run(["which", "gcloud"], capture_output=True).returncode != 0:
            raise RuntimeError(
                "gcloud CLI not found.\n"
                "Install it from https://cloud.google.com/sdk/docs/install, then run:\n"
                "  gcloud auth login\n"
                "  gcloud config set project YOUR_PROJECT_ID"
            )
        self._ensure_authenticated()
        self.cfg = self._load_config()

    def _ensure_authenticated(self):
        """Check for an active gcloud account; run 'gcloud auth login' if missing."""
        out, _ = self._gcloud_capture_static(["auth", "list", "--filter=status:ACTIVE", "--format=value(account)"])
        if not out:
            print("  No active gcloud account found. Launching authentication...")
            is_wsl = Path("/proc/version").exists() and "microsoft" in Path("/proc/version").read_text().lower()
            if is_wsl:
                print("  WSL detected — a URL will be printed below. Open it in your browser to log in.")
                login_cmd = ["gcloud", "auth", "login", "--no-launch-browser"]
            else:
                login_cmd = ["gcloud", "auth", "login"]
            result = subprocess.run(login_cmd)
            if result.returncode != 0:
                raise RuntimeError("gcloud authentication failed. Run 'gcloud auth login' manually.")
            out, _ = self._gcloud_capture_static(["auth", "list", "--filter=status:ACTIVE", "--format=value(account)"])
            if not out:
                raise RuntimeError("No active gcloud account after login. Run 'gcloud auth login' manually.")
        print(f"  Authenticated as: {out.splitlines()[0]}")

    @staticmethod
    def _gcloud_capture_static(args: list) -> tuple[str, int]:
        result = subprocess.run(["gcloud"] + args, capture_output=True, text=True)
        return result.stdout.strip(), result.returncode

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _load_config(self) -> dict:
        if CONFIG_PATH.exists():
            return json.loads(CONFIG_PATH.read_text())
        return {}

    def _save_config(self):
        CONFIG_PATH.write_text(json.dumps(self.cfg, indent=2))

    def prompt_config(self):
        """Prompt for missing project, then auto-select best zone for the machine type."""
        if "project" not in self.cfg:
            self.cfg["project"] = input("  GCP project ID (e.g. my-project-123): ").strip()
        if "zone" not in self.cfg:
            self.cfg["zone"] = self._pick_best_zone()
        self._save_config()

    def _pick_best_zone(self) -> str:
        """Query available zones for the c4d machine family.

        Prefer US zones (cheapest). If no US zone is available, fall back to
        the lowest-latency zone among remaining options.
        """
        reference_type = MACHINE_TYPES[0][0]
        print(f"  Finding best zone for {reference_type}...")
        out, code = self._gcloud_capture([
            "compute", "machine-types", "list",
            f"--filter=name={reference_type}",
            "--format=value(zone)",
            f"--project={self.project}",
        ])
        if code != 0 or not out:
            print("  Could not query zones, defaulting to us-central1-a")
            return "us-central1-a"

        zones = out.splitlines()
        us_zones = [z for z in zones if z.startswith("us-")]
        if us_zones:
            chosen = sorted(us_zones)[0]
            print(f"  Selected US zone: {chosen}")
            return chosen

        # No US zone — pick lowest-latency from remaining zones
        print(f"  No US zones available. Checking latency across {len(zones)} zones...")
        best_zone, best_ms = None, float("inf")
        for zone in zones:
            region = "-".join(zone.split("-")[:-1])
            host = f"{region}.gcp.pingdom.com"
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "2", host],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                for part in result.stdout.split():
                    if part.startswith("time="):
                        try:
                            ms = float(part.split("=")[1].replace("ms", ""))
                            if ms < best_ms:
                                best_ms, best_zone = ms, zone
                        except ValueError:
                            pass
                        break

        if best_zone:
            print(f"  Selected zone: {best_zone} ({best_ms:.0f} ms)")
            return best_zone

        chosen = zones[0]
        print(f"  Ping unavailable, selecting first available zone: {chosen}")
        return chosen

    @property
    def project(self) -> str:
        return self.cfg["project"]

    @property
    def zone(self) -> str:
        return self.cfg["zone"]

    # ------------------------------------------------------------------
    # gcloud helpers
    # ------------------------------------------------------------------

    def _gcloud(self, args: list):
        """Run a gcloud command, streaming output live. Raises on failure."""
        result = subprocess.run(["gcloud"] + args)
        if result.returncode != 0:
            raise RuntimeError(
                f"gcloud command failed (exit {result.returncode}):\n  gcloud {' '.join(args)}"
            )

    def _gcloud_capture(self, args: list) -> tuple[str, int]:
        """Run a gcloud command and capture stdout. Returns (stdout, exit_code)."""
        return self._gcloud_capture_static(args)

    def _gcloud_account(self) -> str:
        out, _ = self._gcloud_capture(["config", "get-value", "account"])
        return out

    def _gcloud_username(self) -> str:
        return self._gcloud_account().split("@")[0]

    def _get_vm_ip(self, vm_name: str) -> str:
        out, _ = self._gcloud_capture([
            "compute", "instances", "describe", vm_name,
            f"--zone={self.zone}", f"--project={self.project}",
            "--format=get(networkInterfaces[0].accessConfigs[0].natIP)",
        ])
        return out

    def _get_vm_status(self, vm_name: str) -> str:
        out, code = self._gcloud_capture([
            "compute", "instances", "describe", vm_name,
            f"--zone={self.zone}", f"--project={self.project}",
            "--format=get(status)",
        ])
        return out if code == 0 else "UNKNOWN"

    def list_vms(self) -> list[tuple[str, str, str, str]]:
        """Return [(name, status, zone, ip)] for all archilume-vm* instances."""
        out, code = self._gcloud_capture([
            "compute", "instances", "list",
            f"--project={self.project}",
            f"--filter=name~'^{VM_NAME_PREFIX}'",
            "--format=csv[no-heading](name,status,zone,networkInterfaces[0].accessConfigs[0].natIP)",
        ])
        if code != 0 or not out:
            return []
        rows = []
        for line in out.splitlines():
            parts = line.split(",")
            if len(parts) >= 4:
                rows.append((parts[0], parts[1], parts[2], parts[3]))
            elif len(parts) == 3:
                rows.append((parts[0], parts[1], parts[2], ""))
        return rows

    # ------------------------------------------------------------------
    # SSH helpers
    # ------------------------------------------------------------------

    def _ensure_ssh_key(self):
        if SSH_KEY_PATH.exists():
            print(f"  SSH key already exists: {SSH_KEY_PATH}")
            return
        print("  Generating SSH key...")
        email = self._gcloud_account()
        subprocess.run([
            "ssh-keygen", "-t", "rsa", "-b", "4096",
            "-f", str(SSH_KEY_PATH),
            "-C", email,
            "-N", "",
        ], check=True)
        print(f"  SSH key created: {SSH_KEY_PATH}")

    def _read_pubkey(self) -> str:
        return SSH_KEY_PATH.with_suffix(".pub").read_text().strip()

    def update_ssh_config(self, ip: str, username: str):
        """Write or replace the Host gcp-vm block in ~/.ssh/config."""
        SSH_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing = SSH_CONFIG_PATH.read_text() if SSH_CONFIG_PATH.exists() else ""

        new_block = (
            f"Host {SSH_HOST_ALIAS}\n"
            f"    HostName {ip}\n"
            f"    User {username}\n"
            f"    IdentityFile {SSH_KEY_PATH}\n"
            f"    StrictHostKeyChecking accept-new\n"
            f"    ConnectTimeout 5\n"
        )

        lines = existing.splitlines(keepends=True)
        out_lines = []
        skip = False
        found = False
        for line in lines:
            if line.strip() == f"Host {SSH_HOST_ALIAS}":
                skip = True
                found = True
                out_lines.append(new_block)
                continue
            if skip and line.startswith("Host "):
                skip = False
            if not skip:
                out_lines.append(line)

        if not found:
            if out_lines and not out_lines[-1].endswith("\n"):
                out_lines.append("\n")
            out_lines.append("\n" + new_block)

        SSH_CONFIG_PATH.write_text("".join(out_lines))
        print(f"  SSH config updated: {SSH_CONFIG_PATH}")

    # ------------------------------------------------------------------
    # Remote command execution
    # ------------------------------------------------------------------

    def _ssh(self, vm_name: str, command: str) -> int:
        """Run a command on the VM, streaming output live. Returns exit code."""
        return subprocess.run([
            "gcloud", "compute", "ssh", vm_name,
            f"--zone={self.zone}", f"--project={self.project}",
            f"--command={command}",
        ]).returncode

    def _ssh_capture(self, vm_name: str, command: str) -> tuple[str, int]:
        """Run a command on the VM and capture stdout. Returns (stdout, exit_code)."""
        result = subprocess.run([
            "gcloud", "compute", "ssh", vm_name,
            f"--zone={self.zone}", f"--project={self.project}",
            f"--command={command}",
        ], capture_output=True, text=True)
        return result.stdout.strip(), result.returncode

    def _wait_for_running(self, vm_name: str, max_attempts: int = 40, interval: int = 5):
        print("  Waiting for VM to reach RUNNING status", end="", flush=True)
        for _ in range(max_attempts):
            if self._get_vm_status(vm_name) == "RUNNING":
                print(" OK")
                return
            print(".", end="", flush=True)
            time.sleep(interval)
        raise RuntimeError(f"VM {vm_name} did not reach RUNNING after {max_attempts * interval}s")

    def _wait_for_ssh(self, vm_name: str, max_attempts: int = 20, interval: int = 10):
        print("  Waiting for SSH to become available", end="", flush=True)
        time.sleep(10)
        for _ in range(max_attempts):
            if self._ssh(vm_name, "echo ok") == 0:
                print(" OK")
                return
            print(".", end="", flush=True)
            time.sleep(interval)
        raise RuntimeError(f"SSH not available on {vm_name} after {max_attempts * interval}s")

    def _run_step(self, label: str, vm_name: str, command: str):
        print(f"\n  {label}")
        code = self._ssh(vm_name, command)
        if code != 0:
            raise RuntimeError(f"Step failed (exit {code}): {label}")
        print("  ... done")

    def _prompt_delete_on_failure(self, vm_name: str):
        ans = input(f"\n  Delete failed VM '{vm_name}'? (y/N): ").strip().lower()
        if ans == "y":
            print(f"  Deleting {vm_name}...")
            subprocess.run([
                "gcloud", "compute", "instances", "delete", vm_name,
                f"--zone={self.zone}", f"--project={self.project}", "--quiet",
            ])
            print("  Deleted.")
        else:
            print(f"  VM left running. SSH manually: gcloud compute ssh {vm_name} --zone={self.zone}")

    # ------------------------------------------------------------------
    # Public actions
    # ------------------------------------------------------------------

    def _pick_machine_type(self) -> str:
        print("\n  Select machine type:")
        print(f"\n  {'#':<4} {'Machine Type':<30} {'vCPU':>6} {'RAM (GB)':>10} {'$/hr':>8} {'AUD/hr':>8} {'AUD/vCPU/hr':>12} {'$/min':>8}")
        print(f"  {'-'*4} {'-'*30} {'-'*6} {'-'*10} {'-'*8} {'-'*8} {'-'*12} {'-'*8}")
        for i, (name, vcpus, mem_gb, usd_hr) in enumerate(MACHINE_TYPES, 1):
            aud_hr = usd_hr * USD_TO_AUD
            aud_per_vcpu = aud_hr / vcpus
            usd_min = usd_hr / 60
            print(f"  {i:<4} {name:<30} {vcpus:>6} {mem_gb:>10} {usd_hr:>8.2f} {aud_hr:>8.2f} {aud_per_vcpu:>12.4f} {usd_min:>8.4f}")
        try:
            idx = int(input("\n  Select option: ").strip()) - 1
            return MACHINE_TYPES[idx][0]
        except (ValueError, IndexError):
            print("  Invalid selection, defaulting to option 1.")
            return MACHINE_TYPES[0][0]

    def setup(self):
        """Create and fully configure a new VM."""
        self.prompt_config()
        machine_type = self._pick_machine_type()
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        vm_name = f"{VM_NAME_PREFIX}-{ts}"

        print(f"\n--- Setting up new VM: {vm_name} ---")

        print("\n[1/6] Generating SSH key...")
        self._ensure_ssh_key()
        username = self._gcloud_username()
        ssh_key_metadata = f"{username}:{self._read_pubkey()}"

        print(f"\n[2/6] Creating VM ({machine_type})...")
        self._gcloud([
            "compute", "instances", "create", vm_name,
            f"--project={self.project}", f"--zone={self.zone}",
            f"--machine-type={machine_type}",
            "--image-family=debian-12", "--image-project=debian-cloud",
            f"--metadata=ssh-keys={ssh_key_metadata}",
        ])

        print("\n[3/6] Waiting for VM to be ready...")
        self._wait_for_running(vm_name)
        self._wait_for_ssh(vm_name)

        try:
            self._run_step("[4/6] Formatting and mounting local SSD...", vm_name,
                "sudo mkfs.ext4 -m 0 -E lazy_itable_init=0,lazy_journal_init=0,discard /dev/nvme0n1 && "
                "sudo mkdir -p /mnt/disks/localssd && "
                "sudo mount -o discard,defaults /dev/nvme0n1 /mnt/disks/localssd && "
                "sudo chmod a+w /mnt/disks/localssd && "
                "mkdir -p /mnt/disks/localssd/workspace"
            )

            print("\n  Detecting SSD UUID for fstab...")
            uuid_out, code = self._ssh_capture(vm_name, "sudo blkid -s UUID -o value /dev/nvme0n1")
            if code != 0 or not uuid_out:
                raise RuntimeError("Could not detect SSD UUID via blkid")
            uuid = uuid_out.strip()
            print(f"  UUID: {uuid}")
            self._run_step("  Writing /etc/fstab...", vm_name,
                f'echo "UUID={uuid} /mnt/disks/localssd ext4 discard,nofail 0 2" | sudo tee -a /etc/fstab && '
                "sudo mount -a"
            )

            self._run_step("[5/6] Installing Git and Docker...", vm_name,
                "sudo apt-get update -y && "
                "sudo apt-get install -y git docker.io && "
                f"sudo usermod -aG docker {username}"
            )

            self._run_step(
                "[6/6] Cloning repository and running setup (this may take 10+ minutes)...",
                vm_name,
                "cd /mnt/disks/localssd/workspace && "
                "git clone https://github.com/vincentlogarzo/archilume.git && "
                "bash /mnt/disks/localssd/workspace/archilume/.devcontainer/setup.sh && "
                "source ~/.bashrc"
            )

        except RuntimeError as e:
            print(f"\n  ERROR: {e}")
            self._prompt_delete_on_failure(vm_name)
            return

        ip = self._get_vm_ip(vm_name)
        self.update_ssh_config(ip, username)

        print(f"\n=== Setup complete! VM: {vm_name} | IP: {ip} ===")
        print(f"\nTo open in VSCode:\n  code --remote ssh-remote+{SSH_HOST_ALIAS} {REMOTE_WORKSPACE}")
        if input("\nOpen VSCode now? (y/N): ").strip().lower() == "y":
            subprocess.run(["code", "--remote", f"ssh-remote+{SSH_HOST_ALIAS}", REMOTE_WORKSPACE])

    def connect(self):
        """Select a running VM and open VSCode remote."""
        self.prompt_config()
        vms = self.list_vms()
        running = [(n, s, z, ip) for n, s, z, ip in vms if s == "RUNNING"]

        if not running:
            print("  No running archilume VMs found. Run setup first.")
            return

        print("\n  Running VMs:")
        for i, (name, _, zone, ip) in enumerate(running, 1):
            print(f"    {i}. {name}  ({zone})  {ip}")

        try:
            idx = int(input("\n  Select VM number: ").strip()) - 1
            vm_name, _, _, ip = running[idx]
        except (ValueError, IndexError):
            print("  Invalid selection.")
            return

        self.update_ssh_config(ip, self._gcloud_username())
        print(f"\n  Opening VSCode remote: {vm_name}")
        subprocess.run(["code", "--remote", f"ssh-remote+{SSH_HOST_ALIAS}", REMOTE_WORKSPACE])

    def delete(self):
        """Select and delete one or more VMs."""
        self.prompt_config()
        vms = self.list_vms()
        if not vms:
            print("  No archilume VMs found.")
            return

        print("\n  All archilume VMs:")
        for i, (name, status, zone, ip) in enumerate(vms, 1):
            print(f"    {i}. {name}  [{status}]  {zone}  {ip or 'no IP'}")

        try:
            indices = [int(x.strip()) - 1 for x in input("\n  Enter numbers to delete (e.g. 1,3): ").split(",")]
            selected = [vms[i] for i in indices]
        except (ValueError, IndexError):
            print("  Invalid selection.")
            return

        print("\n  VMs to delete:")
        for name, status, zone, _ in selected:
            print(f"    {name}  [{status}]  {zone}")

        if input("\n  Confirm deletion? (y/N): ").strip().lower() != "y":
            print("  Cancelled.")
            return

        for name, _, zone, _ in selected:
            print(f"\n  Deleting {name}...")
            subprocess.run([
                "gcloud", "compute", "instances", "delete", name,
                f"--zone={zone}", f"--project={self.project}", "--quiet",
            ])
            print(f"  Deleted {name}.")

    def check(self):
        """List all archilume VMs and their status."""
        self.prompt_config()
        print(f"\n  Archilume VMs in project '{self.project}':")
        vms = self.list_vms()
        if not vms:
            print("  None found.")
            return
        print(f"\n  {'Name':<30}  {'Status':<12}  {'Zone':<25}  IP")
        print(f"  {'-'*30}  {'-'*12}  {'-'*25}  {'-'*15}")
        for name, status, zone, ip in vms:
            print(f"  {name:<30}  {status:<12}  {zone:<25}  {ip or '—'}")

    def run(self):
        """Show the main menu and dispatch the selected action."""
        print("\n============= Archilume GCP VM Manager =============")
        if self.cfg:
            print(f"  Config: project={self.cfg.get('project', '?')}  zone={self.cfg.get('zone', '?')}")

        print("\n  1. Setup new VM")
        print("  2. Connect to a VM")
        print("  3. Delete VM(s)")
        print("  4. Check / list VMs")
        print("  5. Exit")

        choice = input("\nSelect option: ").strip()

        if choice == "1":
            self.setup()
        elif choice == "2":
            self.connect()
        elif choice == "3":
            self.delete()
        elif choice == "4":
            self.check()
        elif choice == "5":
            raise SystemExit(0)
        else:
            print("  Invalid option.")
