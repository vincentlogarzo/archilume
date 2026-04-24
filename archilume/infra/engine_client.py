"""
engine_client.py — HTTP client for the archilume-engine FastAPI layer.

Opens an SSH tunnel to a remote VM (or points at a local engine), submits
workflow jobs, and polls for completion. Independent of gcloud / GCP — can
be used against any VM reachable by SSH alias, or against localhost.

Typical usage:

    from archilume.infra.engine_client import engine_tunnel, submit_job, poll_job

    with engine_tunnel("gcp-vm") as base_url:
        job_id = submit_job(base_url, "daylight", {...})
        result = poll_job(base_url, job_id)
"""

import json
import subprocess
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from typing import Iterator

ENGINE_PORT = 8100
_TUNNEL_WAIT_S = 30
_POLL_INTERVAL_S = 5
_TERMINAL_STATUSES = {"done", "succeeded", "failed", "error", "cancelled"}


@contextmanager
def engine_tunnel(host_alias: str = "gcp-vm", port: int = ENGINE_PORT) -> Iterator[str]:
    """Open `ssh -N -L port:localhost:port host_alias`; yield base URL.

    Tunnel is torn down when the context exits.
    Raises RuntimeError if the tunnel does not accept TCP within _TUNNEL_WAIT_S.
    """
    proc = subprocess.Popen(
        ["ssh", "-N", "-L", f"{port}:localhost:{port}", host_alias],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    base_url = f"http://localhost:{port}"
    try:
        for _ in range(_TUNNEL_WAIT_S):
            if proc.poll() is not None:
                err = proc.stderr.read().decode() if proc.stderr else ""
                raise RuntimeError(f"SSH tunnel exited early: {err}")
            try:
                with urllib.request.urlopen(f"{base_url}/health", timeout=1):
                    break
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                time.sleep(1)
        else:
            raise RuntimeError(f"Engine tunnel to {host_alias}:{port} did not become ready")
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _post_json(url: str, payload: dict, timeout: int = 30) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _get_json(url: str, timeout: int = 10) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def submit_job(base_url: str, workflow: str, payload: dict) -> str:
    """POST a job payload; return the job_id."""
    if workflow not in ("daylight", "sunlight"):
        raise ValueError(f"Unknown workflow: {workflow}")
    response = _post_json(f"{base_url}/workflows/{workflow}", payload)
    job_id = response.get("job_id")
    if not job_id:
        raise RuntimeError(f"Engine did not return job_id: {response}")
    return job_id


def poll_job(
    base_url: str,
    job_id: str,
    interval: int = _POLL_INTERVAL_S,
    timeout_s: int = 3600,
) -> dict:
    """Poll GET /jobs/{id} until status is terminal. Returns final record."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        record = _get_json(f"{base_url}/jobs/{job_id}")
        status = str(record.get("status", "")).lower()
        if status in _TERMINAL_STATUSES:
            return record
        time.sleep(interval)
    raise TimeoutError(f"Job {job_id} did not finish within {timeout_s}s")


def health(base_url: str) -> bool:
    """Return True if the engine's /health endpoint responds 200."""
    try:
        _get_json(f"{base_url}/health", timeout=5)
        return True
    except Exception:
        return False
