"""Entry point for the archilume engine API server.

Used as the Docker container CMD:
    CMD ["python", "-m", "archilume.api.run"]

Endpoints:
    GET  /health                 → health check
    POST /workflows/daylight     → submit IESVE daylight job
    POST /workflows/sunlight     → submit sunlight access job
    GET  /jobs                   → list all jobs
    GET  /jobs/{job_id}          → poll job status
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("archilume.api.app:app", host="0.0.0.0", port=8100)
