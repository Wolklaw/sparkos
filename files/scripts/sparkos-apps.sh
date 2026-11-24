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
#   kcm-plasma-keyboard the on-screen keyboard's settings page (the keyboard itself: see below)
#   plasma-discover-notifier
#                       Discover's update checker in the tray; Spark Update sends the update
#                       notification (Discover itself stays, hidden, for now)
set -oue pipefail

remove=()
for pkg in firefox firefox-langpacks kwrite kate filelight kfind krdc krfb kwalletmanager5 \
           kdebugsettings khelpcenter kmahjongg kmines kpat elisa-player dragon \
           gwenview okular kcalc skanpage haruna plasma-welcome kcharselect kde-partitionmanager \
           plasma-setup plasma-drkonqi fedora-third-party fedora-workstation-repositories \
           spectacle plasma-systemmonitor \
           kcm-plasma-keyboard plasma-discover-notifier; do
  rpm -q "$pkg" >/dev/null 2>&1 && remove+=("$pkg")
done
if [ ${#remove[@]} -gt 0 ]; then
  echo "--- removing: ${remove[*]}"
  dnf -y remove "${remove[@]}"
else
  echo "--- none of Kinoite's third-party apps are installed as RPMs"
fi

# The on-screen keyboard: plasma-workspace requires the package, so it stays, but KWin starts
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
rpm -q plasma-workspace plasma-login-manager dolphin konsole ark plasma-systemsettings \
  plasma-discover flatpak kde-connect kwin
# nor what packages.sh installed for SparkOS that Firefox also used (H.264 in Soot)
rpm -q mozilla-openh264
if [ -e /usr/share/applications/org.kde.plasma.keyboard.desktop ]; then
  echo "the on-screen keyboard would still start"; exit 1
fi
echo "No third-party apps preinstalled as RPMs."
