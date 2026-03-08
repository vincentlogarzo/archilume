# Archilume: Docker-Based GCP Transition Plan

## 🎯 Objective

Transition from the current 10-minute script-based VM setup to a Docker-based "Pull & Play" architecture. This will reduce setup time to < 1 minute, ensure environment parity between local/remote, and optimize the use of high-speed local SSDs.

---

## 🏗️ Phase 1: Docker Image Engineering

**Goal:** Bake all heavy dependencies into a single, GPU-ready image.

### 1.1 Create the `Dockerfile`

- **Base Image:** `nvidia/cuda:12.4.1-devel-ubuntu22.04` (to support Accelerad/GPU).
- **Baked-in Tools:**
    - Radiance 6.1 (Linux binaries).
    - Accelerad (compiled from source).
    - Python 3.12 (via `uv`).
    - System deps: `libgl1`, `libtiff-tools`, `build-essential`.
- **Environment:** Pre-set `RAYPATH`, `PATH`, and `UV_LINK_MODE`.

### 1.2 Setup Google Artifact Registry

- Create a private repository: `australia-southeast1-docker.pkg.dev/<project>/archilume`.
- Authenticate local machine and VM to this registry.

---

## 🚀 Phase 2: Refactoring `GCPVMManager`

**Goal:** Shift the Python manager from "System Installer" to "Orchestrator."

### 2.1 The "Docker-on-SSD" Strategy

Modify `setup()` in `archilume/gcp_vm_manager.py`:

1.  **Format/Mount SSD:** (Keep existing logic).
2.  **Redirect Docker Storage:** 
    - Create `/mnt/disks/localssd/docker`.
    - Update `/etc/docker/daemon.json` to set `"data-root": "/mnt/disks/localssd/docker"`.
    - Restart Docker.
3.  **Auth & Pull:**
    - `gcloud auth configure-docker <region>-docker.pkg.dev`.
    - `docker pull <image-url>:latest`.

### 2.2 The Execution Command

Replace the "Cloning & Setup" step with a robust `docker run` template:

```bash
docker run --rm -it \
  --gpus all \
  -v /mnt/disks/localssd/workspace:/workspace \
  -w /workspace \
  <image-url>:latest \
  /bin/bash
```

---

## 📂 Phase 3: Mounting & Data Strategy

**Goal:** Ensure zero data loss and maximum performance.

- **Workspace Mount:** The entire `/mnt/disks/localssd/workspace` folder is mounted as a volume.
- **Persistent Code:** Use `git clone` on the SSD once, but run the Python interpreter from the Docker container. This allows editing code via VS Code Remote-SSH while using the container's environment.
- **Output Management:** All results written to `/workspace/outputs` on the SSD remain after the container exits.

---

## 🛠️ Phase 4: CI/CD Automation

**Goal:** One command to update the remote environment.

- Create a `build_and_push.sh` script:
    1. `docker build -t archilume-env .`
    2. `docker tag archilume-env <gcp-url>:latest`
    3. `docker push <gcp-url>:latest`

---

## 📈 Success Metrics

- **Setup Time:** Reduced from ~600s to <45s.
- **Stability:** Elimination of "failed to install Radiance" or "broken symlink" errors on the VM.
- **Performance:** GPU utilization verified via `nvidia-smi` inside the container.

---

## 📝 Future Notes for Execution

- Check the version of `libtiff` required by Radiance (currently symlinked in `setup.sh`).
- Ensure the Service Account attached to the VM has `Artifact Registry Reader` permissions.
- Consider a `docker-compose.yml` for more complex multi-container tasks (e.g., Dash dashboard + Simulation).
