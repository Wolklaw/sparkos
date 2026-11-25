#!/usr/bin/env bash
# Spark Firewall: the firewall in plain words (replaces firewall-config). Its source lives in
# this repo at files/spark-firewall.
#
# install.sh --deps installs it system-wide: the window, the root helper that polkit guards, the
# polkit action, the desktop entry and the icons. Installing never changes a firewall rule. The
# self-test only reads; the build fails if it or any file below is missing.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-firewall"
test -f "$SRC/install.sh" || { echo "Spark Firewall source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps

test -x /usr/bin/spark-firewall
test -x /usr/libexec/spark-firewall-helper
test -f /usr/share/applications/dev.wolklaw.SparkFirewall.desktop
test -f /usr/share/icons/hicolor/scalable/apps/dev.wolklaw.SparkFirewall.svg
test -f /usr/share/polkit-1/actions/dev.wolklaw.SparkFirewall.policy
command -v firewall-cmd >/dev/null
# The helper's path in the polkit action is what lets pkexec use it
grep -q 'exec.path">/usr/libexec/spark-firewall-helper<' \
  /usr/share/polkit-1/actions/dev.wolklaw.SparkFirewall.policy

# The helper refuses anything that isn't a known operation, before it runs a command
if echo '{"ops": [{"op": "service", "zone": "--reload", "name": "ssh", "add": true}]}' \
    | /usr/libexec/spark-firewall-helper apply 2>/dev/null; then
  echo "the helper accepted a bad operation"; exit 1
fi

# firewall-config is removed from the image (sparkos-apps.sh); firewalld itself stays

report=$(/usr/bin/spark-firewall --self-test)
echo "$report"
grep -q '^self-test passed' <<<"$report"
echo "$(/usr/bin/spark-firewall --version) installed."
