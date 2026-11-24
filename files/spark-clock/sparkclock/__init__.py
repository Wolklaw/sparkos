"""Spark Clock: alarms, timers, a stopwatch and world clocks. A small background service
(`spark-clock --daemon`, a systemd user unit) rings alarms and timers with the window closed and
after a restart; the window edits them and shows the time."""

APP_NAME = "Spark Clock"
APP_SLUG = "spark-clock"         # command, folders, log names
APP_CLASS = "SparkClock"         # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkClock"
VERSION = "0.1.0"
