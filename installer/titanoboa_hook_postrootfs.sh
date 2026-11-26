#!/usr/bin/env bash
# Sets up the SparkOS live installer: Anaconda, the install kickstart, and live-session tweaks.
# Adapted from Bazzite's installer/titanoboa_hook_postrootfs.sh (github.com/ublue-os/bazzite,
# Apache-2.0). Kept: Anaconda, the BitLocker warning, the Flatpak copy. Left out: NVIDIA and
# Steam Deck handling, Bazzite's wallpaper and panel pins, and Secure Boot key enrollment
# (SparkOS runs Fedora's kernel, signed by Fedora, so Secure Boot needs no extra key; the
# kernel modules SparkOS builds aren't signed, see docs/fedora-base.md "Secure Boot").
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

# SparkOS's os-release matches Anaconda's own Fedora Kinoite profile too; remove that one so
# SparkOS's (installer/system_files/.../profile.d/sparkos.conf) is the only match
for f in /usr/share/anaconda/profile.d/*.conf; do
    if grep -qE '^os_id *= *fedora' "$f" && grep -qE '^variant_id *= *kinoite' "$f"; then rm -v "$f"; fi
done
test -f /etc/anaconda/profile.d/sparkos.conf

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
e2label "\$xboot_dev" "sparkos_xboot"
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

EOF

# After install, follow signed SparkOS updates from the registry
cat <<EOF >>/usr/share/anaconda/post-scripts/install-configure-upgrade.ks
%post --erroronfail --log=/tmp/anacoda_custom_logs/bootc-switch.log
bootc switch --mutate-in-place --enforce-container-sigpolicy --transport registry $imageref:$imagetag
%end
EOF


### Live session only ###

# Services that make no sense in a live installer
(
    set +e
    for s in rpm-ostree-countme.service tailscaled.service bootloader-update.service \
        brew-upgrade.timer brew-update.timer rpm-ostreed-automatic.timer spark-update.timer \
        flatpak-add-fedora-repos.service greenboot-set-rollback-trigger.service \
        greenboot-healthcheck.service input-remapper.service switcheroo-control.service; do
        if systemctl list-unit-files "$s" >/dev/null 2>&1; then
            systemctl disable "$s"
        fi
    done
    for s in podman-auto-update.timer; do
        if systemctl --global list-unit-files "$s" >/dev/null 2>&1; then
            systemctl --global disable "$s"
        fi
    done
    true # a service missing from this image is fine; never fail the build here
)

# Open the live desktop without a sign-in screen: greetd signs liveuser (made by livesys at
# boot) straight into the Spark session once, and the installer opens by itself. livesys has no
# Spark session script (installer/build.sh turns its session setup off), so it is done here.
# This is the live image's /etc only: the installed system comes from the SparkOS image and
# keeps the Spark sign-in screen.
test -f /usr/share/wayland-sessions/spark-wl.desktop || { echo "spark-wl.desktop session not found"; exit 1; }
grep -q '^command = "/usr/libexec/spark-greeter-session"$' /etc/greetd/config.toml \
    || { echo "/etc/greetd/config.toml is not the Spark one"; exit 1; }
printf '\n# Live installer only (installer/titanoboa_hook_postrootfs.sh)\n[initial_session]\ncommand = "/usr/bin/spark-wl-session"\nuser = "liveuser"\n' >>/etc/greetd/config.toml
cat /etc/greetd/config.toml
sed -i 's/^NoDisplay=true/NoDisplay=false/' /usr/share/applications/liveinst.desktop
mkdir -p /etc/xdg/autostart
cat >/etc/xdg/autostart/sparkos-liveinst.desktop <<'AUTOSTART'
[Desktop Entry]
Type=Application
Name=Install SparkOS
Exec=liveinst
OnlyShowIn=sparkwl;
X-GNOME-Autostart-enabled=true
AUTOSTART

rm -f /usr/bin/rpm-ostree # never run on the live ISO

# Partition editor for people who want to shrink a drive first
dnf -yq install gparted
