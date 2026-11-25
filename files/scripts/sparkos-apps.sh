#!/usr/bin/env bash
# Containerfile step 5. The app policy on the Fedora Kinoite base: SparkOS ships only the
# owner's own apps. Kinoite installs a few other projects' apps as RPMs; they go. Each removal is skipped when the package isn't there, so
# the list is safe to keep as Kinoite changes. Every app here is installable from Flathub.
#
# Also removed:
#   plasma-setup        Fedora KDE's first-boot wizard; it opens before the SparkOS sign-in
#                       even when the installer already made a user (seen in the first boot test)
#   plasma-drkonqi      the crash reporter that sends reports to KDE's bug tracker
#   fedora-third-party, fedora-workstation-repositories
#                       Fedora's switch for Google Chrome, NVIDIA and Steam repositories
#   spectacle, plasma-systemmonitor
#                       replaced by Spark Snip and Spark Monitor
#   plasma-discover (and its flatpak, rpm-ostree and kns backends), plasma-discover-notifier
#                       Spark Store installs apps and Spark Update updates the system
#   konsole, konsole-part   Spark Terminal
#   ark                 Spark Archive
#   kde-connect, kdeconnectd   Spark Link
#   kinfocenter, kjournald     Spark Settings (About) and Spark Terminal's journalctl
#   gnome-disk-utility  Spark Disks
#   btrfs-assistant     snapshots are off; snapper's command line stays
#   firewall-config     Spark Firewall (firewalld itself stays)
# These were hidden from the menu for one release first (PLAN.md, "Replacing KDE", stage 1).
# Dolphin stays until Spark Files network places have been used daily. kmenuedit stays because
# plasma-desktop requires it (sparkos-cleanup.sh hides it), and so do the Emoji Selector and
# Klipper, which are part of plasma-desktop and plasma-workspace.
set -oue pipefail

remove=()
for pkg in firefox firefox-langpacks kwrite kate filelight kfind krdc krfb kwalletmanager5 \
           kdebugsettings khelpcenter kmahjongg kmines kpat elisa-player dragon \
           gwenview okular kcalc skanpage haruna plasma-welcome kcharselect kde-partitionmanager \
           plasma-setup plasma-drkonqi fedora-third-party fedora-workstation-repositories \
           spectacle plasma-systemmonitor \
           plasma-discover-notifier plasma-discover konsole konsole-part ark kde-connect \
           kdeconnectd kinfocenter kjournald gnome-disk-utility btrfs-assistant firewall-config; do
  rpm -q "$pkg" >/dev/null 2>&1 && remove+=("$pkg")
done
if [ ${#remove[@]} -gt 0 ]; then
  echo "--- removing: ${remove[*]}"
  dnf -y remove "${remove[@]}"
else
  echo "--- none of Kinoite's third-party apps are installed as RPMs"
fi

# The on-screen keyboard: plasma-workspace requires the package (and it requires its settings
# page, kcm-plasma-keyboard), so both stay, but KWin starts
# /usr/share/applications/org.kde.plasma.keyboard.desktop as its default input method whenever
# that file exists (about 190 MB of RAM on a desktop with a real keyboard). Without the file
# KWin starts nothing.
rm -f /usr/share/applications/org.kde.plasma.keyboard.desktop

# Flatpak: Kinoite 45 configures no remote in the image; build_files/flathub.sh adds Flathub (step 6)
# (the boot test lists the remotes the user gets).
for pkg in "${remove[@]}"; do
  if rpm -q "$pkg" >/dev/null 2>&1; then echo "still installed: $pkg"; exit 1; fi
done
# The removals must not have taken the platform with them
rpm -q plasma-workspace plasma-login-manager dolphin plasma-systemsettings flatpak kwin \
  kio-gdrive kaccounts-integration-qt6 firewalld snapper
# nor what packages.sh installed for SparkOS that Firefox also used (H.264 in Soot)
rpm -q mozilla-openh264
if [ -e /usr/share/applications/org.kde.plasma.keyboard.desktop ]; then
  echo "the on-screen keyboard would still start"; exit 1
fi
# The hidden apps are gone, with their sub-packages and menu entries
for pkg in konsole konsole-part ark ark-libs kde-connect kde-connect-libs kdeconnectd \
           plasma-discover plasma-discover-libs plasma-discover-flatpak plasma-discover-kns \
           plasma-discover-rpm-ostree plasma-discover-notifier kinfocenter kjournald \
           gnome-disk-utility btrfs-assistant firewall-config spectacle plasma-systemmonitor; do
  if rpm -q "$pkg" >/dev/null 2>&1; then echo "still installed: $pkg"; exit 1; fi
done
for id in org.kde.konsole org.kde.ark org.kde.discover org.kde.kdeconnect.app org.kde.kinfocenter \
          org.kde.kjournaldbrowser org.gnome.DiskUtility btrfs-assistant firewall-config; do
  if [ -e "/usr/share/applications/$id.desktop" ]; then echo "$id.desktop is still there"; exit 1; fi
done
echo "No third-party apps preinstalled as RPMs."
