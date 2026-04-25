"""Archilume Google Cloud VM CLI.

Usage:
    python examples/launch_google_cloud_vm.py setup [--project P] [--vm NAME] [--machine-type M] [--zone Z]
    python examples/launch_google_cloud_vm.py delete --vm NAME [--project P] [--zone Z]
    python examples/launch_google_cloud_vm.py tunnel [--vm NAME]
    python examples/launch_google_cloud_vm.py restart --vm NAME
    python examples/launch_google_cloud_vm.py list
"""

import argparse

from archilume.infra.gcp_vm_manager import (
    DEFAULT_MACHINE_TYPE,
    DEFAULT_ZONE,
    MACHINE_TYPES,
    GCPVMManager,
)


def main() -> None:
    parser = argparse.ArgumentParser(prog="launch_google_cloud_vm")
    parser.add_argument("--project", help="GCP project ID (defaults to `gcloud config get-value project`)")
    parser.add_argument("--archilume-project", help="Local archilume project name (display label)")
    parser.add_argument("--zone", default=DEFAULT_ZONE, help=f"GCP zone (default: {DEFAULT_ZONE})")
    sub = parser.add_subparsers(dest="action", required=True)

    p_setup = sub.add_parser("setup", help="Create a new COS+LSSD VM")
    p_setup.add_argument("--vm", help="VM name (default: archilume-vm-<timestamp>)")
    p_setup.add_argument("--machine-type", choices=MACHINE_TYPES, default=DEFAULT_MACHINE_TYPE)

    p_delete = sub.add_parser("delete", help="Delete a VM by name")
    p_delete.add_argument("--vm", required=True)

    p_tunnel = sub.add_parser("tunnel", help="SSH port-forward 8100 to engine")
    p_tunnel.add_argument("--vm", help="VM name (default: first RUNNING archilume VM)")

    p_restart = sub.add_parser("restart", help="Restart the engine container on a VM")
    p_restart.add_argument("--vm", required=True)

    sub.add_parser("list", help="List archilume-managed VMs")

    args = parser.parse_args()
    mgr = GCPVMManager(project_name=args.archilume_project, project=args.project, zone=args.zone)

    if args.action == "setup":
        mgr.setup(machine_type=args.machine_type, vm_name=args.vm)
    elif args.action == "delete":
        mgr.delete(args.vm)
    elif args.action == "tunnel":
        mgr.tunnel(args.vm)
    elif args.action == "restart":
        mgr.restart(args.vm)
    elif args.action == "list":
        for name, status, zone, ip in mgr.list_vms():
            print(f"  {name:40s} {status:12s} {zone:24s} {ip}")


if __name__ == "__main__":
    main()
