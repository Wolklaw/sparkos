#!/usr/bin/bash
# Runs when the SparkOS live installer reaches the desktop: blocks Legacy/CSM boot and
# low-memory installs, then offers to start the installer.
# Adapted from Bazzite's on_gui_login.sh (github.com/ublue-os/bazzite, Apache-2.0).

if [[ ! -d /sys/firmware/efi ]]; then
    yad --undecorated --on-top --timeout=0 --button="Shut down:0" \
        --text="SparkOS needs UEFI boot. In your UEFI/BIOS settings, turn off CSM/Legacy mode, then start from the USB stick again." || true
    systemctl poweroff || shutdown -h now || true
fi

memory_kb=$(awk '/^MemTotal/{print $2}' /proc/meminfo)
if [[ -n $memory_kb && $memory_kb -lt 5000000 ]]; then
    yad --undecorated --on-top --timeout=0 --warning --button="Shut down:0" \
        --text="SparkOS needs <b>at least 8 GB of memory</b> to install. This computer has $((memory_kb / 1024 / 1024)) GB."
    systemctl poweroff || shutdown -h now || true
fi

while true; do
    yad --no-escape --on-top --text-align=center --buttons-layout=center --title="SparkOS" \
        --text="
<big><b>SparkOS installer</b></big>

This live session is for installing. SparkOS's own apps (Soot, FreeSuite and
the Spark apps) are part of the system and are there on the first start.
Everything else installs from the Store after that.

Games and performance here are not representative: install first." \
        --button="Install SparkOS:10" --button="Edit partitions (GParted):20" --button="Close:0"
    case $? in
        10) liveinst & disown $!; break ;;
        20) gparted & disown $! ;;
        *) break ;;
    esac
done
