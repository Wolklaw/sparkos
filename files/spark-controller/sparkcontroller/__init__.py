"""Spark Controller: one place for the PC's hardware. Fans (curves with smoothing, applied by a
small service), RGB lighting, and firmware updates. Drivers come with the system image.
"""

APP_NAME = "Spark Controller"
APP_SLUG = "spark-controller"    # command, folders, log names
APP_CLASS = "SparkController"    # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkController"
VERSION = "1.0.0"

INTERVAL_MS = 2000               # one sample every two seconds while the window is visible
SYSTEM_CONFIG = "/etc/spark-controller/fans.json"   # read by the daemon, written by the helper
RUN_DIR = "/run/spark-controller"                   # daemon state, readable by everyone
