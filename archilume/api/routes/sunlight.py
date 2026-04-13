"""POST /workflows/sunlight — submit a sunlight access analysis job."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from starlette.responses import JSONResponse

from archilume import config
from archilume.workflows import SunlightAccessWorkflow
from archilume.api.jobs import job_manager
from archilume.api.models import SunlightJobRequest, JobSubmittedResponse

router = APIRouter()


def _resolve_input(base: Path, p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else base / p


def _run_sunlight(req: SunlightJobRequest) -> None:
    """Execute the sunlight workflow (runs in background thread)."""
    paths = config.get_project_paths(req.project)
    paths.create_dirs()

    room_csv = _resolve_input(paths.aoi_inputs_dir, req.room_boundaries_csv)
    obj_paths = [_resolve_input(paths.inputs_dir, p) for p in req.obj_paths]

    workflow = SunlightAccessWorkflow()
    workflow.run(
        building_latitude=req.building_latitude,
        month=req.month,
        day=req.day,
        start_hour=req.start_hour,
        end_hour=req.end_hour,
        timestep=req.timestep,
        ffl_offset=req.ffl_offset,
        grid_resolution=req.grid_resolution,
        rendering_mode=req.rendering_mode,
        rendering_quality=req.rendering_quality,
        room_boundaries_csv=room_csv,
        obj_paths=obj_paths,
        animation_format=req.animation_format,
        paths=paths,
    )


@router.post("/sunlight", response_model=JobSubmittedResponse, status_code=202)
def submit_sunlight(req: SunlightJobRequest):
    paths = config.get_project_paths(req.project)
    errors = []

    room_csv = _resolve_input(paths.aoi_inputs_dir, req.room_boundaries_csv)
    if not room_csv.exists():
        errors.append(f"room_boundaries_csv: not found at {room_csv}")

    for i, obj_rel in enumerate(req.obj_paths):
        obj = _resolve_input(paths.inputs_dir, obj_rel)
        if not obj.exists():
            errors.append(f"obj_paths[{i}]: not found at {obj}")
        elif not obj.with_suffix(".mtl").exists():
            errors.append(f"obj_paths[{i}]: missing .mtl file for {obj}")

    if not req.obj_paths:
        errors.append("obj_paths: list is empty")

    if errors:
        raise HTTPException(status_code=422, detail=errors)

    try:
        record = job_manager.submit(_run_sunlight, args=(req,))
    except RuntimeError:
        return JSONResponse(
            status_code=429,
            content={"detail": "A job is already running. Wait for it to complete."},
        )

    return JobSubmittedResponse(job_id=record.job_id)
