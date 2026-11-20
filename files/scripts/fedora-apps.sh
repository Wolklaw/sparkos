#!/usr/bin/env bash
# PROTOTYPE (recipes/recipe-fedora.yml). The app policy on a Fedora Kinoite base: SparkOS ships
# only the owner's own apps. Kinoite installs a few other projects' apps as RPMs; they go, like
# sparkos-apps.sh removes Bazzite's. Each removal is skipped when the package isn't there, so
# the list is safe to keep as Kinoite changes. Every app here is installable from Flathub.
#
# Also removed, because SparkOS on Bazzite doesn't have them either:
#   plasma-setup        Fedora KDE's first-boot wizard; it opens before the SparkOS sign-in
#                       even when the installer already made a user (seen in the first boot test)
#   plasma-drkonqi      the crash reporter that sends reports to KDE's bug tracker
#   fedora-third-party, fedora-workstation-repositories
#                       Fedora's switch for Google Chrome, NVIDIA and Steam repositories
#   spectacle, plasma-systemmonitor
#                       replaced by Spark Snip and Spark Monitor, as in the real recipe
set -oue pipefail

remove=()
for pkg in firefox firefox-langpacks kwrite kate filelight kfind krdc krfb kwalletmanager5 \
           kdebugsettings khelpcenter kmahjongg kmines kpat elisa-player dragon \
           gwenview okular kcalc skanpage haruna plasma-welcome kcharselect kde-partitionmanager \
           plasma-setup plasma-drkonqi fedora-third-party fedora-workstation-repositories \
           spectacle plasma-systemmonitor; do
  rpm -q "$pkg" >/dev/null 2>&1 && remove+=("$pkg")
done
if [ ${#remove[@]} -gt 0 ]; then
  echo "--- removing: ${remove[*]}"
  dnf -y remove "${remove[@]}"
else
  echo "--- none of Kinoite's third-party apps are installed as RPMs"
fi

# Flatpak: Kinoite 45 configures no remote in the image; the default-flatpaks module adds Flathub
# (the boot test lists the remotes the user gets).
for pkg in "${remove[@]}"; do
  if rpm -q "$pkg" >/dev/null 2>&1; then echo "still installed: $pkg"; exit 1; fi
done
# The removals must not have taken the platform with them
rpm -q plasma-workspace plasma-login-manager dolphin konsole ark plasma-systemsettings \
  plasma-discover flatpak kde-connect kwin
echo "No third-party apps preinstalled as RPMs."
