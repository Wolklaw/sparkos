"""Spark Monitor: the SparkOS task manager. Ctrl+Shift+Esc opens it. It lists apps grouped the
way Plasma starts them, ends the ones that stopped responding, graphs the CPU, memory, GPU,
disks and network, and switches startup apps on and off. It reads /proc and /sys directly and
runs nothing in the background.
"""

APP_NAME = "Spark Monitor"
APP_SLUG = "spark-monitor"       # command, folders, log names
APP_CLASS = "SparkMonitor"       # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkMonitor"
VERSION = "1.0.1"
SHORTCUT = "Ctrl+Shift+Esc"

INTERVAL_MS = 1000               # one sample a second while the window is visible
HISTORY = 60                     # seconds of graph
END_GRACE_S = 5.0                # SIGTERM, then SIGKILL after this long
