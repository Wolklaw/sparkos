#!/usr/bin/env python3
"""Spark Controller launcher: spark-controller runs this."""
import sys

from sparkcontroller.cli import main

if __name__ == "__main__":
    sys.exit(main())
