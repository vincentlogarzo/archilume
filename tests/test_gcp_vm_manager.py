"""Tests for the pure-logic slice of :class:`GCPVMManager`.

All tests bypass ``__init__`` (which tries to install gcloud and authenticate).
Only methods whose behaviour can be exercised without a real GCP project are
covered — ~15 of the 50 methods on the class. The remaining 35 are thin
wrappers around ``gcloud`` subprocess calls, covered indirectly.
"""

from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path

import pytest

from archilume.infra import gcp_vm_manager as gvm
from archilume.infra.gcp_vm_manager import GCPVMManager

pytestmark = pytest.mark.gcp


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def mgr() -> GCPVMManager:
    """Build a ``GCPVMManager`` without touching gcloud or the network."""
    m = object.__new__(GCPVMManager)
    m.cfg = {"project": "demo-proj", "zone": "us-central1-a"}
    m.archilume_project = None
    return m


# =========================================================================
# Config properties
# =========================================================================


class TestConfigProperties:
    def test_project_returns_cfg_value(self, mgr):
        assert mgr.project == "demo-proj"

    def test_zone_returns_cfg_value(self, mgr):
        assert mgr.zone == "us-central1-a"


# =========================================================================
# _load_config / _save_config (round-trip)
# =========================================================================


class TestConfigRoundTrip:
    def test_load_missing_returns_empty(self, mgr, tmp_path, monkeypatch):
        monkeypatch.setattr(gvm, "CONFIG_PATH", tmp_path / "nope.json")
        assert mgr._load_config() == {}

    def test_load_reads_existing(self, mgr, tmp_path, monkeypatch):
        cfg_file = tmp_path / "c.json"
        cfg_file.write_text(json.dumps({"project": "p", "zone": "z"}))
        monkeypatch.setattr(gvm, "CONFIG_PATH", cfg_file)
        assert mgr._load_config() == {"project": "p", "zone": "z"}

    def test_save_writes_json(self, mgr, tmp_path, monkeypatch):
        cfg_file = tmp_path / "c.json"
        monkeypatch.setattr(gvm, "CONFIG_PATH", cfg_file)
        mgr.cfg = {"project": "saved"}
        mgr._save_config()
        assert json.loads(cfg_file.read_text()) == {"project": "saved"}


# =========================================================================
# _upsert_ssh_config_block (static)
# =========================================================================


class TestUpsertSshConfigBlock:
    def test_creates_file_when_missing(self, tmp_path):
        cfg = tmp_path / "ssh_config"
        block = "Host gcp-vm\n    HostName 1.2.3.4\n"
        GCPVMManager._upsert_ssh_config_block(cfg, "gcp-vm", block)
        assert block in cfg.read_text()

    def test_appends_to_existing_unrelated_host(self, tmp_path):
        cfg = tmp_path / "ssh_config"
        cfg.write_text("Host github.com\n    HostName github.com\n")
        block = "Host gcp-vm\n    HostName 1.2.3.4\n"
        GCPVMManager._upsert_ssh_config_block(cfg, "gcp-vm", block)
        text = cfg.read_text()
        assert "github.com" in text
        assert "gcp-vm" in text

    def test_replaces_existing_block(self, tmp_path):
        cfg = tmp_path / "ssh_config"
        cfg.write_text(
            "Host gcp-vm\n"
            "    HostName old.ip\n"
            "    User olduser\n"
            "Host other\n"
            "    HostName other.host\n"
        )
        new_block = "Host gcp-vm\n    HostName new.ip\n"
        GCPVMManager._upsert_ssh_config_block(cfg, "gcp-vm", new_block)
        text = cfg.read_text()
        assert "new.ip" in text
        assert "old.ip" not in text
        assert "other.host" in text  # unrelated block preserved


# =========================================================================
# _read_pubkey
# =========================================================================


class TestReadPubkey:
    def test_reads_public_key(self, mgr, tmp_path, monkeypatch):
        key = tmp_path / "id_test"
        pub = key.with_suffix(".pub")
        pub.write_text("ssh-rsa AAAA...testkey user@host\n")
        monkeypatch.setattr(gvm, "SSH_KEY_PATH", key)
        assert mgr._read_pubkey() == "ssh-rsa AAAA...testkey user@host"


# =========================================================================
# _compute_usd_hr
# =========================================================================


class TestComputeUsdHr:
    def test_returns_none_when_family_unknown(self, mgr):
        machine = {"name": "zzz-standard-64", "vcpus": 64, "mem_gb": 256}
        assert mgr._compute_usd_hr(machine, {}) is None

    def test_returns_none_when_pricing_missing(self, mgr):
        machine = {"name": "c4d-standard-64", "vcpus": 64, "mem_gb": 256}
        assert mgr._compute_usd_hr(machine, {"c4d": {}}) is None

    def test_computes_rate_from_core_plus_ram(self, mgr):
        machine = {"name": "c4d-standard-64", "vcpus": 64, "mem_gb": 256}
        pricing = {"c4d": {"core": 0.05, "ram": 0.01}}
        # vcpus=64 × 0.05 + 256×1.024 × 0.01 = 3.2 + 2.6214 = 5.8214
        out = mgr._compute_usd_hr(machine, pricing)
        assert out == pytest.approx(3.2 + 256 * 1.024 * 0.01, rel=1e-3)

    def test_longer_prefix_precedence(self, mgr):
        # "c4d" should match before "c4" — pricing attached to c4d wins.
        machine = {"name": "c4d-standard-64-lssd", "vcpus": 64, "mem_gb": 256}
        pricing = {"c4d": {"core": 0.05, "ram": 0.01}, "c4": {"core": 99, "ram": 99}}
        out = mgr._compute_usd_hr(machine, pricing)
        assert out < 10  # nowhere near the c4 numbers


# =========================================================================
# _load_pricing_cache / _save_pricing_cache
# =========================================================================


class TestPricingCache:
    def test_load_returns_none_when_no_projects(self, mgr, monkeypatch):
        monkeypatch.setattr(mgr, "_all_project_cache_paths", lambda: [])
        assert mgr._load_pricing_cache() is None

    def test_load_ignores_expired_cache(self, mgr, tmp_path, monkeypatch):
        old = tmp_path / "cache.json"
        old.write_text(json.dumps({"date": "2020-01-01", "data": {"x": 1}}))
        monkeypatch.setattr(mgr, "_all_project_cache_paths", lambda: [old])
        # > 7 days old → skipped.
        assert mgr._load_pricing_cache() is None

    def test_load_returns_fresh_cache(self, mgr, tmp_path, monkeypatch):
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        fresh = tmp_path / "cache.json"
        fresh.write_text(json.dumps({"date": today, "data": {"x": 1}}))
        monkeypatch.setattr(mgr, "_all_project_cache_paths", lambda: [fresh])
        assert mgr._load_pricing_cache() == {"x": 1}

    def test_save_writes_to_all_project_paths(self, mgr, tmp_path, monkeypatch):
        p1 = tmp_path / "a" / "cache.json"
        p2 = tmp_path / "b" / "cache.json"
        monkeypatch.setattr(mgr, "_all_project_cache_paths", lambda: [p1, p2])
        mgr._save_pricing_cache({"c4": {"core": 1}}, [{"name": "m"}], 1.5)
        for p in (p1, p2):
            assert p.exists()
            payload = json.loads(p.read_text())
            assert payload["data"]["pricing"] == {"c4": {"core": 1}}


# =========================================================================
# _fetch_usd_to_aud
# =========================================================================


class TestFetchUsdToAud:
    def test_returns_fallback_on_error(self, mgr, monkeypatch):
        def _raise(*a, **kw):
            raise OSError("network down")

        monkeypatch.setattr(urllib.request, "urlopen", _raise)
        assert mgr._fetch_usd_to_aud() == 1.55

    def test_returns_parsed_rate(self, mgr, monkeypatch):
        class _Ctx:
            def __enter__(self_inner):
                class R:
                    @staticmethod
                    def read():
                        return json.dumps({"rates": {"AUD": 1.42}}).encode()

                return R()

            def __exit__(self_inner, *a):
                return False

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: _Ctx())
        assert mgr._fetch_usd_to_aud() == 1.42


# =========================================================================
# _gcloud_account / _gcloud_username
# =========================================================================


class TestGcloudAccount:
    def test_account_uses_capture(self, mgr, monkeypatch):
        monkeypatch.setattr(mgr, "_gcloud_capture",
                            lambda args: ("me@example.com", 0))
        assert mgr._gcloud_account() == "me@example.com"

    def test_username_is_account_prefix(self, mgr, monkeypatch):
        monkeypatch.setattr(mgr, "_gcloud_account", lambda: "alice@example.com")
        assert mgr._gcloud_username() == "alice"


# =========================================================================
# _get_vm_ip / _get_vm_status / list_vms — mock _gcloud_capture
# =========================================================================


class TestVmQueries:
    def test_get_vm_ip_returns_capture_stdout(self, mgr, monkeypatch):
        monkeypatch.setattr(mgr, "_gcloud_capture",
                            lambda args: ("203.0.113.7", 0))
        assert mgr._get_vm_ip("vm1") == "203.0.113.7"

    def test_get_vm_status_unknown_on_nonzero(self, mgr, monkeypatch):
        monkeypatch.setattr(mgr, "_gcloud_capture", lambda args: ("", 1))
        assert mgr._get_vm_status("vm1") == "UNKNOWN"

    def test_get_vm_status_returns_stdout_on_success(self, mgr, monkeypatch):
        monkeypatch.setattr(mgr, "_gcloud_capture",
                            lambda args: ("RUNNING", 0))
        assert mgr._get_vm_status("vm1") == "RUNNING"

    def test_list_vms_parses_csv_rows(self, mgr, monkeypatch):
        csv_out = (
            "archilume-vm-1,RUNNING,us-central1-a,1.1.1.1\n"
            "archilume-vm-2,TERMINATED,us-central1-b,\n"
        )
        monkeypatch.setattr(mgr, "_gcloud_capture", lambda args: (csv_out, 0))
        rows = mgr.list_vms()
        assert len(rows) == 2
        assert rows[0] == ("archilume-vm-1", "RUNNING", "us-central1-a", "1.1.1.1")
        assert rows[1][3] == ""  # empty IP preserved

    def test_list_vms_empty_when_no_matches(self, mgr, monkeypatch):
        monkeypatch.setattr(mgr, "_gcloud_capture", lambda args: ("", 0))
        assert mgr.list_vms() == []


# =========================================================================
# _pick_best_zone
# =========================================================================


class TestPickBestZone:
    def test_falls_back_on_query_failure(self, mgr, monkeypatch):
        monkeypatch.setattr(mgr, "_gcloud_capture", lambda args: ("", 1))
        assert mgr._pick_best_zone() == "us-central1-a"

    def test_prefers_us_zones(self, mgr, monkeypatch):
        zones = "europe-west1-b\nus-central1-a\nus-east1-b\nasia-east1-a\n"
        monkeypatch.setattr(mgr, "_gcloud_capture", lambda args: (zones, 0))
        assert mgr._pick_best_zone() == "us-central1-a"

    def test_picks_first_available_when_no_us_and_no_ping(
        self, mgr, monkeypatch
    ):
        zones = "europe-west1-b\nasia-east1-a\n"
        monkeypatch.setattr(mgr, "_gcloud_capture", lambda args: (zones, 0))
        # Ping returns non-zero → no best_zone chosen → fall back to first.
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **kw: type("R", (), {"returncode": 1, "stdout": ""})(),
        )
        assert mgr._pick_best_zone() == "europe-west1-b"


# =========================================================================
# _all_project_cache_paths
# =========================================================================


class TestAllProjectCachePaths:
    def test_returns_empty_when_projects_dir_missing(self, mgr, monkeypatch, tmp_path):
        # Pointing config.PROJECTS_DIR at a nonexistent path.
        from archilume import config
        monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "missing")
        assert mgr._all_project_cache_paths() == []

    def test_lists_archive_cache_per_project(self, mgr, monkeypatch, tmp_path):
        from archilume import config
        root = tmp_path / "projects"
        (root / "p1").mkdir(parents=True)
        (root / "p2").mkdir()
        monkeypatch.setattr(config, "PROJECTS_DIR", root)
        paths = mgr._all_project_cache_paths()
        names = {p.parent.parent.name for p in paths}
        assert names == {"p1", "p2"}
        assert all(p.name == gvm._PRICING_CACHE_FILENAME for p in paths)
