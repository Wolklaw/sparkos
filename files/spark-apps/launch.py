#!/usr/bin/python3 -I
"""Start a Spark app from the right copy. /usr/bin/spark-<app> runs this (not as root, as you):

    launch.py <slug> [arguments the app was given]

It starts the newest verified live copy whose system_api matches the image's, or else the
built-in copy in /usr/lib/<slug>. Any problem at all means the built-in copy: the app must
always open. SPARK_APPS_LOG=1 prints which copy was chosen, and why, to stderr."""

import os
import sys

LIB = os.path.dirname(os.path.abspath(__file__))


def main(argv):
    slug = argv[1] if len(argv) > 1 else ''
    args = argv[2:]
    folder, name = '/usr/lib/' + slug, slug.replace('-', '_') + '.py'
    try:
        sys.path.insert(0, LIB)
        from sparkapps.choose import entry_name, select
        from sparkapps.paths import Paths
        choice = select(Paths('/'), slug, trusted_uid=0)
        folder, name = choice.directory, entry_name(slug)
        if os.environ.get('SPARK_APPS_LOG'):
            print(f"spark-apps: {slug}: {choice.source} {choice.version} ({choice.why})",
                  file=sys.stderr)
    except Exception:                # noqa: BLE001 - never stop the app from opening
        pass
    script = os.path.join(folder, name)
    os.execv('/usr/bin/python3', ['/usr/bin/python3', script] + args)


if __name__ == '__main__':
    main(sys.argv)
