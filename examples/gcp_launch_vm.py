"""
gcp_launch_vm.py — Archilume GCP VM Manager (entry point)

Usage:
    python examples/gcp_launch_vm.py
"""

from archilume.gcp_vm_manager import GCPVMManager

if __name__ == "__main__":
    GCPVMManager().run()
