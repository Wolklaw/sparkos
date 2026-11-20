#!/usr/bin/env bash
# Spark Monitor, the SparkOS task manager (Ctrl+Shift+Esc). Its source lives in this repo at
# files/spark-monitor. Plasma System Monitor stays in the image next to it for now; whether
# Spark Monitor replaces it is the owner's call.
#
# install.sh --deps installs it system-wide, links its desktop entry into
# /usr/share/kglobalaccel so Plasma registers Ctrl+Shift+Esc, and runs --self-test (reads
# /proc and /sys of the build container); the build fails if that or any file below is missing.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-monitor"
test -f "$SRC/install.sh" || { echo "Spark Monitor source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps

test -x /usr/bin/spark-monitor
test -f /usr/share/applications/dev.wolklaw.SparkMonitor.desktop
test -L /usr/share/kglobalaccel/dev.wolklaw.SparkMonitor.desktop
grep -q '^X-KDE-Shortcuts=Ctrl+Shift+Esc$' /usr/share/applications/dev.wolklaw.SparkMonitor.desktop
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkMonitor.svg

# The self-test (also what the boot test runs) must find the shortcut registered, and no other
# installed desktop entry claiming Ctrl+Shift+Esc.
report=$(/usr/bin/spark-monitor --self-test)
echo "$report"
grep -q '^self-test passed' <<<"$report"
grep -q '^shortcut:  Ctrl+Shift+Esc registered for Plasma by /usr/share/kglobalaccel/' <<<"$report"
if grep -q 'also claimed by' <<<"$report"; then
  echo "Ctrl+Shift+Esc is claimed by another desktop entry; tell the owner"; exit 1
fi
echo "$(/usr/bin/spark-monitor --version) installed."
