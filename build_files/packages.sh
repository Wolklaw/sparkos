#!/usr/bin/bash
# Containerfile step 4: packages, on the Fedora Kinoite base.
#
# First what Bazzite brought when SparkOS was built on it (until 2026-11-23) and Kinoite doesn't
# have (ImageMagick, printing, scanning, the gaming layer, device rules, everyday tools, umu-run,
# tuning), and full video playback from RPM Fusion free. Then SparkOS's own list.
set -euo pipefail

dnf_install() { dnf -y --setopt=install_weak_deps=True install "$@"; }

dnf -y makecache

# What Bazzite brought that SparkOS's scripts and the boot test use, from Fedora's own
# repositories: ImageMagick (sparkos-theme.sh draws the wallpaper and boot splash), kio-gdrive
# (Google Drive in Spark Files), printing, scanning, libratbag (gaming mice), the gaming layer (gamescope, MangoHud,
# GameMode), vulkaninfo/vainfo to check the drivers, and xdg-terminal-exec (how Plasma and apps
# open the default terminal, Spark Terminal). Kinoite's other projects' apps are
# removed by sparkos-apps.sh (step 5).
dnf_install \
  ImageMagick \
  kio-gdrive \
  plasma-print-manager cups-browsed ipp-usb \
  sane-airscan sane-backends-drivers-scanners \
  libratbag-ratbagd \
  fastfetch jq xdg-terminal-exec \
  gamescope mangohud gamemode \
  vulkan-tools libva-utils

# What Spark Settings runs (files/spark-settings): printers (lpadmin, lpinfo), the sound test
# tone and per-app volume, PCI names for About, and the D-Bus watcher for live Bluetooth.
# Kinoite has most of these already; naming them keeps that true. (The power profile goes
# through busctl to tuned-ppd; power-profiles-daemon would conflict with it.)
dnf_install cups-client pipewire-utils pulseaudio-utils pciutils dbus-tools

# mokutil: "spark secureboot" reads Secure Boot state and enrolls the module-signing certificate
# with it (Kinoite usually has it; named here so that stays true).
dnf_install mokutil

# Device access rules Bazzite ships that Fedora packages itself (all tiny, no dependencies):
# - steam-devices: Valve's controller and VR rules, so Steam (also from Flathub) can use them
# - openrgb-udev-rules: RGB controllers (ASUS AURA, NZXT, ...) for OpenRGB without root
# - solaar-udev: Logitech receivers and devices (the G502 too) for Solaar without root
# - ntsync-autoload: loads the ntsync module at boot, for Wine and Proton's NT sync
# The rules Fedora doesn't package (game-devices-udev, the not-a-joystick list, wheel
# settings) are in files/device-rules, installed by fedora-gaming.sh.
dnf_install steam-devices openrgb-udev-rules solaar-udev ntsync-autoload

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

# Tools Bazzite ships that SparkOS and its owner use, from Fedora's own repositories:
# distrobox (other distributions' software in a container), btop and lm_sensors (`sensors`:
# temperatures), tmux, fzf, cabextract (unpacks Windows .cab files; winetricks needs it).
dnf_install distrobox btop lm_sensors tmux fzf cabextract

# Package parity: everything else Bazzite has that someone could miss, from Fedora's own
# repositories (docs/fedora-base.md, "Package parity", lists each and what was left out).
# files/scripts/fedora-parity.sh adds the ones Fedora doesn't package (winetricks, the Nerd
# Font symbols, ls-iommu, ...). About 680 MiB in all, 220 of it the compilers, 146 ROCm.
# - command-line tools: nvtop (GPU use), fish, just, vim, squashfs-tools, duf, glow, gum, f3
#   (fake USB stick check), evtest, lshw, powerstat, stress-ng, usbip, v4l-utils (webcams),
#   wmctrl, xdotool, ydotool, xwininfo, wlr-randr, tcpdump, traceroute, ncurses-term (fish's
#   terminal list), lzip, unrar, 7zip-standalone (7za), icoutils (Windows icons, for game
#   shortcuts), mtools, symlinks, msedit, libinput-utils, libimobiledevice-utils (iPhones),
#   libbluray-utils, sbsigntools and grub2-tools-extra (boot files), udica, python3-pip
# - yad and zenity: the dialogs winetricks, Proton tools and scripts open
dnf_install \
  nvtop fish just vim-enhanced squashfs-tools duf glow gum f3 evtest lshw powerstat \
  stress-ng usbip v4l-utils wmctrl xdotool ydotool xwininfo wlr-randr tcpdump traceroute \
  ncurses-term lzip unrar 7zip-standalone icoutils mtools symlinks msedit libinput-utils \
  libimobiledevice-utils libbluray-utils sbsigntools grub2-tools-extra udica python3-pip \
  yad zenity
# - unrar: Fedora's `unrar` is unrar-free 0.3, which can't decrypt RAR, so password-protected
#   RAR (which Spark Archive hands to unrar) wouldn't open. RARLAB's unrar 7, as on Bazzite,
#   comes from RPM Fusion nonfree. That repository is used for this one package and isn't
#   left on the system; the daily image build keeps unrar current.
dnf_install "https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-${fedora}.noarch.rpm"
dnf -y upgrade --setopt=rpmfusion-nonfree.includepkgs=unrar \
  --setopt=rpmfusion-nonfree-updates.includepkgs=unrar unrar
dnf -y remove rpmfusion-nonfree-release
[ "$(rpm -q --qf '%{VENDOR}' unrar)" = "RPM Fusion" ] \
  || { echo "unrar isn't RPM Fusion's: $(rpm -q unrar)"; exit 1; }
# - gcc, gcc-c++, make: Bazzite has a C/C++ compiler; Rust (cargo links with cc), pip and npm
#   packages with native parts, and Claude Code's builds need one
dnf_install gcc gcc-c++ make
# - disks and system: snapper (snapshots, off until set up, as on Bazzite; its GUI,
#   btrfs-assistant, is not installed),
#   btrfsmaintenance (scrub and balance timers, off as on Bazzite), bees (btrfs dedup, off),
#   greenboot (goes back to the previous system after three
#   failed boots of an update; fedora-parity.sh sets it up), Cockpit's pages (web admin, for
#   Cockpit's own client or container; no web server is installed, as on Bazzite)
dnf_install \
  snapper btrfsmaintenance bees \
  greenboot greenboot-default-health-checks \
  cockpit-system cockpit-files cockpit-networkmanager cockpit-podman cockpit-storaged
# - security keys: sign in or sudo with a YubiKey or other U2F key, and YubiKey's manager
dnf_install pam-u2f pamu2fcfg pam_yubico yubikey-manager
# - desktop: xdg-native-messaging-proxy (browser extensions talking to apps, for Flatpak
#   browsers), flatpak-spawn, dbus-x11 (dbus-launch for older apps), gvfs (trash, network
#   folders and phones in GTK apps), wsdd (Windows network discovery), openxr (VR runtime
#   loader), libFAudio, libnsl and libxcrypt-compat (older games and Linux programs),
#   bluez-cups (Bluetooth printers)
dnf_install \
  xdg-native-messaging-proxy flatpak-spawn dbus-x11 gvfs wsdd openxr libFAudio libnsl \
  libxcrypt-compat bluez-cups
# - sound: alsa-firmware and alsa-tools-firmware (firmware for sound cards that load it, with
#   fxload), PipeWire's SOFA spatial audio filter, the CAPS LADSPA plugins (EasyEffects and
#   filter chains)
dnf_install alsa-firmware alsa-tools-firmware pipewire-module-filter-chain-sofa ladspa-caps-plugins
# - AMD GPU compute: ROCm's OpenCL (Blender, DaVinci Resolve, Darktable, AI tools), with
#   rocm-clinfo, rocm-smi and amdsmi to check the GPU. Fedora lets every user open /dev/kfd.
dnf_install rocm-opencl rocm-clinfo rocm-smi amdsmi
# - fonts Bazzite ships: Fira Code, Lato, Twemoji, and Noto for Balinese, Javanese, Sundanese
#   and Egyptian hieroglyphs (Noto CJK is already in Kinoite, as variable fonts; named here
#   because Spark Run maps Windows CJK fonts to "Noto Sans CJK SC/TC/JP/KR")
dnf_install \
  google-noto-sans-cjk-vf-fonts fira-code-fonts lato-fonts twitter-twemoji-fonts google-noto-sans-balinese-fonts \
  google-noto-sans-javanese-fonts google-noto-sans-sundanese-fonts \
  google-noto-sans-egyptian-hieroglyphs-fonts
# - text recognition in the languages Bazzite has (English and French come with Spark Scan)
dnf_install \
  tesseract-langpack-ces tesseract-langpack-chi_sim tesseract-langpack-chi_sim_vert \
  tesseract-langpack-chi_tra tesseract-langpack-chi_tra_vert tesseract-langpack-deu \
  tesseract-langpack-ell tesseract-langpack-ita tesseract-langpack-jpn \
  tesseract-langpack-jpn_vert tesseract-langpack-nld tesseract-langpack-pol \
  tesseract-langpack-por tesseract-langpack-rus tesseract-langpack-spa tesseract-langpack-tur
# From RPM Fusion free and Cisco, like the video codecs above: HEIC photos (iPhone pictures;
# Fedora's libheif can't decode HEVC), aptX for Bluetooth headphones, and OpenH264 for
# Firefox-based browsers
dnf_install libheif-freeworld pipewire-codec-aptx
dnf_install --enablerepo=fedora-cisco-openh264 mozilla-openh264
# Kinoite already has it as a dependency of Firefox, so removing Firefox (sparkos-apps.sh)
# would take it too; marking it installed on purpose keeps it
dnf -y mark user mozilla-openh264

# 32-bit graphics drivers. Proton runs a 32-bit Windows program (Battle.net, many older
# games, most launchers' helper processes) as a 32-bit Linux process, and the Steam Runtime
# container umu-run starts takes its GPU drivers from the host. Without these, Vulkan and
# OpenGL fail in every 32-bit process ("DxvkInstance::createInstance: Failed to create Vulkan
# instance") and the program quits with no window. Bazzite shipped them; Kinoite doesn't.
# Steam from Flathub brings its own; this is for umu-run (Spark Games, Spark Run).
dnf_install mesa-dri-drivers.i686 mesa-vulkan-drivers.i686 vulkan-loader.i686 \
  mesa-libGL.i686 mesa-libEGL.i686 mesa-libgbm.i686
test -s /usr/share/vulkan/icd.d/radeon_icd.i686.json \
  || { echo "32-bit Vulkan driver missing"; exit 1; }

# Tuning Bazzite has (files/scripts/fedora-tuning.sh sets the rest up), from Fedora:
# vkBasalt (Vulkan post-processing layer, off unless ENABLE_VKBASALT=1) and python3-pyinotify
# (for ds-inhibit, the DualSense touchpad fix in files/ds-inhibit)
dnf_install vkBasalt python3-pyinotify

# From Terra (Fyra Labs, which builds Bazzite's copies), because Fedora doesn't package them:
# - umu-launcher: umu-run, which Spark Games uses to start Windows games with Proton
# - dmemcg-booster, plasma-foreground-booster-dmemcg and its library kcgroups-dmemcg: Valve's
#   and KDE's VRAM protection for the focused game (fedora-tuning.sh turns it on)
# The Terra repository is used for these packages only (includepkgs) and isn't left on the
# system, so Terra's Mesa and other builds never replace Fedora's. Its signing key is checked
# against Terra's fingerprint.
terra_url="https://repos.fyralabs.com/terra${fedora}"
terra_fpr=C2AC02124AF114F086592E3C8DDE7D14C1C23D8C   # "Terra 45 <security@fyralabs.com>"
GNUPGHOME=$(mktemp -d)
export GNUPGHOME
curl -fsSL --retry 3 -o /tmp/terra.asc "${terra_url}/key.asc"
terra_key=$(gpg --show-keys --with-colons /tmp/terra.asc)
[[ $terra_key == *"fpr:::::::::${terra_fpr}:"* ]] \
  || { echo "Terra's key isn't ${terra_fpr} (new Fedora release? update terra_fpr)"; exit 1; }
dnf_install \
  --repofrompath="terra,${terra_url}" --setopt=terra.gpgcheck=1 \
  --setopt=terra.gpgkey=file:///tmp/terra.asc \
  --setopt=terra.includepkgs=umu-launcher,dmemcg-booster,kcgroups-dmemcg,plasma-foreground-booster-dmemcg \
  umu-launcher dmemcg-booster plasma-foreground-booster-dmemcg
# dnf imported Terra's key into rpm's keyring; nothing else in the image should trust it
rpmkeys --delete "${terra_fpr,,}"
rm -rf /tmp/terra.asc "$GNUPGHOME"
unset GNUPGHOME
rpm -q umu-launcher dmemcg-booster plasma-foreground-booster-dmemcg kcgroups-dmemcg

# SparkOS's own list:
# - python3-liquidctl, openrgb, fwupd: what Spark Controller (files/spark-controller) drives.
#   liquidctl is imported as a Python library (NZXT and other USB coolers and lighting), OpenRGB
#   runs as a command (ASUS Aura, mice, keyboards, memory), fwupd gives device firmware from
#   LVFS. Fedora Kinoite already has fwupd; naming it keeps that true. OpenRGB's own window is
#   hidden (spark-controller.sh): Spark Controller replaces it. Its udev rules come from
#   openrgb-udev-rules above.
# - bubblewrap, socat: Claude Code's command sandbox
# - kdialog: folder picker for sparkos-claude and the install dialogs
# - fuse and fuse-libs (FUSE 2): AppImages mount themselves
# - rsms-inter-fonts: Inter, the interface font (Chakra Petch is in files/sparkos-theme/fonts)
# - python3.13 through libXtst: so Androidbox installs for the user (install.sh --user) with no
#   root: a Python that Qt for Python supports (Fedora 45's own is 3.15), and the libraries Qt,
#   SDL and Google's emulator load. Androidbox itself is not in the image.
dnf_install \
  python3-liquidctl openrgb fwupd \
  bubblewrap socat kdialog fuse fuse-libs rsms-inter-fonts \
  python3.13 SDL2 xcb-util-cursor libxkbcommon-x11 libxkbfile \
  mesa-libGL mesa-libEGL mesa-libgbm alsa-lib pulseaudio-libs nss \
  libXcomposite libXcursor libXdamage libXi libXrandr libXtst

# Virtual machines (`spark virt setup` turns them on): libvirt's modular daemons for QEMU/KVM,
# the default NAT network's definition, QEMU, UEFI firmware (OVMF) and a software TPM (Windows
# 11 guests ask for both). They are in the image rather than layered with rpm-ostree on the PC
# because layering ties the PC to one exact base image, makes every update slower and can fail
# when Fedora's repositories and the image drift apart; in the image the build tests it once.
# Nothing runs by default: the sockets are turned off below, so an idle PC pays only the disk
# (on plain Kinoite this is 109 packages, a 59 MiB download). The management window is Spark
# Boxes (files/spark-boxes, installed by files/scripts/spark-boxes.sh); it talks to this libvirt
# at qemu:///system through python3-libvirt and shows a machine's screen with spice-gtk3. Those
# two add 8 packages: 4 MiB installed, a 1 MiB download (measured on Fedora 45 with GTK and
# libvirt-client already there). Virtual Machine Manager is no longer suggested.
dnf_install \
  libvirt-daemon-driver-qemu libvirt-daemon-driver-network libvirt-daemon-driver-storage-core \
  libvirt-daemon-driver-nodedev libvirt-daemon-driver-secret libvirt-daemon-config-network \
  libvirt-client qemu-kvm edk2-ovmf swtpm swtpm-tools \
  python3-libvirt spice-gtk3
# Fedora's preset may turn some of these on at install; they stay off until `spark virt setup`.
for unit in /usr/lib/systemd/system/virt*.socket /usr/lib/systemd/system/libvirt*.socket \
            /usr/lib/systemd/system/libvirt-guests.service; do
  [ -e "$unit" ] || continue
  systemctl disable "${unit##*/}" 2>/dev/null || true
done
# The firewall side: libvirt ships its own firewalld "libvirt" zone (accepts forwarding, lets
# guests reach the PC's DHCP and DNS) and puts virbr0 in it when the network starts, so the
# closed "sparkos" default zone needs no change.
test -f /usr/lib/firewalld/zones/libvirt.xml
test -f /usr/lib/firewalld/policies/libvirt-to-host.xml
test -f /usr/share/libvirt/networks/default.xml
test -f /usr/share/polkit-1/rules.d/50-libvirt.rules
rpm -q libvirt-daemon-driver-qemu qemu-kvm edk2-ovmf swtpm python3-libvirt spice-gtk3
if find /etc/systemd/system -path '*.wants/*' \( -name 'virt*.socket' -o -name 'libvirt*' \) | grep -q .; then
  echo "a libvirt unit is still enabled"; exit 1
fi
