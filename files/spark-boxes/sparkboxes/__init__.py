"""Spark Boxes: SparkOS's own virtual machines (replaces virt-manager and VirtualBox).
It talks to libvirt (QEMU/KVM) and shows a machine's screen over SPICE."""

APP_NAME = "Spark Boxes"
APP_SLUG = "spark-boxes"         # command, folders, log names
APP_ID = "dev.wolklaw.SparkBoxes"
VERSION = "0.1.0"

GTK_VERSION = "3.0"              # spice-gtk's widget is GTK 3 only
