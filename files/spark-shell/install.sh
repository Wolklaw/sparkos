#!/usr/bin/env bash
# Install the Spark session: Spark Shell (panel, tray, notifications, launcher, wallpaper, OSD)
# and the "Spark" entry on the login screen. Plasma stays the default session.
#
#   bash install.sh [--no-test]            system-wide (the image build), root
#   bash install.sh --uninstall            remove the system-wide install, root
#   bash install.sh --user                 just you: the shell under ~/.local, no login entry
#   bash install.sh --user --uninstall
#   bash install.sh --self-test            check that the modules load; no display needed
#   bash install.sh --stage DIR            copy the system layout under DIR (tests, packaging)
#
# --user does not touch a running Plasma session; run ~/.local/bin/spark-shell from a Spark
# session (the login entry needs the system install, because the display manager reads
# /usr/share/wayland-sessions).
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
TEST=1; USER_MODE=0; UNINSTALL=0; SELF_TEST=0; STAGE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --user) USER_MODE=1 ;;
    --uninstall) UNINSTALL=1 ;;
    --no-test) TEST=0 ;;
    --deps) ;;
    --self-test) SELF_TEST=1 ;;
    --stage) STAGE="${2:?--stage needs a directory}"; shift ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

if [ "$SELF_TEST" = 1 ]; then
  env -u DISPLAY -u WAYLAND_DISPLAY python3 "$here/spark_shell.py" --self-test
  exit $?
fi

if [ "$USER_MODE" = 1 ]; then
  lib="${XDG_DATA_HOME:-$HOME/.local/share}/spark-shell"
  bin="$HOME/.local/bin"
  libexec="$lib/session"
  units=""; sessions=""
else
  lib="$STAGE/usr/lib/spark-shell"; bin="$STAGE/usr/bin"; libexec="$STAGE/usr/libexec"
  units="$STAGE/usr/lib/systemd/user"; sessions="$STAGE/usr/share/wayland-sessions"
fi

if [ "$UNINSTALL" = 1 ]; then
  if [ "$USER_MODE" = 1 ]; then
    rm -rf "$lib" "$bin/spark-shell"
  else
    rm -rf "$lib" "$bin/spark-shell" "$bin/spark-session" "$libexec/spark-session-run" \
           "$libexec/spark-session-polkit" "$units/spark-workspace.target" "$units/spark-wl-workspace.target" \
           "$units/spark-polkit-agent.service" "$units/spark-xembed.service" "$sessions/spark.desktop"
  fi
  echo "Spark Shell removed"
  exit 0
fi

install -d "$lib/sparkshell" "$bin" "$libexec"
install -m 0644 "$here"/sparkshell/*.py "$lib/sparkshell/"
install -m 0755 "$here/spark_shell.py" "$lib/spark_shell.py"
# the launcher's search, shared with the Spark Launcher widget's tests
install -m 0644 "$here/../spark-launcher/launcher_logic.py" "$lib/launcher_logic.py"

# a wrapper, so the session script and spark-shell --toggle find it on PATH
cat > "$bin/spark-shell" <<WRAP
#!/bin/sh
exec python3 "${lib#"$STAGE"}/spark_shell.py" "\$@"
WRAP
chmod 0755 "$bin/spark-shell"

if [ "$USER_MODE" = 0 ]; then
  install -m 0755 "$here/session/spark-session" "$bin/spark-session"
  install -m 0755 "$here/session/spark-session-run" "$libexec/spark-session-run"
  install -m 0755 "$here/session/spark-session-polkit" "$libexec/spark-session-polkit"
  install -d "$units" "$sessions"
  install -m 0644 "$here/session/spark-workspace.target" "$here/session/spark-wl-workspace.target" \
    "$here/session/spark-polkit-agent.service" "$here/session/spark-xembed.service" "$units/"
  install -m 0644 "$here/session/spark.desktop" "$sessions/spark.desktop"
fi

if [ "$TEST" = 1 ] && [ -z "$STAGE" ]; then
  env -u DISPLAY -u WAYLAND_DISPLAY "$bin/spark-shell" --self-test
fi
echo "Spark Shell installed${STAGE:+ under $STAGE}"
