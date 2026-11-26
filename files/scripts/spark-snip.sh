#!/usr/bin/env bash
# Spark Snip, the SparkOS tool for screenshots, copying text off the screen (OCR) and
# screen recording. Its source lives in this repo at files/spark-snip.
#
# The screenshot keys are bound by spark-compositor: Print and Super+Shift+S take a screenshot,
# Super+Shift+T copies text, Super+Shift+R starts and stops a recording. Spark Snip reads the
# screen through spark-compositor (wlr-screencopy).
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-snip"
test -f "$SRC/install.sh" || { echo "Spark Snip source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps

# Fail the build if anything is missing, so a broken Spark Snip never ships.
test -x /usr/bin/spark-snip
test -f /usr/share/applications/dev.wolklaw.SparkSnip.desktop
if grep -q '^X-KDE' /usr/share/applications/dev.wolklaw.SparkSnip.desktop; then
  echo "the Spark Snip desktop entry still has X-KDE keys"; exit 1
fi

echo "$(/usr/bin/spark-snip --version) installed."
