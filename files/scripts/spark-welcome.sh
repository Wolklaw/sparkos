#!/usr/bin/env bash
# Spark Welcome, the SparkOS first-login helper (game launchers and apps from Flathub on click,
# files from Windows, a check of this PC). Its source lives in this repo at files/spark-welcome.
#
# Installed system-wide, its autostart entry goes in /etc/xdg/autostart, so it opens once at
# each new user's first login; `spark-welcome --first-login` exits at once after that. The
# self-test must pass: it needs flatpak, udisksctl, lsblk, Tk and the autostart entry.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-welcome"
test -f "$SRC/install.sh" || { echo "Spark Welcome source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps

test -x /usr/bin/spark-welcome
test -f /usr/share/applications/dev.wolklaw.SparkWelcome.desktop
test -f /etc/xdg/autostart/dev.wolklaw.SparkWelcome.desktop
echo "$(/usr/bin/spark-welcome --version) installed."
