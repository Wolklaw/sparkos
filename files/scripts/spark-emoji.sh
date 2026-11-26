#!/usr/bin/env bash
# Spark Emoji, the SparkOS emoji and symbol picker Its source
# lives in this repo at files/spark-emoji; the emoji and names are Unicode's and CLDR's data
# (Unicode-3.0, see THIRD-PARTY.md), already turned into JSON in the repo, so nothing is
# downloaded here.
#
# install.sh --deps installs the app system-wide (and a colour emoji font if the image has none)
# and runs --self-test; the build fails if that or any check below fails.
#
# Spark Emoji takes Meta+. (Windows key and full stop):
# spark-compositor binds it; the desktop entry carries no shortcut keys.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-emoji"
test -f "$SRC/install.sh" || { echo "Spark Emoji source not found at $SRC"; exit 1; }

# the build runs as root with HOME=/root: keep the self-test's folders out of the image
export XDG_CONFIG_HOME=/tmp/spark-emoji-build/config XDG_STATE_HOME=/tmp/spark-emoji-build/state
bash "$SRC/install.sh" --deps
rm -rf /tmp/spark-emoji-build

APP=/usr/share/applications/dev.wolklaw.SparkEmoji.desktop
test -x /usr/bin/spark-emoji
test -f "$APP"
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkEmoji.svg
test -f /usr/lib/spark-emoji/sparkemoji/data/emoji.json
test -f /usr/lib/spark-emoji/sparkemoji/data/symbols.json
fc-list ':charset=1f600' family | grep -q . || { echo "no installed font has emoji (U+1F600)"; exit 1; }

if grep -q '^X-KDE' "$APP"; then
  echo "the Spark Emoji desktop entry still has X-KDE keys"; exit 1
fi

echo "$(/usr/bin/spark-emoji --version) installed."
