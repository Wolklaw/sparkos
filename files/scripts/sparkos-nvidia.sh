#!/usr/bin/env bash
# Checks the build has the graphics driver its name says. Installs and changes nothing.
#
#   IMAGE_NAME=sparkos-nvidia (built from Bazzite's bazzite-nvidia-open): NVIDIA's driver, its
#     open kernel module built for this image's kernel, and the user-space parts games need
#     (Vulkan, 32-bit libraries) must be there. The module must be the open one (license
#     "Dual MIT/GPL"), which runs GeForce RTX 20 series and newer and GTX 16; older cards need
#     NVIDIA's closed module, which this build doesn't have.
#   IMAGE_NAME=sparkos (built from bazzite): no NVIDIA kernel module, so a wrong base can't ship
#     under the wrong name.
#
# The driver itself comes from Bazzite, signed with Universal Blue's Secure Boot key like
# Bazzite's kernel (the installer offers to enroll that key).
set -oue pipefail

name=${IMAGE_NAME:-sparkos}
kver=$(find /usr/lib/modules -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -V | tail -1)
test -n "$kver" || { echo "no kernel in /usr/lib/modules"; exit 1; }
module=$(find "/usr/lib/modules/$kver" -name 'nvidia.ko*' | head -1)
echo "--- image $name, kernel $kver"

case "$name" in
  *-nvidia)
    for pkg in kmod-nvidia nvidia-driver; do
      rpm -q "$pkg" || { echo "$pkg is missing: is the base bazzite-nvidia-open?"; exit 1; }
    done
    ls /usr/lib64/libGLX_nvidia.so* /usr/lib64/libnvidia-glcore.so* >/dev/null || { echo "NVIDIA's OpenGL libraries are missing"; exit 1; }
    ls /usr/lib/libGLX_nvidia.so* >/dev/null || { echo "32-bit NVIDIA libraries missing (Steam and Proton need them)"; exit 1; }
    test -n "$module" || { echo "no nvidia.ko for kernel $kver"; exit 1; }
    version=$(modinfo -F version "$module")
    license=$(modinfo -F license "$module")
    echo "--- $module: version $version, license $license"
    [ "$version" = "$(rpm -q --qf '%{VERSION}' nvidia-driver)" ] || { echo "kernel module $version doesn't match the driver $(rpm -q nvidia-driver)"; exit 1; }
    [ "$license" = "Dual MIT/GPL" ] || { echo "expected NVIDIA's open kernel module (Dual MIT/GPL), got '$license'"; exit 1; }
    for m in nvidia-drm nvidia-modeset nvidia-uvm; do
      find "/usr/lib/modules/$kver" -name "$m.ko*" | grep -q . || { echo "$m.ko missing"; exit 1; }
    done
    ls /usr/share/vulkan/icd.d/ | grep -qi nvidia || { echo "no NVIDIA Vulkan driver in /usr/share/vulkan/icd.d"; exit 1; }
    echo "--- signer: $(modinfo -F signer "$module" 2>/dev/null || echo none)"
    echo "--- nvidia-smi: $(command -v nvidia-smi || echo 'not installed')"
    echo "--- kernel arguments for the driver:"; cat /usr/lib/bootc/kargs.d/*.toml 2>/dev/null | grep -i -E 'nvidia|nouveau' || echo "(none in kargs.d)"
    echo "--- NVIDIA driver $version present (open kernel module)"
    ;;
  *)
    if [ -n "$module" ] || rpm -q kmod-nvidia >/dev/null 2>&1; then
      echo "$name has an NVIDIA kernel module ($module): built from an NVIDIA base by mistake?"; exit 1
    fi
    echo "--- no NVIDIA driver, as expected for $name"
    ;;
esac

# Released yet? Spark Welcome offers the switch to SparkOS for NVIDIA only when this file is there
install -d /usr/share/sparkos
if [ "${NVIDIA_RELEASED:-false}" = true ]; then
  echo "SparkOS for NVIDIA is released: ghcr.io/wolklaw/sparkos-nvidia is public" > /usr/share/sparkos/nvidia-released
  echo "--- SparkOS for NVIDIA marked as released"
else
  rm -f /usr/share/sparkos/nvidia-released
  echo "--- SparkOS for NVIDIA not released yet (no switch offered)"
fi
