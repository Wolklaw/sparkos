#!/usr/bin/env python3
"""Install and remove one optional Spark app through Spark Store, from the source folder the
SparkOS image ships (/usr/share/spark-store/sources/<slug>), for the user running this, and
check every step. CI runs it as a normal user; on a PC run it only in a test account.

    python3 tests/spark_source_check.py [--store DIR] [--sources DIR] SLUG

--store is the Store to use (default: this folder's; CI passes the installed one,
/usr/lib/spark-store or ~/.local/lib/spark-store, so its spark-apps/ list is the real one).
It uses the Store's own code: it finds the app the way the Store does, installs it through the
queue with the command the Install button runs (install.sh --user) and removes it with the one
Remove runs. It checks the source folder is not changed (nothing written into it), that the
app runs (--self-test) and that nothing of it is left in ~/.local afterwards. The app must not
be installed for this user yet.
"""

import argparse
import glob
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

FAILURES = []


def check(ok: bool, what: str) -> None:
    print(("ok:      " if ok else "FAILED:  ") + what, flush=True)
    if not ok:
        FAILURES.append(what)


def snapshot(folder: str) -> dict:
    """Every file and folder under it, with size and modification time."""
    out = {}
    for root, dirs, files in os.walk(folder):
        for name in dirs + files:
            path = os.path.join(root, name)
            st = os.lstat(path)
            out[os.path.relpath(path, folder)] = (st.st_size, st.st_mtime_ns, st.st_mode)
    return out


def run(q, job, limit: float = 300):
    q.add(job)
    end = time.monotonic() + limit
    while not job.finished and time.monotonic() < end:
        q.drain()
        time.sleep(0.05)
    print(f"         {job.kind} {job.app_id}: {job.state}; last line: {job.line!r}")
    if job.error:
        print("         error: " + job.error)
    return job


def leftovers(home: str, app) -> list:
    found = []
    for pattern in (f'*{app.slug}*', f'*{app.id}*'):
        found += glob.glob(os.path.join(home, '.local', '**', pattern), recursive=True)
    # the app's own log may stay by design (its README says so), and a Store installed for
    # this user lists every Spark app in its own spark-apps/ folder
    keep = (os.path.join(home, '.local', 'state', app.slug),
            os.path.join(home, '.local', 'lib', 'spark-store', 'spark-apps') + os.sep)
    return sorted({p for p in found if not p.startswith(keep)})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--store', default=os.path.dirname(HERE),
                    help="the Spark Store folder whose code is used")
    ap.add_argument('--sources', default='/usr/share/spark-store/sources',
                    help="the folder that holds <slug>/install.sh")
    ap.add_argument('slug')
    args = ap.parse_args()
    sys.path.insert(0, os.path.abspath(args.store))
    from sparkstore import sparkapps
    from sparkstore.jobs import DONE, Job, JobQueue
    print(f"         Store code: {sparkapps.__file__}")
    if os.geteuid() == 0:
        print("run this as a normal user: install.sh --user refuses root")
        return 2
    home = os.path.expanduser('~')
    os.environ.setdefault('SPARK_STORE_SOURCES', args.sources)

    folder = os.path.join(args.sources, args.slug)
    check(os.path.isfile(os.path.join(folder, 'install.sh')), f"{folder}/install.sh is there")
    check(not os.access(folder, os.W_OK), f"{folder} is read-only for {os.environ.get('USER')}")
    before = snapshot(folder)

    apps = {a.slug: a for a in sparkapps.discover()}
    app = apps.get(args.slug)
    check(app is not None, f"the Store lists {args.slug}")
    if app is None:
        return 1
    check(app.installed is None, f"{app.name} isn't installed yet")
    check(app.source == folder, f"the Store installs it from {app.source or '(nothing)'}")
    cmd = sparkapps.install_command(app)
    check(cmd == ['bash', os.path.join(folder, 'install.sh'), '--user'],
          f"Install runs {cmd}")
    if FAILURES:
        return 1

    q = JobQueue()
    job = run(q, Job('spark_install', app.id, app.name, steps=[cmd], flatpak=False))
    check(job.state == DONE, "installed through the queue")
    sparkapps.refresh_state(app)
    check(app.installed == 'user', f"installed for this user (state: {app.installed})")
    exe = os.path.join(home, '.local', 'bin', app.slug)
    check(os.access(exe, os.X_OK), f"{exe} is there")
    out = subprocess.run([exe, '--self-test'], capture_output=True, text=True, timeout=120)
    check(out.returncode == 0 and 'self-test passed' in out.stdout.lower(),
          f"{app.slug} --self-test passes")
    if out.returncode != 0:
        print(out.stdout + out.stderr)
    check(os.path.isfile(os.path.join(home, '.local', 'share', 'applications', app.desktop)),
          f"its menu entry {app.desktop} is in ~/.local/share/applications")

    cmd = sparkapps.uninstall_command(app)
    check(cmd == ['bash', os.path.join(folder, 'install.sh'), '--user', '--uninstall'],
          f"Remove runs {cmd}")
    if cmd:
        job = run(q, Job('spark_remove', app.id, app.name, steps=[cmd], flatpak=False))
        check(job.state == DONE, "removed through the queue")
    sparkapps.refresh_state(app)
    check(app.installed is None, "not installed any more")
    left = leftovers(home, app)
    check(not left, "nothing left in ~/.local" + (": " + ", ".join(left) if left else ""))
    check(snapshot(folder) == before, f"nothing in {folder} changed")

    print(("FAILED: " + "; ".join(FAILURES)) if FAILURES else
          f"{app.name} installed from {folder}, ran and was removed")
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
