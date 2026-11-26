#!/usr/bin/env bash
# Spark Tray, the SparkOS tray icons: network, Bluetooth, power, printers and volume. Its source
# lives in this repo at files/spark-tray. It starts in the Spark session
# (/etc/xdg/autostart carries OnlyShowIn=Spark).
#
# install.sh --deps installs it system-wide and runs --self-test (no display needed); the build
# fails if that or any file below is missing.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-tray"
test -f "$SRC/install.sh" || { echo "Spark Tray source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps

test -x /usr/bin/spark-tray
test -f /usr/share/applications/dev.wolklaw.SparkTray.desktop
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkTray.svg
test -f /usr/share/spark-apps/spark-tray.json
grep -q '^OnlyShowIn=Spark;$' /etc/xdg/autostart/dev.wolklaw.SparkTray.desktop

report=$(/usr/bin/spark-tray --self-test)
echo "$report"
grep -q '^self-test passed' <<<"$report"

# The tray talks to tuned-ppd through net.hadess.PowerProfiles; power-profiles-daemon would conflict
if rpm -q power-profiles-daemon >/dev/null 2>&1; then
  echo "power-profiles-daemon is installed; it conflicts with tuned-ppd. Tell the owner."
fi
echo "$(/usr/bin/spark-tray --version) installed."
