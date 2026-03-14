"""
To run:
    uv run archilume
    uv run archilume --debug
    uv run archilume --project my_project
"""

import argparse

from archilume.apps.hdr_aoi_editor_matplotlib import launch


def main():
    parser = argparse.ArgumentParser(description="Launch the Archilume HDR AOI Editor")
    parser.add_argument("--debug", action="store_true", help="Launch in debug mode")
    parser.add_argument("--project", type=str, default=None, help="Project name to open on startup")
    args = parser.parse_args()

    launch(project=args.project, debug=args.debug)


if __name__ == "__main__":
    main()