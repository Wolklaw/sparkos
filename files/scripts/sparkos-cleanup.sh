#!/usr/bin/env bash
# Release 2 cleanup: SparkOS relies less on other people's products (PLAN.md, Independence
# roadmap). The recipe removes the packages; this step fixes what they leave behind, turns off
# calls home to services SparkOS doesn't control, and fails the build if any of it is still
# there. Runs after the Spark apps are installed.
set -oue pipefail

# --- Spark Monitor replaces Plasma System Monitor (removed in the recipe)
# Spark Monitor keeps Ctrl+Shift+Esc (the Windows key) and also takes the keys Plasma gave its
# own monitor: Meta+Esc (Plasma 6) and Ctrl+Esc (Plasma 5 and earlier).
if rpm -q plasma-systemmonitor >/dev/null 2>&1; then echo "plasma-systemmonitor is still installed"; exit 1; fi
MON=/usr/share/applications/dev.wolklaw.SparkMonitor.desktop
sed -i --follow-symlinks 's/^X-KDE-Shortcuts=.*/X-KDE-Shortcuts=Ctrl+Shift+Esc,Meta+Esc,Ctrl+Esc/' "$MON"
grep -qx 'X-KDE-Shortcuts=Ctrl+Shift+Esc,Meta+Esc,Ctrl+Esc' /usr/share/kglobalaccel/dev.wolklaw.SparkMonitor.desktop
# No other desktop entry may claim those keys
others=$(grep -lE '^X-KDE-Shortcuts=(.*,)?(Ctrl\+Shift\+Esc|Meta\+Esc|Ctrl\+Esc)(,|$)' \
  /usr/share/applications/*.desktop /usr/share/kglobalaccel/*.desktop 2>/dev/null \
  | grep -v 'dev.wolklaw.SparkMonitor.desktop$' || true)
[ -z "$others" ] || { echo "these also claim Spark Monitor's keys:"; echo "$others"; exit 1; }

# --- Tailscale (removed in the recipe): its package repository and any unit left enabled
if rpm -q tailscale >/dev/null 2>&1; then echo "tailscale is still installed"; exit 1; fi
rm -fv /etc/yum.repos.d/tailscale.repo
find /etc/systemd /usr/lib/systemd -name 'tailscale*' -print -delete
if systemctl list-unit-files --no-legend 'tailscale*' | grep -q .; then echo "a Tailscale unit is still there"; exit 1; fi

# --- No calling home to services SparkOS doesn't control
# Fedora's usage counting: the rpm-ostree timer (10-sparkos.preset keeps it off at first boot)
# and DNF's countme on Fedora's and Terra's repositories.
systemctl disable rpm-ostree-countme.timer
state=$(systemctl is-enabled rpm-ostree-countme.timer || true)
[ "$state" = disabled ] || { echo "rpm-ostree-countme.timer is $state"; exit 1; }
grep -q '^disable rpm-ostree-countme.timer$' /usr/lib/systemd/system-preset/10-sparkos.preset
for repo in /usr/share/dnf5/repos.d/*.repo /etc/yum.repos.d/*.repo; do
  if [ -f "$repo" ]; then sed -i 's/^countme=1$/countme=0/' "$repo"; fi
done
if grep -l '^countme=1' /usr/share/dnf5/repos.d/*.repo /etc/yum.repos.d/*.repo 2>/dev/null; then
  echo "countme is still on in the files above"; exit 1
fi
# KDE's "Get New Stuff" (store.kde.org) is hidden by [KDE Action Restrictions] in /etc/xdg/kdeglobals
grep -qx 'ghns=false' /etc/xdg/kdeglobals
# Homebrew's update timers: off until `sparkos-dev-setup --brew` (00-sparkos-homebrew.preset)
for timer in brew-update.timer brew-upgrade.timer; do
  [ -f "/usr/lib/systemd/system/$timer" ] || continue
  systemctl disable "$timer" 2>/dev/null || true
  grep -qx "disable $timer" /usr/lib/systemd/system-preset/00-sparkos-homebrew.preset
  test ! -e "/etc/systemd/system/timers.target.wants/$timer"
done

# No COPR repository on: SparkOS doesn't layer packages; the image is built in CI.
if grep -l '^enabled=1' /etc/yum.repos.d/_copr* 2>/dev/null; then
  echo "a COPR repository is still switched on (above)"; exit 1
fi

# --- Out of the app menu (still installed; the commands and the platform keep working)
# KDE Connect, Ark, Discover, Konsole, GNOME Disks, Info Center, Journald Browser, Btrfs
# Assistant and firewall-config are gone from the image (sparkos-apps.sh), so they are not here.
# What stays installed because Plasma needs it, and is hidden:
#   the Emoji Selector (Spark Emoji has Meta+. since spark-emoji.sh) and the Menu Editor
#   (Spark Launcher is the menu); both are parts of plasma-desktop
# Command-line tools that need no menu entry (they run in Spark Terminal): btop, nvtop,
#   Microsoft Edit (msedit), yad's Icon Browser
# The Foreground Booster's settings
HIDE=(org.kde.plasma.emojier org.kde.kmenuedit
      btop nvtop com.microsoft.edit yad-icon-browser org.kde.foreground-booster
      org.kde.kfontview org.kde.kfontinst)
for id in "${HIDE[@]}"; do
  entry=/usr/share/applications/$id.desktop
  [ -f "$entry" ] || { echo "--- $id.desktop is not installed, nothing to hide"; continue; }
  # replace any NoDisplay in the [Desktop Entry] group (actions have their own groups)
  sed -i --follow-symlinks -e '/^\[Desktop Entry\]/,/^\[/{/^NoDisplay=/d}' \
    -e '/^\[Desktop Entry\]/a NoDisplay=true' "$entry"
  # read the group first: `sed | grep -q` fails under pipefail when grep stops early
  group=$(sed -n '/^\[Desktop Entry\]/,/^\[/p' "$entry")
  grep -qx 'NoDisplay=true' <<<"$group" || { echo "$id.desktop is still in the menu"; exit 1; }
done
echo "--- hid ${#HIDE[@]} menu entries"

# --- The hidden apps are gone from the image (sparkos-apps.sh removes them; nothing installed
# since may bring one back)
for pkg in konsole konsole-part ark ark-libs kde-connect kde-connect-libs kdeconnectd \
           plasma-discover plasma-discover-libs plasma-discover-flatpak plasma-discover-kns \
           plasma-discover-rpm-ostree plasma-discover-notifier kinfocenter kjournald \
           gnome-disk-utility btrfs-assistant firewall-config spectacle plasma-systemmonitor; do
  if rpm -q "$pkg" >/dev/null 2>&1; then echo "$pkg is back in the image"; exit 1; fi
done
for id in org.kde.konsole org.kde.ark org.kde.discover org.kde.kdeconnect.app org.kde.kinfocenter \
          org.kde.kjournaldbrowser org.gnome.DiskUtility gnome-disk-image-mounter \
          gnome-disk-image-writer btrfs-assistant firewall-config; do
  if [ -e "/usr/share/applications/$id.desktop" ]; then echo "$id.desktop is back"; exit 1; fi
done
echo "--- the hidden apps are gone"

# NetworkManager's connectivity check (fedoraproject.org, every 5 minutes) stays for now: it is
# what detects hotel and café Wi-Fi sign-in pages. The owner decides (see the release2-cleanup PR).

echo "Release 2 cleanup done."
