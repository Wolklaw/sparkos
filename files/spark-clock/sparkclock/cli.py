"""The command line. --version and --self-test never open a window and never touch your alarms
(the self-test works in a temporary folder it makes and removes)."""

import argparse
import os
import sys
import tempfile
import time
from typing import List, Optional

from . import APP_NAME, APP_SLUG, VERSION


def self_test() -> int:
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
    try:
        from gi.repository import Gio, GLib  # noqa: F401
        print("gobject:   ok (the service rings through it)")
    except (ImportError, ValueError) as exc:
        print(f"gobject:   MISSING ({exc}); alarms can't ring without python3-gobject")
        failures.append("gobject")
    from . import sound, text
    missing = [k for k in text.EN if k not in text.FR]
    print(f"text:      {len(text.EN)} strings, French "
          f"{'complete' if not missing else 'missing ' + ', '.join(missing)}")
    if missing:
        failures.append("text")
    gone = [name for name in sound.BUILT_IN if sound.sound_path(name) is None]
    print(f"sounds:    {len(sound.BUILT_IN) - len(gone)} of {len(sound.BUILT_IN)} found"
          + (f" (missing {', '.join(gone)})" if gone else ""))
    if gone:
        failures.append("sounds")
    player = sound.find_player()
    print(f"player:    {player or 'NONE (pw-play, paplay, gst-play-1.0 or ffplay)'}")
    if player is None:
        failures.append("player")

    # the schedule and the engine, in a temporary home, with a fake clock and fake outputs
    saved = {k: os.environ.get(k) for k in ('XDG_CONFIG_HOME', 'XDG_STATE_HOME')}
    with tempfile.TemporaryDirectory(prefix='spark-clock-selftest-') as tmp:
        os.environ['XDG_CONFIG_HOME'] = os.path.join(tmp, 'config')
        os.environ['XDG_STATE_HOME'] = os.path.join(tmp, 'state')
        try:
            ok, detail = _engine_check()
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    print(f"engine:    {detail}{'' if ok else '  (WRONG)'}")
    if not ok:
        failures.append("engine")
    from . import cities
    zone = cities.time_in(cities.HOME_ZONE, time.time())
    print(f"zones:     Montréal {zone.strftime('%H:%M') if zone else 'MISSING (no tz database)'}")
    if zone is None:
        failures.append("zones")
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def _engine_check():
    """An alarm and a timer, due one second after a fake 'now': both ring, Stop answers them."""
    import datetime as dt
    from . import engine, store

    class Notes:
        def __init__(self):
            self.rung, self.infos, self.closed = [], [], []

        def ring(self, ring, replaces=0):
            self.rung.append(ring.key)
            return len(self.rung)

        def info(self, summary, body, replaces=0):
            self.infos.append(summary)
            return 99

        def close(self, notification):
            self.closed.append(notification)

    class Quiet:
        def __init__(self):
            self.log = []

        def start(self, name, volume=80):
            self.log.append(('start', name))
            return True

        def tick(self):
            pass

        def stop(self):
            self.log.append(('stop',))

    now = dt.datetime.now().replace(second=0, microsecond=0) + dt.timedelta(minutes=3)
    alarm_at = now.timestamp()
    store.update_config(lambda c: c['alarms'].append(
        {'time': now.strftime('%H:%M'), 'days': [], 'label': 'self-test', 'enabled': True}))
    start = alarm_at - 120
    store.add_timer(60, 'self-test', now=start)
    notes, loop = Notes(), Quiet()
    eng = engine.Engine(notes, loop, clock=lambda: start)
    eng.tick(start)
    if notes.rung:
        return False, "rang before it was time"
    eng.tick(alarm_at + 1)
    keys = sorted(notes.rung)
    if len(keys) != 2 or not keys[0].startswith('alarm:') or not keys[1].startswith('timer:'):
        return False, f"expected an alarm and a timer to ring, got {keys}"
    for key in list(eng.rings):
        eng.action(key, 'stop', alarm_at + 2)
    if eng.rings or loop.log[-1] != ('stop',):
        return False, "Stop didn't end the rings"
    still_on = [a for a in store.load_config()['alarms'] if a['enabled']]
    if still_on:
        return False, "a one-time alarm stayed on"
    return True, "an alarm and a timer rang on time, Stop ended them, the one-time alarm turned off"


def parse_args(argv):
    parser = argparse.ArgumentParser(prog=APP_SLUG, description=f"{APP_NAME}: alarms, timers, "
                                     "a stopwatch and world clocks.")
    parser.add_argument('--tab', choices=('alarms', 'timers', 'stopwatch', 'world'),
                        default='alarms', help="open on this tab")
    parser.add_argument('--daemon', action='store_true',
                        help="run the background service that rings alarms and timers "
                             "(systemd starts it at login)")
    parser.add_argument('--timer', metavar='DURATION',
                        help="start a timer now: 90, 5m, 1h30m or 1:30")
    parser.add_argument('--label', default='', help="a name for the timer")
    parser.add_argument('--self-test', action='store_true',
                        help="check the install; needs no display and touches nothing of yours")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        return self_test()
    if args.daemon:
        from . import daemon
        return daemon.run()
    if args.timer is not None:
        from . import core, store
        from .text import t
        seconds = core.parse_duration(args.timer)
        if seconds <= 0:
            print(t('cli.timer_bad', text=args.timer), file=sys.stderr)
            return 2
        store.add_timer(seconds, args.label)
        print(t('cli.timer_added', duration=core.duration_words(seconds)))
        return 0
    try:
        import tkinter as tk
    except ImportError as exc:
        print(f"{APP_NAME} needs Python's tkinter: {exc}", file=sys.stderr)
        return 1
    from . import core
    core.setup_logging()
    from .app import App
    try:
        app = App(tab=args.tab)
    except tk.TclError as exc:
        print(f"{APP_NAME} needs a display: {exc}", file=sys.stderr)
        return 1
    app.run()
    return 0
