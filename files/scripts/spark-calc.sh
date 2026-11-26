#!/usr/bin/env bash
# Spark Calc, the SparkOS calculator (standard, scientific and programmer modes). Its source
# lives in this repo at files/spark-calc. SparkOS has no other calculator.
#
# install.sh --deps installs it system-wide and runs --self-test (works a set of sums out; no display needed). The build fails if that or any
# file below is missing. spark-compositor binds the keyboard's Calculator key to it; the
# desktop entry carries no shortcut keys.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-calc"
test -f "$SRC/install.sh" || { echo "Spark Calc source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps

test -x /usr/bin/spark-calc
test -f /usr/share/applications/dev.wolklaw.SparkCalc.desktop
if grep -q '^X-KDE' /usr/share/applications/dev.wolklaw.SparkCalc.desktop; then
  echo "the Spark Calc desktop entry still has X-KDE keys"; exit 1
fi
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkCalc.svg

report=$(/usr/bin/spark-calc --self-test)
echo "$report"
grep -q '^self-test passed' <<<"$report"
[ "$(/usr/bin/spark-calc --eval '0.1+0.2')" = "0.3" ]

echo "$(/usr/bin/spark-calc --version) installed."
