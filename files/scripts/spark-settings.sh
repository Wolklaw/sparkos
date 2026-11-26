#!/usr/bin/env bash
# Spark Settings, SparkOS's settings app. Its source lives in this repo at files/spark-settings.
#
# install.sh --deps installs it system-wide and runs --self-test; the build fails if that or any
# file below is missing.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-settings"
test -f "$SRC/install.sh" || { echo "Spark Settings source not found at $SRC"; exit 1; }

# the build runs as root with HOME=/root: keep the self-test's folders out of the image
export XDG_CONFIG_HOME=/tmp/spark-settings-build/config XDG_STATE_HOME=/tmp/spark-settings-build/state \
       XDG_DATA_HOME=/tmp/spark-settings-build/data
bash "$SRC/install.sh" --deps
rm -rf /tmp/spark-settings-build

test -x /usr/bin/spark-settings
test -f /usr/share/applications/dev.wolklaw.SparkSettings.desktop
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkSettings.svg

echo "$(/usr/bin/spark-settings --version) installed."
