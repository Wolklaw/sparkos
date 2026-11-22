"""Spark Bench: game benchmarks on SparkOS without the hand work. It sets MangoHud up to record
on a hotkey (for the Flatpak Steam too), plays a sound when a recording starts and ends, works
out average FPS and the lows for every run, and compares them with Windows PresentMon runs.

Optional Spark app: not in the SparkOS image, installed per user."""

APP_NAME = "Spark Bench"
APP_SLUG = "spark-bench"         # command, folders, log names
APP_CLASS = "SparkBench"         # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkBench"
VERSION = "0.1.0"

DEFAULT_HOTKEY = "Control_L+F11"     # MangoHud's name for Ctrl+F11
DEFAULT_DURATION_S = 90
WATCH_INTERVAL_MS = 500              # how often the output folder is listed while watching
