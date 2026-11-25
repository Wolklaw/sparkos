#!/usr/bin/env python3
"""Spark Boxes, the SparkOS virtual machines. See README.md."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == '__main__':
    from sparkboxes.app import main  # noqa: E402
    sys.exit(main())
