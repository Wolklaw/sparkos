"""Spark Space: see what fills a drive. Lists the drives with how full they are, scans a folder
in the background (without crossing into other drives, following links or counting a hard
link twice), and shows the result as a treemap and a sorted list. Open, Show in folder and
Move to Trash; it never deletes anything for good.
"""

APP_NAME = "Spark Space"
APP_SLUG = "spark-space"         # command, folders, log names
APP_CLASS = "SparkSpace"         # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkSpace"
VERSION = "1.0.0"
