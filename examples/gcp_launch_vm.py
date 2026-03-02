"""
gcp_launch_vm.py — Archilume GCP VM Manager (entry point)

Usage:
    python examples/gcp_launch_vm.py
"""

from archilume.gcp_vm_manager import GCPVMManager

if __name__ == "__main__":
    GCPVMManager().run()
    

#TODO: file transfer speed is a huge issue, how can this be done fast, uploads and fast downloads. There must be a way. Might be fast if it zips the folder uploads as one and then unzips on the other side. Sameas downloading, zips on one side and then downloads zip directly to archive dir. 



