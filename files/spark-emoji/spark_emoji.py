#!/usr/bin/env python3
"""Spark Emoji, the SparkOS emoji and symbol picker. See README.md."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sparkemoji.app import main  # noqa: E402

if __name__ == '__main__':
    sys.exit(main())
