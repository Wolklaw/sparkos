#!/usr/bin/env bash
# Spark Backup: snapshots of /home on a schedule, a copy on another drive, and file restore.
# Its source lives in this repo at files/spark-backup.
#
# install.sh --deps installs it system-wide: the window, the root service and timer (the timer
# is NOT enabled; the window enables it when the owner saves a schedule), the polkit action and
# the desktop entry. The build never creates a snapshot and never writes to a drive.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-backup"
test -f "$SRC/install.sh" || { echo "Spark Backup source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps

test -x /usr/bin/spark-backup
test -x /usr/libexec/spark-backup-helper
test -f /usr/share/applications/dev.wolklaw.SparkBackup.desktop
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkBackup.svg
test -f /usr/lib/systemd/system/spark-backup.service
test -f /usr/lib/systemd/system/spark-backup.timer
test -f /usr/share/polkit-1/actions/dev.wolklaw.SparkBackup.policy
# The helper's path in the polkit action is what lets pkexec use it
grep -q 'exec.path">/usr/libexec/spark-backup-helper<' \
  /usr/share/polkit-1/actions/dev.wolklaw.SparkBackup.policy

# Nothing runs until the owner saves a schedule
test ! -e /etc/spark-backup/config.json
[ "$(systemctl is-enabled spark-backup.timer 2>/dev/null || true)" != enabled ] \
  || { echo "spark-backup.timer is enabled before any schedule was saved"; exit 1; }

report=$(/usr/bin/spark-backup --self-test)
echo "$report"
grep -q '^self-test passed' <<<"$report"
echo "$(/usr/bin/spark-backup --version) installed."
