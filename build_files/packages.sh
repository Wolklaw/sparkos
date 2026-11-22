#!/usr/bin/bash
# Containerfile step 4: packages.
#   packages.sh bazzite|fedora
#
# Both bases get the same SparkOS list. Each base then gets what differs:
#   bazzite  removes other projects' apps that Bazzite ships, and Universal Blue's updater
#   fedora   adds what Bazzite brought and Fedora Kinoite doesn't (ImageMagick, printing,
#            scanning, the gaming layer) and full video playback from RPM Fusion free
set -euo pipefail

base=${1:?base: bazzite or fedora}
dnf_install() { dnf -y --setopt=install_weak_deps=True install "$@"; }

dnf -y makecache

case "$base" in
bazzite)
  # - steam, lutris, waydroid, input-remapper, kate, kwrite, filelight, kfind, krdc, krfb,
  #   kwalletmanager5, kdebugsettings, khelpcenter: other projects' apps that Bazzite ships, all
  #   installable from the Store
  # - plasma-systemmonitor (Spark Monitor replaces it) and spectacle (Spark Snip captures through
  #   KWin): KDE apps a Spark app replaces; nothing else in the image requires them
  # - tailscale: a company's VPN service Bazzite preinstalls (docs/switching.md says how to add it)
  # - uupd and bazzite-updater: Universal Blue's updater and its window. Spark Update downloads
  #   and stages updates itself (SPARK_UPDATE_ENGINE=spark, step 5)
  dnf -y remove \
    steam lutris waydroid input-remapper kate kwrite filelight kfind krdc krfb \
    kwalletmanager5 kdebugsettings khelpcenter plasma-systemmonitor spectacle tailscale \
    uupd bazzite-updater
  ;;
fedora)
  # What Bazzite brought that SparkOS's scripts and the boot test use, from Fedora's own
  # repositories: ImageMagick (sparkos-theme.sh draws the wallpaper and boot splash), Ark, KDE
  # Connect, printing, scanning, libratbag (gaming mice), the gaming layer (gamescope, MangoHud,
  # GameMode), vulkaninfo/vainfo to check the drivers, and xdg-terminal-exec (how Plasma and apps
  # open the default terminal, Spark Terminal). Kinoite's other projects' apps are
  # removed by fedora-apps.sh (step 5).
  dnf_install \
    ImageMagick \
    ark kde-connect kio-gdrive \
    plasma-print-manager cups-browsed ipp-usb \
    sane-airscan sane-backends-drivers-scanners \
    libratbag-ratbagd \
    fastfetch jq xdg-terminal-exec \
    gamescope mangohud gamemode \
    vulkan-tools libva-utils

  # Video and music that play everywhere else: H.264, H.265, AAC, MP3. Fedora's own FFmpeg
  # leaves out the patented codecs; RPM Fusion free has the full one, and Mesa's video decode
  # for AMD/Intel GPUs with H.264/H.265 turned on. H.264 for browsers also comes from Cisco's
  # OpenH264 (Fedora's fedora-cisco-openh264 repository; Kinoite ships an empty stand-in).
  fedora=$(rpm -E %fedora)
  dnf_install \
    "https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-${fedora}.noarch.rpm"
  dnf -y makecache
  if rpm -q ffmpeg-free >/dev/null 2>&1; then
    dnf -y swap ffmpeg-free ffmpeg --allowerasing
  else
    dnf -y install --allowerasing ffmpeg-libs
  fi
  if rpm -q mesa-va-drivers >/dev/null 2>&1; then
    dnf -y swap mesa-va-drivers mesa-va-drivers-freeworld --allowerasing
  else
    dnf_install mesa-va-drivers-freeworld
  fi
  if rpm -q noopenh264 >/dev/null 2>&1; then
    dnf -y swap noopenh264 openh264 --enablerepo=fedora-cisco-openh264
  fi
  dnf_install --enablerepo=fedora-cisco-openh264 \
    gstreamer1-plugin-openh264 gstreamer1-plugin-libav \
    gstreamer1-plugins-bad-free gstreamer1-plugins-ugly-free
  rpm -q ffmpeg-libs mesa-va-drivers-freeworld openh264
  ;;
*)
  echo "unknown base '$base' (bazzite or fedora)"; exit 1 ;;
esac

# Both bases:
# - bubblewrap, socat: Claude Code's command sandbox
# - kdialog: folder picker for sparkos-claude and the install dialogs
# - fuse and fuse-libs (FUSE 2): AppImages mount themselves
# - rsms-inter-fonts: Inter, the interface font (Chakra Petch is in files/sparkos-theme/fonts)
# - python3.13 through libXtst: so Androidbox installs for the user (install.sh --user) with no
#   root: a Python that Qt for Python supports (Fedora 45's own is 3.15), and the libraries Qt,
#   SDL and Google's emulator load. Androidbox itself is not in the image.
dnf_install \
  bubblewrap socat kdialog fuse fuse-libs rsms-inter-fonts \
  python3.13 SDL2 xcb-util-cursor libxkbcommon-x11 libxkbfile \
  mesa-libGL mesa-libEGL mesa-libgbm alsa-lib pulseaudio-libs nss \
  libXcomposite libXcursor libXdamage libXi libXrandr libXtst
