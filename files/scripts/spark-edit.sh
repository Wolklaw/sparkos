#!/usr/bin/env bash
# Spark Edit, the SparkOS text and code editor (Kate and KWrite are gone, so without it text
# files open in FreeSuite Writer). Its source lives in this repo at files/spark-edit.
#
# install.sh --deps installs it system-wide and runs --self-test (writes and reads back each
# kind of file it keeps as it was, lexes every language); the build fails if that or any file
# below is missing. Making it the default for text files is sparkos-defaults.sh's job.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-edit"
test -f "$SRC/install.sh" || { echo "Spark Edit source not found at $SRC"; exit 1; }

# the build runs as root with HOME=/root: keep the self-test's folders out of the image
export XDG_CONFIG_HOME=/tmp/spark-edit-build/config XDG_STATE_HOME=/tmp/spark-edit-build/state \
       XDG_CACHE_HOME=/tmp/spark-edit-build/cache
bash "$SRC/install.sh" --deps
rm -rf /tmp/spark-edit-build

test -x /usr/bin/spark-edit
test -f /usr/share/applications/dev.wolklaw.SparkEdit.desktop
grep -q '^MimeType=text/plain;' /usr/share/applications/dev.wolklaw.SparkEdit.desktop
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkEdit.svg
echo "$(/usr/bin/spark-edit --version) installed."
