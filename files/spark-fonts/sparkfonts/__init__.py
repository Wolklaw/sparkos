"""Spark Fonts: SparkOS's own font manager. Lists every font on the PC grouped by family,
previews any font file (installed or not) with Pillow, installs fonts for you and removes
them to the trash, and copies fonts from a Windows drive without ever writing to it.
"""

APP_NAME = "Spark Fonts"
APP_SLUG = "spark-fonts"         # command, folders, log names
APP_CLASS = "SparkFonts"         # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkFonts"
VERSION = "0.1.0"
