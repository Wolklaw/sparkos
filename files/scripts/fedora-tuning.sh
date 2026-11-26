#!/usr/bin/env bash
# Containerfile step 5. The system tuning Bazzite had that plain Fedora Kinoite doesn't, as SparkOS's own config. docs/fedora-base.md ("Performance
# and tuning") lists every Bazzite tweak and why each one is here or left out.
#
# Packages for this are installed by build_files/packages.sh: vkBasalt and python3-pyinotify
# (Fedora), dmemcg-booster (Terra, build time only).
# The gaming sysctls (split lock, max_map_count, inotify) are in fedora-gaming.sh.
set -oue pipefail

SRC="${CONFIG_DIRECTORY:-/tmp/files}"
mkdir -p /usr/lib/sysctl.d /usr/lib/modules-load.d /usr/lib/modprobe.d /usr/lib/udev/rules.d \
  /usr/lib/tmpfiles.d /usr/lib/systemd/zram-generator.conf.d /usr/lib/systemd/system.conf.d \
  /usr/lib/systemd/user.conf.d /usr/lib/systemd/system/fstrim.service.d \
  /etc/security/limits.d /usr/share/sparkos/fedora-base

# Network: BBR congestion control, MTU probing, IPv6 privacy addresses (Bazzite's
# 75-networking.conf). Fedora builds BBR as a module, so it loads at boot first.
cat > /usr/lib/sysctl.d/75-sparkos-network.conf <<'EOS'
# SparkOS network defaults (same values as Bazzite)
net.ipv4.tcp_congestion_control = bbr
net.ipv4.tcp_mtu_probing = 1
net.ipv6.conf.all.use_tempaddr = 2
net.ipv6.conf.default.use_tempaddr = 2
EOS
echo tcp_bbr > /usr/lib/modules-load.d/sparkos-tcp-bbr.conf

# Swap in RAM: zstd, half the RAM up to 16 GiB (Bazzite's zram-generator.conf). Fedora's
# default is lzo-rle and at most 8 GiB.
cat > /usr/lib/systemd/zram-generator.conf.d/50-sparkos.conf <<'EOS'
# SparkOS zram (same as Bazzite)
[zram0]
compression-algorithm = zstd
zram-size = min(ram / 2, 16384)
EOS

# Disk I/O schedulers (Bazzite's 60-schedulers.rules): kyber for SSDs and NVMe, BFQ for hard
# drives and SD cards. Fedora's 60-block-scheduler.rules gives every sd* disk BFQ, SSDs too;
# this file sorts after it, so it wins.
cat > /usr/lib/udev/rules.d/60-sparkos-io-scheduler.rules <<'EOS'
# SparkOS I/O schedulers (same as Bazzite)
ACTION!="add|change", GOTO="sparkos_io_end"
SUBSYSTEM!="block", GOTO="sparkos_io_end"
ENV{DEVTYPE}!="disk", GOTO="sparkos_io_end"
# SATA SSD
KERNEL=="sd*", ATTR{queue/rotational}=="0", ATTR{queue/scheduler}="kyber"
# NVMe
KERNEL=="nvme*", ATTR{queue/rotational}=="0", ATTR{queue/scheduler}="kyber"
# SD card
KERNEL=="mmcblk*", ATTR{queue/rotational}=="0", ATTR{queue/scheduler}="bfq"
# Hard drive
KERNEL=="sd*", ATTR{queue/rotational}=="1", ATTR{queue/scheduler}="bfq"
LABEL="sparkos_io_end"
EOS

# Btrfs gives back half-empty data chunks on its own, so the disk doesn't report "full" while
# space is free (Bazzite's btrfs-reclaim.conf)
cat > /usr/lib/tmpfiles.d/sparkos-btrfs-reclaim.conf <<'EOS'
w /sys/fs/btrfs/*/allocation/data/dynamic_reclaim - - - - 1
w /sys/fs/btrfs/*/allocation/data/periodic_reclaim - - - - 1
EOS

# The weekly TRIM: every mounted filesystem, not only the ones in /etc/fstab, where "/" is
# read-only on an image system (Bazzite's fstrim drop-in; Fedora Atomic tracker issue 81)
cat > /usr/lib/systemd/system/fstrim.service.d/50-sparkos-mounted.conf <<'EOS'
[Service]
ExecStart=
ExecStart=/usr/bin/fstrim --listed-in /proc/self/mountinfo --verbose --quiet-unsupported
EOS

# mcelog only in a real machine (Bazzite's override): in a VM there is no AMD EDAC driver, so its
# own "skip on AMD" condition doesn't apply and it fails with "CPU is unsupported" at every boot.
# On the PC it is already skipped because edac_mce_amd is loaded.
mkdir -p /usr/lib/systemd/system/mcelog.service.d
printf '[Unit]\nConditionVirtualization=no\n' > /usr/lib/systemd/system/mcelog.service.d/50-sparkos-no-vm.conf

# Shutdown doesn't wait 45 s for a stuck service: 15 s, as on Bazzite
for scope in system user; do
  printf '[Manager]\nDefaultTimeoutStopSec=15s\n' \
    > "/usr/lib/systemd/${scope}.conf.d/50-sparkos-timeout.conf"
done

# The sign-in screen doesn't wait for the network. Fedora enables nfs-client.target, whose
# rpc-statd-notify.service waits for network-online.target; that holds back remote-fs.target and
# so systemd-user-sessions and the sign-in screen, by about 6 s on the PC (NetworkManager's wait
# for a connection). SparkOS has no NFS mounts; mounting one by hand still works, because
# mount.nfs starts rpc-statd itself when it needs it.
systemctl disable nfs-client.target
grep -qx 'disable nfs-client.target' /usr/lib/systemd/system-preset/10-sparkos.preset

# Locked memory up to 2 GiB per process (Bazzite's memlock.conf; Fedora's is 8 MiB). Emulators
# such as RPCS3 and some anti-cheat and VR software need more.
cat > /etc/security/limits.d/90-sparkos-memlock.conf <<'EOS'
* hard memlock 2147484
* soft memlock 2147484
EOS

# Xbox controllers over Bluetooth: Bazzite turns L2CAP ERTM off with a kernel argument
# (bluetooth.disable_ertm=1). Fedora builds Bluetooth as a module, so a module option does it
# without changing the kernel command line.
echo 'options bluetooth disable_ertm=1' > /usr/lib/modprobe.d/sparkos-bluetooth.conf

# ds-inhibit (Valve's, from SteamOS): while Steam has a DualShock 4 or DualSense open, its
# touchpad stops moving the mouse pointer. Copied unchanged into files/ds-inhibit.
install -m 0755 "$SRC/ds-inhibit/ds-inhibit" /usr/bin/ds-inhibit
install -m 0644 "$SRC/ds-inhibit/ds-inhibit.service" /usr/lib/systemd/system/ds-inhibit.service
install -Dm 0644 -t /usr/share/licenses/sparkos-ds-inhibit "$SRC/ds-inhibit/LICENSE" "$SRC/ds-inhibit/SOURCE"
systemctl enable ds-inhibit.service

# VRAM for games (Valve's dmemcg-booster, as on SteamOS): when video memory runs out, games
# keep theirs and other apps are moved out first. Fedora's kernel has the dmem cgroup controller
# with amdgpu support. KDE's foreground booster, which also favoured the focused window, went
# with Plasma (sparkos-no-kde.sh).
systemctl enable dmemcg-booster-system.service
systemctl --global enable dmemcg-booster-user.service

# Fail the build if the tuning layer is incomplete
rpm -q vkBasalt python3-pyinotify dmemcg-booster
python3 -c 'import pyinotify'
for f in /usr/lib/sysctl.d/75-sparkos-network.conf /usr/lib/udev/rules.d/60-sparkos-io-scheduler.rules \
  /usr/lib/systemd/zram-generator.conf.d/50-sparkos.conf /usr/lib/tmpfiles.d/sparkos-btrfs-reclaim.conf \
  /usr/lib/systemd/system/fstrim.service.d/50-sparkos-mounted.conf \
  /usr/lib/systemd/system.conf.d/50-sparkos-timeout.conf /usr/lib/systemd/user.conf.d/50-sparkos-timeout.conf \
  /etc/security/limits.d/90-sparkos-memlock.conf /usr/lib/modprobe.d/sparkos-bluetooth.conf \
  /usr/lib/modules-load.d/sparkos-tcp-bbr.conf /usr/bin/ds-inhibit \
  /usr/lib/systemd/system/mcelog.service.d/50-sparkos-no-vm.conf; do
  test -s "$f" || { echo "missing $f"; exit 1; }
done
kver=$(rpm -q kernel-core --qf '%{VERSION}-%{RELEASE}.%{ARCH}\n' | tail -1)
for opt in CONFIG_CGROUP_DMEM=y CONFIG_TCP_CONG_BBR=m CONFIG_MQ_IOSCHED_KYBER=y CONFIG_IOSCHED_BFQ=y; do
  grep -qx "$opt" "/usr/lib/modules/$kver/config" || { echo "kernel $kver: $opt not set"; exit 1; }
done
state=$(systemctl is-enabled nfs-client.target || true)
[ "$state" = disabled ] || { echo "nfs-client.target is $state"; exit 1; }
for unit in ds-inhibit.service dmemcg-booster-system.service; do
  [ "$(systemctl is-enabled "$unit")" = enabled ] || { echo "$unit not enabled"; exit 1; }
done
[ "$(systemctl --global is-enabled dmemcg-booster-user.service)" = enabled ] \
  || { echo "dmemcg-booster-user.service not enabled"; exit 1; }

# A record for docs/fedora-base.md and the boot test
{
  rpm -q vkBasalt dmemcg-booster tuned tuned-ppd \
    zram-generator --qf '%{NAME} %{VERSION}-%{RELEASE} (%{VENDOR})\n'
  echo "sysctl: $(grep -hv '^#' /usr/lib/sysctl.d/75-sparkos-network.conf | paste -sd ' ')"
  echo "zram: $(grep -v '^[#[]' /usr/lib/systemd/zram-generator.conf.d/50-sparkos.conf | paste -sd ' ')"
  echo "services: ds-inhibit dmemcg-booster-system (system), dmemcg-booster-user (all users)"
} | tee /usr/share/sparkos/fedora-base/tuning-layer.txt
echo "Tuning layer ready."
