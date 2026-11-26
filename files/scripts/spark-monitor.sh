#!/usr/bin/env bash
# Spark Monitor, the SparkOS task manager (Ctrl+Shift+Esc). Its source lives in this repo at
# files/spark-monitor. spark-compositor binds Ctrl+Shift+Esc, Super+Esc and Ctrl+Esc to it.
#
# install.sh --deps installs it system-wide and runs --self-test (reads
# /proc and /sys of the build container); the build fails if that or any file below is missing.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-monitor"
test -f "$SRC/install.sh" || { echo "Spark Monitor source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps

test -x /usr/bin/spark-monitor
test -f /usr/share/applications/dev.wolklaw.SparkMonitor.desktop
if grep -q '^X-KDE' /usr/share/applications/dev.wolklaw.SparkMonitor.desktop; then
  echo "the Spark Monitor desktop entry still has X-KDE keys"; exit 1
fi
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkMonitor.svg

# The self-test is also what the boot test runs
report=$(/usr/bin/spark-monitor --self-test)
echo "$report"
grep -q '^self-test passed' <<<"$report"
grep -q '^shortcut:  Ctrl+Shift+Esc opens this window' <<<"$report"
echo "$(/usr/bin/spark-monitor --version) installed."
