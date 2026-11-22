#!/usr/bin/bash
# Out-of-tree kernel modules for the Fedora base (SPARKOS_BASE=fedora). Bazzite ships its own,
# built for its OGC kernel; Fedora's kernel has none of these, so SparkOS builds them for the
# exact kernel in the image, at image build time.
#
#   kmods.sh build   <base>   Containerfile stage "kmods-build": compiles into /kmods
#   kmods.sh install <base>   Containerfile step 4b: puts /tmp/kmods (that stage's /kmods) into
#                             the image and runs depmod
# On the Bazzite base both do nothing (Bazzite's own modules stay as they are).
#
# What's built and why (docs/fedora-base.md, "Kernel modules"):
#   zenergy        CPU power per core and per socket as hwmon sensors anyone can read (Fedora's
#                  in-kernel RAPL counters are root-only): MangoHud's cpu_power, sensors
#   ryzen_smu      the Ryzen SMU's power and clock table (ryzenadj, ryzen_monitor)
#   v4l2loopback   virtual webcam (OBS "Start Virtual Camera"); RPM Fusion's own package, built
#                  with akmods
#   xone           Microsoft's Xbox wireless USB dongle (wired pads use the kernel's xpad), plus
#                  the dongle's firmware from Microsoft's Windows Update servers
#   hid-fanatecff, new-lg4ff, hid-tmff2 (+ hid-tminit): Fanatec, Logitech and Thrustmaster
#                  racing wheels with full force feedback
#   vhba           virtual disc drive (CDEmu)
# The commits are the ones Bazzite's own builds used on 2026-11-22 (rpm -qa in
# ghcr.io/wolklaw/sparkos:latest), so the drivers behave the same after the switch.
set -euo pipefail

mode=${1:?build or install}
base=${2:?base: bazzite or fedora}
case "$base" in
  bazzite)
    echo "kmods.sh: Bazzite base, its own kernel modules are used"
    if [ "$mode" = build ]; then mkdir -p /kmods; fi # step 4b mounts it either way
    exit 0 ;;
  fedora) ;;
  *) echo "kmods.sh: unknown base '$base' (bazzite or fedora)"; exit 1 ;;
esac

# The one kernel in the image. A bootc image has exactly one; more (or none) means something
# upgraded or removed the kernel and the modules would not match it.
image_kernel() {
  local k
  mapfile -t k < <(find /usr/lib/modules -mindepth 1 -maxdepth 1 -type d -printf '%f\n')
  if [ "${#k[@]}" -ne 1 ]; then
    echo "kmods.sh: expected one kernel in /usr/lib/modules, found ${#k[@]}: ${k[*]}" >&2
    exit 1
  fi
  echo "${k[0]}"
}

# name | URL | SHA-256 | licence. GitHub archives of a full commit id; vhba is CDEmu's release.
SOURCES=(
  "zenergy|https://github.com/BoukeHaarsma23/zenergy/archive/2a40d24d9253298b3b7a7098e07895e72fef291c.tar.gz|eee4771ffb209169cb7f2696162d6d163eac140f93ba9c8eb3911521f1e64c9d|GPL-2.0"
  "ryzen_smu|https://github.com/amkillam/ryzen_smu/archive/d2983668300dd2a598e5a7dc40e71ce0678cc270.tar.gz|a8652895271b69ee5ba9c414fff62f82681a8b2c48a7b185f3fd966006ec22c5|GPL-2.0"
  "xone|https://github.com/OpenGamingCollective/xonedo/archive/982cbcb019ae4d2bee5ae69385223409ee555c88.tar.gz|09a17f363050d0c2aa57bf7e874dff755f720944eab6d3de2965c912accb15bc|GPL-2.0"
  "hid-fanatecff|https://github.com/gotzl/hid-fanatecff/archive/136cb2d65ae3db0f1ad75d4f6d6a688d8688699c.tar.gz|9440b6e24b369b43493c5dab3fff1f3a6a77b8b1e3d68172d73142a65aa94dc7|GPL-2.0"
  "new-lg4ff|https://github.com/berarma/new-lg4ff/archive/2092db19f7b40854e0427a1b2e39eda9f8d0c3cd.tar.gz|5f772ed2b1c967a9d62f8da14f56b75d40c8a51dc804b977780a9048851cce46|GPL-2.0"
  "hid-tmff2|https://github.com/Kimplul/hid-tmff2/archive/7a1274d25b2304deed326c5a43bf3617fedcb990.tar.gz|21623cd05e20b7ccd061ffb286659fecf3be84e4eaa9b25606a2f5b2e300b04e|GPL-2.0"
  "hid-tminit|https://github.com/Kimplul/hid-tminit/archive/8c4547288a6c182ed4ff131e36f710f11a76c4a9.tar.gz|c57b196c85c2a9baa0960b30274a8632b4095ff05f1395253a8bc6840bad59b6|GPL-2.0"
  "vhba|https://downloads.sourceforge.net/cdemu/vhba-module-20260313.tar.xz|293003bf5d9dc2b386db0d05f595c5548355a535d6dfc06fd379fd98bb190174|GPL-2.0-or-later"
)

# The xone dongle's firmware: Microsoft's Windows driver packages (.cab), the file inside each and
# its SHA-256, and the USB product id the driver asks for (xone_dongle_<pid>.bin). From
# xonedo's install/firmware.sh at the commit above.
FIRMWARE=(
  "02e6|https://catalog.s.download.windowsupdate.com/d/msdownload/update/driver/drvs/2017/03/2ea9591b-f751-442c-80ce-8f4692cdc67b_6b555a3a288153cf04aec6e03cba360afe2fce34.cab|FW_ACC_00U.bin|080ce4091e53a4ef3e5fe29939f51fd91f46d6a88be6d67eb6e99a5723b3a223"
  "02fe|https://catalog.s.download.windowsupdate.com/c/msdownload/update/driver/drvs/2017/07/1cd6a87c-623f-4407-a52d-c31be49e925c_e19f60808bdcbfbd3c3df6be3e71ffc52e43261e.cab|FW_ACC_00U.bin|48084d9fa53b9bb04358f3bb127b7495dc8f7bb0b3ca1437bd24ef2b6eabdf66"
  "02f9|https://catalog.s.download.windowsupdate.com/c/msdownload/update/driver/drvs/2017/06/1dbd7cb4-53bc-4857-a5b0-5955c8acaf71_9081931e7d664429a93ffda0db41b7545b7ac257.cab|FW_ACC_CL.bin|0023a7bae02974834500c665a281e25b1ba52c9226c84989f9084fa5ce591d9b"
  "091e|https://catalog.s.download.windowsupdate.com/d/msdownload/update/driver/drvs/2017/08/aeff215c-3bc4-4d36-a3ea-e14bfa8fa9d2_e58550c4f74a27e51e5cb6868b10ff633fa77164.cab|FW_ACC_BR.bin|e2710daf81e7b36d35985348f68a81d18bc537a2b0c508ffdfde6ac3eae1bad7"
)

fetch() { # url sha256 dest
  curl -fsSL --retry 5 --retry-delay 5 -o "$3" "$1"
  echo "$2  $3" | sha256sum -c - || { echo "kmods.sh: checksum mismatch for $1" >&2; exit 1; }
}

build() {
  local kver kdir out=/kmods src=/var/tmp/kmods-src
  kver=$(image_kernel)
  kdir=/usr/src/kernels/$kver
  echo "kmods.sh: building for $kver"

  # kernel-devel of exactly this kernel (updates-archive keeps it after newer kernels come out),
  # and RPM Fusion free for v4l2loopback's akmod.
  local fedora
  fedora=$(rpm -E %fedora)
  dnf -y install \
    "https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-${fedora}.noarch.rpm"
  dnf -y --setopt=install_weak_deps=False install \
    "kernel-devel-$kver" gcc make elfutils-libelf-devel xz bsdtar akmods binutils cpio
  # Without its scripts: they'd start a build for the running kernel, as root, which akmods
  # refuses. The build is started below for the image's kernel instead.
  dnf -y --setopt=install_weak_deps=False --setopt=tsflags=noscripts install akmod-v4l2loopback

  # Fail loudly if the headers aren't the image's kernel: same release, same symbol versions.
  test "$(rpm -q --qf '%{VERSION}-%{RELEASE}.%{ARCH}' "kernel-devel-$kver")" = "$kver"
  test -f "$kdir/Module.symvers"
  if [ -f "/usr/lib/modules/$kver/symvers.xz" ]; then
    cmp <(xz -dc "/usr/lib/modules/$kver/symvers.xz") "$kdir/Module.symvers" ||
      { echo "kmods.sh: kernel-devel's Module.symvers differs from the image kernel's" >&2; exit 1; }
  fi

  # The base image has no /var/tmp; rpmbuild (as the akmods user) needs one it can write to
  mkdir -p /var/tmp && chmod 1777 /var/tmp
  rm -rf "$src"
  mkdir -p "$src" "$out/extra" "$out/rpms" "$out/firmware" "$out/files" "$out/licenses"

  local entry name url sum lic dir
  for entry in "${SOURCES[@]}"; do
    IFS='|' read -r name url sum lic <<<"$entry"
    fetch "$url" "$sum" "$src/$name.tar"
    mkdir -p "$src/$name"
    tar -xf "$src/$name.tar" -C "$src/$name" --strip-components=1
    mkdir -p "$out/licenses/$name"
    for f in LICENSE COPYING; do
      [ -f "$src/$name/$f" ] && cp "$src/$name/$f" "$out/licenses/$name/"
    done
    echo "$name $url sha256:$sum $lic" >>"$out/SOURCES"
  done
  # hid-tminit is hid-tmff2's git submodule (GitHub's archives leave it out)
  rmdir "$src/hid-tmff2/deps/hid-tminit"
  mv "$src/hid-tminit" "$src/hid-tmff2/deps/hid-tminit"
  # xone stamps its version into the modules at install time; do the same
  find "$src/xone" -name '*.c' -exec sed -i 's/#VERSION#/0.5.7-ogc1+git982cbcb/' {} +

  # name -> folders to build in (each is a kbuild folder: Kbuild or a Makefile with obj-m)
  local -A DIRS=(
    [zenergy]="zenergy"
    [ryzen_smu]="ryzen_smu"
    [xone]="xone"
    [hid-fanatecff]="hid-fanatecff"
    [new-lg4ff]="new-lg4ff"
    [hid-tmff2]="hid-tmff2 hid-tmff2/deps/hid-tminit"
    [vhba]="vhba"
  )
  local d ko
  for name in "${!DIRS[@]}"; do
    mkdir -p "$out/extra/$name"
    for d in ${DIRS[$name]}; do
      echo "==================== $name: $d ===================="
      # No BTF type info in the modules (see the check below)
      make -C "$kdir" M="$src/$d" -j"$(nproc)" CONFIG_DEBUG_INFO_BTF_MODULES= modules
      for ko in "$src/$d"/*.ko; do
        install -m 0644 "$ko" "$out/extra/$name/"
      done
    done
  done
  # vhba's Makefile only sets VHBA_VERSION when make runs there; kbuild reads it too, so it's set.

  # Files the drivers need besides the module: udev rules from upstream, the dongle's
  # Wi-Fi-chip conflict, and racing wheel permissions.
  install -D -m 0644 "$src/hid-fanatecff/fanatec.rules" "$out/files/udev/99-fanatec.rules"
  install -D -m 0644 "$src/xone/install/modprobe.conf" "$out/files/modprobe/xone.conf"

  # xone's firmware
  local pid cab file fsum tmp
  tmp=$(mktemp -d)
  for entry in "${FIRMWARE[@]}"; do
    IFS='|' read -r pid cab file fsum <<<"$entry"
    curl -fsSL --retry 5 --retry-delay 5 -o "$tmp/driver.cab" "$cab"
    bsdtar -xf "$tmp/driver.cab" -C "$tmp" "$file"
    echo "$fsum  $tmp/$file" | sha256sum -c -
    xz -C crc32 -c "$tmp/$file" >"$out/firmware/xone_dongle_$pid.bin.xz"
    rm -f "$tmp/driver.cab" "$tmp/$file"
  done
  rm -rf "$tmp"

  # v4l2loopback: RPM Fusion's akmod (a source RPM), built into a kmod RPM for this kernel by
  # akmodsbuild, as the unprivileged akmods user like akmods itself does
  local rpms
  rpms=$(mktemp -d)
  chown akmods: "$rpms"
  runuser -u akmods -- env HOME="$rpms" akmodsbuild --kernels "$kver" --outputdir "$rpms" \
    /usr/src/akmods/v4l2loopback-kmod.latest
  cp "$rpms"/kmod-v4l2loopback-"$kver"-*.rpm "$out/rpms/"
  rm -rf "$rpms"

  # Every module must be for this kernel
  for ko in "$out"/extra/*/*.ko; do
    vm=$(modinfo -F vermagic "$ko")
    [ "${vm%% *}" = "$kver" ] || { echo "kmods.sh: $ko is for '${vm%% *}', not $kver" >&2; exit 1; }
  done
  # ...and carry no BTF. Fedora's kernel checks a module's BTF against its own when loading and,
  # without CONFIG_MODULE_ALLOW_BTF_MISMATCH, refuses a module whose BTF doesn't match (-EINVAL).
  # Matching BTF needs the kernel's vmlinux and the pahole it was built with; kernel-devel ships
  # no vmlinux, so kbuild skips BTF ("Skipping BTF generation ... unavailability of vmlinux", and
  # the "pahole version differs" warning is harmless). Stop here if that ever changes, for our
  # modules or the akmod's.
  local rpmdir
  rpmdir=$(mktemp -d)
  (cd "$rpmdir" && rpm2cpio "$out"/rpms/kmod-v4l2loopback-*.rpm | cpio -idm --quiet)
  while IFS= read -r ko; do
    if [ "${ko%.xz}" != "$ko" ]; then
      xz -dc "$ko" >"$rpmdir/check.ko"
    else
      cp "$ko" "$rpmdir/check.ko"
    fi
    if readelf -S -W "$rpmdir/check.ko" | grep -q '\.BTF'; then
      echo "kmods.sh: $ko has a .BTF section; the kernel may refuse to load it" >&2
      exit 1
    fi
  done < <(find "$out/extra" "$rpmdir" -name '*.ko' -o -name '*.ko.xz' | grep -v '/check\.ko$')
  rm -rf "$rpmdir"
  echo "$kver" >"$out/KVER"
  find "$out" -type f | sort
}

install_kmods() {
  local in=/tmp/kmods kver built ko name
  kver=$(image_kernel)
  built=$(cat "$in/KVER")
  if [ "$built" != "$kver" ]; then
    echo "kmods.sh: modules were built for $built but the image's kernel is $kver" >&2
    echo "kmods.sh: (did a package step upgrade the kernel?)" >&2
    exit 1
  fi

  # The modules built from source, compressed like Fedora's own (xz, CRC32 for the kernel)
  for dir in "$in"/extra/*/; do
    name=$(basename "$dir")
    mkdir -p "/usr/lib/modules/$kver/extra/$name"
    for ko in "$dir"*.ko; do
      xz -C crc32 --lzma2=dict=1MiB -c "$ko" >"/usr/lib/modules/$kver/extra/$name/$(basename "$ko").xz"
    done
  done

  # v4l2loopback from RPM Fusion: the kmod built for this kernel and its common package
  # (v4l2loopback-ctl, loads at boot as "OBS Virtual Camera" with exclusive_caps=1).
  # linuxconsoletools: evdev-joystick, which the Fanatec udev rule runs.
  dnf -y --setopt=install_weak_deps=False install "$in"/rpms/kmod-v4l2loopback-*.rpm v4l2loopback \
    linuxconsoletools

  mkdir -p /usr/lib/firmware /usr/lib/udev/rules.d /usr/lib/modprobe.d /usr/lib/modules-load.d
  install -m 0644 "$in"/firmware/*.bin.xz /usr/lib/firmware/
  install -m 0644 "$in"/files/udev/*.rules /usr/lib/udev/rules.d/
  install -m 0644 "$in/files/modprobe/xone.conf" /usr/lib/modprobe.d/xone.conf
  # vhba: /dev/vhba_ctl for the signed-in user (CDEmu runs as the user)
  echo 'KERNEL=="vhba_ctl", SUBSYSTEM=="misc", TAG+="uaccess"' >/usr/lib/udev/rules.d/69-vhba.rules
  # The same modules Bazzite loads at boot. zenergy, xone and the wheel drivers load by
  # themselves when the CPU or device is there; these are loaded so they're ready without that
  # (and the wheel drivers win over the kernel's hid-logitech, which is blocked below, as on
  # Bazzite).
  cat >/usr/lib/modules-load.d/sparkos-kmods.conf <<'EOF'
# SparkOS (build_files/kmods.sh): the out-of-tree modules Bazzite loads at boot
ryzen_smu
vhba
hid-fanatec
hid-logitech-new
hid-tmff-new
EOF
  cat >/usr/lib/modprobe.d/sparkos-new-lg4ff.conf <<'EOF'
# new-lg4ff's hid-logitech-new replaces the kernel's hid-logitech (same devices, full force
# feedback for Logitech wheels), as on Bazzite
blacklist hid_logitech
EOF

  mkdir -p /usr/share/licenses/sparkos-kmods
  cp -r "$in"/licenses/. /usr/share/licenses/sparkos-kmods/
  cp "$in/SOURCES" /usr/share/licenses/sparkos-kmods/SOURCES

  depmod -a "$kver"

  # Every module is where modprobe finds it, and for this kernel
  for name in zenergy ryzen_smu v4l2loopback vhba xone_dongle xone_gip xone_gip_gamepad \
    hid-fanatec hid-logitech-new hid-tmff-new hid-tminit-new usb-tminit-new; do
    vm=$(modinfo -k "$kver" -F vermagic "$name")
    [ "${vm%% *}" = "$kver" ] || { echo "kmods.sh: $name is for '${vm%% *}', not $kver" >&2; exit 1; }
    echo "$name: $(modinfo -k "$kver" -F filename "$name")"
  done
  mkdir -p /usr/share/sparkos/fedora-base
  { echo "kernel: $kver"; cat "$in/SOURCES"; rpm -q kmod-v4l2loopback-"$kver" v4l2loopback; } \
    >/usr/share/sparkos/fedora-base/kmods.txt
}

case "$mode" in
  build) build ;;
  install) install_kmods ;;
  *) echo "kmods.sh: unknown mode '$mode' (build or install)"; exit 1 ;;
esac
