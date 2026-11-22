"""Spark Welcome: the SparkOS first-login helper. It offers game launchers and popular apps from
Flathub (nothing installs until you click), copies your folders from a Windows partition without
writing to it, and checks graphics, sound, printers, network and updates.

The steps (catalog, flatpak, windows, checks) have no window code in them, so a future Spark
Portal can reuse them; app.py and pages.py are the window.
"""

APP_NAME = "Spark Welcome"
APP_SLUG = "spark-welcome"       # command, folders, log names
APP_CLASS = "SparkWelcome"       # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkWelcome"
VERSION = "1.0.3"

PAGES = ("welcome", "games", "apps", "windows", "checks", "done")
