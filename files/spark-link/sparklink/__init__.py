"""Spark Link: the phone and the PC, linked over the local network with no outside service.

A background user service (spark-link --service) announces the PC over mDNS, accepts the
phones paired with it over pinned mutual TLS, and handles links, the shared clipboard, files,
phone notifications, battery and "Find my phone". The window (spark-link) pairs phones and
switches features. The protocol is docs/spark-link-protocol.md in the SparkOS repo; the phone
side lives in Soot's Android app.
"""

import os as _os

APP_NAME = "Spark Link"
APP_SLUG = "spark-link"          # command, folders, log names
APP_CLASS = "SparkLink"          # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkLink"
VERSION = "1.0.0"

PROTOCOL = 1                     # docs/spark-link-protocol.md, "v"
SERVICE_TYPE = "_sparklink._tcp"
DEFAULT_PORT = 47100
FEATURES = ("url", "clipboard", "files", "notify", "battery", "ring")
DEFAULT_FEATURES = {"url": True, "clipboard": False, "files": True, "notify": True,
                    "battery": True, "ring": True}

MAX_FRAME = 1 << 20              # 1 MiB, JSON or binary
MAX_CHUNK = 64 * 1024            # binary frame after file.chunk
MAX_FILE = 16 << 30              # 16 GiB
IDLE_TIMEOUT = 75.0              # seconds of silence before a link is dropped
PAIR_CODE_TTL = 300.0            # a pairing code lives 5 minutes
PAIR_MAX_WRONG = 5               # wrong codes before the pairing session is cancelled
PAIR_CONFIRM_TIMEOUT = 120.0     # the user has this long to confirm on the PC
OFFER_TIMEOUT = 120.0            # and this long to accept an incoming file
FIRST_FRAME_TIMEOUT = 10.0       # an unpaired connection must send pair within this
MAX_CONNECTIONS = 8

# the tests run the waits faster; nothing else sets this
_SCALE = float(_os.environ.get('SPARK_LINK_TEST_TIMESCALE') or 1) or 1.0
if _SCALE != 1.0:
    IDLE_TIMEOUT *= _SCALE
    PAIR_CONFIRM_TIMEOUT *= _SCALE
    OFFER_TIMEOUT *= _SCALE
