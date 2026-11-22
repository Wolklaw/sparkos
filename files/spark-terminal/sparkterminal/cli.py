"""The command line, in Konsole's shape so the scripts that start Konsole can switch:

    spark-terminal [--workdir DIR] [--hold] [--title TITLE] [-e COMMAND [ARGS...]]

Everything after -e (or -x, or --) is the command, arguments included. A single -e argument
with spaces in it ("-e 'ls -l'") is split the way a shell would, as Konsole does, unless it
names a program that exists as written. --nofork, --new-tab and --separate are accepted and
change nothing: every spark-terminal runs in its own process and returns when its window
closes, which is what scripts that wait for --nofork expect.
"""

import argparse
import os
import shlex
import shutil
from typing import List, Optional

from . import APP_NAME, VERSION

COMMAND_FLAGS = ('-e', '-x', '--')
VALUE_OPTIONS = ('--workdir', '--working-directory', '--title', '-T', '-p', '--profile')


class Options(argparse.Namespace):
    workdir: Optional[str] = None
    title: Optional[str] = None
    hold: bool = False
    command: List[str] = []
    self_test: bool = False
    version: bool = False
    bench: bool = False


def split_command(argv: List[str]):
    """(options, command): the command is everything after the first -e/-x/--."""
    i = 0
    while i < len(argv):
        token = argv[i]
        if token in COMMAND_FLAGS:
            return argv[:i], argv[i + 1:]
        if token in VALUE_OPTIONS:
            i += 2
            continue
        i += 1
    return argv, []


def normalize_command(command: List[str]) -> List[str]:
    """['ls -l'] -> ['ls', '-l'] when 'ls -l' isn't itself a program; anything else as given."""
    if len(command) == 1 and any(c.isspace() for c in command[0]):
        word = os.path.expanduser(command[0])
        exists = os.path.isfile(word) if os.sep in word else shutil.which(word) is not None
        if not exists:
            try:
                return shlex.split(command[0]) or command
            except ValueError:
                return command
    return command


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='spark-terminal', description=f"{APP_NAME}: the SparkOS terminal.",
        epilog="-e COMMAND [ARGS...]   run COMMAND instead of your shell; everything after -e "
               "belongs to it")
    p.add_argument('--workdir', '--working-directory', dest='workdir', metavar='DIR',
                   help="start in DIR")
    p.add_argument('--hold', '--noclose', dest='hold', action='store_true',
                   help="keep the tab open after the command ends")
    p.add_argument('--title', '-T', dest='title', help="the window's title")
    p.add_argument('--version', action='store_true', help="print the version and exit")
    p.add_argument('--self-test', dest='self_test', action='store_true',
                   help="check what Spark Terminal needs, without a window")
    p.add_argument('--bench', action='store_true', help=argparse.SUPPRESS)
    # accepted for Konsole's callers; Spark Terminal always behaves this way
    for flag in ('--nofork', '--new-tab', '--separate', '--fullscreen'):
        p.add_argument(flag, action='store_true', help=argparse.SUPPRESS)
    p.add_argument('-p', '--profile', help=argparse.SUPPRESS)
    return p


def parse(argv: List[str]) -> Options:
    own, command = split_command(list(argv))
    opts = parser().parse_args(own, namespace=Options())
    opts.command = normalize_command(command)
    return opts


def version_line() -> str:
    return f"{APP_NAME} {VERSION}"
