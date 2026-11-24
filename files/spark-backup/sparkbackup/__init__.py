"""Spark Backup: Btrfs snapshots of /home on a schedule, a copy of each on another drive, and a
way to get a file or folder back. Snapshots and copies are made by a root service; the window
browses and restores as the user."""

APP_NAME = "Spark Backup"
APP_SLUG = "spark-backup"        # command, folders, log names
APP_CLASS = "SparkBackup"        # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkBackup"
VERSION = "0.1.2"

SOURCE = "/home"                                    # the subvolume that is backed up
CONFIG_PATH = "/etc/spark-backup/config.json"       # written by the helper, read by the service
RUN_DIR = "/run/spark-backup"                       # state.json (now) and the lock
STATE_DIR = "/var/lib/spark-backup"                 # history.json (the last runs)
SNAP_FOLDER = ".spark-backup/snapshots"             # inside SOURCE
TARGET_FOLDER = "SparkBackup"                       # the only folder used on the target drive
HELPER = "/usr/libexec/spark-backup-helper"
TIMER_DROPIN = "/etc/systemd/system/spark-backup.timer.d/schedule.conf"
INTERVAL_MS = 3000                                  # window refresh while it is visible
