"""The command line. Only the window loads Tk; the timers' runs, --status and --self-test
don't need a display."""

import argparse
import os
import sys
import time
from typing import List, Optional, Tuple

from . import APP_NAME, APP_SLUG, CONF_PATH, HELPER, IMAGE, IMAGES, POLKIT_ACTION, RELEASE_PATH, VERSION
from .core import Env, log, run, setup_logging, which
from .engine import NONE, SPARK, UUPD, both_on, engine, timer_enabled

SYSTEM_UNITS = '/usr/lib/systemd/system'
USER_UNITS = '/usr/lib/systemd/user'
# Bazzite's and Fedora's automatic updaters. Exactly one updater may be on: uupd (Bazzite's,
# the default for now) or Spark Update's own timer; the rest must stay off.
OTHER_TIMERS = ('uupd.timer', 'rpm-ostreed-automatic.timer', 'bootc-fetch-apply-updates.timer')


def user_timer_enabled(env: Env) -> Optional[str]:
    """Where spark-update-user.timer is enabled: for every user, or just this one."""
    if timer_enabled(env, 'spark-update-user.timer', user=True):
        return "every user"
    home = os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')
    if os.path.lexists(os.path.join(home, 'systemd', 'user', 'timers.target.wants',
                                    'spark-update-user.timer')):
        return "this user"
    return None


def other_updaters(env: Env) -> List[str]:
    """Automatic updaters that are on besides the one in charge (see engine.py)."""
    mine = 'uupd.timer' if engine(env) == UUPD else ''
    found = [name for name in OTHER_TIMERS if name != mine and timer_enabled(env, name)]
    conf = env.read('/etc/rpm-ostreed.conf') or ''
    for line in conf.splitlines():
        line = line.split('#', 1)[0].strip()
        if line.replace(' ', '').lower().startswith('automaticupdatepolicy='):
            policy = line.split('=', 1)[1].strip().lower()
            if policy not in ('none', 'off', ''):
                found.append(f"rpm-ostreed AutomaticUpdatePolicy={policy}")
    return found


def is_sparkos(env: Env) -> bool:
    text = env.read('/usr/lib/os-release') or env.read('/etc/os-release') or ''
    return any(line.strip() in ('NAME="SparkOS"', 'NAME=SparkOS') for line in text.splitlines())


def self_test(env: Env) -> int:
    from . import release, status
    from .settings import load_system
    failures: List[str] = []
    try:
        sys.stdout.reconfigure(errors='replace')
    except (AttributeError, ValueError):
        pass
    print(f"{APP_NAME} {VERSION} self-test")
    print(f"python:    {sys.version.split()[0]}")
    try:
        import tkinter
        print(f"tkinter:   Tk {tkinter.TkVersion}")
    except ImportError as exc:
        print(f"tkinter:   MISSING ({exc})")
        failures.append("tkinter")
    tools = ('rpm-ostree', 'bootc', 'flatpak', 'notify-send', 'pkexec', 'gdbus', 'systemctl')
    print("commands:  " + ', '.join(f"{c} {'yes' if which(c) else 'no'}" for c in tools))

    host = status.read_host(env, prefer_bootc=hasattr(os, 'geteuid') and os.geteuid() == 0)
    if host.booted is not None:
        b = host.booted
        print(f"status:    {host.source}: booted {b.version or '?'} ({b.image or 'no image'})"
              + (f", staged {host.staged.version}" if host.staged else '')
              + (f", previous {host.rollback.version}" if host.rollback else ''))
    else:
        print(f"status:    not booted from an image here (a container or a build): "
              f"{host.error}")
    name, where = status.find_image_name(env, host)
    sparkos = is_sparkos(env)
    if name:
        print(f"image:     {name} (from {where})")
        if sparkos and name not in IMAGES:
            print(f"image:     expected {' or '.join(IMAGES)} - tell the owner")
            failures.append("image name")
    elif sparkos:
        print("image:     NOT FOUND on SparkOS (no status, release file or signing policy)")
        failures.append("image name")
    else:
        print("image:     none (not SparkOS)")

    data = release.load(env.path('/'), use_rpm=False)
    if data:
        parts = [f"{c['name']} {c['version']}" for c in data.get('components') or []]
        origin = RELEASE_PATH if data.get('from_file') else "read from files (no release.json)"
        print(f"release:   {data.get('name') or '?'} {data.get('version') or '?'}: "
              f"{', '.join(parts) or 'no SparkOS apps found'} ({origin})")

    conf, warnings = load_system(env)
    has_conf = env.read(CONF_PATH) is not None
    print(f"settings:  automatic {'yes' if conf.automatic else 'no'}, mode {conf.mode}, "
          f"every {conf.every_hours} h, flatpak {'yes' if conf.flatpak else 'no'} "
          f"({CONF_PATH if has_conf else 'defaults; no ' + CONF_PATH})")
    for w in warnings:
        print(f"settings:  update.conf {w}")

    # Updates must never stop: exactly one updater on, and on SparkOS at least one
    eng = engine(env)
    if both_on(env):
        print("updater:   TWO UPDATERS ON: spark-update.timer and uupd.timer - tell the owner")
        failures.append("two updaters")
    elif eng == SPARK:
        print("updater:   Spark Update (spark-update.timer enabled; uupd off)")
    elif eng == UUPD:
        print("updater:   Universal Blue's uupd (uupd.timer enabled, daily at 04:00); Spark "
              "Update adds the notification, the window and roll back")
    else:
        print("updater:   NONE: no automatic updater is enabled" +
              (" - tell the owner" if is_sparkos(env) else " (not SparkOS)"))
        if is_sparkos(env):
            failures.append("no updater")

    system_install = os.path.isfile(env.path(f'{SYSTEM_UNITS}/spark-update.timer'))
    where = user_timer_enabled(env)
    print("timers:    spark-update-user.timer (notification) " +
          (f"enabled for {where}" if where else "NOT ENABLED"))
    if system_install:
        if not where:
            failures.append("notification timer")
        helper_ok = os.path.isfile(env.path(HELPER)) and os.path.isfile(
            env.path(f'/usr/share/polkit-1/actions/{POLKIT_ACTION.rsplit(".", 1)[0]}.policy'))
        print(f"helper:    {HELPER if helper_ok else 'MISSING'} (polkit action {POLKIT_ACTION})")
        if not helper_ok:
            failures.append("helper")
    else:
        print("timers:    a per-user install (the system parts come with the SparkOS image)")
    others = other_updaters(env)
    if others:
        print(f"others:    other updaters still on: {', '.join(others)} - tell the owner")
        if system_install:
            failures.append("other updaters")
    else:
        print("others:    no other automatic updater is on")
    uupd_dropin = env.path(f'{SYSTEM_UNITS}/uupd.service.d/50-sparkos.conf')
    if os.path.isfile(uupd_dropin):
        print("others:    uupd.service and `ujust update` run Spark Update instead")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def print_status(env: Env) -> int:
    from . import status
    from .updater import load_state
    host = status.read_host(env)
    if host.booted is None:
        print(f"Can't read the system status: {host.error}")
        return 1
    b = host.booted
    print(f"Running:  SparkOS {b.version} ({b.image or 'no image'})")
    if host.rollback_queued and host.next_boot:
        print(f"Next:     SparkOS {host.next_boot.version} (rolled back)")
    elif host.update_ready:
        print(f"Next:     SparkOS {host.staged.version} (staged; starts at the next restart)")
    if host.rollback and not host.rollback_queued:
        print(f"Previous: SparkOS {host.rollback.version}" +
              (" (pinned)" if host.rollback.pinned else ''))
    state = load_state(env)
    if state.get('last_check'):
        print(f"Checked:  {time.strftime('%Y-%m-%d %H:%M', time.localtime(state['last_check']))}"
              f", {state.get('result', '?')}" +
              (f": {state['error']}" if state.get('result') == 'failed' else ''))
    held = state.get('held')
    if isinstance(held, dict) and held.get('digests'):
        print(f"Held:     SparkOS {held.get('version', '?')} (you rolled back from it; the "
              "next newer version is staged as usual)")
    return 0


def helper_cmd(*args: str) -> List[str]:
    return ['pkexec', HELPER, *args]


def cli_rollback(env: Env) -> int:
    """For a terminal (and the rollback-helper shim): the same as the window's Roll back."""
    if os.path.isfile(HELPER):
        cmd = helper_cmd('rollback')
    else:
        cmd = ['rpm-ostree', 'rollback']
    code, out, err = run(cmd, timeout=900)
    print((out + err).strip())
    if code == 0:
        print("Done. Restart to start the previous version. Nothing was deleted; run this "
              "again to undo it.")
    return code


def write_release(path: str) -> int:
    import json
    from . import release
    # The build passes the image's own name (Containerfile ARGs IMAGE_REGISTRY and IMAGE_NAME)
    registry, name = os.environ.get('IMAGE_REGISTRY', ''), os.environ.get('IMAGE_NAME', '')
    image = f"{registry.lower()}/{name}" if registry and name else IMAGE
    if image not in IMAGES:
        print(f"unknown image {image}; expected {' or '.join(IMAGES)}")
        return 1
    data = release.collect('/', use_rpm=True, built=time.time(), image=image)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    print(json.dumps(data, indent=2))
    return 0


def notify_test() -> int:
    """Show the real notification with a made-up version, to see it on a desktop."""
    from .notify import answer, show
    from .updater import Offer
    setup_logging()
    choice = show(Offer('ready', 'test', 'TEST'), True)
    print(f"answer: {choice or 'closed'}")
    if choice == 'open':
        answer(choice)
    elif choice == 'restart':
        print("(a test: not restarting)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_SLUG, description=f"{APP_NAME}: SparkOS's "
                                     "updater.")
    parser.add_argument('--view', choices=('main', 'settings', 'log'), help="open on this view")
    parser.add_argument('--status', action='store_true', help="print the versions and exit")
    parser.add_argument('--rollback', action='store_true',
                        help="make the previous version start at the next restart (asks for "
                             "a password)")
    parser.add_argument('--system-run', action='store_true',
                        help="the background check (root; spark-update.timer runs it)")
    parser.add_argument('--now', choices=('check', 'stage'),
                        help="with --system-run: run now whatever the settings (Check now)")
    parser.add_argument('--user-run', action='store_true',
                        help="your Flatpak apps and the notification (spark-update-user.timer)")
    parser.add_argument('--notify-test', action='store_true',
                        help="show the notification with a made-up version")
    parser.add_argument('--write-release', metavar='PATH',
                        help="write what's in this image to PATH (the image build)")
    parser.add_argument('--self-test', action='store_true',
                        help="check what Spark Update needs; no display needed")
    parser.add_argument('--root', help="read a fake system under this folder (tests)")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)
    env = Env(args.root)
    if args.self_test:
        return self_test(env)
    if args.status:
        return print_status(env)
    if args.write_release:
        return write_release(args.write_release)
    if args.notify_test:
        return notify_test()
    if args.system_run:
        from .updater import system_run
        setup_logging(system=True, env=env)
        try:
            return system_run(env, now_mode=args.now)
        except Exception:                       # noqa: BLE001 - logged, and the timer tries again
            log.exception("the check failed")
            return 1
    if args.user_run:
        from .notify import answer
        from .updater import user_run
        setup_logging()
        try:
            return user_run(env, on_answer=answer)
        except Exception:                       # noqa: BLE001
            log.exception("the user run failed")
            return 1
    if args.rollback:
        setup_logging()
        return cli_rollback(env)
    try:
        import tkinter as tk
    except ImportError as exc:
        print(f"{APP_NAME} needs Python's tkinter: {exc}", file=sys.stderr)
        return 1
    from .app import App
    setup_logging()
    try:
        app = App(env, view=args.view)
    except tk.TclError as exc:
        print(f"{APP_NAME} needs a display: {exc}", file=sys.stderr)
        return 1
    app.run()
    return 0
