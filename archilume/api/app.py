"""FastAPI application for the archilume engine API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from archilume.api.routes import daylight, sunlight, jobs, system

app = FastAPI(title="Archilume Engine", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(daylight.router, prefix="/workflows", tags=["workflows"])
app.include_router(sunlight.router, prefix="/workflows", tags=["workflows"])
app.include_router(jobs.router, tags=["jobs"])
app.include_router(system.router, tags=["system"])


@app.get("/health")
def health():
    return {"status": "ok"}
