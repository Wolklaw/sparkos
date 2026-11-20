"""Spark Calc: the SparkOS calculator. Standard, scientific and programmer modes. Sums are
exact (0.1 + 0.2 is 0.3) because it counts in fractions and decimals with its own expression
parser, never Python's eval.
"""

APP_NAME = "Spark Calc"
APP_SLUG = "spark-calc"          # command, folders, log names
APP_CLASS = "SparkCalc"          # X11 window class, matched by the desktop file
APP_ID = "dev.wolklaw.SparkCalc"
VERSION = "1.0.0"

MODES = ("standard", "scientific", "programmer")
