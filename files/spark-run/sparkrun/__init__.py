"""Spark Run: Windows programs on SparkOS, on Wine. Double-click an .exe or .msi to run it once
or install it as an app with its own Windows folder (Wine prefix) and a menu entry with the
program's own icon. Wine itself is downloaded on first use, checked against fingerprints pinned
in sources.py, and kept in ~/.local/share/spark-run.
"""

APP_NAME = "Spark Run"
APP_SLUG = "spark-run"           # command, folders, log names
APP_CLASS = "SparkRun"           # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkRun"
VERSION = "1.0.0"

# Where a plain error points people: what runs on SparkOS and what doesn't.
GUIDE_URL = "https://github.com/Wolklaw/sparkos/blob/main/docs/switching.md"
