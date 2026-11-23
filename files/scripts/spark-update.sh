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
# Exactly one updater, and never none. SPARK_UPDATE_ENGINE picks who downloads images:
#   uupd   (default, the initial release) Bazzite's uupd stays on and does the downloading,
#          daily at 04:00. Spark Update adds the "SparkOS updated" notification, the window
#          (what changed, Check now = uupd-manual.service, Restart, Roll back) and the
#          rollback through pkexec. spark-update.timer stays off.
#   spark  Spark Update's own timer stages images and updates Flatpak apps; uupd.timer is
#          disabled and a drop-in makes uupd.service and uupd-manual.service run Spark Update
#          instead, so `ujust update` still works and the two never run side by side.
# SparkOS builds with spark since 2026-11-20 (the Containerfile sets SPARK_UPDATE_ENGINE and
# removes the uupd package), after the boot test staged and booted a real update with Spark
# Update's own engine. If the variable isn't set and uupd is missing, this still picks spark,
# so updates never stop.
#
# Both engines:
#   1. Spark Update installed: spark-update-user.timer (every user: the notification), the
#      pkexec helper and polkit files, and spark-update.timer (enabled only under spark).
#   3. Bazzite Updater hidden from the menu (Spark Update's window has Check now).
#   4. bazzite-rollback-helper replaced by a short note that points to Spark Update; its
#      `rollback` and `current` still work, through Spark Update. (It offered stock
#      ublue-os/bazzite images, which would leave SparkOS.)
#   5. rpm-ostreed's and bootc's own automatic updates checked to stay off.
#   6. /usr/share/sparkos/release.json: what's in this image (Soot, FreeSuite, the Spark apps,
#      kernel, Mesa, Plasma) and the release notes (files/whats-new.json), which the window
#      compares between versions.
# The self-test then fails the build unless exactly one updater's timer is on, the
# notification timer is on, and the image name is this image's own (ghcr.io/wolklaw/sparkos).
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}/spark-update"
test -f "$SRC/install.sh" || { echo "Spark Update source not found at $SRC"; exit 1; }

ENGINE="${SPARK_UPDATE_ENGINE:-uupd}"
case "$ENGINE" in
  uupd|spark) ;;
  *) echo "SPARK_UPDATE_ENGINE must be uupd or spark, not $ENGINE"; exit 1 ;;
esac
if [ "$ENGINE" = uupd ] && [ ! -f /usr/lib/systemd/system/uupd.timer ]; then
  echo "--- uupd isn't in this image: Spark Update downloads updates itself (engine spark)"
  ENGINE=spark
fi
echo "--- updater: $ENGINE"

bash "$SRC/install.sh" --deps --no-test --engine "$ENGINE"

# ── 2. Who downloads ──
if [ "$ENGINE" = uupd ]; then
  # keep Bazzite's updater on, exactly as it ships
  if [ ! -e /etc/systemd/system/timers.target.wants/uupd.timer ]; then
    systemctl enable uupd.timer
    echo "--- uupd.timer was off; enabled it"
  fi
  rm -f /usr/lib/systemd/system/uupd.service.d/50-sparkos.conf \
        /usr/lib/systemd/system/uupd-manual.service.d/50-sparkos.conf
  echo "--- uupd.timer stays on (daily at 04:00); Spark Update notifies and rolls back"
else
  if [ -f /usr/lib/systemd/system/uupd.service ]; then
    systemctl disable uupd.timer 2>/dev/null || true
    rm -f /etc/systemd/system/timers.target.wants/uupd.timer /usr/lib/systemd/system/timers.target.wants/uupd.timer
    for unit in uupd.service uupd-manual.service; do
      install -d "/usr/lib/systemd/system/$unit.d"
      cat > "/usr/lib/systemd/system/$unit.d/50-sparkos.conf" <<'EOF'
# SparkOS: Spark Update is the updater (files/scripts/spark-update.sh). Whatever starts
# this unit (`ujust update`, the Bazzite Updater) runs a Spark Update check now instead.
[Service]
ExecStart=
ExecStart=/usr/bin/spark-update --system-run --now stage
Restart=no
# `ujust update` shows this unit's journal through jq, which keeps only JSON lines
Environment=SPARK_UPDATE_LOG_JSON=1
StateDirectory=spark-update
StateDirectoryMode=0755
LogsDirectory=spark-update
LogsDirectoryMode=0755
EOF
    done
    echo "--- uupd.timer disabled; uupd.service and uupd-manual.service run Spark Update"
  else
    # Removing the uupd package leaves its enable link behind, pointing at nothing
    rm -f /etc/systemd/system/timers.target.wants/uupd.timer /usr/lib/systemd/system/timers.target.wants/uupd.timer
    # uupd isn't in the image (SparkOS removes the package). `ujust update` still runs
    # /usr/libexec/uupd-update: point it at Spark Update's Check now, which active local users
    # may start without a password (50-spark-update.rules).
    if [ -x /usr/bin/ujust ]; then
      cat > /usr/libexec/uupd-update <<'EOF'
#!/bin/sh
# SparkOS: `ujust update` downloads and stages the next SparkOS with Spark Update
# (files/scripts/spark-update.sh). Restart afterwards to use it.
systemctl start --wait spark-update-now@stage.service
status=$?
spark-update --status
exit $status
EOF
      chmod 0755 /usr/libexec/uupd-update
      echo "--- uupd isn't installed; ujust update runs Spark Update"
    fi
    if systemctl list-unit-files --no-legend 'uupd*' | grep -q .; then
      echo "uupd units are still in the image:"; systemctl list-unit-files --no-legend 'uupd*'; exit 1
    fi
  fi
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
echo "Switching to another image (rebase) isn't offered: SparkOS follows its own signed image."
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
if [ "$ENGINE" = uupd ]; then
  test -e /etc/systemd/system/timers.target.wants/uupd.timer
  test ! -e /etc/systemd/system/timers.target.wants/spark-update.timer
else
  test -e /etc/systemd/system/timers.target.wants/spark-update.timer
  test ! -e /etc/systemd/system/timers.target.wants/uupd.timer
fi
test -f /usr/share/polkit-1/actions/dev.wolklaw.SparkUpdate.policy
test -f /usr/share/applications/dev.wolklaw.SparkUpdate.desktop
report=$(/usr/bin/spark-update --self-test) || { echo "$report"; echo "Spark Update's self-test failed"; exit 1; }
echo "$report"
grep -q '^self-test passed' <<<"$report"
grep -q '^others:    no other automatic updater is on' <<<"$report"
grep -qF "image:     ${IMAGE_REGISTRY:-ghcr.io/wolklaw}/${IMAGE_NAME:-sparkos} " <<<"$report"
if [ "$ENGINE" = uupd ]; then
  grep -q "^updater:   Universal Blue's uupd" <<<"$report"
else
  grep -q '^updater:   Spark Update' <<<"$report"
fi
echo "$(/usr/bin/spark-update --version) installed; updates run through $ENGINE."
