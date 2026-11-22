"""Spark Snip: the SparkOS tool for snipping the screen, copying the text in it, and
recording it. Everything runs on this computer; nothing is uploaded.

It grew out of QuickOCR (github.com/Wolklaw/QuickOCR), whose Windows app is finished.
"""

APP_NAME = "Spark Snip"
APP_SLUG = "spark-snip"          # command, folders, log and lock names
APP_CLASS = "SparkSnip"          # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkSnip"
VERSION = "1.1.1"

MODES = ("text", "image", "video")
SHORTCUTS = {"text": "Meta+Shift+T", "image": "Print", "video": "Meta+Shift+R"}
