#!/usr/bin/env python3
"""Spark Connect launcher: spark-connect runs this (on Windows: py spark_connect.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sparkconnect.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
