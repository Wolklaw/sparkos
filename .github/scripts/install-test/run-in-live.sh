#!/usr/bin/bash
# Test-only (installer-install-test.yml): runs inside the SparkOS live session, started from
# the debug shell on ttyS0. Installs SparkOS with Anaconda the way liveinst starts it, but in
# command-line mode with ks.cfg instead of the WebUI, then saves the logs to the KSTEST disk.
SRC=/run/kst
W=/tmp/kst
mkdir -p "$W"
cp -r "$SRC"/. "$W"/
# Always to ttyS0, also when this was started from the shell on tty9
exec > >(tee -a "$W/run.log" >/dev/ttyS0) 2>&1
set -x
echo "KSTEST-STAGE booted $(date -u +%T)"
timeout 600 systemctl is-system-running --wait
echo "KSTEST-STAGE system-up $(systemctl is-system-running) $(date -u +%T)"

cat /proc/cmdline
cat /etc/os-release
uname -r
rpm -q anaconda-core anaconda-live anaconda-webui anaconda-tui shim-x64 grub2-efi-x64 kernel-core
mokutil --sb-state
lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,PARTLABEL,SERIAL,MOUNTPOINTS
efibootmgr -v

data=$(lsblk -dn -o NAME,SERIAL | awk '$2=="SPARKDATA"{print $1}')
if [ -z "$data" ]; then
    echo "KSTEST-RESULT rc=97 (target disk SPARKDATA not found)"
    exit 97
fi
sed "s|@DATADISK@|$data|g" "$W/ks.cfg" >"$W/ks-final.cfg"
echo "--- interactive-defaults.ks from the ISO"
cat /usr/share/anaconda/interactive-defaults.ks

# Nothing of ours stays mounted while Anaconda scans the disks
umount "$SRC"

# What liveinst does before starting Anaconda
for i in raid0 raid1 raid5 raid6 raid456 raid10 dm-mod dm-zero dm-mirror dm-snapshot dm-multipath dm-round-robin vfat dm-crypt cbc sha256 lrw xts iscsi_tcp iscsi_ibft; do
    modprobe $i 2>/dev/null
done
export PATH=/sbin:/usr/sbin:$PATH
# liveinst runs Anaconda (through pkexec) with the desktop user's session environment;
# Anaconda needs that session bus (it inhibits the screensaver first)
luser=$(loginctl list-sessions --no-legend | awk '$3!="root" && $3!=""{print $3; exit}')
luser=${luser:-liveuser}
uid=$(id -u "$luser")
for _ in $(seq 1 150); do [ -S "/run/user/$uid/bus" ] && break; sleep 2; done
readarray -t user_environment < <(runuser -u "$luser" -- env XDG_RUNTIME_DIR="/run/user/$uid" systemctl --user show-environment)
for variable in "${user_environment[@]}"; do export "${variable?}"; done
HOME=$(bash -c "cd ~$luser && pwd")
export HOME XDG_CONFIG_HOME="$HOME/.config"
env | grep -E '^(DBUS_SESSION|WAYLAND|DISPLAY|XDG_RUNTIME|HOME)' || true
setenforce 0
args=(--liveinst --cmdline --kickstart "$W/ks-final.cfg")
sestatus | grep -q enabled || args+=(--noselinux)
anaconda-cleanup anaconda "${args[@]}"

echo "KSTEST-STAGE anaconda-start $(date -u +%T)"
yes '' | timeout 120m anaconda "${args[@]}"
rc=${PIPESTATUS[1]}
echo "KSTEST-STAGE anaconda-end rc=$rc $(date -u +%T)"
# Anaconda can exit 0 after a failure it reported itself; its log says which
if [ "$rc" = 0 ] && grep -qE "Installation failed|Traceback \(most recent call last\)" /tmp/anaconda.log 2>/dev/null; then
    rc=98
fi

efibootmgr -v
mokutil --list-new 2>&1 | grep -E 'Subject:|Issuer:' || true
lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,PARTLABEL,SERIAL

mkdir -p "$SRC"
mount -L KSTEST "$SRC"
mkdir -p "$SRC/out"
cp /tmp/*.log "$SRC/out/" 2>/dev/null
cp -r /tmp/anacoda_custom_logs "$SRC/out/" 2>/dev/null
cp "$W/ks-final.cfg" "$SRC/out/"
journalctl -b --no-pager >"$SRC/out/live-journal.txt" 2>&1
cp "$W/run.log" "$SRC/out/"
sync
umount "$SRC"
echo "KSTEST-RESULT rc=$rc"
sleep 3
systemctl poweroff
