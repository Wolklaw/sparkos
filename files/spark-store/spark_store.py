#!/usr/bin/env python3
"""Spark Store launcher: spark-store runs this."""
import sys

from sparkstore.cli import main

if __name__ == "__main__":
    sys.exit(main())
