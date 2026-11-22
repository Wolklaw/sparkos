"""Spark Terminal: the SparkOS terminal. Tabs, split panes, search, links and the SparkOS
colours around VTE, the terminal library GNOME's terminals use. VTE does the terminal
emulation (escape codes, Unicode, mouse, true colour); everything around it is Spark's own.
"""

APP_NAME = "Spark Terminal"
APP_SLUG = "spark-terminal"      # command, folders, log names
APP_ID = "dev.wolklaw.SparkTerminal"
VERSION = "1.0.0"

GTK_VERSION = "4.0"
VTE_VERSION = "3.91"             # VTE's GTK 4 API (Fedora package vte291-gtk4)
