"""Spark Disks: the PC's drives in one window. List drives and partitions, mount and unmount,
format, create, resize and delete partitions, read SMART health, write an image to a USB stick.
It talks to udisks2 (the service GNOME Disks and Plasma use); the system disk, Windows and D:
are marked, and D: can't be changed from here at all.
"""

APP_NAME = "Spark Disks"
APP_SLUG = "spark-disks"         # command, folders, log names
APP_CLASS = "SparkDisks"         # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkDisks"
VERSION = "0.1.0"

REFRESH_MS = 5000                # the list reloads this often while the window is visible
