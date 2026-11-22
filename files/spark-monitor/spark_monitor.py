#!/usr/bin/env python3
"""Spark Monitor launcher: spark-monitor runs this."""
import sys

from sparkmonitor.cli import main

if __name__ == "__main__":
    sys.exit(main())
