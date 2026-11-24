# Spark Disks

SparkOS's own disk tool: drives and partitions, mount and unmount, format, create, delete and resize partitions, SMART health, and writing an image to a USB stick. It replaces GNOME Disks (gnome-disk-utility, including its image writer and image mounter) for the owner. KDE Partition Manager is not installed as an app (only its library, kpmcore, comes with Plasma), so there is no menu entry to replace. Source: [files/spark-disks](../files/spark-disks). In the SparkOS image.

Status: built 2026-11-23. See "Not tried on hardware".

## Why

The owner's goal is as little software from others as possible ([PLAN.md](../PLAN.md), Independence roadmap). Disks and Firewall were the two admin tools left in the menu. The owner also has one real hazard that no stock disk tool knows about: the SATA SSD that Windows calls D: holds downloads and temp files and is never written from SparkOS, and the NVMe drive that holds SparkOS also holds Windows' E:. A tool that lists every drive with the same Format button is one slip away from the wrong drive.

## What

Three tabs.

- **Drives.** Every drive and partition as a tree, with free space between partitions: size, file system, label, where it is mounted, and a tag (SYSTEM, WINDOWS, D:, USB). Buttons for the selected row: Mount, Unmount, Format, New partition, Delete, Resize, Erase disk, Eject. A button that can't apply says why in the line under the list (a tooltip is not enough: nobody hovers a disabled button).
- **Health.** SMART for each drive that has it (SATA through libatasmart, NVMe through udisks): a plain verdict (Good, Warning, Failing, Unknown), temperature, hours on, and the counters that matter (reallocated, pending and uncorrectable sectors; for NVMe the spare, wear, media errors and critical warnings). A short self-test button and a refresh. Reading SMART is allowed everywhere, including D:.
- **Write image.** An `.iso` or `.img` (also `.gz`, `.xz`, `.bz2`) to a USB stick or SD card, with a progress bar, Cancel, and a read-back check. Only removable drives are offered, never an internal drive.

### How it talks to the disks

udisks2 over D-Bus (PyGObject's Gio), the service GNOME Disks and Plasma use. No raw `parted`, no root code of our own, no pkexec helper: udisks asks polkit for each action, so the password prompt is the system's. Spark Disks lists with `lsblk --json` (read only) and acts with udisks methods: `Filesystem.Mount/Unmount`, `Block.Format`, `PartitionTable.CreatePartitionAndFormat`, `Partition.Delete/Resize`, `Filesystem.Resize`, `Drive.Eject`, `Drive.Ata.*` and `NVMe.Controller.*` for SMART, and `Block.OpenDevice` for the image writer (udisks hands back a file descriptor, so the app writes the stick without ever being root).

### Safety rules (the owner's)

Every destructive action is checked three times: the button is off when it is refused, the dialog states the refusal, and the operation layer (`ops.py`) looks the device up again just before acting and refuses on its own. A bug in the window can't skip the last one.

- **Locked (look only): D:** and the drive it sits on. The test is the Windows-drive list SparkOS keeps (`/run/sparkos/windows-drives.json`, letter D), or a mount at `/var/mnt/d` or `/mnt/d`. No mount, unmount, format, delete, resize, erase or image write. SMART can still be read.
- **Locked: what the running system uses.** A partition mounted at `/`, `/boot`, `/boot/efi`, `/var`, `/sysroot`, `/usr`, `/etc`, `/home` or as swap can't be unmounted, formatted, deleted or resized. Erase disk is refused on a drive that holds any of them.
- **Hard confirmation: Windows partitions, anything else on the system disk, and any other internal drive.** The dialog names the device, model, size and label, says what is lost, and the button stays off until the person types the device name (for example `nvme1n1p1`). Cancel is the default.
- **Ordinary confirmation: removable drives.** The same dialog shows the facts; Cancel is the default; no typing.
- **The image writer only offers removable drives** (USB sticks, SD cards), refuses one that holds the system or D:, and refuses an image bigger than the stick.
- Nothing runs by itself. Opening the window changes nothing.

## Copy

Plain verbs: Format, Delete, Mount, Unmount, Write, Cancel. Say what is lost ("Everything on this partition is erased"). English and French.

## Packages

`udisks2` (already there), `python3-gobject`, `smartmontools`, and the `mkfs` tools for the file systems it offers (e2fsprogs, xfsprogs, btrfs-progs, ntfs-3g, exfatprogs, dosfstools) are in the image. The file system list shows only what udisks reports it can format on this PC.

GNOME Disks stays installed but hidden (`org.gnome.DiskUtility`, `gnome-disk-image-writer`, `gnome-disk-image-mounter`) for one release, like Dolphin and Ark, then it goes. Cockpit's storage page is untouched.

## Not tried on hardware

Tested against fake data, and on loop devices backed by image files in `/tmp`, never on a real disk. The first use on real USB sticks is the owner's. In particular: the udisks polkit prompts in a Plasma session, write speed and the read-back on a real stick, resizing an NTFS partition, and what a real failing drive reports.

## Later

Encrypted (LUKS) partitions, a bad-block scan, a disk benchmark, mounting an image file, mount options in fstab, and a per-drive "protect this drive" list the owner can add to (the lock for D: is built in).
