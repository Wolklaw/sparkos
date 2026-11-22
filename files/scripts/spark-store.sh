#!/usr/bin/env bash
# Spark Store, SparkOS's own app store: the Spark apps first, then every app on Flathub, read
# from the Flathub catalog flatpak keeps on the PC. Its source lives in this repo at
# files/spark-store.
#
# This installs it. Its menu entry takes appstream:// links; sparkos-defaults.sh makes it the
# default for .flatpakref and .flatpakrepo files, and the taskbar layout pins it. Bazaar, where
# the base still has it, is only a fallback.
#
# install.sh --deps installs it system-wide, copies every Spark app's spark-app.json and icon
# (files/spark-*/) into /usr/lib/spark-store/spark-apps, and runs --self-test. The build
# container has no Flathub catalog yet (it's fetched at first boot), so the self-test says so
# and checks the rest; the build fails if that or any file below is missing.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-store"
test -f "$SRC/install.sh" || { echo "Spark Store source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps

test -x /usr/bin/spark-store
test -f /usr/share/applications/dev.wolklaw.SparkStore.desktop
grep -q '^MimeType=application/vnd.flatpak.ref;application/vnd.flatpak.repo;x-scheme-handler/appstream;$' \
  /usr/share/applications/dev.wolklaw.SparkStore.desktop
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkStore.svg
ls /usr/lib/spark-store/spark-apps/*/spark-app.json >/dev/null

report=$(/usr/bin/spark-store --self-test)
echo "$report"
grep -q '^self-test passed' <<<"$report"
grep -q '^spark:     ' <<<"$report"
echo "$(/usr/bin/spark-store --version) installed."
