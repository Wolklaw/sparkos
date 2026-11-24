"""Spark Audio: the SparkOS sound mixer. Outputs and inputs with a live level, a volume and mute
for every app and a way to move it to another output, a small equalizer per output through
PipeWire's filter-chain, and a page for Focusrite Scarlett interfaces. It talks to PipeWire
through pw-dump, wpctl, pactl and pw-record; nothing runs in the background when it is closed
(the equalizer, once turned on, is a systemd user service you can remove from the EQ page).
"""

APP_NAME = "Spark Audio"
APP_SLUG = "spark-audio"         # command, folders, log names
APP_CLASS = "SparkAudio"         # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkAudio"
VERSION = "0.1.0"
