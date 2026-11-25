"""The command line:

    spark-boxes                  open the window
    spark-boxes NAME             open that machine's screen (starts it first when it is off)
    spark-boxes --list           print the machines and their state, no window
    spark-boxes --start NAME     turn a machine on, no window
    spark-boxes --shutdown NAME  ask a machine to shut down, no window
    spark-boxes --self-test      check what Spark Boxes needs
"""

import argparse
from typing import List, Optional

from . import APP_NAME, VERSION


class Options(argparse.Namespace):
    machine: Optional[str] = None
    list: bool = False
    start: Optional[str] = None
    shutdown: Optional[str] = None
    self_test: bool = False
    version: bool = False


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='spark-boxes', description=f"{APP_NAME}: virtual machines.",
        epilog="Set up once with: spark virt setup (then log out and in).")
    p.add_argument('machine', nargs='?', help="open this machine's screen")
    p.add_argument('--list', action='store_true', help="print the machines and exit")
    p.add_argument('--start', metavar='NAME', help="turn a machine on and exit")
    p.add_argument('--shutdown', metavar='NAME', help="ask a machine to shut down and exit")
    p.add_argument('--version', action='store_true', help="print the version and exit")
    p.add_argument('--self-test', dest='self_test', action='store_true',
                   help="check what Spark Boxes needs, without a window")
    return p


def parse(argv: List[str]) -> Options:
    return parser().parse_args(argv, namespace=Options())


def version_line() -> str:
    return f"{APP_NAME} {VERSION}"
