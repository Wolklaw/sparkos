#!/usr/bin/env bash
# Spark Games, SparkOS's one library for every installed game (Steam, Heroic, Lutris and the
# user's own). Its source lives in this repo at files/spark-games. SparkOS ships no launcher,
# so a fresh install shows the empty state, which points to Spark Welcome and the Store.
#
# install.sh --deps installs it system-wide and runs --self-test (the scanners against the
# bundled fixtures, Pillow, xdg-open); the build fails if that or any file below is missing.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-games"
test -f "$SRC/install.sh" || { echo "Spark Games source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps

test -x /usr/bin/spark-games
test -f /usr/share/applications/dev.wolklaw.SparkGames.desktop
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkGames.svg
echo "$(/usr/bin/spark-games --version) installed."
