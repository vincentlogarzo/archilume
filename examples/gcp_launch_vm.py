"""
gcp_launch_vm.py — Archilume GCP VM Manager (entry point)

Usage:
    python examples/gcp_launch_vm.py
"""

from archilume.gcp_vm_manager import GCPVMManager

if __name__ == "__main__":
    GCPVMManager().run()
    

#TODO: file transfer speed is a huge issue, how can this be done fast, uploads and fast downloads. There must be a way. 



