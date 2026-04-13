"""Pydantic request/response models for the archilume engine API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Workflow request models
# ---------------------------------------------------------------------------

class DaylightJobRequest(BaseModel):
    """Request body for POST /workflows/daylight."""

    project: str
    octree_path: str
    rendering_params: str
    iesve_room_data: str
    image_resolution: int = Field(default=2048, ge=128)
    ffl_offset: float = 0.0
    use_ambient_file: bool = True
    n_cpus: int | None = None
    cleanup_resolution_changed: bool = False
    cleanup_rendering_quality_changed: bool = False


class SunlightJobRequest(BaseModel):
    """Request body for POST /workflows/sunlight."""

    project: str
    building_latitude: float = Field(ge=-90, le=90)
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)
    start_hour: int = Field(ge=0, le=23)
    end_hour: int = Field(ge=0, le=23)
    timestep: int = Field(ge=1)
    ffl_offset: float
    grid_resolution: int = Field(ge=10, le=50)
    rendering_mode: Literal["cpu", "gpu"]
    rendering_quality: Literal[
        "draft", "stand", "prod", "final", "4k",
        "custom", "fast", "med", "high", "detailed",
    ]
    room_boundaries_csv: str
    obj_paths: list[str]
    animation_format: Literal["gif", "apng"] = "apng"

    @model_validator(mode="after")
    def _check_time_range(self) -> SunlightJobRequest:
        if self.start_hour >= self.end_hour:
            raise ValueError("end_hour must be greater than start_hour")
        return self


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class JobSubmittedResponse(BaseModel):
    job_id: str
    status: Literal["accepted"] = "accepted"


class JobResponse(BaseModel):
    job_id: str
    status: Literal["pending", "running", "done", "failed"]
    phase: str | None = None
    log_lines: list[str] = Field(default_factory=list)
    error: str | None = None
    result: dict | None = None
