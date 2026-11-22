#!/usr/bin/env bash
# Spark Media, the SparkOS app for photos, videos and music. Its source lives in this repo at
# files/spark-media. It's the default for photos, videos and music (sparkos-defaults.sh), so
# a fresh SparkOS opens them without installing anything.
#
# The build fails if the common formats can't play: H.264, H.265 and AAC (phones, cameras,
# most downloads) and MP3, on top of the open formats the self-test always checks.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-media"
test -f "$SRC/install.sh" || { echo "Spark Media source not found at $SRC"; exit 1; }

SPARK_MEDIA_REQUIRE=h264,h265,aac,mp3 bash "$SRC/install.sh" --deps

test -x /usr/bin/spark-media
test -f /usr/share/applications/dev.wolklaw.SparkMedia.desktop
echo "$(/usr/bin/spark-media --version) installed."
