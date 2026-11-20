#!/usr/bin/env bash
# Spark Run, SparkOS's own way to run Windows programs (replaces fetching Bottles). Its source
# lives in this repo at files/spark-run.
#
# Wine is NOT added to the image: Fedora's wine would add about 2 GiB. Spark Run downloads a
# pinned Wine (94 MB) and Wine Mono (38 MB) into the user's home the first time someone runs a
# Windows program, and checks their SHA-256 against files/spark-run/sparkrun/sources.py. What
# Wine loads from Linux (X11, FreeType, GnuTLS, Vulkan...) is already in the image; install.sh
# --deps only adds what's missing, by soname.
#
# install.sh --deps installs it system-wide and runs --self-test; the build fails if that or any
# file below is missing. Hooking it into double-clicking an .exe/.msi is sparkos-open-package's
# job (see the Spark Run PR).
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-run"
test -f "$SRC/install.sh" || { echo "Spark Run source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps

test -x /usr/bin/spark-run
test -f /usr/share/applications/dev.wolklaw.SparkRun.desktop
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkRun.svg
grep -q '^MimeType=.*application/x-ms-dos-executable' /usr/share/applications/dev.wolklaw.SparkRun.desktop

report=$(/usr/bin/spark-run --self-test)
echo "$report"
grep -q '^self-test passed' <<<"$report"
if command -v rpm >/dev/null && rpm -q wine-core >/dev/null 2>&1; then
  echo "note: wine-core is installed in the image; Spark Run doesn't use it"
fi
echo "$(/usr/bin/spark-run --version) installed ($(du -sh /usr/lib/spark-run | cut -f1) in /usr/lib/spark-run)."
