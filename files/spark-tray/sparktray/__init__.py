"""Spark Tray: the SparkOS tray applets. Network, Bluetooth, power and battery, printers and
volume, each its own StatusNotifierItem with a menu and a small popup. They talk to
NetworkManager, BlueZ, UPower, power-profiles-daemon (tuned-ppd on SparkOS), logind and CUPS
directly, and to PipeWire through Spark Audio. They are the image's network, Bluetooth,
battery, printer and volume tray."""

APP_NAME = "Spark Tray"
APP_SLUG = "spark-tray"
APP_ID = "dev.wolklaw.SparkTray"
BUS_NAME = APP_ID
VERSION = "0.1.0"
