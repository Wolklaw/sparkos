#!/usr/bin/env bash
# Sets up the SparkOS live installer: Anaconda, the install kickstart, and live-session tweaks.
# Adapted from Bazzite's installer/titanoboa_hook_postrootfs.sh (github.com/ublue-os/bazzite,
# Apache-2.0). Kept: Anaconda, the BitLocker warning, Secure Boot key enrollment, the Flatpak
# copy. Left out: NVIDIA and Steam Deck handling, Bazzite's wallpaper and panel pins.
set -exo pipefail

source /etc/os-release

dnf -qy versionlock clear

# Anaconda (web UI, shown in Firefox)
dnf install -qy --enable-repo=fedora-cisco-openh264 --allowerasing firefox anaconda-live libblockdev-{btrfs,lvm,dm}
mkdir -p /var/lib/rpm-state
dnf install -qy --setopt=install_weak_deps=0 qrencode yad

# The image being installed, as loaded into this image's container storage by build.sh
imageref="$(podman images --format '{{ index .Names 0 }}\n' '*sparkos*' | head -1)"
imageref="${imageref##*://}"
imageref="${imageref%%:*}"
imagetag="$(podman images --format '{{ .Tag }}\n' "$imageref" | head -1)"
[ -n "$imageref" ] && [ -n "$imagetag" ] || { echo "SparkOS image not found in container storage"; exit 1; }
echo "Installer will install: $imageref:$imagetag"

# Bazzite's kernel is signed with the Universal Blue key; offer to enroll it for Secure Boot
sbkey='https://github.com/ublue-os/akmods/raw/main/certs/public_key.der'
SECUREBOOT_KEY="/usr/share/ublue-os/sb_pubkey.der"
SECUREBOOT_DOC_URL="https://docs.bazzite.gg/sb"
SECUREBOOT_DOC_URL_QR="/usr/share/ublue-os/secure_boot_qr.png"
mkdir -p /usr/share/ublue-os
curl -fLo "$SECUREBOOT_KEY" "$sbkey"

echo "SparkOS release $VERSION_ID" >/etc/system-release

cat <<EOF >>/usr/share/anaconda/interactive-defaults.ks

%pre
mkdir -p /tmp/anacoda_custom_logs
%end

# Warn if a BitLocker partition is present
%pre --erroronfail --log=/tmp/anacoda_custom_logs/detect_bitlocker.log
DOCS_QR=/tmp/detect_bitlocker_qr.png
IS_BITLOCKER=\$(lsblk -o FSTYPE --json | jq '.blockdevices | map(select(.fstype == "BitLocker")) | . != []')
WARNING_MSG='<span size="x-large">Windows BitLocker partition detected</span>

It can interrupt the installation. Do <b>one</b> of these first:
    a) Disconnect that drive.
    b) Turn off BitLocker in Windows.
    c) Delete the partition, if you no longer need it.

Continue anyway?'
if [[ \$IS_BITLOCKER =~ true ]]; then
    qrencode -o \$DOCS_QR "https://support.microsoft.com/windows/turn-off-device-encryption"
    run0 --user=liveuser yad --on-top --timeout=0 --image=\$DOCS_QR --text="\$WARNING_MSG" \
        --button="Continue":0 --button="Cancel installation":10
    if [[ \$? -eq 10 ]]; then pkill liveinst; pkill firefox; exit 0; fi
fi
%end

# Remove the efi dir, must match efi_dir from the profile config
%pre-install --erroronfail
rm -rf /mnt/sysroot/boot/efi/EFI/fedora
%end

%pre-install --erroronfail --log=/tmp/anacoda_custom_logs/repartitioning.log
set -x
xboot_dev=\$(findmnt -o SOURCE --nofsroot --noheadings -f --target /mnt/sysroot/boot)
[[ -n \$xboot_dev ]] || { echo "ERROR: xboot_dev not found"; exit 1; }
e2label "\$xboot_dev" "bazzite_xboot"
%end

%onerror
run0 --user=liveuser yad --timeout=0 --text-info --no-buttons --width=600 --height=400 \
    --text="The installation failed. The log is below; please keep a copy." < /tmp/anaconda.log
%end

ostreecontainer --url=$imageref:$imagetag --transport=containers-storage --no-signature-verification
%include /usr/share/anaconda/post-scripts/install-configure-upgrade.ks
%include /usr/share/anaconda/post-scripts/disable-fedora-flatpak.ks
%include /usr/share/anaconda/post-scripts/install-flatpaks.ks
%include /usr/share/anaconda/post-scripts/restore-selinux-labels.ks
%include /usr/share/anaconda/post-scripts/secureboot-enroll-key.ks
%include /usr/share/anaconda/post-scripts/secureboot-docs.ks

EOF

# After install, follow signed SparkOS updates from the registry
cat <<EOF >>/usr/share/anaconda/post-scripts/install-configure-upgrade.ks
%post --erroronfail --log=/tmp/anacoda_custom_logs/bootc-switch.log
bootc switch --mutate-in-place --enforce-container-sigpolicy --transport registry $imageref:$imagetag
%end
EOF

cat <<EOF >>/usr/share/anaconda/post-scripts/secureboot-enroll-key.ks
%post --erroronfail --nochroot --log=/tmp/anacoda_custom_logs/secureboot-enroll-key.log
set -oue pipefail
readonly ENROLLMENT_PASSWORD="universalblue"
readonly SECUREBOOT_KEY="$SECUREBOOT_KEY"
if [[ ! -d "/sys/firmware/efi" ]]; then echo "EFI mode not detected. Skipping key enrollment."; exit 0; fi
if [[ ! -f "\$SECUREBOOT_KEY" ]]; then echo "Secure boot key not provided: \$SECUREBOOT_KEY"; exit 0; fi
mokutil --timeout -1 || :
echo -e "\$ENROLLMENT_PASSWORD\n\$ENROLLMENT_PASSWORD" | mokutil --import "\$SECUREBOOT_KEY" || :
%end
EOF

cat <<EOF >>/usr/share/anaconda/post-scripts/secureboot-docs.ks
%post --nochroot --log=/tmp/anacoda_custom_logs/secureboot-docs.log
LC_ALL=C mokutil -t "$SECUREBOOT_KEY" | grep -q "is already in the enrollment request" && \
    run0 --user=liveuser yad --timeout=0 --on-top --button=OK:0 --image="$SECUREBOOT_DOC_URL_QR" \
    --text="<b>Secure Boot key added.</b>\nOn the next start, a blue screen (MOK manager) asks to enroll it:\nchoose Enroll MOK, then Continue, and type the password <b>universalblue</b>.\nDetails: $SECUREBOOT_DOC_URL"
%end
EOF
qrencode -o "$SECUREBOOT_DOC_URL_QR" "$SECUREBOOT_DOC_URL"

### Live session only ###

# Services that make no sense in a live installer
(
    set +e
    for s in rpm-ostree-countme.service tailscaled.service bazzite-hardware-setup.service \
        ublue-hardware-setup.service bootloader-update.service brew-upgrade.timer brew-update.timer \
        brew-setup.service rpm-ostreed-automatic.timer uupd.timer ublue-guest-user.service \
        ublue-os-media-automount.service ublue-system-setup.service bazzite-flatpak-manager.service \
        ublue-flatpak-manager.service flatpak-add-fedora-repos.service system-flatpak-setup.timer \
        user-flatpak-setup.timer greenboot-set-rollback-trigger.service greenboot-healthcheck.service \
        input-remapper.service switcheroo-control.service check-sb-key.service; do
        if systemctl list-unit-files "$s" >/dev/null 2>&1; then
            systemctl disable "$s"
        fi
    done
    for s in podman-auto-update.timer bazzite-user-setup.service ublue-user-setup.service; do
        if systemctl --global list-unit-files "$s" >/dev/null 2>&1; then
            systemctl --global disable "$s"
        fi
    done
    true # a service missing from this image is fine; never fail the build here
)

# Open the live desktop without a sign-in screen. livesys makes liveuser but only sets up
# autologin for SDDM; SparkOS uses Plasma Login, which reads /etc/plasmalogin.conf.d/.
# This is the live image's /etc only: the installed system comes from the SparkOS image
# and keeps its sign-in screen.
mkdir -p /etc/plasmalogin.conf.d
cat >/etc/plasmalogin.conf.d/zz-sparkos-live-autologin.conf <<'EOF'
[Autologin]
User=liveuser
Session=plasma
EOF
test -f /usr/share/wayland-sessions/plasma.desktop || { echo "plasma.desktop session not found"; exit 1; }

rm -vf /etc/skel/.config/autostart/steam*.desktop
dnf -yq remove steam lutris bazaar waydroid || :
rm -vf /etc/profile.d/verify_motd.sh
rm -f /usr/share/applications/bbrew.desktop /usr/share/applications/bazzite-steam*.desktop
rm -f /usr/bin/rpm-ostree # never run on the live ISO

# Partition editor for people who want to shrink a drive first
dnf -yq install gparted
