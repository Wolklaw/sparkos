"""The command line:

    spark-notes                    open the notes window
    spark-notes --clipboard        open the clipboard popup (Meta+V; again: close it)
    spark-notes --watch            keep the clipboard history (the background service runs this)
    spark-notes --capture          record the current clipboard once (wl-paste --watch runs this)
    spark-notes --list [QUERY]     print the clipboard history (newest first), no window
    spark-notes --pause / --resume stop or restart keeping the clipboard
    spark-notes --self-test        check what Spark Notes needs
"""

import argparse
from typing import List, Optional

from . import APP_NAME, VERSION


class Options(argparse.Namespace):
    clipboard: bool = False
    watch: bool = False
    capture: bool = False
    list: Optional[str] = None
    pause: bool = False
    resume: bool = False
    self_test: bool = False
    version: bool = False


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='spark-notes', description=f"{APP_NAME}: quick notes and clipboard history.",
        epilog="On SparkOS the clipboard popup opens with Meta+V.")
    p.add_argument('--clipboard', action='store_true',
                   help="open the clipboard history popup (again while open: close it)")
    p.add_argument('--watch', action='store_true',
                   help="keep the clipboard history until stopped (the background service)")
    p.add_argument('--capture', action='store_true', help=argparse.SUPPRESS)
    p.add_argument('--list', nargs='?', const='', metavar='QUERY',
                   help="print the clipboard history, or what matches QUERY, and exit")
    p.add_argument('--pause', action='store_true', help="stop keeping what you copy")
    p.add_argument('--resume', action='store_true', help="keep what you copy again")
    p.add_argument('--version', action='store_true', help="print the version and exit")
    p.add_argument('--self-test', dest='self_test', action='store_true',
                   help="check what Spark Notes needs, without a window")
    return p


def parse(argv: List[str]) -> Options:
    return parser().parse_args(argv, namespace=Options())


def version_line() -> str:
    return f"{APP_NAME} {VERSION}"
