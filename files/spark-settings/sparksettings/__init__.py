"""Spark Settings: SparkOS's own settings app. One window with a sidebar of pages and a search
across every setting. Each page changes things through the system's own tools (wlr-randr,
wpctl, nmcli, bluetoothctl, ...) or the Spark compositor's and shell's settings files.
"""

APP_NAME = "Spark Settings"
APP_SLUG = "spark-settings"      # command, folders, log names
APP_CLASS = "SparkSettings"      # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkSettings"
VERSION = "1.1.0"
