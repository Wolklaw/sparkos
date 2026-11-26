"""Spark Settings: SparkOS's own settings app, in place of KDE's System Settings. One window
with a sidebar of pages and a search across every setting. Each page changes things through
the system's own tools (wlr-randr, wpctl, nmcli, bluetoothctl, ...); whatever it doesn't
cover yet opens KDE's own module (kcmshell6) from "More settings", so nothing is lost.
"""

APP_NAME = "Spark Settings"
APP_SLUG = "spark-settings"      # command, folders, log names
APP_CLASS = "SparkSettings"      # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkSettings"
VERSION = "1.1.0"
