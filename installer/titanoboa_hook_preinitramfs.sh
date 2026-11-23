#!/usr/bin/env bash
# Adapted from Bazzite's installer (github.com/ublue-os/bazzite, Apache-2.0). Bazzite swapped in
# Fedora's signed kernel here so the live USB boots with Secure Boot on. SparkOS already runs
# Fedora's own kernel (signed by Fedora), so there is nothing to swap.
#
set -exo pipefail

# The kernel the live initramfs is built for must be Fedora's
rpm -q kernel-core --qf '%{VENDOR}\n' | grep -qx 'Fedora Project'

# Include nvidia-gpu-firmware package.
dnf install -yq nvidia-gpu-firmware || :
dnf clean all -yq
