#!/usr/bin/env bash
# Spark Launcher, SparkOS's app menu: the button on the dock and the top bar, and the Meta key.
# A Plasma widget; its source lives in this repo at files/spark-launcher. The SparkOS desktop
# layout (look-and-feel dev.wolklaw.sparkos.desktop) uses it where Plasma's Kickoff was.
#
# install.sh copies the package to /usr/share/plasma/plasmoids/dev.wolklaw.sparklauncher and
# runs --self-test; the build fails if that or any file below is missing. Runs after
# spark-calc.sh (the launcher's sums use spark-calc --eval).
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-launcher"
test -f "$SRC/install.sh" || { echo "Spark Launcher source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --no-test

DIR=/usr/share/plasma/plasmoids/dev.wolklaw.sparklauncher
test -f "$DIR/metadata.json"
test -f "$DIR/contents/ui/main.qml"
test -f "$DIR/contents/ui/Launcher.qml"
kpackagetool6 -g -t Plasma/Applet --show dev.wolklaw.sparklauncher | grep -q "$DIR"

report=$(bash "$SRC/install.sh" --self-test)
echo "$report"
grep -q '^self-test passed' <<<"$report"
grep -q '^sums:      spark-calc answers' <<<"$report" || { echo "spark-calc doesn't answer sums"; exit 1; }
# The SparkOS layout must ask for this widget, not Kickoff
LAYOUT=/usr/share/plasma/look-and-feel/dev.wolklaw.sparkos.desktop/contents/layouts/org.kde.plasma.desktop-layout.js
if [ -f "$LAYOUT" ]; then
  grep -q 'addWidget("dev.wolklaw.sparklauncher")' "$LAYOUT"
  if grep -q 'org.kde.plasma.kickoff' "$LAYOUT"; then echo "the SparkOS layout still adds Kickoff"; exit 1; fi
fi
