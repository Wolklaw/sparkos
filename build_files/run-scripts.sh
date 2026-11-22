#!/usr/bin/bash
# Containerfile step 5: run SparkOS's build scripts from files/scripts, in the order given.
# Stops at the first one that fails, so a broken app never ships.
#
# An argument "a.sh|b.sh" runs a.sh on the Bazzite base and b.sh on the Fedora base
# (SPARKOS_BASE); "-" stands for nothing, so "-|fedora-gaming.sh" runs on Fedora only.
set -euo pipefail

base=${SPARKOS_BASE:-bazzite}
dir=${CONFIG_DIRECTORY:-/tmp/files}/scripts
cd "$dir"
for arg in "$@"; do
  script=$arg
  if [[ $arg == *"|"* ]]; then
    case "$base" in
      bazzite) script=${arg%%|*} ;;
      fedora) script=${arg##*|} ;;
      *) echo "unknown SPARKOS_BASE '$base' (bazzite or fedora)"; exit 1 ;;
    esac
  fi
  [ "$script" = - ] && continue
  test -f "$script" || { echo "files/scripts/$script not found"; exit 1; }
  echo "==================== $script ===================="
  bash "./$script"
  echo "==================== $script done ===================="
done
