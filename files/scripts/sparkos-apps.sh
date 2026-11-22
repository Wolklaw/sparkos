#!/usr/bin/env bash
# SparkOS ships only the owner's own apps (Soot, FreeSuite, Spark Snip, Spark Media). This removes what
# Bazzite would otherwise add on top of the platform: its first-boot Flatpak apps, its Portal
# window at login, and menu entries left behind by apps the recipe removes. Everything removed
# here can be installed from Spark Store.
set -oue pipefail

# Bazzite's first-boot app list (Firefox, Gwenview, Okular, KCalc, Haruna, Filelight, Gear Lever,
# Flatseal, Warehouse, ProtonUp-Qt, DistroShelf and overlay layers). Its manager still runs, for
# the Flathub setup and Flatpak permission fixes it does, but installs nothing.
for list in /usr/share/ublue-os/bazzite/flatpak/install; do
  if [ -f "$list" ]; then
    echo "--- emptying $list (was: $(tr '\n' ' ' < "$list"))"
    : > "$list"
  fi
done

# The Bazzite Portal that opens at every new user's first login, and its menu entries
rm -fv /etc/skel/.config/autostart/bazzite-portal.desktop
find /usr/share/applications -maxdepth 1 -iname '*portal*.desktop' ! -name 'org.freedesktop.*' -print -delete || true

# Menu entries and autostarts for Steam, which the recipe removes
rm -fv /etc/skel/.config/autostart/steam*.desktop
find /usr/share/applications -maxdepth 1 -iname 'bazzite-steam*.desktop' -print -delete || true

# Fail the build if a removed app is still installed
for pkg in steam lutris waydroid kate kwrite filelight; do
  if rpm -q "$pkg" >/dev/null 2>&1; then echo "still installed: $pkg"; exit 1; fi
done
test ! -s /usr/share/ublue-os/bazzite/flatpak/install
echo "No third-party apps preinstalled."
