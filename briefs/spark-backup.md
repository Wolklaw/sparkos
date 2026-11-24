# Spark Backup

Backups for the owner's PC: Btrfs snapshots of `/home` on a schedule, a copy of each one on another drive, a way to look inside a snapshot and get a file or folder back, and "keep the last N". Nothing covered this before (Btrfs Assistant is hidden, and it is not a backup tool). Source: [files/spark-backup](../files/spark-backup). In the SparkOS image.

Status: built 2026-11-23, version 0.1.0. Snapshots, pruning, browsing and restoring were run for real on a throwaway Btrfs image in `/tmp`. **Nothing has been run on the real `/home`, on the real disks or as root yet**, and `btrfs send | receive` (root only) was tested only against a fake runner. See "Not tried on hardware".

## How `/home` is laid out here (read on 2026-11-23, read only)

- One Btrfs filesystem, label `sparkos`, on `nvme1n1p4`. `/var/home` (and `/home`, a link to it) is the subvolume `home`, id 257, mounted next to `/var` (subvolume `var`, 256) and `/sysroot` (subvolume `root`, 258).
- The other drives are all NTFS: `D:` is `sda2` (label Scrap, about 104 GB free), `E:` is `nvme1n1p1` (Games), `C:` is `nvme0n1p3`. `/home` is about 229 GB.
- So a snapshot of `/home` is cheap and instant (same filesystem, shared blocks), but it is **not a backup** on its own: if the disk dies, the snapshots die with it. That is why the copy to another drive is the point of the app. And the only other drives in this PC are NTFS, which Btrfs cannot send to (see "What it does").

## What it does

- **Snapshot.** A read-only snapshot of the `home` subvolume in `/home/.spark-backup/snapshots/<date>_<time>` (for example `2026-11-23_020000`). It lives inside the subvolume it snapshots, the way snapper does it: a snapshot never contains snapshots, and the hidden folder keeps them on the same filesystem so they cost no copy. Created by a root service, so the owner needs no password at 2 a.m.
- **Copy to a drive.** One target drive, chosen by filesystem UUID (so it works wherever it is mounted). Everything goes in one folder, `SparkBackup/<hostname>/`, on that drive; nothing else on the drive is read or written.
  - **Btrfs target:** `btrfs send` (incremental from the newest snapshot both sides have) piped into `btrfs receive`. The copy is a real read-only snapshot on the drive, with its own history.
  - **ext4, xfs or NTFS target:** `rsync` of the snapshot into a plain folder `<date>_<time>`, hardlinked against the previous one (`--link-dest`) so unchanged files take no space. It is written as `<name>.partial` and renamed when finished, so an interrupted copy never looks like a backup. Caches, the Steam game library (`steamapps/common`, which Steam can download again), the trash and the snapshot folder itself are left out. **On NTFS, Linux owners, permissions and some file names (`:`, `?`, `*`) do not survive**: files that can't be written are counted and listed, not hidden.
  - exFAT and FAT are refused with a reason (no hardlinks, no owners: every copy would be a full one).
  - The system disk itself is refused as a target (a copy on the same disk does not survive the disk).
- **Browse and restore.** The Browse tab opens any snapshot, on this PC or on the drive, as a folder tree. "Restore here" copies the chosen file or folder next to where it was, named `name (restored 2026-11-23 02:00)`: it never overwrites. "Restore to..." puts it in a folder the owner picks. Restoring runs as the owner, with the owner's own permissions on the snapshot, so it needs no password.
- **Keep the last N.** Two numbers: how many snapshots to keep on the PC (default 7) and how many copies to keep on the drive (default 14). Older ones are removed after a successful run. The newest snapshot that is also on the drive is always kept (it is the parent of the next incremental copy), and the newest snapshot is never removed.
- **Schedule.** A systemd timer: daily at a chosen time (default 02:00) or weekly, `Persistent=true` so a PC that was off at that time runs it at the next start. Off until the owner saves a schedule: a fresh install does nothing.
- **Drive not plugged in.** The snapshot is still taken; the copy is skipped and the run says so. The next run sends everything the drive is missing.

## Why a root service and a polkit helper

Sending, receiving and mounting need root, and the schedule must run with nobody logged in. Same shape as Spark Controller:

1. `spark-backup.service` and `spark-backup.timer` run `spark-backup-helper run` as root. Nothing is enabled until a schedule is saved.
2. The window never writes to `/etc` or a disk. To save the settings, start a run now or remove a snapshot it runs `pkexec /usr/libexec/spark-backup-helper <action>` (polkit action `dev.wolklaw.SparkBackup.manage`, password once per session). The helper validates the settings with the same code the service uses, checks every snapshot name against a strict pattern, and refuses any path that is not inside the snapshot folder or the `SparkBackup` folder. It starts Python with `-I`.
3. The window reads `/run/spark-backup/state.json` (what the run is doing now) and `/var/lib/spark-backup/history.json` (the last 30 runs), both world readable and free of secrets.

## Safety

- The tests never snapshot, send or restore the real `/home` and never write to a real disk. Every test runs in a temporary folder, on a throwaway Btrfs image, or against a fake runner.
- `D:` and the other NTFS drives are used only if the owner picks one in Settings, and then only inside `SparkBackup/`.
- Delete is limited by code to names that match `YYYY-MM-DD_HHMMSS` inside the two backup folders, and to Btrfs subvolumes there (inode 256) or plain folders on a copy target, so a bad name can't remove anything else.
- A failed receive removes only the half-received copy it just started.
- A lock keeps the timer and "Back up now" from running together.

## Window

Three tabs, in the house style (dark, 3 px corners, mint with the magenta and cyan slip, mono type):

- **Backups:** last backup (when, worked or not), next run, the target drive and whether it is plugged in, the list of snapshots with "On this PC" and "On the drive" columns, **Back up now**, **Remove**.
- **Browse:** pick a snapshot, walk its folders, **Restore here**, **Restore to...**.
- **Settings:** the drive (a list of what is plugged in, with its type, size and free space, and why one can't be used), schedule, keep counts, **Save**, **Turn off**.

French and English follow the PC's language.

## Not tried on hardware

- Anything on the real `/home`, the real timer, a real boot with the service present.
- `btrfs send | receive` to a second Btrfs drive: needs root, so it was run against a fake runner only (the exact command lines and the clean-up on failure are tested).
- rsync to a real NTFS drive such as `D:`, including the file name and ownership losses described above.
- The temporary mount of a target that is not mounted (`mount` by UUID), and a USB disk being unplugged mid-copy.
- The pkexec prompts.
- How long the first copy of `/home` takes.

## Decisions for the owner

1. **Target drive.** `D:` has 104 GB free and is NTFS; `/home` is about 229 GB, so the first copy fits only if what is left after the default excludes (caches, the Steam library, the trash) is under about 100 GB. A second internal or USB drive formatted Btrfs would give real incremental snapshots on the drive.
2. **Schedule.** Default daily 02:00 with catch-up at the next start.
3. **How many to keep.** Default 7 on the PC, 14 on the drive.

## Later

Restore by replacing a file (with the old one set aside), excludes the owner edits, copies to another machine over SSH (the OptiPlex), encrypted copies, a size column per snapshot, and a "what changed since" view between two snapshots.
