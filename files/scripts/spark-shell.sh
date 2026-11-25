#!/usr/bin/env bash
# Spark Shell and the Spark login session (the Replacing KDE project, stage 3): the panel, tray,
# notifications, launcher, wallpaper and on-screen display, and /usr/share/wayland-sessions/spark.desktop.
# Plasma stays the default session. Source: files/spark-shell. Runs after spark-launcher.sh
# (the shell shares its search code) and after packages.sh (gtk4-layer-shell).
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-shell"
test -f "$SRC/install.sh" || { echo "Spark Shell source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --no-test

test -x /usr/bin/spark-shell
test -x /usr/bin/spark-session
test -x /usr/libexec/spark-session-run
test -f /usr/share/wayland-sessions/spark.desktop
test -f /usr/lib/systemd/user/spark-workspace.target
test -f /usr/lib/systemd/user/spark-wl-workspace.target
test -f /usr/lib/spark-shell/launcher_logic.py
# the default session must still be Plasma
if [ -f /usr/share/wayland-sessions/plasma.desktop ]; then
  test ! -e /etc/sddm.conf.d/spark-session.conf
fi
report=$(env -u DISPLAY -u WAYLAND_DISPLAY /usr/bin/spark-shell --self-test)
echo "$report"
grep -q "self-test ok" <<<"$report"
ls /usr/lib64/libgtk4-layer-shell.so.0 >/dev/null
