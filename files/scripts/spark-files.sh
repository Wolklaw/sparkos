#!/usr/bin/env bash
# Spark Files, the SparkOS file manager. Its source lives in this repo at
# files/spark-files.
#
# install.sh --deps installs it system-wide and runs --self-test (copies, moves, renames, trashes
# and restores in a temporary folder); the build fails if that or any file below is missing.
# The D-Bus name org.freedesktop.FileManager1 ("Show in folder" in every other app) starts
# Spark Files: any other activation file for that name is removed, so only one is left.
# Making it the default for folders (inode/directory) is sparkos-defaults.sh's job; the dock
# pins it (Spark Shell's dock).
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-files"
test -f "$SRC/install.sh" || { echo "Spark Files source not found at $SRC"; exit 1; }

# the build runs as root with HOME=/root: keep the self-test's folders out of the image
export XDG_CONFIG_HOME=/tmp/spark-files-build/config XDG_STATE_HOME=/tmp/spark-files-build/state \
       XDG_CACHE_HOME=/tmp/spark-files-build/cache XDG_DATA_HOME=/tmp/spark-files-build/data
bash "$SRC/install.sh" --deps
rm -rf /tmp/spark-files-build

test -x /usr/bin/spark-files
test -f /usr/share/applications/dev.wolklaw.SparkFiles.desktop
grep -q '^MimeType=inode/directory;' /usr/share/applications/dev.wolklaw.SparkFiles.desktop
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkFiles.svg
grep -qx 'Name=org.freedesktop.FileManager1' /usr/share/dbus-1/services/dev.wolklaw.SparkFiles.FileManager1.service
grep -qx 'Name=dev.wolklaw.SparkFiles' /usr/share/dbus-1/services/dev.wolklaw.SparkFiles.service
# the Spark session's Open and Save dialogs (the portal backend)
grep -qx 'Name=org.freedesktop.impl.portal.desktop.spark' \
  /usr/share/dbus-1/services/org.freedesktop.impl.portal.desktop.spark.service
grep -q 'FileChooser' /usr/share/xdg-desktop-portal/portals/spark.portal
grep -qx 'org.freedesktop.impl.portal.FileChooser=spark;gtk;' \
  /usr/share/xdg-desktop-portal/spark-portals.conf

# ── "Show in folder" goes to Spark Files ──
# Two activation files for one name is undefined behaviour on the session bus: remove every
# other file that claims org.freedesktop.FileManager1
for f in /usr/share/dbus-1/services/*.service; do
  [ "$f" = /usr/share/dbus-1/services/dev.wolklaw.SparkFiles.FileManager1.service ] && continue
  if grep -qx 'Name=org.freedesktop.FileManager1' "$f"; then
    rm -f "$f"
    echo "--- removed $(basename "$f"): Spark Files answers org.freedesktop.FileManager1"
  fi
done
left=$(grep -lx 'Name=org.freedesktop.FileManager1' /usr/share/dbus-1/services/*.service)
[ "$left" = /usr/share/dbus-1/services/dev.wolklaw.SparkFiles.FileManager1.service ] || {
  echo "more than one FileManager1 provider: $left"; exit 1; }

echo "$(/usr/bin/spark-files --version) installed."
