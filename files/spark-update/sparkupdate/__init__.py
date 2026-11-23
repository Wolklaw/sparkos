"""Spark Update: SparkOS's own updater. A systemd timer (no daemon) checks for a new SparkOS
image, downloads and stages it and updates Flatpak apps; a notification says when the new
version is ready; the window shows what changed, checks now, restarts, and rolls back.
It never restarts the PC on its own.
"""

APP_NAME = "Spark Update"
APP_SLUG = "spark-update"        # command, folders, log names
APP_CLASS = "SparkUpdate"        # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkUpdate"
VERSION = "1.1.1"

IMAGE = "ghcr.io/wolklaw/sparkos"
# Every image Spark Update knows
IMAGES = (IMAGE,)

# Where the image-wide parts live (the system install puts them there; tests use --root)
CONF_PATH = "/etc/sparkos/update.conf"           # system settings, written through pkexec
STATE_PATH = "/var/lib/spark-update/state.json"   # what the last background run did
SYSTEM_LOG = "/var/log/spark-update/spark-update.log"
RELEASE_PATH = "/usr/share/sparkos/release.json"  # what's inside this image (spark-update.sh)
HELPER = "/usr/libexec/spark-update-helper"      # the only part that runs as root on request
POLKIT_ACTION = "dev.wolklaw.SparkUpdate.helper"
