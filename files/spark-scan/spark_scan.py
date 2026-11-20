#!/usr/bin/env python3
"""Spark Scan launcher: spark-scan runs this."""
import sys

from sparkscan.cli import main

if __name__ == "__main__":
    sys.exit(main())
