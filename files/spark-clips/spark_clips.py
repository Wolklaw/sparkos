#!/usr/bin/env python3
"""Spark Clips launcher: spark-clips runs this."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sparkclips.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
