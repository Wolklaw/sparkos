#!/usr/bin/bash
# Builds a disk image that looks like a Windows PC's drives, for testing sparkos-windows-drives (needs root: loop devices).
#
#   sudo bash make_disk.sh OUT.img
#
# GPT with three NTFS partitions: C: (no label) with Windows\System32\config\SYSTEM mapping the letters and a Claude Code profile in
# Users\Tester\.claude, D: "Scrap", and E: "Games" with Personal Projects\demo (a Git repository). Prints the PARTUUIDs.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
out=${1:?output image}
command -v mkfs.ntfs >/dev/null || { apt-get install -y -qq ntfs-3g >/dev/null || dnf -y install ntfs-3g ntfsprogs; }
command -v sgdisk >/dev/null || { apt-get install -y -qq gdisk >/dev/null || dnf -y install gdisk; }

rm -f "$out"
truncate -s 640M "$out"
sgdisk -q -n1:0:+256M -t1:0700 -n2:0:+128M -t2:0700 -n3:0:0 -t3:0700 "$out"
loop=$(losetup -fP --show "$out")
trap 'umount -q /tmp/make-disk-mnt 2>/dev/null || true; losetup -d "$loop"' EXIT
udevadm settle 2>/dev/null || sleep 2
mkfs.ntfs -Q -q "${loop}p1"
mkfs.ntfs -Q -q -L Scrap "${loop}p2"
mkfs.ntfs -Q -q -L Games "${loop}p3"
c=$(sgdisk -i 1 "$out" | sed -n 's/^Partition unique GUID: //p' | tr 'A-Z' 'a-z')
d=$(sgdisk -i 2 "$out" | sed -n 's/^Partition unique GUID: //p' | tr 'A-Z' 'a-z')
e=$(sgdisk -i 3 "$out" | sed -n 's/^Partition unique GUID: //p' | tr 'A-Z' 'a-z')

mkdir -p /tmp/make-disk-mnt
mount -t ntfs-3g "${loop}p1" /tmp/make-disk-mnt
python3 "$here/make_hive.py" /tmp/make-disk-mnt/Windows/System32/config/SYSTEM "C=$c" "D=$d" "E=$e"
mkdir -p "/tmp/make-disk-mnt/Users/Tester/.claude/projects/E--Personal-Projects-demo/memory"
printf '# global instructions from Windows\n' > /tmp/make-disk-mnt/Users/Tester/.claude/CLAUDE.md
printf -- '- a memory from Windows\n' > /tmp/make-disk-mnt/Users/Tester/.claude/projects/E--Personal-Projects-demo/memory/MEMORY.md
umount /tmp/make-disk-mnt
mount -t ntfs-3g "${loop}p3" /tmp/make-disk-mnt
mkdir -p "/tmp/make-disk-mnt/Personal Projects/demo"
git -C "/tmp/make-disk-mnt/Personal Projects/demo" -c init.defaultBranch=main init -q
printf 'print("hi")\r\n' > "/tmp/make-disk-mnt/Personal Projects/demo/app.py"
git -C "/tmp/make-disk-mnt/Personal Projects/demo" -c user.name=t -c user.email=t@t -c core.autocrlf=true add -A
git -C "/tmp/make-disk-mnt/Personal Projects/demo" -c user.name=t -c user.email=t@t commit -q -m first
umount /tmp/make-disk-mnt
echo "C=$c D=$d E=$e"
