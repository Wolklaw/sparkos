#!/bin/sh
# Boots the Spark session on a virtual KWin (no real screen) and runs session_check.py against
# it. Needs kwin_wayland, PyGObject with Gtk 4 and gtk4-layer-shell: run it in the SparkOS
# image or any Fedora with those. In a container add --cap-add=SYS_NICE (kwin_wayland carries a
# file capability).
#
#   tests/headless.sh [outputs] [screenshot-dir]
set -u
outputs="${1:-1}"
shot="${2:-}"
src=$(cd "$(dirname "$0")/.." && pwd)

work=$(mktemp -d)
export HOME="$work/home"
export XDG_RUNTIME_DIR="$work/run"
export XDG_CONFIG_HOME="$HOME/.config" XDG_STATE_HOME="$HOME/.local/state"
export XDG_DATA_HOME="$HOME/.local/share" XDG_CACHE_HOME="$HOME/.cache"
mkdir -p "$HOME" "$XDG_RUNTIME_DIR" "$XDG_CONFIG_HOME/spark"
chmod 700 "$XDG_RUNTIME_DIR"
export KWIN_COMPOSE=Q GSK_RENDERER=cairo KWIN_SCREENSHOT_NO_PERMISSION_CHECKS=1
export SPARK_SESSION_VIRTUAL=1 SPARK_SESSION_OUTPUTS="$outputs" SPARK_SESSION_NO_SYSTEMD=1
export SPARK_SESSION_SOCKET=wayland-spark SPARK_LANG=en
export SPARK_SHELL_FROM_SOURCE=1
unset DISPLAY WAYLAND_DISPLAY

cat > "$work/inside.sh" <<EOF
#!/bin/sh
"$src/session/spark-session" > "$work/session.log" 2>&1 &
session=\$!
python3 "$src/tests/session_check.py" --outputs "$outputs" ${shot:+--screenshot "$shot"}
rc=\$?
kill \$session 2>/dev/null
wait \$session 2>/dev/null
echo "--- session log"
tail -n 60 "$work/session.log"
exit \$rc
EOF
chmod +x "$work/inside.sh"
dbus-run-session -- "$work/inside.sh"
rc=$?
rm -rf "$work"
exit $rc
