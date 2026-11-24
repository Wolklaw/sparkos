"""Spark Firewall: firewalld in plain words. On or off, which network is in which zone, and the
rules for the things people actually want (Steam Remote Play, Spark Link) plus ports by number.
Reads firewalld as the user; every change goes through one polkit-gated helper.
"""

APP_NAME = "Spark Firewall"
APP_SLUG = "spark-firewall"    # command, folders, log names
APP_CLASS = "SparkFirewall"    # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkFirewall"
VERSION = "0.1.1"

INTERVAL_MS = 4000             # firewalld is read again this often while the window is visible
