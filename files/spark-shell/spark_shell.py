#!/usr/bin/env python3
"""Spark Shell: the panel, tray, notifications, launcher, wallpaper and on-screen display of the
Spark session.

    spark-shell                run the shell (the session script does this)
    spark-shell --toggle       open or close the launcher of the running shell
    spark-shell --version
    spark-shell --self-test    check that the modules load; needs no display
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def self_test() -> int:
    from sparkshell import config, strings, tray  # noqa: F401
    from sparkshell import notifyd, windows  # noqa: F401
    print('spark-shell self-test ok')
    return 0


def toggle() -> int:
    import subprocess
    return subprocess.call(['gdbus', 'call', '--session', '--dest', 'dev.wolklaw.SparkShell',
                            '--object-path', '/Shell', '--method',
                            'dev.wolklaw.SparkShell.ToggleLauncher'],
                           stdout=subprocess.DEVNULL)


def preload_layer_shell():
    """gtk4-layer-shell has to be loaded before libwayland-client, which Python's GTK import
    pulls in too early: start again with the library in LD_PRELOAD (its documented way)."""
    if os.environ.get('SPARK_SHELL_PRELOADED'):
        return
    import glob
    for pattern in ('/usr/lib64/libgtk4-layer-shell.so.0', '/usr/lib/libgtk4-layer-shell.so.0',
                    '/usr/lib/*/libgtk4-layer-shell.so.0', '/usr/lib64/libgtk4-layer-shell.so',
                    '/usr/lib/libgtk4-layer-shell.so'):
        found = glob.glob(pattern)
        if found:
            env = dict(os.environ, SPARK_SHELL_PRELOADED='1')
            env['LD_PRELOAD'] = (found[0] + ' ' + env.get('LD_PRELOAD', '')).strip()
            os.execve(sys.executable, [sys.executable, os.path.abspath(__file__)] + sys.argv[1:],
                      env)
    # not installed: the shell still runs, with ordinary windows instead of a panel


def main(argv) -> int:
    if '--version' in argv:
        from sparkshell import VERSION
        print('spark-shell ' + VERSION)
        return 0
    if '--self-test' in argv:
        return self_test()
    if '--toggle' in argv:
        return toggle()
    preload_layer_shell()
    logging.basicConfig(level=logging.INFO, format='spark-shell: %(message)s')
    from sparkshell.app import Shell
    return Shell().run([])


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
