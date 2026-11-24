"""The command line:

    spark-emoji                    open the picker (again while it is open: close it)
    spark-emoji --search QUERY     print what the search finds, one per line, no window
    spark-emoji --self-test        check the data, the search and what pasting needs
"""

import argparse
from typing import List, Optional

from . import APP_NAME, VERSION


class Options(argparse.Namespace):
    search: Optional[str] = None
    self_test: bool = False
    version: bool = False
    limit: int = 20


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='spark-emoji', description=f"{APP_NAME}: the SparkOS emoji and symbol picker.",
        epilog="On SparkOS it opens with Meta+. (Windows key and full stop).")
    p.add_argument('--search', metavar='QUERY',
                   help="print the characters that match QUERY (English or French) and exit")
    p.add_argument('--limit', type=int, default=20, help="most results --search prints")
    p.add_argument('--version', action='store_true', help="print the version and exit")
    p.add_argument('--self-test', dest='self_test', action='store_true',
                   help="check the data and what Spark Emoji needs, without a window")
    return p


def parse(argv: List[str]) -> Options:
    return parser().parse_args(argv, namespace=Options())


def version_line() -> str:
    return f"{APP_NAME} {VERSION}"
