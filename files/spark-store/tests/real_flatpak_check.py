#!/usr/bin/env python3
"""Install, update and remove one real Flathub app through Spark Store, with the real flatpak,
for the user running this, and check every step. CI runs it; it changes this user's Flatpak
apps, so on a PC run it only in a test account.

    python3 tests/real_flatpak_check.py [--ui] APP_ID [APP_ID...]

The first app ID found in the Flathub catalog on this PC is used. Without --ui it drives the
install queue directly; with --ui it opens the Store's window (a display is needed: xvfb-run)
and goes through the app's page, the queue bar and the Installed page, like a person would.
The app must not be installed yet; the user's Flathub remote is added if it's missing.
"""

import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from sparkstore import flatpak, permissions  # noqa: E402
from sparkstore.catalog import Catalog  # noqa: E402
from sparkstore.jobs import DONE, Job, JobQueue  # noqa: E402

FAILURES = []


def check(ok: bool, what: str) -> None:
    print(("ok:      " if ok else "FAILED:  ") + what, flush=True)
    if not ok:
        FAILURES.append(what)


def pick(ids):
    cat = Catalog().load()
    check(bool(cat.apps), f"catalog has {len(cat.apps)} apps")
    for app_id in ids:
        if app_id in cat.apps:
            return cat, cat.apps[app_id]
    print("none of these apps is in the catalog: " + ", ".join(ids))
    sys.exit(1)


def watch(q: JobQueue, job: Job, limit: float = 900):
    """Run a job to the end; report the progress flatpak showed."""
    seen, steps = [], set()
    end = time.monotonic() + limit
    while not job.finished and time.monotonic() < end:
        q.drain()
        if job.progress is not None and (not seen or seen[-1] != job.progress):
            seen.append(job.progress)
        if job.step_text:
            steps.add(job.step_text)
        time.sleep(0.05)
    took = job.ended - job.started if job.ended else 0
    print(f"         {job.kind} {job.app_id}: {job.state} in {took:.0f} s; progress seen: "
          f"{[round(p * 100) for p in seen[:12]]}{' ...' if len(seen) > 12 else ''}; "
          f"steps: {sorted(steps)}; last line: {job.line!r}")
    if job.error:
        print("         error: " + job.error.replace('\n', '\n                '))
    return seen


def queue_check(cat, app) -> None:
    info = flatpak.remote_info(app.id, app.branch)
    check(info.error == '', f"remote-info {app.id}: {info.error or 'read'}")
    check(bool(info.download and info.installed),
          f"sizes: {info.download} B download, {info.installed} B installed")
    lines = permissions.describe(info.metadata)
    check(bool(info.metadata), f"permissions from the index: {len(lines)} line(s)")
    for group, level, text in lines:
        print(f"         {group:8} {level:5} {text}")

    q = JobQueue()
    job = q.add(Job('install', app.id, app.name, steps=[flatpak.cmd_install(app.id, app.branch)],
                    needs_flathub=True))
    seen = watch(q, job)
    check(job.state == DONE, f"install {app.id}")
    check(len(seen) >= 2, "install showed progress as it went")
    installed = flatpak.installed()
    check(app.id in installed and installed[app.id].scope == 'user',
          "installed for this user only")
    if app.id in installed:
        check(bool(installed[app.id].size), f"size on disk: {installed[app.id].size} B")
    check(bool(flatpak.installed_metadata(app.id, 'user')), "permissions of the installed app")

    job = q.add(Job('update', app.id, app.name, steps=[flatpak.cmd_update(app.id, 'user')]))
    watch(q, job)
    check(job.state == DONE, f"update {app.id} (nothing new is fine)")

    job = q.add(Job('install', 'org.example.DoesNotExist', 'Nothing',
                    steps=[flatpak.cmd_install('org.example.DoesNotExist')]))
    watch(q, job, limit=120)
    check(job.state == 'failed' and bool(job.error), "a failing install keeps flatpak's error")

    job = q.add(Job('remove', app.id, app.name,
                    steps=[flatpak.cmd_remove(app.id, 'user', delete_data=True)]))
    watch(q, job)
    check(job.state == DONE, f"remove {app.id}")
    check(app.id not in flatpak.installed(), "gone from the installed list")


def ui_check(cat, app) -> None:
    os.environ['SPARK_STORE_REDUCED_MOTION'] = '1'
    from sparkstore.app import Store
    store = Store(offline=True)

    def pump(until, limit=900.0):
        end = time.monotonic() + limit
        while time.monotonic() < end:
            store.root.update()
            if until():
                return True
            time.sleep(0.02)
        return False

    check(pump(lambda: not store.catalog_busy and store.installed_loaded, 60),
          "window open, catalog and installed list loaded")
    check(app.id not in store.installed, f"{app.id} isn't installed yet")
    store.search.set(app.name)
    check(pump(lambda: store.page == 'search', 10), f"searching for {app.name!r}")
    found = [a.id for a in store.pages['search'].results]
    check(app.id in found[:5], f"{app.id} in the top 5 results ({found[:5]})")
    store.open_app(app)
    page = store.pages['app']
    check(pump(lambda: app.id in page.facts, 120), "size and permissions on the app page")
    facts = page.facts.get(app.id)
    check(bool(facts and facts.installed), "size shown")
    store.install(page.subject)
    seen = []

    def progressing():
        job = store.queue.for_app(app.id)
        if job and job.progress is not None and (not seen or seen[-1] != job.progress):
            seen.append(job.progress)
        return app.id in store.installed

    check(pump(progressing), "installed through the app page")
    check(len(seen) >= 2, f"progress shown while installing ({[round(p * 100) for p in seen][:10]})")
    check(pump(lambda: not store.qbar_shown, 30), "queue bar gone when done")
    check(store.installed[app.id].scope == 'user' if app.id in store.installed else False,
          "installed for this user")
    store.go('installed')
    texts = _texts(store.pages['installed'].inner)
    check(store.installed[app.id].name in texts, "listed on the Installed page")
    store.open_app(app)
    store.remove(page.subject, 'user', delete_data=True)
    check(pump(lambda: app.id not in store.installed), "removed through the app page")
    check(pump(lambda: 'INSTALL' in _texts(page.actions), 30), "the page offers Install again")
    store.close()


def _texts(widget):
    out = []
    try:
        out.append(str(widget.cget('text')))
    except Exception:     # noqa: BLE001 - not every widget has text
        pass
    for child in widget.winfo_children():
        out.extend(_texts(child))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--ui', action='store_true')
    parser.add_argument('apps', nargs='+')
    args = parser.parse_args()
    print(f"flatpak: {flatpak.version()}; remotes: {flatpak.remotes()}")
    cat, app = pick(args.apps)
    det = cat.details(app.id)
    print(f"app:     {app.id} ({app.name}, runtime {det.runtime})")
    if app.id in flatpak.installed():
        print(f"{app.id} is already installed; pick another")
        return 1
    (ui_check if args.ui else queue_check)(cat, app)
    if FAILURES:
        print("FAILED: " + "; ".join(FAILURES))
        return 1
    print("real flatpak check passed")
    return 0


if __name__ == '__main__':
    sys.exit(main())
