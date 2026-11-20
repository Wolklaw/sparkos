#!/usr/bin/bash
# Containerfile steps 5 and 8: run SparkOS's build scripts from files/scripts, in the order given
# (the recipe's "script" steps). Stops at the first one that fails, so a broken app never ships.
set -euo pipefail

dir=${CONFIG_DIRECTORY:-/tmp/files}/scripts
cd "$dir"
for script in "$@"; do
  test -f "$script" || { echo "files/scripts/$script not found"; exit 1; }
  echo "==================== $script ===================="
  bash "./$script"
  echo "==================== $script done ===================="
done
