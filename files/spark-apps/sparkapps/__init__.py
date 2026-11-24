"""Spark Apps: signed per-app updates for the Spark apps, installed live (no reboot).

The image ships a built-in copy of every app. A root service (spark-apps-update) fetches one
signed index and installs a newer signed app bundle into /var/lib/spark-apps, root-owned. The
launcher (/usr/lib/spark-apps/launch.py, run by /usr/bin/spark-<app>) picks the newest verified
copy whose system_api matches the image's, else the built-in one. Root code never reads /var.
"""

VERSION = "1.0.0"

# Where the signed index lives: one file on a fixed release (docs/app-updates.md says why)
INDEX_URL = "https://github.com/Wolklaw/sparkos/releases/download/apps-index/index.json"
# Bundles must come from here (the signed index also pins each bundle's sha256 and size)
URL_PREFIX = "https://github.com/Wolklaw/sparkos/releases/download/"

INDEX_TYPE = "sparkos-app-index"
INDEX_FORMAT = 1

MAX_INDEX_BYTES = 256 * 1024
MAX_BUNDLE_BYTES = 64 * 1024 * 1024         # the compressed download
MAX_UNPACKED_BYTES = 256 * 1024 * 1024
MAX_ENTRIES = 5000
MAX_PATH_DEPTH = 16
HTTP_TIMEOUT = 30                           # seconds without data
HTTP_DEADLINE = 300                         # seconds for one whole download
