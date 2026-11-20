#!/usr/bin/env python3
"""Spark Update launcher: spark-update runs this."""
import sys

from sparkupdate.cli import main

if __name__ == "__main__":
    sys.exit(main())
