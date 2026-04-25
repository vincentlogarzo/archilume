"""Zip a project's ``logs/`` folder for sharing.

Run after experiencing an issue in the archilume_app to package every debug
artefact (rotating log + trace + archive) into a single zip the user can
attach to a bug report.

Usage:

    python -m archilume_app.scripts.share_debug_bundle <project_dir>

If ``<project_dir>`` is omitted, falls back to the user-profile location at
``~/.archilume/logs/`` so pre-project sessions can still be shared.

The output zip is written next to the logs folder as
``logs-<timestamp>.zip`` and printed to stdout. Cross-platform (Windows +
Linux + macOS) — uses ``shutil.make_archive``.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path


def bundle(logs_dir: Path) -> Path:
    if not logs_dir.is_dir():
        raise SystemExit(f"logs folder not found: {logs_dir}")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = logs_dir.parent / f"logs-{stamp}"
    archive_path = Path(shutil.make_archive(str(base), "zip", root_dir=logs_dir))
    return archive_path


def resolve_logs_dir(project_dir: Path | None) -> Path:
    if project_dir is not None:
        return project_dir / "logs"
    return Path.home() / ".archilume" / "logs"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Zip a project's logs/ folder for sharing.")
    parser.add_argument("project_dir", nargs="?", type=Path,
                        help="Project directory (omit to use ~/.archilume/logs/)")
    args = parser.parse_args(argv)
    logs = resolve_logs_dir(args.project_dir)
    out = bundle(logs)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
