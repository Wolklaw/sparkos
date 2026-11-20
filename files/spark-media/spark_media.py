#!/usr/bin/env python3
"""Spark Media launcher: /usr/bin/spark-media runs this."""
import sys

from sparkmedia.app import main

if __name__ == "__main__":
    sys.exit(main())
