"""Spark Files: the SparkOS file manager. Browse with a sidebar, tabs and a split view, copy
and move big folders in the background, search by name, open files with their default app,
and keep working while it watches folders for changes. It is the system's file manager:
folders open in it, and "Show in folder" from other apps lands in it (FileManager1 on D-Bus).
"""

APP_NAME = "Spark Files"
APP_SLUG = "spark-files"         # command, folders, log names
APP_CLASS = "SparkFiles"         # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkFiles"
VERSION = "1.1.1"

BUS_NAME = "dev.wolklaw.SparkFiles"            # one copy per session; others hand over to it
BUS_PATH = "/dev/wolklaw/SparkFiles"
FM1_NAME = "org.freedesktop.FileManager1"      # "Show in folder" from every other app
FM1_PATH = "/org/freedesktop/FileManager1"

THUMB_MAX_BYTES = 200 * 1024 * 1024            # bigger photos get an icon, not a thumbnail
SERVICE_IDLE_MS = 15000                        # started by D-Bus and no window asked: quit
