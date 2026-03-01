"""
gcp_launch_vm.py — Archilume GCP VM Manager (entry point)

Usage:
    python examples/gcp_launch_vm.py
"""

from archilume.gcp_vm_manager import GCPVMManager

if __name__ == "__main__":
    GCPVMManager().run()

    # TODO: add in clock speed, add in look up of all vm machines types and filter down to ons taht have lssd and at least 64 vCPUs. Users will only want these ones. 
    





