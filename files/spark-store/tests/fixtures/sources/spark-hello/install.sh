#!/usr/bin/env bash
# A tiny optional Spark app for the tests: installs for one user, like the real ones.
set -euo pipefail
[ "${1:-}" = "--user" ] || { echo "only --user" >&2; exit 2; }
LIB=$HOME/.local/lib/spark-hello
DESK=${XDG_DATA_HOME:-$HOME/.local/share}/applications/dev.wolklaw.SparkHello.desktop
if [ "${2:-}" = "--uninstall" ]; then
  rm -f "$HOME/.local/bin/spark-hello" "$DESK"
  rm -rf "$LIB"
  echo "removed"
  exit 0
fi
[ -n "${SPARK_HELLO_FAIL:-}" ] && { echo "error: spark-hello failed on purpose" >&2; exit 1; }
mkdir -p "$LIB" "$HOME/.local/bin" "$(dirname "$DESK")"
printf '#!/bin/sh\necho hello\n' > "$HOME/.local/bin/spark-hello"
chmod +x "$HOME/.local/bin/spark-hello"
printf '[Desktop Entry]\nType=Application\nName=Spark Hello\nExec=spark-hello\n' > "$DESK"
printf '%s\n' "$HOME/.local/bin/spark-hello" "$DESK" > "$LIB/installed-files"
echo "installed 100%"
