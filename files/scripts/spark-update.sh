#!/usr/bin/env bash
# Spark Update, SparkOS's own updater, and switching off Bazzite's. Source: files/spark-update.
# Run it after the other app scripts (it lists their versions in release.json).
#
# What Bazzite runs today (read from the image on 2026-11-20, Bazzite F45.20261117):
#   uupd.timer          enabled; daily at 04:00 (+ up to 15 min) runs uupd.service: bootc
#                       upgrade (staged, no reboot), Flatpak (system and user), brew, distrobox.
#                       Polkit (uupd.rules) lets anyone start uupd.service.
#   uupd-manual.service what `ujust update` starts (through /usr/libexec/uupd-update).
#   bazzite-updater     "Bazzite Updater", a Qt app in the menu that runs uupd.
#   bazzite-rollback-helper  a terminal menu (ujust/brh) to roll back or rebase; it lists
#                       and offers stock ublue-os/bazzite images, which would leave SparkOS.
#   rpm-ostreed-automatic.timer, bootc-fetch-apply-updates.timer: present, disabled
#                       (AutomaticUpdatePolicy=none). bootc-fetch-apply-updates would reboot.
#   brew-update/brew-upgrade timers: Homebrew's own packages, not the system; left alone.
#
# The switch, so there is exactly one updater:
#   1. Spark Update installed: spark-update.timer (root, hourly look; checks every 6 h by
#      default), spark-update-user.timer (every user: their Flatpak apps and the
#      notification), the pkexec helper and polkit files.
#   2. uupd.timer disabled. A drop-in makes uupd.service and uupd-manual.service run Spark
#      Update instead, so `ujust update` and anything else that starts them still works and
#      the two never run side by side. (The uupd package stays: removing it is the recipe's
#      job; see the PR.)
#   3. Bazzite Updater hidden from the menu (it drives uupd directly).
#   4. bazzite-rollback-helper replaced by a short note that points to Spark Update; its
#      `rollback` and `current` still work, through Spark Update.
#   5. rpm-ostreed's and bootc's own automatic updates checked to stay off.
#   6. /usr/share/sparkos/release.json: what's in this image (Soot, FreeSuite, the Spark apps,
#      kernel, Mesa, Plasma), which the window compares between versions.
# The self-test then fails the build if Spark Update's timers aren't on or another updater is.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-update"
test -f "$SRC/install.sh" || { echo "Spark Update source not found at $SRC"; exit 1; }

bash "$SRC/install.sh" --deps --no-test

# ── 2. uupd: off, and pointed at Spark Update ──
if [ -f /usr/lib/systemd/system/uupd.service ]; then
  systemctl disable uupd.timer 2>/dev/null || true
  rm -f /etc/systemd/system/timers.target.wants/uupd.timer
  for unit in uupd.service uupd-manual.service; do
    install -d "/usr/lib/systemd/system/$unit.d"
    cat > "/usr/lib/systemd/system/$unit.d/50-sparkos.conf" <<'EOF'
# SparkOS: Spark Update is the updater (files/scripts/spark-update.sh). Whatever starts
# this unit (`ujust update`, the Bazzite Updater) runs a Spark Update check now instead.
[Service]
ExecStart=
ExecStart=/usr/bin/spark-update --system-run --now stage
Restart=no
StateDirectory=spark-update
StateDirectoryMode=0755
LogsDirectory=spark-update
LogsDirectoryMode=0755
EOF
  done
  echo "--- uupd.timer disabled; uupd.service and uupd-manual.service run Spark Update"
else
  echo "--- uupd isn't in this image; nothing to switch off"
fi

# ── 3. Bazzite Updater out of the menu ──
for entry in /usr/share/applications/io.github.rfrench3.bazzite-updater.desktop; do
  if [ -f "$entry" ] && ! grep -q '^NoDisplay=true' "$entry"; then
    sed -i '/^\[Desktop Entry\]/a NoDisplay=true' "$entry"
    echo "--- hid $(basename "$entry") from the menu"
  fi
done

# ── 4. The rollback helper points to Spark Update ──
for helper in /usr/bin/bazzite-rollback-helper /usr/bin/brh; do
  [ -e "$helper" ] || continue
  if [ -L "$helper" ]; then
    target=$(readlink -f "$helper")
    [ "$target" = /usr/bin/bazzite-rollback-helper ] && continue    # replaced below/above
  fi
  cat > "$helper" <<'EOF'
#!/bin/sh
# SparkOS: Spark Update handles updates and rollbacks (files/scripts/spark-update.sh).
case "$1" in
  rollback) exec spark-update --rollback ;;
  current) exec spark-update --status ;;
esac
echo "SparkOS updates and rollbacks are in Spark Update: open it from the menu, or run"
echo "  spark-update --status     what's running and what starts next"
echo "  spark-update --rollback   start the previous version at the next restart"
echo "Switching to another image (rebase) isn't offered: SparkOS follows ghcr.io/wolklaw/sparkos."
exit 1
EOF
  chmod 0755 "$helper"
  echo "--- $helper now points to Spark Update"
done

# ── 5. Fedora's own automatic updates stay off ──
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

# ── 6. What's in this image ──
install -d /usr/share/sparkos
/usr/bin/spark-update --write-release /usr/share/sparkos/release.json
test -s /usr/share/sparkos/release.json

# ── Checks: the build fails if any of this didn't take ──
test -x /usr/bin/spark-update
test -x /usr/libexec/spark-update-helper
test -f /usr/lib/systemd/system/spark-update.timer
test -f /usr/lib/systemd/user/spark-update-user.timer
test -e /etc/systemd/system/timers.target.wants/spark-update.timer
test -e /etc/systemd/user/timers.target.wants/spark-update-user.timer
test ! -e /etc/systemd/system/timers.target.wants/uupd.timer
test -f /usr/share/polkit-1/actions/dev.wolklaw.SparkUpdate.policy
test -f /usr/share/applications/dev.wolklaw.SparkUpdate.desktop
report=$(/usr/bin/spark-update --self-test)
echo "$report"
grep -q '^self-test passed' <<<"$report"
grep -q '^others:    no other automatic updater is on' <<<"$report"
echo "$(/usr/bin/spark-update --version) installed; Bazzite's updater is off."
