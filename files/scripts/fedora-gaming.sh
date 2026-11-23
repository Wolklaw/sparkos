#!/usr/bin/env bash
# Containerfile step 5. SparkOS's own gaming layer on Fedora, for AMD.
#
# What build_files/packages.sh already adds from Fedora: gamescope, MangoHud, GameMode.
# Fedora's kernel already has the controller drivers SparkOS's hardware needs (xpad,
# hid-playstation, hid-nintendo, hid-steam) and Fedora's Mesa has RADV and RadeonSI.
#
# Device access rules (who may open a controller, wheel or RGB device). Bazzite ships them as
# packages; on Fedora:
# - from Fedora's own packages (packages.sh): steam-devices (Valve's controller and VR rules),
#   openrgb-udev-rules, solaar-udev, ntsync-autoload
# - from files/device-rules, here: the rules Fedora doesn't package, copied unchanged from their
#   projects (each folder's SOURCE says from where, at which version, under which licence):
#   game-devices-udev (more controllers: 8BitDo, PowerA, Hori, Nacon, ... and wheels),
#   udev-joystick-blacklist (keyboards and mice the kernel wrongly reports as joysticks,
#   Keychron's included) and Oversteer's Logitech wheel settings rule.
set -oue pipefail

RULES=/usr/lib/udev/rules.d
SRC="${CONFIG_DIRECTORY:-/tmp/files}/device-rules"
LIC=/usr/share/licenses/sparkos-device-rules
mkdir -p "$RULES" /usr/share/sparkos/fedora-base

for dir in game-devices-udev udev-joystick-blacklist oversteer; do
  install -m 0644 -t "$RULES" "$SRC/$dir"/*.rules
  mkdir -p "$LIC/$dir"
  for doc in SOURCE LICENSE; do
    if [ -f "$SRC/$dir/$doc" ]; then install -m 0644 "$SRC/$dir/$doc" "$LIC/$dir/$doc"; fi
  done
done

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
rpm -q steam-devices openrgb-udev-rules solaar-udev ntsync-autoload
for f in 60-steam-input.rules 60-openrgb.rules 42-logitech-unify-permissions.rules \
  71-8bitdo-gdu.rules 51-these-are-not-joysticks-rm.rules 99-logitech-wheel-perms.rules; do
  test -s "$RULES/$f" || { echo "missing $RULES/$f"; exit 1; }
done
grep -qx ntsync /usr/lib/modules-load.d/ntsync.conf

# A record of what the gaming layer is, for the boot test and docs/fedora-base.md
{
  echo "kernel: $(rpm -q kernel-core --qf '%{VERSION}-%{RELEASE} (%{VENDOR})\n' | tail -1)"
  rpm -q mesa-dri-drivers mesa-vulkan-drivers mesa-va-drivers gamescope mangohud gamemode \
    linux-firmware amd-gpu-firmware amd-ucode-firmware --qf '%{NAME} %{VERSION}-%{RELEASE} (%{VENDOR})\n' 2>&1 || true
  rpm -q steam-devices openrgb-udev-rules solaar-udev ntsync-autoload \
    --qf '%{NAME} %{VERSION}-%{RELEASE} (%{VENDOR})\n'
  echo "device rules from files/device-rules: $(cd "$SRC" && ls -- */*.rules | wc -l) files"
  echo "sysctl: $(grep -hv '^#' /usr/lib/sysctl.d/70-sparkos-gaming.conf | paste -sd ' ')"
} | tee /usr/share/sparkos/fedora-base/gaming-layer.txt
echo "Gaming layer ready."
