#!/usr/bin/env python3
"""Spark Firewall launcher: spark-firewall runs this."""
import sys

from sparkfirewall.cli import main

if __name__ == "__main__":
    sys.exit(main())
