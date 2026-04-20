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

    obj_paths = [_resolve_input(paths.inputs_dir, p) for p in req.obj_paths]

    workflow = SunlightAccessWorkflow()
    workflow.run(
        building_latitude=req.building_latitude,
        month=req.month,
        day=req.day,
        start_hour=req.start_hour,
        end_hour=req.end_hour,
        timestep_min=req.timestep_min,
        ffl_offset_mm=req.ffl_offset_mm,
        grid_resolution_mm=req.grid_resolution_mm,
        aoi_inputs_dir=paths.aoi_inputs_dir,
        obj_paths=obj_paths,
        project=req.project,
    )


@router.post("/sunlight", response_model=JobSubmittedResponse, status_code=202)
def submit_sunlight(req: SunlightJobRequest):
    paths = config.get_project_paths(req.project)
    errors = []

    if not paths.aoi_inputs_dir.exists():
        errors.append(f"aoi_inputs_dir: not found at {paths.aoi_inputs_dir}")

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
