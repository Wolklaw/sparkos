#!/usr/bin/env python3
"""Spark Bench launcher: spark-bench runs this."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sparkbench.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
