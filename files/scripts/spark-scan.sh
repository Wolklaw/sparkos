#!/usr/bin/env bash
# Spark Scan, scanning for SparkOS (preview, crop, multi-page PDF, searchable text). Its source
# lives in this repo at files/spark-scan. Not in the recipe yet: whether it ships in the image
# or stays an optional app (install.sh --user) is the owner's call when merging.
#
# install.sh --deps installs it system-wide with what it needs (SANE with pixma and airscan,
# tesseract with English and French) and runs --self-test; the build fails if that or any file
# below is missing. The self-test lists scanners but doesn't need one: the build has none.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-scan"
test -f "$SRC/install.sh" || { echo "Spark Scan source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps --no-test

test -x /usr/bin/spark-scan
test -f /usr/share/applications/dev.wolklaw.SparkScan.desktop
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkScan.svg
test -f /usr/share/icons/hicolor/256x256/apps/dev.wolklaw.SparkScan.png

# A build container has no D-Bus, and some SANE backends abort scanimage without it, so the
# scanner search is limited to SANE's test scanner here (only for this check).
conf=$(mktemp -d)
printf 'test\n' > "$conf/dll.conf"
report=$(SANE_CONFIG_DIR="$conf" /usr/bin/spark-scan --self-test --device test:0)
rm -rf "$conf"
echo "$report"
grep -q '^self-test passed' <<<"$report"
grep -q '^scanner:   test:0' <<<"$report"
grep -q '^tesseract: .*searchable PDF in: eng+fra' <<<"$report"
echo "$(/usr/bin/spark-scan --version) installed."
