#!/usr/bin/env bash
# Spark Audio, the SparkOS sound mixer: outputs, microphones, per-app volume, an equalizer and
# Focusrite Scarlett controls. Its source lives in this repo at files/spark-audio. It replaces
# Focusrite Control and a separate mixer.
#
# install.sh --deps installs it system-wide (and alsa-utils, which the Scarlett page needs: it is
# not in the base image) and runs --self-test; the build fails if that or any file below is missing.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-audio"
test -f "$SRC/install.sh" || { echo "Spark Audio source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps

test -x /usr/bin/spark-audio
test -f /usr/share/applications/dev.wolklaw.SparkAudio.desktop
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkAudio.svg
rpm -q alsa-utils >/dev/null
command -v amixer >/dev/null

report=$(/usr/bin/spark-audio --self-test)
echo "$report"
grep -q '^self-test passed' <<<"$report"
echo "$(/usr/bin/spark-audio --version) installed."
