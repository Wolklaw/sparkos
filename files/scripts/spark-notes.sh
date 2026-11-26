#!/usr/bin/env bash
# Spark Notes, the SparkOS notes and clipboard history. Its source
# lives in this repo at files/spark-notes; nothing is downloaded here except wl-clipboard.
#
# install.sh --deps installs the app system-wide and runs --self-test; it also installs
# wl-clipboard (wl-paste and wl-copy), which the clipboard watcher is built on. wl-clipboard is
# GPL-3.0-or-later and runs as a separate command (THIRD-PARTY.md). The build fails if the
# self-test or any check below fails.
#
# Spark Notes takes Meta+V:
# - its popup entry (dev.wolklaw.SparkNotes.Clipboard.desktop) carries X-KDE-Shortcuts=Meta+V,
#   and the Spark compositor reads the shortcuts of the entries linked in /usr/share/kglobalaccel
# - the watcher is a user service, enabled for every login (graphical-session.target.wants)
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-notes"
test -f "$SRC/install.sh" || { echo "Spark Notes source not found at $SRC"; exit 1; }

# the build runs as root with HOME=/root: keep the self-test's folders out of the image
export XDG_CONFIG_HOME=/tmp/spark-notes-build/config XDG_STATE_HOME=/tmp/spark-notes-build/state
export XDG_DATA_HOME=/tmp/spark-notes-build/data
bash "$SRC/install.sh" --deps
rm -rf /tmp/spark-notes-build

APP=/usr/share/applications/dev.wolklaw.SparkNotes.desktop
POPUP=/usr/share/applications/dev.wolklaw.SparkNotes.Clipboard.desktop
UNIT=/usr/lib/systemd/user/spark-notes-clipboard.service
test -x /usr/bin/spark-notes
test -f "$APP"
test -f "$POPUP"
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkNotes.svg
test -x /usr/bin/wl-paste
test -x /usr/bin/wl-copy
grep -qx 'ExecStart=/usr/bin/spark-notes --watch' "$UNIT"
test -L /usr/lib/systemd/user/graphical-session.target.wants/spark-notes-clipboard.service

# --- Meta+V : the compositor takes the shortcut from the popup entry linked here
install -d /usr/share/kglobalaccel
ln -sfn ../applications/dev.wolklaw.SparkNotes.Clipboard.desktop \
  /usr/share/kglobalaccel/dev.wolklaw.SparkNotes.Clipboard.desktop
grep -qx 'X-KDE-Shortcuts=Meta+V' "$POPUP"
# no other desktop entry may claim Meta+V
others=$(grep -lE '^X-KDE-Shortcuts=(.*,)?Meta\+V(,|$)' /usr/share/applications/*.desktop \
  /usr/share/kglobalaccel/*.desktop 2>/dev/null \
  | grep -v 'dev.wolklaw.SparkNotes.Clipboard.desktop$' || true)
[ -z "$others" ] || { echo "these also claim Meta+V :"; echo "$others"; exit 1; }

echo "$(/usr/bin/spark-notes --version) installed; it has Meta+V"
