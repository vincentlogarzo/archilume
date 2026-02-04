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

**Option B: Admin adds via gcloud CLI**
```bash
gcloud compute instances add-metadata <YOUR-VM-INSTANCE-NAME> \
  --metadata-from-file ssh-keys=path/to/your/public-key.pub \
  --zone <vm-zone>
```

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
