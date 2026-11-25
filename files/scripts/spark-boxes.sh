#!/usr/bin/env bash
# Spark Boxes, the SparkOS virtual machines window (replaces Virtual Machine Manager from
# Flathub). Its source lives in this repo at files/spark-boxes; nothing is downloaded here.
#
# libvirt, QEMU, OVMF and swtpm come from build_files/packages.sh (they have been in the image
# since `spark virt setup` was added). The two libraries the window needs on top, python3-libvirt
# and spice-gtk3 (the machine's screen), come from there too, so this step installs only the app:
# install.sh --deps checks them and would add them with dnf if they were missing. It runs the
# app's self-test, which fails the build if libvirt's Python binding or the GTK 3 and SPICE
# libraries don't load.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-boxes"
test -f "$SRC/install.sh" || { echo "Spark Boxes source not found at $SRC"; exit 1; }

# the build runs as root with HOME=/root: keep the self-test's folders out of the image
export XDG_CONFIG_HOME=/tmp/spark-boxes-build/config XDG_STATE_HOME=/tmp/spark-boxes-build/state
export XDG_DATA_HOME=/tmp/spark-boxes-build/data XDG_CACHE_HOME=/tmp/spark-boxes-build/cache
bash "$SRC/install.sh" --deps
rm -rf /tmp/spark-boxes-build

APP=/usr/share/applications/dev.wolklaw.SparkBoxes.desktop
test -x /usr/bin/spark-boxes
test -f "$APP"
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkBoxes.svg
test -f /usr/share/spark-apps/spark-boxes.json
grep -qx 'Exec=spark-boxes' "$APP"
python3 -c 'import libvirt'
python3 -c '
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("SpiceClientGLib", "2.0")
gi.require_version("SpiceClientGtk", "3.0")
from gi.repository import Gtk, SpiceClientGLib, SpiceClientGtk'
# what Windows 11 machines ask for
rpm -q edk2-ovmf swtpm >/dev/null
ls /usr/share/qemu/firmware/*-x64-sb-enrolled.json >/dev/null

echo "$(/usr/bin/spark-boxes --version) installed"
