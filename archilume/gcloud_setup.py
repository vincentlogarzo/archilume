"""
Setup script to install Google Cloud CLI for Archilume.
This is automatically run after 'uv sync' completes.
"""

import platform
import shutil
import subprocess
import sys
from pathlib import Path


def check_gcloud():
    """Check if gcloud CLI is already installed."""
    return shutil.which("gcloud") is not None


def install_gcloud_windows():
    """Install Google Cloud CLI on Windows using the installer."""
    print("☁️  Installing Google Cloud CLI for Windows...")

    gcloud_url = "https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe"
    installer_path = Path.home() / "Downloads" / "GoogleCloudSDKInstaller.exe"

    try:
        # Download the installer
        print(f"  Downloading from {gcloud_url}...")
        import urllib.request
        urllib.request.urlretrieve(gcloud_url, str(installer_path))

        # Run the installer
        print("  Running installer (this may open a new window)...")
        subprocess.run([str(installer_path)], check=False)

        print("✅ Google Cloud SDK installer completed!")
        print("\n📋 Next steps:")
        print("  1. Close and reopen your terminal/PowerShell")
        print("  2. Run: gcloud init")
        print("  3. Run: gcloud auth login")
        print("  4. Run: gcloud config set project YOUR_PROJECT_ID")
        return True
    except Exception as e:
        print(f"❌ Failed to install: {e}")
        print("Manual installation: https://cloud.google.com/sdk/docs/install-gcloud-cli")
        return False


def install_gcloud_unix():
    """Install Google Cloud CLI on macOS/Linux."""
    print("☁️  Installing Google Cloud CLI...")

    try:
        install_script = "curl https://sdk.cloud.google.com | bash"
        result = subprocess.run(install_script, shell=True, check=False)

        if result.returncode == 0:
            print("✅ Google Cloud SDK installed successfully!")
            print("\n📋 Next steps:")
            print("  1. Restart your shell or run: exec -l $SHELL")
            print("  2. Run: gcloud init")
            print("  3. Run: gcloud auth login")
            print("  4. Run: gcloud config set project YOUR_PROJECT_ID")
            return True
        else:
            print("⚠️  Installation had issues")
            return False
    except Exception as e:
        print(f"❌ Failed to install: {e}")
        return False


def main():
    """Main setup function."""
    if check_gcloud():
        print("✅ Google Cloud CLI is already installed")
        # Verify it's accessible
        result = subprocess.run(["gcloud", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(result.stdout.split('\n')[0])
        return 0

    print("Google Cloud CLI not found. Installing...")
    print()

    system = platform.system()

    if system == "Windows":
        success = install_gcloud_windows()
    elif system in ("Darwin", "Linux"):
        success = install_gcloud_unix()
    else:
        print(f"Unsupported platform: {system}")
        print("Manual installation: https://cloud.google.com/sdk/docs/install-gcloud-cli")
        return 1

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
