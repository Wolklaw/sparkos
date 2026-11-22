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
#
# install.sh --sources then copies the source folder of each optional Spark app into
# /usr/share/spark-store/sources/<slug>, read-only, so the Store can install it for one user
# (install.sh --user) when they click Install. Optional means no image build step installs it:
# there is no files/scripts/<slug>.sh (today Spark Bench, Spark Connect and Spark Space). They
# are only copied, not installed: nothing of theirs goes in /usr/bin, /usr/lib or the menu.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-store"
test -f "$SRC/install.sh" || { echo "Spark Store source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps
bash "$SRC/install.sh" --sources /usr/share/spark-store/sources

test -x /usr/bin/spark-store
test -f /usr/share/applications/dev.wolklaw.SparkStore.desktop
grep -q '^MimeType=application/vnd.flatpak.ref;application/vnd.flatpak.repo;x-scheme-handler/appstream;$' \
  /usr/share/applications/dev.wolklaw.SparkStore.desktop
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkStore.svg
ls /usr/lib/spark-store/spark-apps/*/spark-app.json >/dev/null
optional=$(bash "$SRC/install.sh" --optional)
for slug in $optional; do
  test -f "/usr/share/spark-store/sources/$slug/install.sh"
  test -f "/usr/share/spark-store/sources/$slug/spark-app.json"
  test ! -e "/usr/lib/$slug"
  test ! -e "/usr/bin/$slug"
done

report=$(/usr/bin/spark-store --self-test)
echo "$report"
grep -q '^self-test passed' <<<"$report"
grep -q '^spark:     ' <<<"$report"
for slug in $optional; do   # the Store sees each one as not installed, with a source
  grep -q "(not installed, can install from /usr/share/spark-store/sources/$slug)$" <<<"$report"
done
echo "$(/usr/bin/spark-store --version) installed; sources to install from:" $optional
