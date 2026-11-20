"""Spark Store: SparkOS's own app store. The Spark apps first, then every app on Flathub, read
from the Flathub catalog that flatpak keeps on this PC (no web API, no account, no tracking).
Apps install for you only, with `flatpak install --user`, one at a time in a queue.
"""

APP_NAME = "Spark Store"
APP_SLUG = "spark-store"         # command, folders, log names
APP_CLASS = "SparkStore"         # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkStore"
VERSION = "0.1.0"

REMOTE = "flathub"               # the Flatpak remote the catalog and installs come from
FLATHUB_REPO = "https://dl.flathub.org/repo/flathub.flatpakrepo"
INDEX_VERSION = 3                # bump when the cached index's layout changes
CATALOG_MAX_AGE_H = 24           # refresh the catalog through flatpak when older than this
