"""
gcp_vm_manager.py — GCP VM lifecycle manager for Archilume.

Handles creation, setup, connection, and deletion of GCP VMs.
Config is saved to ~/.archilume_gcp_config.json.
SSH key is stored at ~/.ssh/google_cloud_vm_key.
"""

import json
import os
import subprocess
import sys
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
# Base clock speeds (GHz) per machine family — from GCP published specs
_FAMILY_GHZ: dict[str, str] = {
    "c4d": "3.4",
    "c4a": "3.1",
    "c4":  "3.1",
    "c3d": "3.6",
    "c3":  "3.1",
    "h4d": "3.4",
    "z3":  "3.6",
}


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
        reference_type = "c4d-standard-64-lssd"
        print(f"  Finding best zone for lssd machine types...")
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

    def _check_vscode_remote_ssh_config(self):
        """
        Check that VS Code Remote SSH is configured to use SSH_CONFIG_PATH.
        Searches common settings.json locations and warns if the setting is missing or wrong.
        Skips the check inside dev containers where the host filesystem is inaccessible.
        """
        # Inside a dev container we cannot access the host VS Code settings,
        # and update_ssh_config() already writes to the Windows host SSH config
        # via /mnt/c or _find_windows_ssh_config(). Skip the noisy warning.
        if os.environ.get("REMOTE_CONTAINERS") or os.environ.get("CODESPACES"):
            print("  ℹ️  Running inside a dev container — skipping VS Code settings.json check.\n"
                  f"     SSH config is written directly to your host's ~/.ssh/config by this tool.")
            return

        candidate_dirs = [
            Path.home() / ".config" / "Code" / "User",          # Linux host
            Path.home() / ".config" / "Code - Insiders" / "User",
            Path("/vscode/vscode-server/data/User"),             # dev container server
            Path.home() / ".vscode-server" / "data" / "User",
        ]
        if sys.platform == "win32":
            # Native Windows: %APPDATA%\Code\User
            appdata = os.environ.get("APPDATA", "")
            if appdata:
                candidate_dirs.append(Path(appdata) / "Code" / "User")
                candidate_dirs.append(Path(appdata) / "Code - Insiders" / "User")
        else:
            # WSL or Linux dev container: probe Windows drives via /mnt/c
            wsl_users = Path("/mnt/c/Users")
            if wsl_users.exists():
                for user_dir in wsl_users.iterdir():
                    candidate_dirs.append(user_dir / "AppData" / "Roaming" / "Code" / "User")
                    candidate_dirs.append(user_dir / "AppData" / "Roaming" / "Code - Insiders" / "User")

        found_settings = [d / "settings.json" for d in candidate_dirs if (d / "settings.json").exists()]

        correct_path = str(SSH_CONFIG_PATH)
        ok = False
        for settings_file in found_settings:
            try:
                data = json.loads(settings_file.read_text())
                configured = data.get("remote.SSH.configFile", "")
                if configured == correct_path:
                    ok = True
                    break
            except Exception:
                continue

        if not found_settings:
            print(
                f"\n  ⚠️  Could not locate a VS Code settings.json to verify Remote SSH config.\n"
                f"     Ensure 'remote.SSH.configFile' is set to: {correct_path}\n"
                f"     (VS Code → Settings → remote.SSH.configFile)"
            )
        elif not ok:
            print(
                f"\n  ⚠️  VS Code Remote SSH config may not point to the correct file.\n"
                f"     Set 'remote.SSH.configFile' to: {correct_path}\n"
                f"     (VS Code → Settings → remote.SSH.configFile)"
            )
        else:
            print(f"  VS Code Remote SSH config file is correctly set to: {correct_path}")

    def _ensure_ssh_key(self):
        if SSH_KEY_PATH.exists():
            print(f"  SSH key already exists: {SSH_KEY_PATH}")
        else:
            print("  Generating SSH key...")
            email = self._gcloud_account()
            subprocess.run([
                "ssh-keygen", "-t", "rsa", "-b", "4096",
                "-f", str(SSH_KEY_PATH),
                "-C", email,
                "-N", "",
            ], check=True)
            print(f"  SSH key created: {SSH_KEY_PATH}")
        self._check_vscode_remote_ssh_config()

    def _read_pubkey(self) -> str:
        return SSH_KEY_PATH.with_suffix(".pub").read_text().strip()

    @staticmethod
    def _upsert_ssh_config_block(config_path: Path, host_alias: str, block: str):
        """Insert or replace a Host block in an SSH config file."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        existing = config_path.read_text() if config_path.exists() else ""

        lines = existing.splitlines(keepends=True)
        out_lines = []
        skip = False
        found = False
        for line in lines:
            if line.strip() == f"Host {host_alias}":
                skip = True
                found = True
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

        config_path.write_text("".join(out_lines))

    def _find_windows_ssh_config(self) -> Path | None:
        """Find the Windows host SSH config path when running inside WSL/devcontainer."""
        wsl_users = Path("/mnt/c/Users")
        if not wsl_users.exists():
            return None
        for user_dir in wsl_users.iterdir():
            if user_dir.name in ("Public", "Default", "Default User", "All Users"):
                continue
            ssh_dir = user_dir / ".ssh"
            if ssh_dir.exists():
                return ssh_dir / "config"
        return None

    def update_ssh_config(self, ip: str, username: str):
        """Write or replace the Host gcp-vm block in ~/.ssh/config and Windows host config."""
        # Block for the container/WSL config (uses container paths)
        container_block = (
            f"Host {SSH_HOST_ALIAS}\n"
            f"    HostName {ip}\n"
            f"    User {username}\n"
            f"    IdentityFile {SSH_KEY_PATH}\n"
            f"    StrictHostKeyChecking accept-new\n"
            f"    ConnectTimeout 5\n"
        )

        self._upsert_ssh_config_block(SSH_CONFIG_PATH, SSH_HOST_ALIAS, container_block)
        print(f"  SSH config updated: {SSH_CONFIG_PATH}")

        # Also write to Windows host SSH config if accessible (WSL/devcontainer)
        win_config = self._find_windows_ssh_config()
        win_block = (
            f"Host {SSH_HOST_ALIAS}\n"
            f"    HostName {ip}\n"
            f"    User {username}\n"
            f"    IdentityFile C:\\Users\\{username}\\.ssh\\google_cloud_vm_key\n"
            f"    StrictHostKeyChecking accept-new\n"
            f"    ConnectTimeout 5\n"
        )
        if win_config:
            try:
                self._upsert_ssh_config_block(win_config, SSH_HOST_ALIAS, win_block)
                print(f"  Windows SSH config updated: {win_config}")
            except PermissionError:
                print(f"  ⚠️  Could not write Windows SSH config: {win_config} (permission denied)")
                self._print_windows_ssh_config_instructions(win_block)
        else:
            # /mnt/c not mounted (typical in dev containers) — print instructions
            self._print_windows_ssh_config_instructions(win_block)

    def _print_windows_ssh_config_instructions(self, block: str):
        print(
            f"\n  ⚠️  Could not auto-update your Windows SSH config.\n"
            f"     Paste the following into C:\\Users\\<you>\\.ssh\\config\n"
            f"     (replacing any existing 'Host {SSH_HOST_ALIAS}' block):\n"
            f"\n"
        )
        for line in block.splitlines():
            print(f"     {line}")
        print()

    def _ensure_ssh_key_on_vm(self, vm_name: str):
        """Ensure our SSH public key is in the VM's instance metadata."""
        self._ensure_ssh_key()
        username = self._gcloud_username()
        pubkey = self._read_pubkey()
        new_entry = f"{username}:{pubkey}"

        # Fetch existing ssh-keys metadata
        existing, code = self._gcloud_capture([
            "compute", "instances", "describe", vm_name,
            f"--zone={self.zone}", f"--project={self.project}",
            "--format=value(metadata.items.ssh-keys)",
        ])

        if new_entry in (existing or ""):
            print(f"  SSH public key already present on {vm_name}")
            return

        # Append our key to existing keys
        if existing:
            updated = existing.rstrip("\n") + "\n" + new_entry
        else:
            updated = new_entry

        print(f"  Adding SSH public key to {vm_name}...")
        self._gcloud([
            "compute", "instances", "add-metadata", vm_name,
            f"--zone={self.zone}", f"--project={self.project}",
            f"--metadata=ssh-keys={updated}",
        ])
        print(f"  SSH public key added to {vm_name}")

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

    def _fetch_usd_to_aud(self) -> float:
        """Fetch live USD→AUD rate from frankfurter.app (no API key required)."""
        try:
            with urllib.request.urlopen(
                "https://api.frankfurter.app/latest?from=USD&to=AUD", timeout=5
            ) as r:
                return json.loads(r.read())["rates"]["AUD"]
        except Exception:
            print("  Warning: could not fetch exchange rate, using fallback 1.55")
            return 1.55

    def _fetch_gcp_pricing(self) -> dict[str, dict]:
        """
        Fetch on-demand per-core and per-GiB-RAM pricing from the GCP Billing SKUs API.
        Returns a dict mapping lowercase family prefix → (core_usd_hr, ram_usd_gib_hr).
        Requires an active gcloud auth token.
        """
        token_result = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True, text=True
        )
        if token_result.returncode != 0:
            return {}
        token = token_result.stdout.strip()

        base = (
            f"https://cloudbilling.googleapis.com/v1/services/"
            f"{_GCP_BILLING_SERVICE}/skus?currencyCode=USD&pageSize=5000"
        )
        all_skus = []
        page_token = ""
        for _ in range(15):
            url = base + (f"&pageToken={page_token}" if page_token else "")
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    data = json.loads(r.read())
            except Exception:
                break
            all_skus.extend(data.get("skus", []))
            page_token = data.get("nextPageToken", "")
            if not page_token:
                break

        # Parse: on-demand core and RAM pricing per machine family, region=Americas
        pricing: dict[str, dict] = {}
        for sku in all_skus:
            desc = sku.get("description", "")
            cat = sku.get("category", {})
            if cat.get("usageType") != "OnDemand":
                continue
            if "spot" in desc.lower() or "commitment" in desc.lower() or "sole tenancy" in desc.lower():
                continue
            regions = sku.get("serviceRegions", [])
            if "us-central1" not in regions and "americas" not in " ".join(regions).lower():
                continue

            pricing_info = sku.get("pricingInfo", [])
            if not pricing_info:
                continue
            pricing_expr = pricing_info[0].get("pricingExpression", {})
            tiers = pricing_expr.get("tieredRates", [])
            if not tiers:
                continue
            price = tiers[0].get("unitPrice", {})
            usd = float(price.get("units", 0)) + price.get("nanos", 0) / 1e9
            unit = pricing_expr.get("usageUnit", "")

            # Match patterns like "C4D Instance Core running in Americas"
            lower = desc.lower()
            for family in ("c4d", "c4a", "c3d", "h4d", "z3", "c4", "c3"):  # longer prefixes first
                if lower.startswith(family + " instance"):
                    entry = pricing.setdefault(family, {})
                    if "core" in lower and unit.endswith("h"):
                        entry["core"] = usd
                    elif "ram" in lower and ("giby" in unit.lower() or "gby" in unit.lower()):
                        entry["ram"] = usd
                    break

        return pricing

    def _list_lssd_machine_types(self) -> list[dict]:
        """
        Query gcloud for all lssd machine types with >= MIN_VCPUS vCPUs in the
        configured zone. Returns list of dicts with name, vcpus, mem_gb.
        """
        out, code = self._gcloud_capture([
            "compute", "machine-types", "list",
            f"--filter=name~lssd AND guestCpus>={MIN_VCPUS}",
            "--format=csv[no-heading](name,guestCpus,memoryMb)",
            f"--zones={self.zone}",
            f"--project={self.project}",
        ])
        if code != 0 or not out:
            return []
        seen, results = set(), []
        for line in out.splitlines():
            parts = line.split(",")
            if len(parts) < 3:
                continue
            name = parts[0].strip()
            if name in seen:
                continue
            seen.add(name)
            try:
                vcpus = int(float(parts[1]))
                mem_gb = round(float(parts[2]) / 1024, 1)
            except ValueError:
                continue
            ghz = next((v for k, v in _FAMILY_GHZ.items() if name.startswith(k)), "n/a")
            results.append({"name": name, "vcpus": vcpus, "mem_gb": mem_gb, "ghz": ghz})
        return sorted(results, key=lambda x: (x["vcpus"], x["name"]))

    def _compute_usd_hr(self, machine: dict, pricing: dict[str, dict]) -> float | None:
        """Estimate on-demand USD/hr for a machine type using billing SKU rates."""
        name = machine["name"].lower()
        for family in ("c4d", "c4a", "c3d", "h4d", "z3", "c4", "c3"):  # longer prefixes first
            if name.startswith(family):
                entry = pricing.get(family, {})
                core_rate = entry.get("core")
                ram_rate = entry.get("ram")
                if core_rate and ram_rate:
                    mem_gib = machine["mem_gb"] * 1.024  # GB → GiB approx
                    return round(machine["vcpus"] * core_rate + mem_gib * ram_rate, 4)
                break
        return None

    def _pick_machine_type(self) -> str:
        print("\n  Fetching available machine types and live pricing...")
        machines = self._list_lssd_machine_types()
        if not machines:
            print("  Could not query machine types. Enter machine type manually:")
            return input("  Machine type: ").strip()

        pricing = self._fetch_gcp_pricing()
        usd_to_aud = self._fetch_usd_to_aud()

        print(f"\n  {'#':<4} {'Machine Type':<32} {'vCPU':>6} {'RAM(GB)':>8} {'GHz':>5} {'USD/hr':>8} {'AUD/hr':>8} {'cents/vCPU/hr':>15} {'USD/min':>8}")
        print(f"  {'-'*4} {'-'*32} {'-'*6} {'-'*8} {'-'*5} {'-'*8} {'-'*8} {'-'*15} {'-'*8}")
        for i, m in enumerate(machines, 1):
            usd_hr = self._compute_usd_hr(m, pricing)
            ghz = m.get("ghz", "n/a")
            if usd_hr:
                aud_hr = usd_hr * usd_to_aud
                aud_cents_per_vcpu = (aud_hr / m["vcpus"]) * 100
                usd_min = usd_hr / 60
                print(f"  {i:<4} {m['name']:<32} {m['vcpus']:>6} {m['mem_gb']:>8.1f} {ghz:>5} {usd_hr:>8.2f} {aud_hr:>8.2f} {aud_cents_per_vcpu:>15.2f} {usd_min:>8.4f}")
            else:
                print(f"  {i:<4} {m['name']:<32} {m['vcpus']:>6} {m['mem_gb']:>8.1f} {ghz:>5} {'n/a':>8} {'n/a':>8} {'n/a':>15} {'n/a':>8}")

        try:
            idx = int(input("\n  Select option: ").strip()) - 1
            return machines[idx]["name"]
        except (ValueError, IndexError):
            print("  Invalid selection, defaulting to option 1.")
            return machines[0]["name"]

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
        print(f"\n  VM external IP: {ip}")
        self.update_ssh_config(ip, username)
        print(f"  SSH config written: Host {SSH_HOST_ALIAS} → {ip} (key: {SSH_KEY_PATH})")
        self.copy_inputs_to_vm(vm_name)

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

        self._ensure_ssh_key_on_vm(vm_name)
        username = self._gcloud_username()
        self.update_ssh_config(ip, username)
        self.copy_inputs_to_vm(vm_name)
        print(f"\n  Opening VSCode remote: {vm_name}")
        subprocess.run(["code", "--remote", f"ssh-remote+{SSH_HOST_ALIAS}", REMOTE_WORKSPACE])

    def reconnect_and_rebuild(self):
        """Reconnect to an existing VM, re-clone repo, and rebuild dev container."""
        self.prompt_config()
        vms = self.list_vms()
        running = [(n, s, z, ip) for n, s, z, ip in vms if s == "RUNNING"]

        if not running:
            print("  No running archilume VMs found.")
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

        self._ensure_ssh_key_on_vm(vm_name)
        username = self._gcloud_username()
        self.update_ssh_config(ip, username)

        print(f"\n  Re-cloning repository and rebuilding dev container on {vm_name}...")
        print("  This may take 10+ minutes...\n")

        self._run_step(
            "[1/2] Re-cloning repository...",
            vm_name,
            "rm -rf /mnt/disks/localssd/workspace/archilume && "
            "cd /mnt/disks/localssd/workspace && "
            "git clone https://github.com/vincentlogarzo/archilume.git"
        )

        self._run_step(
            "[2/2] Running setup script...",
            vm_name,
            "bash /mnt/disks/localssd/workspace/archilume/.devcontainer/setup.sh && "
            "source ~/.bashrc"
        )

        self.copy_inputs_to_vm(vm_name)

        print(f"\n=== Rebuild complete! VM: {vm_name} | IP: {ip} ===")
        print(f"\nTo open in VSCode:\n  code --remote ssh-remote+{SSH_HOST_ALIAS} {REMOTE_WORKSPACE}")
        if input("\nOpen VSCode now? (y/N): ").strip().lower() == "y":
            subprocess.run(["code", "--remote", f"ssh-remote+{SSH_HOST_ALIAS}", REMOTE_WORKSPACE])

    def _scp_cmd(self, vm_name: str) -> tuple[list[str], str]:
        """Return (ssh_flags_list, user@ip) for direct scp transfers."""
        ip = self._get_vm_ip(vm_name)
        username = self._gcloud_username()
        flags = [
            "-i", str(SSH_KEY_PATH),
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=10",
        ]
        return flags, f"{username}@{ip}"

    def copy_inputs_to_vm(self, vm_name: str) -> None:
        """Copy aoi folder and input files from local inputs to VM via direct scp."""
        local_inputs = Path.cwd() / "inputs"
        if not local_inputs.exists():
            print("  ℹ️  No local inputs folder found, skipping...")
            return

        print("  📂 Copying inputs data to VM...")
        remote_inputs = f"{REMOTE_WORKSPACE}/inputs"
        self._ssh(vm_name,
            f"sudo mkdir -p {remote_inputs}/aoi && "
            f"sudo chmod -R a+rwx {remote_inputs}"
        )

        ssh_flags, remote_host = self._scp_cmd(vm_name)
        remote_dest = f"{remote_host}:{remote_inputs}/"

        def _fmt_size(n: int) -> str:
            for unit in ("B", "KB", "MB", "GB"):
                if n < 1024:
                    return f"{n:.1f} {unit}"
                n /= 1024
            return f"{n:.1f} TB"

        anything_copied = False
        any_failed = False

        aoi_folder = local_inputs / "aoi"
        if aoi_folder.exists():
            size = _fmt_size(sum(f.stat().st_size for f in aoi_folder.rglob("*") if f.is_file()))
            print(f"    → Copying aoi/ ({size})...")
            result = subprocess.run(["scp", "-r"] + ssh_flags + [str(aoi_folder), remote_dest])
            if result.returncode == 0:
                print("    ✅ aoi/ copied")
            else:
                print("    ⚠️  Failed to copy aoi/")
                any_failed = True
            anything_copied = True

        files_to_copy = [f for f in local_inputs.glob("*") if f.is_file()]
        if files_to_copy:
            total_size = _fmt_size(sum(f.stat().st_size for f in files_to_copy))
            print(f"    → Copying {len(files_to_copy)} file(s) ({total_size})...")
            result = subprocess.run(["scp"] + ssh_flags + [str(f) for f in files_to_copy] + [remote_dest])
            if result.returncode == 0:
                print(f"    ✅ {len(files_to_copy)} file(s) copied")
            else:
                print("    ⚠️  Failed to copy files")
                any_failed = True
            anything_copied = True

        if not anything_copied:
            print("  ℹ️  No aoi folder or input files found to copy")
        elif any_failed:
            print("  ⚠️  Some files failed to copy — check errors above.")
        else:
            print("  ✅ Inputs data copied successfully!")

    def _check_vm_idle(self, vm_name: str) -> tuple[bool, str]:
        """Check if the VM has any running user processes (python, bash scripts, etc).
        Returns (is_idle, description)."""
        # Look for python/bash processes that indicate active work
        # Exclude system processes, sshd, and the check command itself
        out, code = self._ssh_capture(
            vm_name,
            "ps aux --no-headers | grep -vE '(sshd|ps aux|grep|bash -c|gcloud)' | "
            "grep -E '(python|node|java|make|gcc|g\\+\\+|cargo|go run)' || true"
        )
        if code != 0:
            return False, "Could not check running processes"
        if out.strip():
            return False, out.strip()
        return True, ""

    def _download_outputs_from_vm(self, vm_name: str, zone: str) -> bool:
        """Download outputs directory from VM to local archive. Returns True on success."""
        remote_outputs = f"{REMOTE_WORKSPACE}/outputs"
        base_flags = [f"--zone={zone}", f"--project={self.project}"]

        # Check if remote outputs directory exists and has content
        out, code = self._ssh_capture(vm_name, f"ls -A {remote_outputs} 2>/dev/null")
        if code != 0 or not out:
            print(f"  No outputs found on {vm_name}, skipping download.")
            return True

        # Create local archive directory
        archive_dir = Path.cwd() / "archive"
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        local_dest = archive_dir / f"{vm_name}_{ts}"
        local_dest.mkdir(parents=True, exist_ok=True)

        print(f"  📥 Downloading outputs from {vm_name} to {local_dest}...")
        ssh_flags, remote_host = self._scp_cmd(vm_name)
        result = subprocess.run(
            ["scp", "-r"] + ssh_flags + [f"{remote_host}:{remote_outputs}/", str(local_dest) + "/"]
        )
        if result.returncode != 0:
            print(f"  ⚠️  Failed to download outputs")
            return False

        # List what was downloaded
        downloaded = list(local_dest.rglob("*"))
        file_count = sum(1 for f in downloaded if f.is_file())
        print(f"  ✅ Downloaded {file_count} file(s) to {local_dest}")
        return True

    def delete(self):
        """Select and delete one or more VMs, downloading outputs first."""
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

        # Check each running VM for active processes
        blocked = []
        for name, status, zone, _ in selected:
            if status != "RUNNING":
                continue
            print(f"\n  Checking {name} for active processes...")
            is_idle, details = self._check_vm_idle(name)
            if not is_idle:
                print(f"  ⚠️  {name} is still running code:")
                for line in details.splitlines()[:5]:
                    print(f"      {line.strip()}")
                blocked.append(name)

        if blocked:
            print(f"\n  Cannot proceed — the following VM(s) are still running code: {', '.join(blocked)}")
            print("  Wait for processes to finish or stop them manually before deleting.")
            return

        # Download outputs from each running VM before deletion
        for name, status, zone, _ in selected:
            if status == "RUNNING":
                self._download_outputs_from_vm(name, zone)

        if input("\n  Have you verified you have downloaded the results you need? (y/N): ").strip().lower() != "y":
            print("  Cancelled. VMs not deleted.")
            return

        print("\n  VMs to delete:")
        for name, status, zone, _ in selected:
            print(f"    {name}  [{status}]  {zone}")

        if input("\n  Type 'delete' to confirm: ").strip() != "delete":
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
        print("  3. Reconnect and rebuild dev container")
        print("  4. Download results and delete VM(s)")
        print("  5. Check / list VMs")
        print("  6. Exit")

        choice = input("\nSelect option: ").strip()

        if choice == "1":
            self.setup()
        elif choice == "2":
            self.connect()
        elif choice == "3":
            self.reconnect_and_rebuild()
        elif choice == "4":
            self.delete()
        elif choice == "5":
            self.check()
        elif choice == "6":
            raise SystemExit(0)
        else:
            print("  Invalid option.")
