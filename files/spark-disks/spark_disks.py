#!/usr/bin/env python3
"""Spark Disks launcher: spark-disks runs this."""
import sys

from sparkdisks.cli import main

if __name__ == "__main__":
    sys.exit(main())
