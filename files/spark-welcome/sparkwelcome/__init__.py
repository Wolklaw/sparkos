"""Spark Welcome: the SparkOS first-login guide, step by step. It says what is different from
Windows and what stays the same, opens your other drives at every start, copies your folders from
a Windows partition without writing to it, offers game launchers and popular apps from Flathub
(nothing installs until you click), checks graphics, sound, printers, network and updates, and
says what to check before you erase Windows.

The steps (catalog, flatpak, windows, drives, checks) have no window code in them, so a future Spark
Portal can reuse them; app.py and pages.py are the window.
"""

APP_NAME = "Spark Welcome"
APP_SLUG = "spark-welcome"       # command, folders, log names
APP_CLASS = "SparkWelcome"       # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkWelcome"
VERSION = "1.2.0"

PAGES = ("welcome", "different", "familiar", "drives", "windows", "games", "apps", "checks",
         "erase", "done")
