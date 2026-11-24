#!/usr/bin/env bash
# Spark Disks: drives, partitions, SMART health and USB image writing (replaces GNOME Disks and
# KDE Partition Manager). Its source lives in this repo at files/spark-disks.
#
# install.sh --deps installs it system-wide with udisks2, polkit, smartmontools and the mkfs
# tools. It talks to udisks over D-Bus as the user, so there is no service or root helper. The
# self-test lists drives and checks the safety rules on made-up ones; it changes nothing.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-disks"
test -f "$SRC/install.sh" || { echo "Spark Disks source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps

test -x /usr/bin/spark-disks
test -f /usr/share/applications/dev.wolklaw.SparkDisks.desktop
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkDisks.svg
command -v udisksctl >/dev/null
command -v smartctl >/dev/null
command -v lsblk >/dev/null
for tool in mkfs.ext4 mkfs.xfs mkfs.btrfs mkfs.vfat mkfs.exfat mkntfs; do
  command -v "$tool" >/dev/null || { echo "$tool isn't installed"; exit 1; }
done

report=$(/usr/bin/spark-disks --self-test)
echo "$report"
grep -q '^self-test passed' <<<"$report"
echo "$(/usr/bin/spark-disks --version) installed."
