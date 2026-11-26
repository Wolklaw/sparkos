#!/usr/bin/env bash
# Containerfile step 5. The app policy: SparkOS ships only the owner's own apps. Fedora's atomic
# desktop base (base-atomic) installs a few other projects' apps and switches as RPMs; they go.
# Each removal is skipped when the package isn't there, so the list is safe to keep as the base
# changes. Every app here is installable from Flathub.
#
#   firefox, firefox-langpacks   Soot is the browser
#   fedora-third-party, fedora-workstation-repositories
#                                Fedora's switch for Google Chrome, NVIDIA and Steam repositories
#
# Until 2026-11-26 SparkOS was built on Fedora Kinoite, and this list also took out KDE's apps
# (Konsole, Ark, Discover, Spectacle, KDE Connect...). The base has none of them now, and
# sparkos-no-kde.sh (the last step) fails the build if any KDE package comes back.
set -oue pipefail

remove=()
for pkg in firefox firefox-langpacks fedora-third-party fedora-workstation-repositories \
           gnome-disk-utility btrfs-assistant firewall-config; do
  rpm -q "$pkg" >/dev/null 2>&1 && remove+=("$pkg")
done
if [ ${#remove[@]} -gt 0 ]; then
  echo "--- removing: ${remove[*]}"
  # On base-atomic, Firefox is what pulled in openh264 (H.264 in Soot); marked as wanted, dnf
  # doesn't take it out with Firefox as an unused dependency
  dnf -y mark user mozilla-openh264
  dnf -y remove "${remove[@]}"
else
  echo "--- none of the base's third-party apps are installed as RPMs"
fi

# Flatpak: the base configures no remote in the image; build_files/flathub.sh adds Flathub (step 6)
# (the boot test lists the remotes the user gets).
for pkg in "${remove[@]}"; do
  if rpm -q "$pkg" >/dev/null 2>&1; then echo "still installed: $pkg"; exit 1; fi
done
# The removals must not have taken the platform with them
rpm -q flatpak firewalld snapper fuse-sshfs rclone greetd
# nor what packages.sh installed for SparkOS that Firefox also used (H.264 in Soot)
rpm -q mozilla-openh264
for id in org.mozilla.firefox firefox org.gnome.DiskUtility btrfs-assistant firewall-config; do
  if [ -e "/usr/share/applications/$id.desktop" ]; then echo "$id.desktop is still there"; exit 1; fi
done
echo "No third-party apps preinstalled as RPMs."
