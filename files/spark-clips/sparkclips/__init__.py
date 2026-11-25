"""Spark Clips: instant replay for games. A background service keeps the last seconds of one
monitor in RAM, encoded on the GPU, and saves them as a clip on Meta+Alt+G. The window is the
clip library and the settings."""

APP_NAME = "Spark Clips"
APP_SLUG = "spark-clips"         # command, folders, log names
APP_CLASS = "SparkClips"         # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkClips"
VERSION = "0.1.0"
