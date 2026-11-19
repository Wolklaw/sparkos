#!/usr/bin/bash
# Turns the SparkOS image into its installer (live ISO) image. Runs inside installer/Containerfile.
# Adapted from Bazzite's installer/build.sh (github.com/ublue-os/bazzite, Apache-2.0).
#
# What makes the SparkOS installer different: every app in installer/flatpaks is installed
# here from Flathub (always the latest version at ISO build time) and copied onto the new
# system during install, so all apps are there on first boot, even offline.

set -exo pipefail
{ export PS4='+( ${BASH_SOURCE}:${LINENO} ): ${FUNCNAME[0]:+${FUNCNAME[0]}(): }'; } 2>/dev/null

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_IMAGE=${BASE_IMAGE:?}
INSTALL_IMAGE_PAYLOAD=${INSTALL_IMAGE_PAYLOAD:?}

# Create the directory that /root is symlinked to
mkdir -p "$(realpath /root)"

# bwrap tries to write /proc/sys/user/max_user_namespaces which is mounted as ro
mount -o remount,rw /proc/sys

# Apps: install every Flatpak from the list (latest from Flathub), fail if any is missing
test -s /src/flatpaks || { echo "installer/flatpaks is missing or empty"; exit 1; }
curl --retry 3 -Lo /etc/flatpak/remotes.d/flathub.flatpakrepo https://dl.flathub.org/repo/flathub.flatpakrepo
xargs -r flatpak install -y --noninteractive --system flathub </src/flatpaks
installed=$(flatpak list --system --columns=application)
missing=0
while read -r ref; do
    [ -n "$ref" ] || continue
    id=${ref#app/}; id=${id#runtime/}; id=${id%%/*}
    grep -qx "$id" <<<"$installed" || { echo "::error::Flatpak not installed: $id"; missing=1; }
done </src/flatpaks
[ "$missing" = 0 ]
echo "Flatpaks in the installer: $(flatpak list --system --app | wc -l) apps"

# The SparkOS image that gets installed
if mountpoint -q /usr/lib/containers/storage; then
    podman save --format oci-archive "$INSTALL_IMAGE_PAYLOAD" | podman load --storage-opt additionalimagestore=''
else
    podman pull "$INSTALL_IMAGE_PAYLOAD"
fi

echo "Copying installer system files..."
cp -a /src/system_files/shared/. /

"$SCRIPT_DIR/titanoboa_hook_preinitramfs.sh"

# Live initramfs
dnf install -y dracut-live
kernel=$(kernel-install list --json pretty | jq -r '.[] | select(.has_kernel == true) | .version')
DRACUT_NO_XATTR=1 dracut -v --force --reproducible --no-hostonly \
    --add "dmsquash-live dmsquash-live-autooverlay" \
    "/usr/lib/modules/${kernel}/initramfs.img" "${kernel}"

dnf install -y livesys-scripts
sed -i "s/^livesys_session=.*/livesys_session=kde/" /etc/sysconfig/livesys
systemctl enable livesys.service livesys-late.service

"$SCRIPT_DIR/titanoboa_hook_postrootfs.sh"

# image-builder needs gcdx64.efi, and expects the EFI directory in /boot/efi
dnf install -y grub2-efi-x64-cdboot
mkdir -p /boot/efi
cp -av /usr/lib/efi/*/*/EFI /boot/efi/
cp -v /boot/efi/EFI/fedora/grubx64.efi /boot/efi/EFI/BOOT/fbx64.efi

rm -f /etc/localtime
systemd-firstboot --timezone UTC

# The live system's / is an overlay under /run; give ostree a bigger /var/tmp while installing
rm -rf /var/tmp
mkdir /var/tmp
cat >/etc/systemd/system/var-tmp.mount <<'EOF'
[Unit]
Description=Larger tmpfs for /var/tmp on live system

[Mount]
What=tmpfs
Where=/var/tmp
Type=tmpfs
Options=size=50%%,nr_inodes=1m,x-systemd.graceful-option=usrquota

[Install]
WantedBy=local-fs.target
EOF
systemctl enable var-tmp.mount

# Keep the Flatpaks read-only in the live session so the copy onto disk is clean
cat >/etc/systemd/system/var-lib-flatpak.mount <<'EOF'
[Mount]
Type=none
What=/var/lib/flatpak
Where=/var/lib/flatpak
Options=bind,ro

[Install]
WantedBy=multi-user.target
EOF
systemctl enable var-lib-flatpak.mount

# systemd-tmpfiles fails to label the install target when /mnt is a symlink
rm /mnt
mkdir /mnt

mkdir -p /usr/lib/bootc-image-builder
cp /src/iso.yaml /usr/lib/bootc-image-builder/iso.yaml

dnf clean all
