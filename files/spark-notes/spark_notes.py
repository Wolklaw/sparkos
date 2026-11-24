#!/usr/bin/env python3
"""Spark Notes, the SparkOS quick notes and clipboard history. See README.md."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == '__main__':
    if sys.argv[1:] == ['--capture']:
        # wl-paste --watch starts this once per copy: load only the capture and core modules,
        # not the whole window code (and not argparse).
        from sparknotes.capture import capture_main  # noqa: E402
        sys.exit(capture_main())
    from sparknotes.app import main  # noqa: E402
    sys.exit(main())
