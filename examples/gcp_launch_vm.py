"""
Archilume Google Cloud Platform (GCP) Virtual Machine (VM) Manager (entry point)

Usage:
    python examples/gcp_launch_vm.py
"""

from archilume.infra.gcp_vm_manager import GCPVMManager

if __name__ == "__main__":
    GCPVMManager().run()
