"""
Archilume Example: IESVE Daylight Factor Analysis (via API, single-command)
=============================================================

Self-contained: starts the engine API server in a background thread,
submits the daylight job, streams log lines, then exits.

This exercises the same code path as the Docker engine container
(FastAPI + Pydantic + JobManager) without needing a separate terminal.

Usage:
    uv run python examples/workflow_daylight_iesve_api.py
"""

import threading
import time

import requests
import uvicorn

from archilume.api.app import app

ENGINE_HOST = "127.0.0.1"
ENGINE_PORT = 8100
ENGINE_URL = f"http://{ENGINE_HOST}:{ENGINE_PORT}"


def _start_server() -> uvicorn.Server:
    """Start the engine API in a background daemon thread; return when /health responds."""
    server = uvicorn.Server(uvicorn.Config(
        app=app, host=ENGINE_HOST, port=ENGINE_PORT, log_level="warning",
    ))
    threading.Thread(target=server.run, daemon=True).start()

    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            if requests.get(f"{ENGINE_URL}/health", timeout=1).status_code == 200:
                return server
        except requests.RequestException:
            pass
        time.sleep(0.2)
    raise RuntimeError("Engine server failed to start within 10s")


def run_daylight_analysis():
    _start_server()

    resp = requests.post(f"{ENGINE_URL}/workflows/daylight", json={
        "project":                          "527DP-gcloud-lowRes-GregW",
        "octree_path":                      "527DP.oct",
        "rendering_params":                 "high_GregW.rdp",
        "iesve_room_data":                  "aoi/iesve_room_data.csv",
        "image_resolution":                 1280,
        "ffl_offset":                       1.54,
        "use_ambient_file":                 True,
        "n_cpus":                           32,
        "cleanup_resolution_changed":       True,
        "cleanup_rendering_quality_changed": True,
    })

    if resp.status_code == 429:
        print("Engine busy — a job is already running.")
        return
    if resp.status_code == 422:
        print(f"Validation failed: {resp.json()}")
        return
    resp.raise_for_status()

    job_id = resp.json()["job_id"]
    print(f"Job submitted: {job_id}")

    seen_lines = 0
    while True:
        time.sleep(3)
        status = requests.get(f"{ENGINE_URL}/jobs/{job_id}").json()

        for line in status["log_lines"][seen_lines:]:
            print(line)
        seen_lines = len(status["log_lines"])

        if status["status"] == "done":
            print("\nJob complete.")
            return
        if status["status"] == "failed":
            print(f"\nJob failed: {status['error']}")
            return


if __name__ == "__main__":
    run_daylight_analysis()
