"""Tests for the ``/overlay_pdf/{project}/{filename:path}`` FastAPI route.

Replaces the prior ``/overlay_cache/`` PNG-cache route; pdf.js fetches the
raw PDF from this endpoint via XHR. The route lives on the FastAPI sub-app
that Reflex mounts via ``api_transformer`` and is exercised here in
isolation by binding it to a ``TestClient``.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_route(monkeypatch, tmp_path: Path):
    """Build a fresh FastAPI app and mount only the overlay-pdf route on it.

    ``archilume_app.archilume_app.archilume_app`` constructs a Reflex app at
    import time (which is heavy and assumes a real frontend tree). Pulling
    just the route handler off the module-level ``_overlay_api`` keeps the
    test focused on routing + path-traversal behaviour.
    """
    from archilume.config import get_project_paths

    # Redirect ``get_project_paths`` to a tmp project layout. The route
    # imports the symbol at call time, so monkeypatching the module attribute
    # is sufficient.
    project_root = tmp_path / "projects"
    project_root.mkdir()

    def _fake_get_project_paths(project: str):
        # Reuse the real dataclass via the actual implementation, but rooted
        # under tmp_path. Easiest: build a tiny stand-in.
        class _Paths:
            def __init__(self, name: str):
                self.project_dir = project_root / name
                self.inputs_dir = self.project_dir / "inputs"
                self.plans_dir = self.inputs_dir / "plans"
                self.image_dir = self.project_dir / "outputs" / "image"

        if not project:
            raise ValueError("empty project name")
        return _Paths(project)

    import archilume.config as _cfg
    monkeypatch.setattr(_cfg, "get_project_paths", _fake_get_project_paths)
    # The archilume_app module imports the symbol at module top — reload its
    # bound reference too.
    from archilume.apps.archilume_app.archilume_app import archilume_app as _app_mod
    monkeypatch.setattr(_app_mod, "get_project_paths", _fake_get_project_paths)

    client = TestClient(_app_mod._overlay_api)
    return client, project_root, _fake_get_project_paths


def _write_pdf(path: Path, pages: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    doc.save(str(path))
    doc.close()


class TestOverlayPdfEndpoint:
    def test_serves_pdf_bytes(self, app_with_route):
        client, project_root, paths_fn = app_with_route
        paths = paths_fn("demo")
        plans = paths.plans_dir
        _write_pdf(plans / "floor.pdf")

        resp = client.get("/overlay_pdf/demo/plans/floor.pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        # PDF magic bytes — guards against a stub returning empty content.
        assert resp.content.startswith(b"%PDF-")
        assert "max-age=86400" in resp.headers.get("cache-control", "")

    def test_404_on_missing_file(self, app_with_route):
        client, _, paths_fn = app_with_route
        paths_fn("demo").plans_dir.mkdir(parents=True)
        resp = client.get("/overlay_pdf/demo/plans/absent.pdf")
        assert resp.status_code == 404

    def test_404_on_unknown_project(self, app_with_route):
        client, _, _ = app_with_route
        # The fake get_project_paths happily fabricates a Paths object for
        # any name — but the file doesn't exist on disk, so 404.
        resp = client.get("/overlay_pdf/never-created/plans/x.pdf")
        assert resp.status_code == 404

    def test_403_on_path_traversal(self, app_with_route):
        client, project_root, paths_fn = app_with_route
        # Create a sibling file outside ``inputs/`` and try to escape into it.
        outside = project_root / "demo" / "secrets.pdf"
        _write_pdf(outside)
        paths_fn("demo").plans_dir.mkdir(parents=True, exist_ok=True)
        resp = client.get("/overlay_pdf/demo/..%2Fsecrets.pdf")
        # FastAPI normalises the path before our handler sees it; either
        # 403 (caught by relative_to check) or 404 (resolved out-of-tree
        # never exists) are acceptable defences in depth — both prove the
        # file is not exfiltrated.
        assert resp.status_code in (403, 404)

    def test_rejects_non_pdf_files(self, app_with_route):
        client, _, paths_fn = app_with_route
        paths = paths_fn("demo")
        plans = paths.plans_dir
        plans.mkdir(parents=True)
        (plans / "rogue.txt").write_text("not a pdf")
        resp = client.get("/overlay_pdf/demo/plans/rogue.txt")
        assert resp.status_code == 404
