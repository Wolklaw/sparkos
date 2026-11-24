# Spark Backup

Snapshots of your home folder on a schedule, a copy on another drive, and file restore.

It follows the PC's language: French when the system language is French, English otherwise; `SPARK_LANG=fr` or `SPARK_LANG=en` picks one for a single run.

Version 0.1.2. It has been tested with fake `btrfs` and `lsblk` output, plain folders, a throwaway loop image and a temp folder. On 2026-11-24 the parts that need no root were run on the real /home (found as a Btrfs subvolume) and the real drives (listed; a drive mounted read-only, like D:, is refused). A real snapshot, copy and restore have not been tried yet; they need a polkit approval. Spark Backup ships in the SparkOS image ([build step](../scripts/spark-backup.sh)) and installs system-wide only (`sudo bash install.sh --deps`), because a root service takes the snapshots. Design and the reasons for the choices: [briefs/spark-backup.md](../../briefs/spark-backup.md).

- **Backups:** when the last backup ran, when the next one will, which drive gets the copy, and every backup with where it is (on this PC, on the drive). Back up now, Remove, Browse.
- **Browse:** pick a snapshot, walk its folders, restore a file or folder. Restore never overwrites: it copies beside the original as `name (restored YYYY-MM-DD HH:MM)`, or to a folder you pick.
- **Settings:** the drive for the copy, daily or weekly, the time, and how many to keep (7 on this PC and 14 on the drive to start). Nothing is enabled until you save.

How it works:

- A snapshot is a read-only Btrfs snapshot of /home, kept in `/home/.spark-backup/snapshots/<date_time>`.
- A Btrfs drive gets `btrfs send` and `btrfs receive`, incremental from the last copy. Any other drive (NTFS, ext4) gets rsync with hard links to the previous copy. FAT and exFAT, and the system drive, are refused.
- The drive is picked by filesystem UUID, so it still works when the letters change. An unmounted drive is mounted for the run and unmounted after.
- Keeping the last N never removes the newest snapshot or the one the last copy is based on.
- Saving settings, starting a backup and removing a snapshot ask for your password once (polkit). Looking and restoring do not.

`spark-backup --self-test` checks the tools, reads the /home layout (read-only) and runs the copy and keep rules in a temp folder. It never creates a snapshot.

Settings are in `/etc/spark-backup/config.json`, the schedule in `/etc/systemd/system/spark-backup.timer.d/`, history in `/var/lib/spark-backup/`. `install.sh --uninstall` removes the app and leaves those, your snapshots and your copies.

## Tests

```
cd files/spark-backup
python3 -m unittest discover -s tests -v
SPARK_LANG=fr python3 -m unittest discover -s tests -v
```

They use a fake runner and plain folders. Nothing creates or deletes a real snapshot or writes to a drive. Window tests are skipped without a display. `tests/test_btrfs_real.py` runs only when `SPARK_BACKUP_TEST_BTRFS` points at a folder on a loop device (never under /home).
