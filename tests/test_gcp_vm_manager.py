"""Tests for the streamlined :class:`GCPVMManager`.

Bypass ``__init__`` (which calls gcloud) by constructing via ``object.__new__``
and setting attrs directly. Only methods that don't require a real GCP project
are covered.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from archilume.infra import gcp_vm_manager as gvm
from archilume.infra.gcp_vm_manager import GCPVMManager

pytestmark = pytest.mark.gcp


@pytest.fixture
def mgr() -> GCPVMManager:
    """Build a ``GCPVMManager`` without touching gcloud or the network."""
    m = object.__new__(GCPVMManager)
    m._gcloud_bin = "/fake/gcloud"
    m.project = "demo-proj"
    m.zone = "us-central1-a"
    m.archilume_project = None
    return m


# ---------------------------------------------------------------------------
# Constants & guardrails
# ---------------------------------------------------------------------------


class TestEngineConstants:
    def test_engine_image_and_port(self):
        assert gvm.ENGINE_IMAGE == "vlogarzo/archilume-engine:latest"
        assert gvm.ENGINE_PORT == 8100

    def test_remote_projects_under_lssd_mount(self):
        assert gvm.REMOTE_PROJECTS == f"{gvm.LSSD_MOUNT}/projects"


class TestMachineTypesConstant:
    def test_non_empty_tuple_of_strings(self):
        assert isinstance(gvm.MACHINE_TYPES, tuple)
        assert len(gvm.MACHINE_TYPES) > 0
        assert all(isinstance(m, str) for m in gvm.MACHINE_TYPES)

    def test_default_is_in_list(self):
        assert gvm.DEFAULT_MACHINE_TYPE in gvm.MACHINE_TYPES

    def test_all_x86_lssd_prefixes(self):
        # Engine image is x86_64-only; arm64 prefixes (c4a/n4a/t2a) must not appear.
        assert all(m.startswith(gvm._X86_LSSD_PREFIXES) for m in gvm.MACHINE_TYPES)
        for m in gvm.MACHINE_TYPES:
            assert not m.startswith(("c4a-", "n4a-", "t2a-"))

    def test_all_end_in_lssd(self):
        assert all(m.endswith("-lssd") for m in gvm.MACHINE_TYPES)


class TestCosStartupScript:
    def test_startup_script_is_bundled(self):
        assert gvm.STARTUP_SCRIPT_PATH.exists(), (
            "cos_startup.sh must sit next to gcp_vm_manager.py so "
            "--metadata-from-file=startup-script=<path> can read it"
        )

    def test_startup_script_is_idempotent_on_format(self):
        text = gvm.STARTUP_SCRIPT_PATH.read_text()
        # mkfs must be guarded by a blkid check — otherwise every reboot wipes the LSSD.
        assert "blkid" in text
        assert "mkfs.ext4" in text

    def test_startup_script_aligned_with_constants(self):
        text = gvm.STARTUP_SCRIPT_PATH.read_text()
        assert gvm.ENGINE_IMAGE in text
        assert f"ENGINE_PORT={gvm.ENGINE_PORT}" in text
        assert f"MNT={gvm.LSSD_MOUNT}" in text


# ---------------------------------------------------------------------------
# gcloud resolution
# ---------------------------------------------------------------------------


class TestResolveGcloud:
    def test_prefers_config_path_when_present(self, tmp_path, monkeypatch):
        fake = tmp_path / "gcloud"
        fake.write_text("#!/bin/sh\n")
        monkeypatch.setattr(gvm, "GCLOUD_EXECUTABLE", fake)
        assert gvm._resolve_gcloud() == str(fake)

    def test_falls_back_to_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gvm, "GCLOUD_EXECUTABLE", tmp_path / "missing")
        monkeypatch.setattr(gvm.shutil, "which", lambda name: "/usr/bin/gcloud" if name == "gcloud" else None)
        assert gvm._resolve_gcloud() == "/usr/bin/gcloud"

    def test_raises_when_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gvm, "GCLOUD_EXECUTABLE", tmp_path / "missing")
        monkeypatch.setattr(gvm.shutil, "which", lambda name: None)
        with pytest.raises(RuntimeError, match="gcloud not found"):
            gvm._resolve_gcloud()


# ---------------------------------------------------------------------------
# VM queries (gcloud wrappers)
# ---------------------------------------------------------------------------


class TestVmQueries:
    def test_get_vm_ip_returns_capture_stdout(self, mgr, monkeypatch):
        monkeypatch.setattr(mgr, "_describe", lambda vm, fmt: ("203.0.113.7", 0))
        assert mgr._get_vm_ip("vm1") == "203.0.113.7"

    def test_get_vm_status_unknown_on_nonzero(self, mgr, monkeypatch):
        monkeypatch.setattr(mgr, "_describe", lambda vm, fmt: ("", 1))
        assert mgr._get_vm_status("vm1") == "UNKNOWN"

    def test_get_vm_status_returns_stdout_on_success(self, mgr, monkeypatch):
        monkeypatch.setattr(mgr, "_describe", lambda vm, fmt: ("RUNNING", 0))
        assert mgr._get_vm_status("vm1") == "RUNNING"

    def test_list_vms_parses_csv_rows(self, mgr, monkeypatch):
        csv_out = (
            "archilume-vm-1,RUNNING,us-central1-a,1.1.1.1\n"
            "archilume-vm-2,TERMINATED,us-central1-b,\n"
        )
        monkeypatch.setattr(mgr, "_gcloud", lambda args, capture=False: (csv_out, 0))
        rows = mgr.list_vms()
        assert len(rows) == 2
        assert rows[0] == ("archilume-vm-1", "RUNNING", "us-central1-a", "1.1.1.1")
        assert rows[1][3] == ""  # empty IP preserved

    def test_list_vms_empty_when_no_matches(self, mgr, monkeypatch):
        monkeypatch.setattr(mgr, "_gcloud", lambda args, capture=False: ("", 0))
        assert mgr.list_vms() == []


class TestUsername:
    def test_strips_at_domain(self, mgr, monkeypatch):
        monkeypatch.setattr(mgr, "_gcloud", lambda args, capture=False: ("alice@example.com", 0))
        assert mgr._username() == "alice"


# ---------------------------------------------------------------------------
# SSH config
# ---------------------------------------------------------------------------


class TestUpdateSshConfig:
    def _mgr_with_config_at(self, mgr, monkeypatch, path: Path) -> GCPVMManager:
        monkeypatch.setattr(gvm, "SSH_CONFIG_PATH", path)
        return mgr

    def test_creates_file_when_missing(self, mgr, tmp_path, monkeypatch):
        cfg = tmp_path / "ssh_config"
        self._mgr_with_config_at(mgr, monkeypatch, cfg)
        mgr._update_ssh_config("1.2.3.4", "alice")
        text = cfg.read_text()
        assert f"Host {gvm.SSH_HOST_ALIAS}" in text
        assert "HostName 1.2.3.4" in text
        assert "User alice" in text

    def test_replaces_existing_block_and_keeps_others(self, mgr, tmp_path, monkeypatch):
        cfg = tmp_path / "ssh_config"
        cfg.write_text(
            f"Host {gvm.SSH_HOST_ALIAS}\n"
            "    HostName old.ip\n"
            "    User olduser\n"
            "Host other\n"
            "    HostName other.host\n"
        )
        self._mgr_with_config_at(mgr, monkeypatch, cfg)
        mgr._update_ssh_config("9.9.9.9", "newuser")
        text = cfg.read_text()
        assert "9.9.9.9" in text
        assert "old.ip" not in text
        assert "other.host" in text  # unrelated block preserved

    def test_appends_when_unrelated_host_exists(self, mgr, tmp_path, monkeypatch):
        cfg = tmp_path / "ssh_config"
        cfg.write_text("Host github.com\n    HostName github.com\n")
        self._mgr_with_config_at(mgr, monkeypatch, cfg)
        mgr._update_ssh_config("1.2.3.4", "alice")
        text = cfg.read_text()
        assert "github.com" in text
        assert f"Host {gvm.SSH_HOST_ALIAS}" in text


# ---------------------------------------------------------------------------
# Action dispatcher
# ---------------------------------------------------------------------------


class TestRunDispatcher:
    def test_dispatches_to_named_action(self, mgr, monkeypatch):
        calls = {}
        for name in ("setup", "delete", "tunnel", "restart"):
            monkeypatch.setattr(mgr, name, lambda action=name, **kw: calls.setdefault(action, kw))
        mgr.run("setup", machine_type="c4d-standard-96-lssd")
        mgr.run("delete", vm_name="x")
        mgr.run("tunnel")
        mgr.run("restart", vm_name="y")
        assert set(calls) == {"setup", "delete", "tunnel", "restart"}
        assert calls["setup"] == {"machine_type": "c4d-standard-96-lssd"}
        assert calls["restart"] == {"vm_name": "y"}

    def test_unknown_action_raises(self, mgr):
        with pytest.raises(ValueError, match="Unknown action"):
            mgr.run("nope")

    def test_setup_rejects_off_list_machine_type(self, mgr, monkeypatch):
        # `setup` validates machine_type before any gcloud call.
        with pytest.raises(ValueError, match="Unknown machine type"):
            mgr.setup(machine_type="n2-standard-4")

    def test_delete_requires_vm_name(self, mgr):
        with pytest.raises(ValueError, match="vm_name is required"):
            mgr.delete("")

    def test_restart_requires_vm_name(self, mgr):
        with pytest.raises(ValueError, match="vm_name is required"):
            mgr.restart("")


# ---------------------------------------------------------------------------
# SSH key generation
# ---------------------------------------------------------------------------


class TestEnsureSshKey:
    def test_skips_when_key_exists(self, mgr, tmp_path, monkeypatch):
        key = tmp_path / "key"
        key.write_text("dummy")
        monkeypatch.setattr(gvm, "SSH_KEY_PATH", key)
        called = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(a))
        mgr._ensure_ssh_key()
        assert called == []

    def test_runs_keygen_when_missing(self, mgr, tmp_path, monkeypatch):
        key = tmp_path / "newkey"
        monkeypatch.setattr(gvm, "SSH_KEY_PATH", key)
        called = []

        def fake_run(args, **kw):
            called.append(args)
            return type("R", (), {"returncode": 0})()

        monkeypatch.setattr(subprocess, "run", fake_run)
        mgr._ensure_ssh_key()
        assert called and called[0][0] == "ssh-keygen"
        assert str(key) in called[0]
