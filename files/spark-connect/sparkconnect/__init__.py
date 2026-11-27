"""Spark Connect: every home server on one screen. It asks each machine for its state over the
system ssh client (one read-only probe script per refresh, nothing installed on the server),
checks the public websites from this PC, and offers a few safe fixes, each confirmed first.

First part only: Linux machines over SSH. Later parts (a dial-out agent through a hub, the
GestionDirecte tablets) add a transport and a machine view; the probe's JSON stays the one
format every transport returns.
"""

APP_NAME = "Spark Connect"
APP_SLUG = "spark-connect"       # command, folders, log names
APP_CLASS = "SparkConnect"       # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkConnect"
VERSION = "0.2.1"

OPEN_REFRESH_S = 15              # the machine view that is open
BACKGROUND_REFRESH_S = 60        # every other machine, and the websites
SSH_TIMEOUT_S = 25               # one probe call, connection included
SITE_TIMEOUT_S = 5
LOG_LINES = 5                    # journal lines per unit in a refresh
