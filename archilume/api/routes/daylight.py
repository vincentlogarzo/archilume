"""POST /workflows/daylight — submit an IESVE daylight analysis job."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from starlette.responses import JSONResponse

from archilume import config, smart_cleanup
from archilume.workflows import IESVEDaylightWorkflow
from archilume.api.jobs import job_manager
from archilume.api.models import DaylightJobRequest, JobSubmittedResponse

router = APIRouter()


def _resolve(base: Path, p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else base / p


def _run_daylight(req: DaylightJobRequest) -> None:
    """Execute the daylight workflow (runs in background thread)."""
    paths = config.get_project_paths(req.project)
    paths.create_dirs()

    octree_path = _resolve(paths.inputs_dir, req.octree_path)
    rendering_params = _resolve(paths.inputs_dir, req.rendering_params)
    iesve_room_data = _resolve(paths.inputs_dir, req.iesve_room_data)

    smart_cleanup(
        paths,
        resolution_changed=req.cleanup_resolution_changed,
        rendering_quality_changed=req.cleanup_rendering_quality_changed,
    )

    workflow = IESVEDaylightWorkflow()
    workflow.run(
        octree_path=octree_path,
        rendering_params=rendering_params,
        iesve_room_data=iesve_room_data,
        image_resolution=req.image_resolution,
        ffl_offset=req.ffl_offset,
        use_ambient_file=req.use_ambient_file,
        n_cpus=req.n_cpus,
        paths=paths,
    )


@router.post("/daylight", response_model=JobSubmittedResponse, status_code=202)
def submit_daylight(req: DaylightJobRequest):
    # Validate file existence before submitting
    paths = config.get_project_paths(req.project)
    errors = []
    for label, rel_path in [
        ("octree_path", req.octree_path),
        ("rendering_params", req.rendering_params),
        ("iesve_room_data", req.iesve_room_data),
    ]:
        resolved = _resolve(paths.inputs_dir, rel_path)
        if not resolved.exists():
            errors.append(f"{label}: not found at {resolved}")

    if errors:
        raise HTTPException(status_code=422, detail=errors)

    try:
        record = job_manager.submit(_run_daylight, args=(req,))
    except RuntimeError:
        return JSONResponse(
            status_code=429,
            content={"detail": "A job is already running. Wait for it to complete."},
        )

    return JobSubmittedResponse(job_id=record.job_id)
