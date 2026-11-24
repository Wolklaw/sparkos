#!/usr/bin/env python3
"""Spark Backup launcher: spark-backup runs this."""
import sys

from sparkbackup.cli import main

if __name__ == "__main__":
    sys.exit(main())
