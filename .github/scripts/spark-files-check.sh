#!/usr/bin/env bash
# Boot test, inside the signed-in Plasma session: Spark Files is the file manager.
#   - folders (inode/directory) open in Spark Files
#   - "Show in folder" (org.freedesktop.FileManager1.ShowItems, what Soot, FreeSuite, KDE's
#     notifications and most other apps call) starts Spark Files through D-Bus and shows the
#     file's folder with the file selected
#   - xdg-open on a folder reaches the same Spark Files (one process per session)
# Run as the session's user over SSH; it borrows plasmashell's environment.
set -euo pipefail

pid=$(pgrep -u "$(id -u)" -x plasmashell | head -1)
[ -n "$pid" ] || { echo "no plasmashell for $(id -un)"; exit 1; }
while IFS= read -r -d '' kv; do
  case "$kv" in
    DBUS_SESSION_BUS_ADDRESS=*|XDG_RUNTIME_DIR=*|WAYLAND_DISPLAY=*|DISPLAY=*|XDG_CURRENT_DESKTOP=*|LANG=*|XDG_DATA_DIRS=*)
      export "${kv?}" ;;
  esac
done < "/proc/$pid/environ"
echo "session: WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-} DISPLAY=${DISPLAY:-} LANG=${LANG:-}"

LOG=${XDG_STATE_HOME:-$HOME/.local/state}/spark-files/spark-files.log
wait_log() {   # $1: text to find in the log, $2: seconds
  for _ in $(seq 1 "$2"); do
    grep -qF -- "$1" "$LOG" 2>/dev/null && return 0
    sleep 1
  done
  echo "not in the log after $2 s: $1"
  tail -20 "$LOG" 2>/dev/null || echo "(no log at $LOG)"
  return 1
}

pkill -u "$(id -u)" -f 'spark_files.py' 2>/dev/null || true
sleep 1

echo "== default for folders"
default=$(xdg-mime query default inode/directory)
echo "inode/directory -> $default"
[ "$default" = dev.wolklaw.SparkFiles.desktop ] || { echo "folders don't open in Spark Files"; exit 1; }

echo "== Show in folder (FileManager1.ShowItems, D-Bus activation)"
gdbus call --session --dest org.freedesktop.FileManager1 --object-path /org/freedesktop/FileManager1 \
  --method org.freedesktop.FileManager1.ShowItems "['file:///etc/os-release']" "" >/dev/null
wait_log "showing /etc with /etc/os-release selected" 30
owner=$(gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
  --method org.freedesktop.DBus.GetConnectionUnixProcessID org.freedesktop.FileManager1 | sed -E 's/^\(uint32 ([0-9]+),\)$/\1/')
cmd=$(tr '\0' ' ' < "/proc/$owner/cmdline")
echo "org.freedesktop.FileManager1 is pid $owner: $cmd"
case "$cmd" in *spark_files.py*) ;; *) echo "FileManager1 isn't Spark Files"; exit 1 ;; esac

echo "== xdg-open on a folder"
xdg-open /usr/share/icons
wait_log "asked to open: /usr/share/icons" 30
count=$(pgrep -u "$(id -u)" -f -c 'spark_files.py' || true)
echo "Spark Files processes: $count"
[ "$count" = 1 ] || { echo "expected one Spark Files process, found $count"; exit 1; }

echo "== Dolphin out of the way"
grep -q '^NoDisplay=true' /usr/share/applications/org.kde.dolphin.desktop && echo "Dolphin hidden from the menu"
if grep -lx 'Name=org.freedesktop.FileManager1' /usr/share/dbus-1/services/*.service | grep -v SparkFiles; then
  echo "another FileManager1 provider is still there"; exit 1
fi

pkill -u "$(id -u)" -f 'spark_files.py' 2>/dev/null || true
echo "Spark Files is the file manager"
