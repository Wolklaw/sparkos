#!/usr/bin/env python3
"""Spark Tray launcher: spark-tray runs this."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sparktray.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
