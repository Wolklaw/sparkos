#!/usr/bin/env bash
# Fedora base only (Containerfile step 5, SPARKOS_BASE=fedora). SparkOS's own gaming layer on
# plain Fedora, for AMD.
#
# What build_files/packages.sh already adds from Fedora: gamescope, MangoHud, GameMode.
# Fedora's kernel already has the controller drivers SparkOS's hardware needs (xpad,
# hid-playstation, hid-nintendo, hid-steam) and Fedora's Mesa has RADV and RadeonSI.
#
# What plain Fedora lacks: the udev rules that let Steam (and Steam from Flathub) talk to
# controllers and VR headsets through hidraw/uinput. On Bazzite they come from the steam-devices
# package; on Fedora that package is only in RPM Fusion. Valve publishes the same rules under
# the MIT licence at github.com/ValveSoftware/steam-devices; this takes them from a pinned commit,
# checked against known SHA-256 sums, so no third-party package repository is needed.
set -oue pipefail

COMMIT=22ec85e5ff5ea2e15c56d71a41bcbef46356cd60
URL="https://raw.githubusercontent.com/ValveSoftware/steam-devices/$COMMIT"
RULES=/usr/lib/udev/rules.d
mkdir -p /usr/share/sparkos/fedora-base
DOC=/usr/share/licenses/sparkos-steam-devices
mkdir -p "$RULES" "$DOC"

while read -r sum name dest; do
  curl -fsSL --retry 5 --retry-delay 5 -o "$dest" "$URL/$name"
  echo "$sum  $dest" | sha256sum -c -
done <<EOS
284930f83cf8fde8a247057d46f48083d5e4aefc23a54310db02cfc2dbe42e50 60-steam-input.rules $RULES/60-steam-input.rules
e12cda322c9f5f7c6336d8048264877690d3488e1b0f1b750cce18a836160420 60-steam-vr.rules $RULES/60-steam-vr.rules
4a8b10a725095d8be78a130dd21984d70976915a658da8fe158d3bc20ca03585 LICENSE $DOC/LICENSE
EOS
echo "steam-devices $COMMIT" > "$DOC/SOURCE"

# uinput must load for Steam Input's virtual controllers
mkdir -p /usr/lib/modules-load.d
echo uinput > /usr/lib/modules-load.d/sparkos-uinput.conf

# Kernel settings for games. Bazzite sets these in /usr/lib/sysctl.d (60-kernel.conf,
# 70-gaming.conf, 80-inotify.conf); Fedora's defaults are max_map_count 1048576 and split-lock
# mitigation on, which slows some Windows games under Proton.
cat > /usr/lib/sysctl.d/70-sparkos-gaming.conf <<'EOS'
# SparkOS gaming defaults (same values as Bazzite)
kernel.split_lock_mitigate = 0
vm.max_map_count = 2147483642
fs.inotify.max_user_instances = 8192
fs.inotify.max_user_watches = 524288
EOS

# Fail the build if the gaming layer is incomplete
for bin in gamescope mangohud gamemoded; do
  command -v "$bin" >/dev/null || { echo "missing $bin"; exit 1; }
done
test -s "$RULES/60-steam-input.rules"

# A record of what the gaming layer is, for the boot test and docs/fedora-base.md
{
  echo "kernel: $(rpm -q kernel-core --qf '%{VERSION}-%{RELEASE} (%{VENDOR})\n' | tail -1)"
  rpm -q mesa-dri-drivers mesa-vulkan-drivers mesa-va-drivers gamescope mangohud gamemode \
    linux-firmware amd-gpu-firmware amd-ucode-firmware --qf '%{NAME} %{VERSION}-%{RELEASE} (%{VENDOR})\n' 2>&1 || true
  echo "sysctl: $(grep -hv '^#' /usr/lib/sysctl.d/70-sparkos-gaming.conf | paste -sd ' ')"
} | tee /usr/share/sparkos/fedora-base/gaming-layer.txt
echo "Gaming layer ready."
