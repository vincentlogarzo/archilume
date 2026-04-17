"""Build and push Archilume Docker images to Docker Hub.

Usage:
    uv run examples/build_docker_images.py              # build + push both as :latest
    uv run examples/build_docker_images.py 0.1.0       # build + push both as :0.1.0 and :latest
    uv run examples/build_docker_images.py --no-push   # build only, skip push
    uv run examples/build_docker_images.py 0.1.0 app   # build + push app only
"""

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = "vlogarzo"

IMAGES = {
    "app": "archilume-app",
    "engine": "archilume-engine",
}


def run(cmd: list[str], label: str) -> bool:
    print(f"\n{'='*60}")
    print(f"{label}")
    print(f"  $ {' '.join(cmd)}")
    print(f"{'='*60}\n")
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        print(f"\nFAILED: {label}")
        return False
    print(f"\nSUCCESS: {label}")
    return True


def build(image: str) -> bool:
    cmd = ["docker", "build", "--target", image, "-t", image, "."]
    return run(cmd, f"Build: {image}")


def push(image: str, tag: str) -> bool:
    remote = f"{REGISTRY}/{image}:{tag}"
    if not run(["docker", "tag", image, remote], f"Tag: {image} → {remote}"):
        return False
    if not run(["docker", "push", remote], f"Push: {remote}"):
        return False
    # Also push as latest (skip if tag is already latest)
    if tag != "latest":
        remote_latest = f"{REGISTRY}/{image}:latest"
        if not run(["docker", "tag", image, remote_latest], f"Tag: {image} → {remote_latest}"):
            return False
        if not run(["docker", "push", remote_latest], f"Push: {remote_latest}"):
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Build and push Archilume Docker images.")
    parser.add_argument("tag", nargs="?", default="latest", help="Image tag (default: latest)")
    parser.add_argument(
        "images",
        nargs="*",
        choices=[*IMAGES.keys(), []],
        default=[],
        help="Which images to build (default: all). Options: app, engine",
    )
    parser.add_argument("--no-push", action="store_true", help="Build only, skip push to Docker Hub")
    args = parser.parse_args()

    selected = args.images if args.images else list(IMAGES.keys())

    # Build
    failed = []
    for key in selected:
        if not build(IMAGES[key]):
            failed.append(IMAGES[key])

    if failed:
        print(f"\nBuild failed: {', '.join(failed)}")
        sys.exit(1)

    # Push
    if not args.no_push:
        for key in selected:
            if not push(IMAGES[key], args.tag):
                failed.append(IMAGES[key])

        if failed:
            print(f"\nPush failed: {', '.join(failed)}")
            sys.exit(1)

    print(f"\n{'='*60}")
    built = [IMAGES[k] for k in selected]
    print(f"Done: {', '.join(built)} tagged {args.tag}")
    if not args.no_push:
        print(f"Pushed to {REGISTRY}/ as :{args.tag} and :latest")


if __name__ == "__main__":
    main()
