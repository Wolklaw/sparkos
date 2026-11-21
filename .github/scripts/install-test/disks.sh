#!/usr/bin/bash
# Test-only (installer-install-test.yml): makes the Windows-style test disks before the
# install, and checks afterwards that nothing that was there changed.
#
#   disks.sh prepare <layout> <workdir>
#   disks.sh verify  <layout> <workdir>     (appends PASS/FAIL/WARN lines to results.tsv)
#
# Layouts:
#   shared-esp  one 80 GiB disk (SPARKDATA): EFI system partition (100 MiB, with Windows
#               boot files), MSR, NTFS "Data" filling half the disk, the rest free.
#               SparkOS goes into the free space and shares the EFI partition.
#   two-disks   the owner's layout. SPARKWIN (32 GiB): EFI, MSR, NTFS "Windows".
#               SPARKDATA (80 GiB): NTFS "Data" on the first half, the rest free.
#               SparkOS goes into SPARKDATA's free space only.
set -euo pipefail
export LC_ALL=C
cmd=$1 layout=$2 W=$3
mkdir -p "$W/disk-before" "$W/disk-after"
RES="$W/results.tsv"
touch "$RES"

result() { printf '%s\t%s\t%s\n' "$1" "$2" "$3" | tee -a "$RES"; }

attach() {
    local l
    l=$(sudo losetup --find --show --partscan "$1")
    sudo udevadm settle || true
    for _ in $(seq 1 20); do [ -e "${l}p1" ] && break; sleep 0.5; done
    echo "$l"
}

# name, size, filesystem and label of every partition (blkid, not the udev cache)
parts() {
    local p
    for p in "$1"p*; do
        printf '%s %s %s %s
' "${p##*/}" "$(numfmt --to=iec "$(sudo blockdev --getsize64 "$p")")"             "$(sudo blkid -o value -s TYPE "$p" || echo -)" "$(sudo blkid -o value -s LABEL "$p" || echo -)"
    done
}
detach() { sudo losetup -d "$1"; }

# Windows-like files on an EFI partition (random bytes; only their names and hashes matter)
fill_esp() {
    local dev=$1 m
    m=$(mktemp -d)
    sudo mkfs.vfat -F 32 -n SYSTEM "$dev" >/dev/null
    sudo mount "$dev" "$m"
    sudo mkdir -p "$m/EFI/Microsoft/Boot/en-US" "$m/EFI/Microsoft/Recovery" "$m/EFI/Boot"
    for f in EFI/Microsoft/Boot/bootmgfw.efi EFI/Microsoft/Boot/bootmgr.efi EFI/Microsoft/Boot/BCD \
        EFI/Microsoft/Boot/memtest.efi EFI/Microsoft/Boot/en-US/bootmgfw.efi.mui \
        EFI/Microsoft/Recovery/BCD EFI/Boot/bootx64.efi; do
        sudo head -c $((200 * 1024 + RANDOM)) /dev/urandom | sudo tee "$m/$f" >/dev/null
    done
    sudo umount "$m"
}

# An NTFS partition with a known file on it
fill_ntfs() {
    local dev=$1 label=$2 m
    m=$(mktemp -d)
    sudo mkntfs -Q -L "$label" "$dev" >/dev/null
    sudo mount -t ntfs-3g "$dev" "$m"
    sudo mkdir -p "$m/Documents"
    sudo head -c $((64 * 1024 * 1024)) /dev/urandom | sudo tee "$m/Documents/keep-me.bin" >/dev/null
    echo "SparkOS install test: this file must survive the install. $(date -u)" | sudo tee "$m/Documents/keep-me.txt" >/dev/null
    sudo umount "$m"
}

# Records what must not change on one partition: its table entry, raw bytes, files
record_part() {
    local disk=$1 dev=$2 n=$3 kind=$4 dir=$5 m
    sudo sfdisk --json "$disk" | jq -c --arg n "$n" '.partitiontable.partitions[] | select(.node|endswith("p"+$n)) | del(.node)' >"$dir/$kind-entry.json"
    sudo sha256sum "$dev" | cut -d' ' -f1 >"$dir/$kind-raw.sha256"
    m=$(mktemp -d)
    if [ "${kind%%-*}" = esp ]; then sudo mount -o ro "$dev" "$m"; else sudo mount -t ntfs-3g -o ro "$dev" "$m"; fi
    (cd "$m" && sudo find . -type f -exec sha256sum {} + | sort -k2) >"$dir/$kind-files.sha256"
    sudo umount "$m"
}

record_all() {
    local dir=$1 L
    case $layout in
    shared-esp)
        L=$(attach "$W/data.img")
        sudo sfdisk --dump "$L" >"$dir/data-table.txt"
        record_part "$L" "${L}p1" 1 esp-data "$dir"
        record_part "$L" "${L}p3" 3 ntfs-data "$dir"
        parts "$L" >"$dir/data-parts.txt"
        detach "$L"
        ;;
    two-disks)
        L=$(attach "$W/win.img")
        sudo sfdisk --dump "$L" >"$dir/win-table.txt"
        record_part "$L" "${L}p1" 1 esp-win "$dir"
        record_part "$L" "${L}p3" 3 ntfs-win "$dir"
        detach "$L"
        sha256sum "$W/win.img" | cut -d' ' -f1 >"$dir/win-whole.sha256"
        L=$(attach "$W/data.img")
        sudo sfdisk --dump "$L" >"$dir/data-table.txt"
        record_part "$L" "${L}p1" 1 ntfs-data "$dir"
        parts "$L" >"$dir/data-parts.txt"
        detach "$L"
        ;;
    esac
}

prepare() {
    local L
    case $layout in
    shared-esp)
        truncate -s 80G "$W/data.img"
        sgdisk -o -n 1:1M:+100M -t 1:EF00 -c 1:"EFI system partition" \
            -n 2:0:+16M -t 2:0C01 -c 2:"Microsoft reserved partition" \
            -n 3:0:+40G -t 3:0700 -c 3:"Basic data partition" "$W/data.img" >/dev/null
        L=$(attach "$W/data.img")
        fill_esp "${L}p1"
        fill_ntfs "${L}p3" Data
        detach "$L"
        ;;
    two-disks)
        truncate -s 32G "$W/win.img"
        sgdisk -o -n 1:1M:+100M -t 1:EF00 -c 1:"EFI system partition" \
            -n 2:0:+16M -t 2:0C01 -c 2:"Microsoft reserved partition" \
            -n 3:0:0 -t 3:0700 -c 3:"Basic data partition" "$W/win.img" >/dev/null
        L=$(attach "$W/win.img")
        fill_esp "${L}p1"
        fill_ntfs "${L}p3" Windows
        detach "$L"
        truncate -s 80G "$W/data.img"
        sgdisk -o -n 1:1M:+40G -t 1:0700 -c 1:"Basic data partition" "$W/data.img" >/dev/null
        L=$(attach "$W/data.img")
        fill_ntfs "${L}p1" Data
        detach "$L"
        ;;
    *) echo "unknown layout $layout"; exit 2 ;;
    esac
    record_all "$W/disk-before"
    echo "Before the install:"
    head -50 "$W"/disk-before/*-table.txt "$W"/disk-before/*-files.sha256
}

cmp_part() { # kind label
    local kind=$1 what=$2 b=$W/disk-before a=$W/disk-after
    if cmp -s "$b/$kind-entry.json" "$a/$kind-entry.json"; then
        result PASS "$what: partition table entry unchanged" "$(jq -r '"start \(.start), size \(.size) sectors"' "$a/$kind-entry.json")"
    elif [ "$(jq -c 'del(.name)' "$b/$kind-entry.json")" = "$(jq -c 'del(.name)' "$a/$kind-entry.json")" ]; then
        result PASS "$what: partition start, size, type and ID unchanged" "$(jq -r '"start \(.start), size \(.size) sectors"' "$a/$kind-entry.json")"
        result WARN "$what: the installer renamed its GPT label" "\"$(jq -r .name "$b/$kind-entry.json")\" is now \"$(jq -r .name "$a/$kind-entry.json")\" (a label only; nothing reads it)"
    else
        result FAIL "$what: partition table entry changed" "before $(cat "$b/$kind-entry.json") after $(cat "$a/$kind-entry.json")"
    fi
    if cmp -s "$b/$kind-files.sha256" "$a/$kind-files.sha256"; then
        result PASS "$what: files unchanged" "$(wc -l <"$a/$kind-files.sha256") files, same SHA-256"
    else
        local gone changed added
        gone=$(join -1 2 -2 2 -v1 <(sort -k2 "$b/$kind-files.sha256") <(sort -k2 "$a/$kind-files.sha256") | wc -l)
        changed=$(join -1 2 -2 2 <(sort -k2 "$b/$kind-files.sha256") <(sort -k2 "$a/$kind-files.sha256") | awk '$2!=$3{print $1}' | tr '\n' ' ')
        added=$(join -1 2 -2 2 -v2 <(sort -k2 "$b/$kind-files.sha256") <(sort -k2 "$a/$kind-files.sha256") | awk '{print $1}' | tr '\n' ' ')
        if [ "${kind%%-*}" = esp ]; then
            # SparkOS adds its own boot files to a shared EFI partition; Windows' must stay
            if [ "$gone" = 0 ] && ! grep -qi microsoft <<<"$changed"; then
                result PASS "$what: Windows boot files still there" "added: ${added:-none}"
                [ -n "$changed" ] && result WARN "$what: a file shared with Windows was replaced" "$changed(the fallback loader; Windows boots from EFI/Microsoft, which is unchanged)"
            else
                result FAIL "$what: Windows boot files removed or changed" "removed: $gone, changed: $changed"
            fi
        else
            result FAIL "$what: files changed" "removed: $gone, changed: ${changed:-none}, added: ${added:-none}"
        fi
    fi
    if [ "${kind%%-*}" = ntfs ]; then
        if cmp -s "$b/$kind-raw.sha256" "$a/$kind-raw.sha256"; then
            result PASS "$what: every byte unchanged" "sha256 $(cut -c1-16 "$a/$kind-raw.sha256")..."
        else
            result FAIL "$what: raw bytes changed" "before $(cat "$b/$kind-raw.sha256") after $(cat "$a/$kind-raw.sha256")"
        fi
    fi
}

verify() {
    record_all "$W/disk-after"
    case $layout in
    shared-esp)
        cmp_part esp-data "EFI partition (shared with Windows)"
        cmp_part ntfs-data "NTFS data partition"
        ;;
    two-disks)
        if cmp -s "$W/disk-before/win-whole.sha256" "$W/disk-after/win-whole.sha256"; then
            result PASS "Windows disk: every byte unchanged" "whole 32 GiB disk, same SHA-256"
        else
            result FAIL "Windows disk changed" "see disk-before/ and disk-after/"
            cmp_part esp-win "Windows disk EFI partition"
            cmp_part ntfs-win "Windows disk NTFS partition"
        fi
        cmp_part ntfs-data "NTFS data partition"
        ;;
    esac
    echo "After the install:"
    cat "$W/disk-after/data-table.txt" "$W/disk-after/data-parts.txt"
    result INFO "Data disk after the install" "$(sed -E 's/^loop[0-9]+//' "$W/disk-after/data-parts.txt" | tr '\n' ';' | sed 's/;/; /g')"
    if grep -q btrfs "$W/disk-after/data-parts.txt"; then
        result PASS "SparkOS went into the free space" "new btrfs partition next to the existing ones"
    else
        result FAIL "No SparkOS btrfs partition on the data disk" "see disk-after/data-parts.txt"
    fi
}

"$cmd"
