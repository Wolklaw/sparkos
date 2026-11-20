"""Spark Edit: the SparkOS text and code editor. Small and fast: tabs, find and replace,
syntax colours for the common languages, files kept in their own encoding and line endings,
and unsaved work kept on disk so a crash or a power cut loses nothing.
"""

APP_NAME = "Spark Edit"
APP_SLUG = "spark-edit"          # command, folders, log names
APP_CLASS = "SparkEdit"          # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkEdit"
VERSION = "1.0.0"

AUTOSAVE_MS = 2000               # unsaved changes reach the disk this long after the last key
AUTOSAVE_BIG_MS = 20000          # the same, for buffers over BIG_BUFFER characters
BIG_BUFFER = 8 * 1024 * 1024
BIG_FILE = 5 * 1024 * 1024       # opened with word wrap off
LONG_LINE = 5000                 # characters coloured per line; the rest stays plain
