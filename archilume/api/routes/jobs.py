"""Job status endpoints."""

from fastapi import APIRouter, HTTPException

from archilume.api.jobs import job_manager
from archilume.api.models import JobResponse

router = APIRouter()


@router.get("/jobs", response_model=list[JobResponse])
def list_jobs():
    return [
        JobResponse(
            job_id=j.job_id,
            status=j.status,
            phase=j.phase,
            log_lines=j.log_lines,
            error=j.error,
            result=j.result,
        )
        for j in job_manager.list_all()
    ]


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str):
    record = job_manager.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(
        job_id=record.job_id,
        status=record.status,
        phase=record.phase,
        log_lines=record.log_lines,
        error=record.error,
        result=record.result,
    )
