#!/usr/bin/env bash
# Spark Terminal, the SparkOS terminal (SparkOS's own terminal). Its source lives in this repo at
# files/spark-terminal; the terminal emulation comes from VTE, the library GNOME's terminals
# use (vte291-gtk4 from Fedora, added here; see THIRD-PARTY.md).
#
# install.sh --deps installs VTE and the app system-wide and runs --self-test (starts a shell
# on a VTE pty and reads its output back); the build fails if that or any check below fails.
#
# Spark Terminal becomes the terminal everywhere:
# - TerminalApplication/TerminalService in /etc/xdg/kdeglobals, which Spark Settings' Default
#   apps page reads and changes (files/system)
# - xdg-terminal-exec's default (/etc/xdg/xdg-terminals.list), for apps with Terminal=true
# - Ctrl+Alt+T: Spark Terminal's desktop entry takes it
# - the shell's dock and SparkOS's own scripts start spark-terminal
# This script also checks nothing SparkOS ships starts Konsole.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-terminal"
test -f "$SRC/install.sh" || { echo "Spark Terminal source not found at $SRC"; exit 1; }

# the build runs as root with HOME=/root: keep the self-test's folders out of the image
export XDG_CONFIG_HOME=/tmp/spark-terminal-build/config XDG_STATE_HOME=/tmp/spark-terminal-build/state
bash "$SRC/install.sh" --deps
rm -rf /tmp/spark-terminal-build

APP=/usr/share/applications/dev.wolklaw.SparkTerminal.desktop
test -x /usr/bin/spark-terminal
test -f "$APP"
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkTerminal.svg
rpm -q vte291-gtk4

# --- Ctrl+Alt+T: spark-compositor reads the shortcut from the desktop entry linked here
install -d /usr/share/kglobalaccel
ln -sfn ../applications/dev.wolklaw.SparkTerminal.desktop /usr/share/kglobalaccel/dev.wolklaw.SparkTerminal.desktop
grep -qx 'X-KDE-Shortcuts=Ctrl+Alt+T' "$APP"

others=$(grep -lE '^X-KDE-Shortcuts=(.*,)?Ctrl\+Alt\+T(,|$)' \
  /usr/share/applications/*.desktop /usr/share/kglobalaccel/*.desktop 2>/dev/null \
  | grep -v 'dev.wolklaw.SparkTerminal.desktop$' || true)
[ -z "$others" ] || { echo "these also claim Ctrl+Alt+T:"; echo "$others"; exit 1; }

# --- the default terminal (the files come from files/system)
grep -qx 'TerminalApplication=spark-terminal' /etc/xdg/kdeglobals
grep -qx 'TerminalService=dev.wolklaw.SparkTerminal.desktop' /etc/xdg/kdeglobals
grep -qx 'dev.wolklaw.SparkTerminal.desktop' /etc/xdg/xdg-terminals.list
if command -v xdg-terminal-exec >/dev/null; then
  picked=$(XDG_CURRENT_DESKTOP=sparkwl:Spark HOME=/nonexistent XDG_CONFIG_HOME=/nonexistent xdg-terminal-exec --print-id 2>/dev/null || true)
  echo "xdg-terminal-exec picks: ${picked:-(no --print-id in this version)}"
  [ -z "$picked" ] || [ "$picked" = dev.wolklaw.SparkTerminal.desktop ] || { echo "xdg-terminal-exec picks $picked"; exit 1; }
fi

# --- nothing SparkOS ships starts Konsole any more
callers=$(grep -rlE '(^|[^.[:alnum:]_-])konsole( |$)' /usr/bin/sparkos-* /usr/share/applications/sparkos-*.desktop \
  /usr/share/kio/servicemenus/sparkos-*.desktop /usr/lib/spark-*/ 2>/dev/null | grep -v '\.pyc$' || true)
[ -z "$callers" ] || { echo "these still start konsole:"; echo "$callers"; exit 1; }

echo "$(/usr/bin/spark-terminal --version) installed; it's the default terminal."
