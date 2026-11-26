#!/usr/bin/env bash
# Spark Update, SparkOS's own updater. Source: files/spark-update.
# Run it after the other app scripts (it lists their versions in release.json).
#
# Spark Update is the only updater, and never none:
#   1. Spark Update installed: spark-update-user.timer (every user: the notification), the
#      pkexec helper and polkit files, and spark-update.timer (stages images, updates Flatpak
#      apps).
#   2. rpm-ostreed's and bootc's own automatic updates checked to stay off.
#      (bootc-fetch-apply-updates would reboot.)
#   3. /usr/share/sparkos/release.json: what's in this image (Soot, FreeSuite, the Spark apps,
#      kernel, Mesa) and the release notes (files/whats-new.json), which the window
#      compares between versions.
# The self-test then fails the build unless spark-update.timer is on, the notification timer
# is on, and the image name is this image's own (ghcr.io/wolklaw/sparkos).
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-update"
test -f "$SRC/install.sh" || { echo "Spark Update source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps --no-test

# ── 2. Fedora's own automatic updates stay off ──
for timer in rpm-ostreed-automatic.timer bootc-fetch-apply-updates.timer; do
  if [ -e "/etc/systemd/system/timers.target.wants/$timer" ]; then
    systemctl disable "$timer" 2>/dev/null || rm -f "/etc/systemd/system/timers.target.wants/$timer"
    echo "--- disabled $timer"
  fi
done
if [ -f /etc/rpm-ostreed.conf ] && grep -Eq '^\s*AutomaticUpdatePolicy\s*=\s*(stage|check|apply)' /etc/rpm-ostreed.conf; then
  sed -i -E 's/^\s*AutomaticUpdatePolicy\s*=.*/AutomaticUpdatePolicy=none/' /etc/rpm-ostreed.conf
  echo "--- rpm-ostreed AutomaticUpdatePolicy set to none"
fi

# ── 3. What's in this image ──
install -d /usr/share/sparkos
# with the release notes (files/whats-new.json): the window lists every note newer than the
# version a PC had, so skipped updates' notes show too
/usr/bin/spark-update --write-release /usr/share/sparkos/release.json \
  --notes "${CONFIG_DIRECTORY:-/tmp/files}/whats-new.json"
test -s /usr/share/sparkos/release.json
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d.get("notes"), "no release notes"' \
  /usr/share/sparkos/release.json

# ── Checks: the build fails if any of this didn't take ──
test -x /usr/bin/spark-update
test -x /usr/libexec/spark-update-helper
test -f /usr/lib/systemd/system/spark-update.timer
test -f /usr/lib/systemd/user/spark-update-user.timer
test -e /etc/systemd/user/timers.target.wants/spark-update-user.timer
test -e /etc/systemd/system/timers.target.wants/spark-update.timer
test -f /usr/share/polkit-1/actions/dev.wolklaw.SparkUpdate.policy
test -f /usr/share/applications/dev.wolklaw.SparkUpdate.desktop
report=$(/usr/bin/spark-update --self-test) || { echo "$report"; echo "Spark Update's self-test failed"; exit 1; }
echo "$report"
grep -q '^self-test passed' <<<"$report"
grep -q '^others:    no other automatic updater is on' <<<"$report"
grep -qF "image:     ${IMAGE_REGISTRY:-ghcr.io/wolklaw}/${IMAGE_NAME:-sparkos} " <<<"$report"
grep -q '^updater:   Spark Update' <<<"$report"
echo "$(/usr/bin/spark-update --version) installed; updates run through Spark Update."
