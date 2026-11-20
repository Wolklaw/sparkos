"""Spark Games: one library for every installed game on SparkOS. It reads what Steam, Heroic
(Epic, GOG, Amazon) and Lutris have installed, plus games you add yourself, and starts each one
through its own launcher. It never changes the launchers' files and it is not a store.
"""

APP_NAME = "Spark Games"
APP_SLUG = "spark-games"         # command, folders, log names
APP_CLASS = "SparkGames"         # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkGames"
VERSION = "0.1.0"

# Where a game comes from (its badge and filter) and which program starts it.
SOURCES = ("steam", "epic", "gog", "amazon", "lutris", "own")
LAUNCHER_OF = {"steam": "steam", "epic": "heroic", "gog": "heroic", "amazon": "heroic",
               "lutris": "lutris", "own": "own"}

# Flatpak IDs of the launchers (on SparkOS they are Flatpaks, under ~/.var/app/<id>/)
STEAM_FLATPAK = "com.valvesoftware.Steam"
HEROIC_FLATPAK = "com.heroicgameslauncher.hgl"
LUTRIS_FLATPAK = "net.lutris.Lutris"
BOTTLES_FLATPAK = "com.usebottles.bottles"
