"""
Archilume Google Cloud Platform (GCP) Virtual Machine (VM) Manager (entry point)



Usage:
    python examples/gcp_launch_vm.py
"""

from archilume.gcp_vm_manager import GCPVMManager

if __name__ == "__main__":
    GCPVMManager().run()

# TODO: investigate pre-compiled docker image uploaded to the GCP registry that would remove the install steps for everything container in the docker. It would speed up the spinup of new VMs

#TODO: solve this Currently, this manager does not work on when in a devcontainer. As it must write ssh files that are used to connect to the VM from your local machine. 
