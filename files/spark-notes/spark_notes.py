#!/usr/bin/env python3
"""Spark Notes, the SparkOS quick notes and clipboard history. See README.md."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sparknotes.app import main  # noqa: E402

if __name__ == '__main__':
    sys.exit(main())
