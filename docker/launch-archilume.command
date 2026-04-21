#!/usr/bin/env bash
# Archilume launcher (macOS Finder double-click entry point).
#
# Finder treats .command files as double-clickable shell scripts opened in
# Terminal.app. This wrapper resolves its own directory and delegates to
# launch-archilume.sh so there is exactly one script to maintain.

set -euo pipefail
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd -P )"
exec "${SCRIPT_DIR}/launch-archilume.sh" "$@"
