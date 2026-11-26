#!/usr/bin/bash
# The Nvidia driver, for the sparkos-nvidia image only (Containerfile build-arg GPU=nvidia).
# kmods.sh calls this; the main sparkos image (AMD and Intel GPUs) never runs it.
#
#   nvidia.sh build OUT KVER     from kmods.sh build: compiles the kernel modules for KVER with
#                                RPM Fusion's akmod into OUT/rpms, writes OUT/NVIDIA_EVR
#   nvidia.sh install IN KVER    from kmods.sh install: installs that kmod RPM and the driver's
#                                userspace of the same version, then the SparkOS settings
#
# Which driver: RPM Fusion nonfree's current one (xorg-x11-drv-nvidia), with Nvidia's open kernel
# modules ("Dual MIT/GPL"). The open modules are Nvidia's recommended ones since driver 560 and
# the only ones for Blackwell (RTX 50); they need a Turing GPU or newer (GTX 16, RTX 20 and later).
# Older cards (GTX 10 and before) need the closed modules or the legacy drivers, which this image
# doesn't ship: on those, use the main sparkos image (nouveau).
#
# The modules are built at image build time for the image's one kernel, like the others in
# kmods.sh, and signed with the same key (Secure Boot). No akmods, compiler or RPM Fusion
# repository is left in the image: the driver is updated by the next image, like the kernel.
set -euo pipefail

mode=${1:?build or install}
dir=${2:?folder}
kver=${3:?kernel version}

fedora=$(rpm -E %fedora)
NONFREE="https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-${fedora}.noarch.rpm"

build() {
  local out=$dir rpms ko lic
  dnf -y install "$NONFREE"
  # Without its scripts, like akmod-v4l2loopback in kmods.sh: they'd start a build for the
  # running kernel. kmodtool, pahole and the driver's kernel source come with it.
  dnf -y --setopt=install_weak_deps=False --setopt=tsflags=noscripts install akmod-nvidia
  rpm -q --qf '%{EPOCH}:%{VERSION}-%{RELEASE}\n' akmod-nvidia >"$out/NVIDIA_EVR"
  echo "nvidia.sh: driver $(cat "$out/NVIDIA_EVR")"

  # The open modules. Without this macro RPM Fusion's spec decides from lspci on the build
  # machine, which has no Nvidia GPU.
  echo '%_with_kmod_nvidia_open 1' >/etc/rpm/macros.sparkos-nvidia-open

  rpms=$(mktemp -d)
  chown akmods: "$rpms"
  runuser -u akmods -- env HOME="$rpms" akmodsbuild --kernels "$kver" --outputdir "$rpms" \
    /usr/src/akmods/nvidia-kmod.latest
  cp "$rpms"/kmod-nvidia-"$kver"-*.rpm "$out/rpms/"
  rm -rf "$rpms"

  # Check the RPM has the open modules, for this kernel
  local x
  x=$(mktemp -d)
  (cd "$x" && rpm2cpio "$out"/rpms/kmod-nvidia-"$kver"-*.rpm | cpio -idm --quiet)
  ko=$(find "$x" -name 'nvidia.ko' -o -name 'nvidia.ko.xz' | head -1)
  [ -n "$ko" ] || { echo "nvidia.sh: no nvidia.ko in the kmod RPM" >&2; exit 1; }
  lic=$(modinfo -F license "$ko")
  [ "$lic" = "Dual MIT/GPL" ] || { echo "nvidia.sh: nvidia.ko's licence is '$lic', not the open modules'" >&2; exit 1; }
  vm=$(modinfo -F vermagic "$ko")
  [ "${vm%% *}" = "$kver" ] || { echo "nvidia.sh: nvidia.ko is for '${vm%% *}', not $kver" >&2; exit 1; }
  find "$x" -name '*.ko*' -printf 'nvidia.sh: %P\n'
  rm -rf "$x"
}

install_nvidia() {
  local in=$dir evr
  evr=$(cat "$in/NVIDIA_EVR")
  # Same version as the modules, from RPM Fusion nonfree, which is removed again afterwards
  dnf -y install "$NONFREE"
  dnf -y --setopt=install_weak_deps=False install \
    "$in"/rpms/kmod-nvidia-"$kver"-*.rpm \
    "xorg-x11-drv-nvidia-$evr" \
    "xorg-x11-drv-nvidia-libs-$evr.x86_64" "xorg-x11-drv-nvidia-libs-$evr.i686" \
    "xorg-x11-drv-nvidia-cuda-$evr" \
    "xorg-x11-drv-nvidia-cuda-libs-$evr.x86_64" "xorg-x11-drv-nvidia-cuda-libs-$evr.i686" \
    "xorg-x11-drv-nvidia-power-$evr" \
    libva-nvidia-driver.x86_64 libva-nvidia-driver.i686
  dnf -y remove rpmfusion-nonfree-release
  [ "$(rpm -q --qf '%{EPOCH}:%{VERSION}-%{RELEASE}' xorg-x11-drv-nvidia)" = "$evr" ] ||
    { echo "nvidia.sh: xorg-x11-drv-nvidia is $(rpm -q xorg-x11-drv-nvidia), not $evr" >&2; exit 1; }

  # nouveau stays out, Nvidia's DRM driver does kernel modesetting (Wayland needs it), and the
  # modules load early. kargs.d applies on install and on every update (bootc).
  mkdir -p /usr/lib/bootc/kargs.d /usr/lib/modprobe.d
  cat >/usr/lib/bootc/kargs.d/20-sparkos-nvidia.toml <<'EOF'
# SparkOS Nvidia image (build_files/nvidia.sh): Nvidia's driver instead of nouveau, with kernel
# modesetting for Wayland
kargs = ["rd.driver.blacklist=nouveau", "modprobe.blacklist=nouveau", "nvidia-drm.modeset=1"]
EOF
  cat >/usr/lib/modprobe.d/sparkos-nvidia.conf <<'EOF'
# SparkOS Nvidia image (build_files/nvidia.sh)
blacklist nouveau
options nouveau modeset=0
# Keeps video memory across suspend (nvidia-suspend.service saves it to /var/tmp), so games and
# the desktop come back after sleep
options nvidia NVreg_PreserveVideoMemoryAllocations=1 NVreg_TemporaryFilePath=/var/tmp
options nvidia-drm modeset=1 fbdev=1
EOF

  # Sleep and wake: Nvidia's services save and restore video memory around suspend and hibernate
  systemctl enable nvidia-suspend.service nvidia-resume.service nvidia-hibernate.service
  if [ -e /usr/lib/systemd/system/nvidia-suspend-then-hibernate.service ]; then
    systemctl enable nvidia-suspend-then-hibernate.service
  fi

  mkdir -p /usr/share/sparkos/fedora-base
  rpm -q kmod-nvidia-"$kver" xorg-x11-drv-nvidia xorg-x11-drv-nvidia-libs xorg-x11-drv-nvidia-cuda \
    xorg-x11-drv-nvidia-power libva-nvidia-driver >/usr/share/sparkos/fedora-base/nvidia.txt
  cat /usr/share/sparkos/fedora-base/nvidia.txt
}

case "$mode" in
  build) build ;;
  install) install_nvidia ;;
  *) echo "nvidia.sh: unknown mode '$mode' (build or install)"; exit 1 ;;
esac
