#!/usr/bin/env bash
# Spark Archive: open, extract and make archives (zip, tar.*, 7z, rar, iso), with Extract here,
# Extract to folder and Compress in Dolphin's right-click menu. Its source lives in this repo
# at files/spark-archive. It is meant to replace Ark; removing Ark (and choosing which MIME
# types Spark Archive opens by default) is done in the recipe and sparkos-defaults.sh, not here.
#
# install.sh --deps installs it system-wide with its KIO service menus in
# /usr/share/kio/servicemenus. Then --self-test compresses and extracts a zip, a tar.zst and
# (with the 7z command) a 7z for real and checks a hostile zip stays contained; the build fails
# if that or any file below is missing.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-archive"
test -f "$SRC/install.sh" || { echo "Spark Archive source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps --no-test

test -x /usr/bin/spark-archive
test -f /usr/share/applications/dev.wolklaw.SparkArchive.desktop
test -f /usr/share/kio/servicemenus/dev.wolklaw.SparkArchive.extract.desktop
test -f /usr/share/kio/servicemenus/dev.wolklaw.SparkArchive.compress.desktop
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkArchive.svg
grep -q '^Exec=spark-archive --extract-here %F$' \
  /usr/share/kio/servicemenus/dev.wolklaw.SparkArchive.extract.desktop

report=$(/usr/bin/spark-archive --self-test)
echo "$report"
grep -q '^self-test passed' <<<"$report"
grep -q '^reads:      7z       with libarchive' <<<"$report"
echo "$(/usr/bin/spark-archive --version) installed."
