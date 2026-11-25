#!/usr/bin/env bash
# Spark Clock's wake-from-sleep helper: the only root part of Spark Clock. The app itself is
# optional and installs per user (files/spark-clock); this is its image half, so that alarms can
# wake a sleeping PC. It is NOT files/scripts/spark-clock.sh on purpose: a script with the app's
# own name would make Spark Store treat Spark Clock as built in.
#
# Installs /usr/libexec/spark-clock-wake (sets or clears one systemd timer with WakeSystem=true,
# named after the caller's uid, for a time at most 8 days away) and the polkit action that lets
# the person at the PC run it without a password. Nothing runs at build time; no timer is set.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-clock/system"
test -f "$SRC/usr/libexec/spark-clock-wake" || { echo "Spark Clock wake helper not found at $SRC"; exit 1; }

install -Dm 0755 "$SRC/usr/libexec/spark-clock-wake" /usr/libexec/spark-clock-wake
install -Dm 0644 "$SRC/usr/share/polkit-1/actions/dev.wolklaw.SparkClock.wake.policy" \
  /usr/share/polkit-1/actions/dev.wolklaw.SparkClock.wake.policy

test -x /usr/libexec/spark-clock-wake
# The helper's path in the polkit action is what lets pkexec use it
grep -q 'exec.path">/usr/libexec/spark-clock-wake<' \
  /usr/share/polkit-1/actions/dev.wolklaw.SparkClock.wake.policy

# It refuses anything but a plain future epoch within 8 days, and anything outside pkexec,
# before it runs a command
for bad in "set" "set 1" "set --help" "set 99999999999" "set 1700000000" "reboot" "set 1 2"; do
  # shellcheck disable=SC2086
  if /usr/libexec/spark-clock-wake $bad 2>/dev/null; then
    echo "the wake helper accepted: $bad"; exit 1
  fi
done
future=$(( $(date +%s) + 3600 ))
if /usr/libexec/spark-clock-wake set "$future" 2>/dev/null; then
  echo "the wake helper ran outside pkexec"; exit 1
fi
echo "Spark Clock wake helper installed."
