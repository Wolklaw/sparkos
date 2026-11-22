#!/usr/bin/env python3
"""Spark Space launcher: spark-space runs this."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sparkspace.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
