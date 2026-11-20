#!/usr/bin/env bash
# PROTOTYPE (recipes/recipe-fedora.yml). The app policy on a Fedora Kinoite base: SparkOS ships
# only the owner's own apps. Kinoite installs a few other projects' apps as RPMs; they go, like
# sparkos-apps.sh removes Bazzite's. Each removal is skipped when the package isn't there, so
# the list is safe to keep as Kinoite changes. Everything here is installable from Flathub.
set -oue pipefail

remove=()
for pkg in firefox firefox-langpacks kwrite kate filelight kfind krdc krfb kwalletmanager5 \
           kdebugsettings khelpcenter kmahjongg kmines kpat elisa-player dragon \
           gwenview okular kcalc skanpage haruna plasma-welcome; do
  rpm -q "$pkg" >/dev/null 2>&1 && remove+=("$pkg")
done
if [ ${#remove[@]} -gt 0 ]; then
  echo "--- removing: ${remove[*]}"
  dnf -y remove "${remove[@]}"
else
  echo "--- none of Kinoite's third-party apps are installed as RPMs"
fi

# Fedora's own Flatpak remote (Fedora-built Flatpaks) stays as Kinoite ships it; the
# default-flatpaks module adds Flathub next to it. What the user sees is measured in the boot test.
for pkg in "${remove[@]}"; do
  if rpm -q "$pkg" >/dev/null 2>&1; then echo "still installed: $pkg"; exit 1; fi
done
echo "No third-party apps preinstalled as RPMs."
