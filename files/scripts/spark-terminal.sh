#!/usr/bin/env bash
# Spark Terminal, the SparkOS terminal (replaces Konsole). Its source lives in this repo at
# files/spark-terminal; the terminal emulation comes from VTE, the library GNOME's terminals
# use (vte291-gtk4 from Fedora, added here; see THIRD-PARTY.md).
#
# install.sh --deps installs VTE and the app system-wide and runs --self-test (starts a shell
# on a VTE pty and reads its output back); the build fails if that or any check below fails.
#
# Spark Terminal becomes the terminal everywhere:
# - KDE's default terminal: TerminalApplication/TerminalService in /etc/xdg/kdeglobals, which
#   Dolphin's "Open Terminal Here" and apps with Terminal=true use (files/system)
# - xdg-terminal-exec's default (/etc/xdg/kde-xdg-terminals.list and xdg-terminals.list)
# - Ctrl+Alt+T: Spark Terminal's desktop entry takes it; Konsole's gives it up
# - the dock (the look-and-feel layout) and SparkOS's own scripts start spark-terminal
# - new shells print one SparkOS line instead of Bazzite's welcome banner (files/system)
# Konsole stays installed for one release as a fallback, hidden from the menu. Removing it is
# a separate change.
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

# --- Ctrl+Alt+T: Plasma registers the shortcut from the desktop entry linked here
install -d /usr/share/kglobalaccel
ln -sfn ../applications/dev.wolklaw.SparkTerminal.desktop /usr/share/kglobalaccel/dev.wolklaw.SparkTerminal.desktop
grep -qx 'X-KDE-Shortcuts=Ctrl+Alt+T' "$APP"

# --- Konsole: kept for one release, out of the menu, without the shortcut
for entry in /usr/share/applications/org.kde.konsole.desktop /usr/share/kglobalaccel/org.kde.konsole.desktop; do
  [ -f "$entry" ] || continue
  sed -i --follow-symlinks '/^X-KDE-Shortcuts=/d' "$entry"
  if [ "$entry" = /usr/share/applications/org.kde.konsole.desktop ] && ! grep -q '^NoDisplay=true' "$entry"; then
    sed -i '/^\[Desktop Entry\]/a NoDisplay=true' "$entry"
  fi
done
others=$(grep -lE '^X-KDE-Shortcuts=(.*,)?Ctrl\+Alt\+T(,|$)' \
  /usr/share/applications/*.desktop /usr/share/kglobalaccel/*.desktop 2>/dev/null \
  | grep -v 'dev.wolklaw.SparkTerminal.desktop$' || true)
[ -z "$others" ] || { echo "these also claim Ctrl+Alt+T:"; echo "$others"; exit 1; }

# --- the default terminal (the files come from files/system)
grep -qx 'TerminalApplication=spark-terminal' /etc/xdg/kdeglobals
grep -qx 'TerminalService=dev.wolklaw.SparkTerminal.desktop' /etc/xdg/kdeglobals
for list in /etc/xdg/kde-xdg-terminals.list /etc/xdg/xdg-terminals.list; do
  grep -qx 'dev.wolklaw.SparkTerminal.desktop' "$list"
done
if command -v xdg-terminal-exec >/dev/null; then
  picked=$(XDG_CURRENT_DESKTOP=KDE HOME=/nonexistent XDG_CONFIG_HOME=/nonexistent xdg-terminal-exec --print-id 2>/dev/null || true)
  echo "xdg-terminal-exec picks: ${picked:-(no --print-id in this version)}"
  [ -z "$picked" ] || [ "$picked" = dev.wolklaw.SparkTerminal.desktop ] || { echo "xdg-terminal-exec picks $picked"; exit 1; }
fi

# --- the banner in each new shell is SparkOS's one line, not "Welcome to Bazzite" (files/system
#     replaces /usr/libexec/ublue-motd, which /etc/profile.d/user-motd.sh runs)
grep -q 'SPARKOS' /usr/libexec/ublue-motd
out=$(script -qc 'TERM=xterm-256color /usr/libexec/ublue-motd' /dev/null 2>/dev/null || /usr/libexec/ublue-motd)
if grep -qi bazzite <<<"$out"; then echo "the terminal banner still says Bazzite: $out"; exit 1; fi

# --- nothing SparkOS ships starts Konsole any more
callers=$(grep -rlE '(^|[^.[:alnum:]_-])konsole( |$)' /usr/bin/sparkos-* /usr/share/applications/sparkos-*.desktop \
  /usr/share/kio/servicemenus/sparkos-*.desktop /usr/lib/spark-*/ 2>/dev/null | grep -v '\.pyc$' || true)
[ -z "$callers" ] || { echo "these still start konsole:"; echo "$callers"; exit 1; }

echo "$(/usr/bin/spark-terminal --version) installed; it's the default terminal."
