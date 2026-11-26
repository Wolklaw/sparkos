#!/bin/bash
# Boots the Spark shell on a headless Spark compositor (no real screen) and runs session_check.py
# against it. Needs spark-compositor, spark-wl-windows, PyGObject with Gtk 4 and
# gtk4-layer-shell: run it in the SparkOS image. Never on a desktop.
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
mkdir -p "$HOME" "$XDG_RUNTIME_DIR" "$XDG_CONFIG_HOME/spark" "$work/cfg"
chmod 700 "$XDG_RUNTIME_DIR"
for i in $(seq 1 "$outputs"); do
  echo "output HEADLESS-$i mode=1920x1080@60 scale=1 pos=$(( (i - 1) * 1920 )),0"
done > "$work/cfg/outputs.conf"
export SPARK_HEADLESS_OUTPUTS="$outputs" WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1
export SPARK_COMPOSITOR_CONFIG_DIR="$work/cfg"
export XDG_CURRENT_DESKTOP=sparkwl:Spark XDG_SESSION_TYPE=wayland
export GSK_RENDERER=cairo GDK_BACKEND=wayland SPARK_LANG=en SPARK_SHELL_FROM_SOURCE=1
unset DISPLAY WAYLAND_DISPLAY

cat > "$work/inside.sh" <<EOF
#!/bin/bash
coproc COMP { spark-compositor -d 2>"$work/compositor.log"; }
comp=\$COMP_PID
read -r -t 20 line <&"\${COMP[0]}" || line=
export WAYLAND_DISPLAY=\${line#WAYLAND_DISPLAY=}
python3 "$src/spark_shell.py" > "$work/shell.log" 2>&1 &
shell=\$!
python3 "$src/tests/session_check.py" --outputs "$outputs" --wayland-display "\$WAYLAND_DISPLAY" ${shot:+--screenshot "$shot"}
rc=\$?
kill \$shell \$comp 2>/dev/null
wait 2>/dev/null
echo "--- compositor log"
tail -n 30 "$work/compositor.log"
echo "--- shell log"
tail -n 60 "$work/shell.log"
exit \$rc
EOF
chmod +x "$work/inside.sh"
dbus-run-session -- "$work/inside.sh"
rc=$?
rm -rf "$work"
exit $rc
