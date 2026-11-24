#!/usr/bin/env bash
# Spark Settings, SparkOS's settings app, in place of KDE System Settings. Its source lives in
# this repo at files/spark-settings.
#
# install.sh --deps installs it system-wide and runs --self-test; the build fails if that or any
# file below is missing. Then it takes over from System Settings:
#   - the real /usr/bin/systemsettings and /usr/bin/kcmshell6 are moved to
#     /usr/libexec/sparkos/kde-settings/ and small stand-ins put in their place. Plasma opens
#     settings by running those two names (for example the desktop's "Configure Display
#     Settings" runs "systemsettings kcm_kscreen"), so the stand-ins send the modules Spark
#     Settings has a page for to that page, and hand every other module to the real tool
#   - the menu entries for System Settings are hidden (NoDisplay) but System Settings stays
#     installed: it is the fallback, and "spark-settings --kde" opens it
# The dock pin is in the look-and-feel layout (files/system).
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

# ── Plasma's entry points go to Spark Settings ──
REAL=/usr/libexec/sparkos/kde-settings
mkdir -p "$REAL"
for tool in systemsettings kcmshell6; do
  if [ -x "/usr/bin/$tool" ] && ! grep -q 'spark-settings --route' "/usr/bin/$tool" 2>/dev/null; then
    mv "/usr/bin/$tool" "$REAL/$tool"
  fi
  if [ -x "$REAL/$tool" ]; then
    printf '#!/bin/sh\nexec /usr/bin/spark-settings --route %s -- "$@"\n' "$tool" > "/usr/bin/$tool"
    chmod 0755 "/usr/bin/$tool"
    echo "--- /usr/bin/$tool now goes through Spark Settings (original in $REAL)"
  else
    echo "--- $tool is not installed: nothing to route"
  fi
done

# ── System Settings out of the menu (still installed) ──
for entry in /usr/share/applications/systemsettings.desktop /usr/share/applications/kdesystemsettings.desktop; do
  if [ -f "$entry" ] && ! grep -q '^NoDisplay=true' "$entry"; then
    sed -i '/^\[Desktop Entry\]/a NoDisplay=true' "$entry"
    echo "--- hid $(basename "$entry") from the menu"
  fi
done

# the stand-ins reach the real tools (offscreen: the build has no display)
if [ -x "$REAL/kcmshell6" ]; then
  # read the list first: `kcmshell6 --list | grep -q` fails under pipefail when grep stops early
  kcms=$(QT_QPA_PLATFORM=offscreen /usr/bin/kcmshell6 --list) || kcms=''
  grep -q 'kcm_' <<<"$kcms" || { echo "kcmshell6 does not run through the stand-in"; exit 1; }
fi
echo "$(/usr/bin/spark-settings --version) installed."
