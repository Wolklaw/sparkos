#!/usr/bin/env bash
# Spark Shell: the panel, tray, notifications, launcher, wallpaper and on-screen display, and
# spark-session-run, which the Spark session (spark-wl-startup) runs it with. Source:
# files/spark-shell. Runs after packages.sh (gtk4-layer-shell).
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-shell"
test -f "$SRC/install.sh" || { echo "Spark Shell source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --no-test

test -x /usr/bin/spark-shell
test -x /usr/libexec/spark-session-run
test -f /usr/lib/systemd/user/spark-wl-workspace.target
test -f /usr/lib/spark-shell/launcher_logic.py
report=$(env -u DISPLAY -u WAYLAND_DISPLAY /usr/bin/spark-shell --self-test)
echo "$report"
grep -q "self-test ok" <<<"$report"
ls /usr/lib64/libgtk4-layer-shell.so.0 >/dev/null
