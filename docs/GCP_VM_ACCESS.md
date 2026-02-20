# GCP VM Access Guide

This document explains how to access the shared company GCP VM for the Archilume project.

## VM Details

- **Hostname**: `<YOUR-VM-IP>`
- **VM Name**: `<YOUR-VM-INSTANCE-NAME>`
- **OS**: Debian GNU/Linux (kernel 6.12.63)
- **Purpose**: Shared development and rendering environment for Archilume project

## Prerequisites

1. GCP account with access to the project
2. SSH key pair (or create one following steps below)
3. VM access permissions (contact project admin to add your SSH key)

## Setup Instructions

### Step 1: Generate SSH Key (if you don't have one)

```bash
# Generate a new SSH key pair
ssh-keygen -t rsa -b 4096 -f ~/.ssh/google_cloud_vm_key -C "your.email@company.com"

# This creates two files:
# - ~/.ssh/google_cloud_vm_key (private key - keep this secret!)
# - ~/.ssh/google_cloud_vm_key.pub (public key - share this)
```

### Step 2: Request VM Access

Send your **public key** to the project administrator:

```bash
# Display your public key
cat ~/.ssh/google_cloud_vm_key.pub
```

**Option A: Admin adds via GCP Console**
1. Admin goes to GCP Console → Compute Engine → VM instances
2. Clicks the VM name → Edit
3. Scrolls to "SSH Keys" section → Add Item
4. Pastes your public key → Save


### Step 3: Configure Your Local SSH Config

Add this to your `~/.ssh/config` file:

```ssh
Host gcp-vm
    HostName <YOUR-VM-IP>
    User <your-username>
    IdentityFile ~/.ssh/google_cloud_vm_key
    StrictHostKeyChecking accept-new
```

Replace `<your-username>` with your GCP username (usually your email prefix or company username).

**Note for Windows users**: Windows OpenSSH doesn't support the `Include` directive properly. You must add the configuration directly to your `~/.ssh/config` file, not in a project-specific config file.

### Step 4: Test Connection

```bash
ssh gcp-vm
```

You should see:
```
Welcome to Debian GNU/Linux...
```

### Step 5: Format Local SSD, Install Docker and Git, Clone Repository

Once connected to the VM, set up the local SSD, install the required tools, and clone the Archilume repository:

#### 5.1: Format and Mount the Local SSD

```bash
# List attached disks to find the local SSD device
ls -l /dev/disk/by-id/google-*

# For local SSDs, the device is typically /dev/nvme0n1 or similar
# You can also check with:
lsblk

# Format the local SSD with ext4 filesystem
# Replace /dev/nvme0n1 with your actual device name
sudo mkfs.ext4 -m 0 -E lazy_itable_init=0,lazy_journal_init=0,discard /dev/nvme0n1

# Create mount point directory
sudo mkdir -p /mnt/disks/localssd

# Mount the local SSD
sudo mount -o discard,defaults /dev/nvme0n1 /mnt/disks/localssd

# Set permissions so all users can read/write
sudo chmod a+w /mnt/disks/localssd

# Create a workspace directory for the project
mkdir -p /mnt/disks/localssd/workspace
```

#### 5.2: Enable Automatic Mounting on Reboot (Recommended)

```bash
# Get the UUID of the local SSD
sudo blkid /dev/nvme0n1

# Add entry to /etc/fstab for automatic mounting
# Replace UUID_VALUE with the actual UUID from the blkid command
echo "UUID=UUID_VALUE /mnt/disks/localssd ext4 discard,nofail 0 2" | sudo tee -a /etc/fstab

# Verify fstab entry is correct (this will fail safely if there's an error)
sudo mount -a
```

**Note**: Local SSDs are ephemeral storage - data is lost if the VM is stopped or deleted. Always back up important work to persistent storage or git.

#### 5.3: Install Docker and Git

```bash
# Update package manager
sudo apt-get update

# Install Git
sudo apt-get install -y git

# Install Docker
sudo apt-get install -y docker.io

# Add your user to the docker group (so you don't need sudo for docker)
sudo usermod -aG docker $USER

# Activate the new group membership
newgrp docker
```

#### 5.4: Clone Repository to Local SSD

```bash
# Navigate to the local SSD workspace
cd /mnt/disks/localssd/workspace

# Clone the Archilume repository
git clone https://github.com/vincentlogarzo/archilume.git
cd archilume

# Run the automated setup script
bash .devcontainer/setup.sh

# Source bashrc to update PATH
source ~/.bashrc

# Optional: Create a symlink in home directory for convenience
ln -s /mnt/disks/localssd/workspace/archilume ~/archilume
```

This will automatically install:

- **Radiance 6.1.5** (for rendering)
- **Accelerad** (GPU acceleration for rendering)
- **uv package manager** (Python dependency manager)
- **Python dependencies** (via `uv sync`)
- **System dependencies** (OpenGL, Radiance libraries)

## Troubleshooting

### Connection timeout
- Check that your IP is allowed in GCP firewall rules
- Verify the VM is running in GCP Console

### Permission denied (publickey)
- Verify your public key was added to the VM
- Check that your username matches the one in the public key
- Ensure you're using the correct private key file

### Host key verification failed
- This happens when the VM was recreated with a new host key
- Remove old key: `ssh-keygen -R <YOUR-VM-IP>`
- Or set `StrictHostKeyChecking accept-new` in your config

## Alternative: Using gcloud SSH

If you have `gcloud` CLI installed and configured:

```bash
# Connect without manual SSH configuration
gcloud compute ssh <YOUR-VM-INSTANCE-NAME> --zone <vm-zone>
```

This method:
- Automatically handles SSH key management
- Uses your GCP IAM permissions
- No manual SSH config needed

## Security Notes

- **Never commit private keys to git** (`.ssh/` is in `.gitignore`)
- Each team member should have their own SSH key pair
- Rotate keys periodically
- Remove SSH keys for team members who leave the project

## Support

For access issues, contact:
- Project Admin: [Add contact info]
- GCP Project: [Add project ID]
