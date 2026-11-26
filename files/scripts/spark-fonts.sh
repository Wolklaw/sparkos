#!/usr/bin/env bash
# Spark Fonts: see, install and remove fonts. Its source lives in this repo at
# files/spark-fonts. sparkos-defaults.sh makes it open font files.
#
# install.sh --deps installs it system-wide (and python3-pillow, which draws the previews), and
# runs --self-test (no display needed, changes no fonts). The build fails if that or any file
# below is missing.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-fonts"
test -f "$SRC/install.sh" || { echo "Spark Fonts source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps

test -x /usr/bin/spark-fonts
test -f /usr/share/applications/dev.wolklaw.SparkFonts.desktop
grep -q '^MimeType=.*font/ttf' /usr/share/applications/dev.wolklaw.SparkFonts.desktop
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkFonts.svg
test -f /usr/share/spark-apps/spark-fonts.json
python3 -c 'import PIL'

report=$(/usr/bin/spark-fonts --self-test)
echo "$report"
grep -q '^self-test passed' <<<"$report"
echo "$(/usr/bin/spark-fonts --version) installed."
