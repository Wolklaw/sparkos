#!/usr/bin/env bash
# Spark Calc, the SparkOS calculator (standard, scientific and programmer modes). Its source
# lives in this repo at files/spark-calc. SparkOS has had no calculator since KCalc went.
#
# install.sh --deps installs it system-wide, links its desktop entry into
# /usr/share/kglobalaccel so Plasma gives it the keyboard's Calculator key, and runs
# --self-test (works a set of sums out; no display needed). The build fails if that or any
# file below is missing.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-calc"
test -f "$SRC/install.sh" || { echo "Spark Calc source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps

test -x /usr/bin/spark-calc
test -f /usr/share/applications/dev.wolklaw.SparkCalc.desktop
test -L /usr/share/kglobalaccel/dev.wolklaw.SparkCalc.desktop
grep -q '^X-KDE-Shortcuts=Calculator$' /usr/share/applications/dev.wolklaw.SparkCalc.desktop
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkCalc.svg

report=$(/usr/bin/spark-calc --self-test)
echo "$report"
grep -q '^self-test passed' <<<"$report"
[ "$(/usr/bin/spark-calc --eval '0.1+0.2')" = "0.3" ]

# Another desktop entry claiming the Calculator key would fight over it
others=$(grep -l '^X-KDE-Shortcuts=.*Calculator' /usr/share/applications/*.desktop 2>/dev/null \
         | grep -v 'dev.wolklaw.SparkCalc.desktop' || true)
if [ -n "$others" ]; then
  echo "The Calculator key is also claimed by: $others; tell the owner"
fi
echo "$(/usr/bin/spark-calc --version) installed."
