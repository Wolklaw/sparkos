"""The command line. --version and --self-test never load Tk; a second launch hands over to the
open window before Tk is even imported."""

import argparse
import os
import shutil
import sys
from typing import List, Optional

from . import APP_NAME, APP_SLUG, VERSION

TOOLS = ('pw-dump', 'wpctl', 'pactl', 'pw-record', 'pw-play', 'pw-cli', 'amixer')


def self_test(fake_dir: Optional[str]) -> int:
    """Read PipeWire once and say what was found. No display needed. Missing PipeWire is a
    note, not a failure, so this also runs in a build container; a missing tkinter fails."""
    from . import eq, model
    from .backend import FakeBackend
    from .core import run
    from .scarlett import default_runner, fake_runner, find_interfaces
    failures: List[str] = []
    print(f"{APP_NAME} {VERSION} self-test")
    print(f"python:    {sys.version.split()[0]}")
    try:
        import tkinter
        print(f"tkinter:   Tk {tkinter.TkVersion}")
    except ImportError as exc:
        print(f"tkinter:   MISSING ({exc})")
        failures.append("tkinter")
    for tool in TOOLS:
        path = shutil.which(tool)
        note = ""
        if tool == 'amixer' and not path:
            note = " (the Scarlett page needs alsa-utils)"
        print(f"tool:      {tool}: {path or 'not found'}{note}")

    state = None
    if fake_dir:
        print(f"source:    test data in {fake_dir}")
        state = FakeBackend(fake_dir).state()
    elif shutil.which('pw-dump'):
        r = run(['pw-dump'], timeout=10)
        if r.returncode == 0:
            graph = model.Graph()
            for updates in model.parse_dump(r.stdout):
                graph.apply(updates)
            state = graph.state()
        else:
            print(f"pipewire:  not reachable ({r.stderr.strip() or r.returncode})")
    else:
        print("pipewire:  pw-dump is not installed")
    if state is not None:
        print(f"pipewire:  {len(state.sinks)} outputs, {len(state.sources)} inputs, "
              f"{len(state.playing)} playing, {len(state.recording)} recording, "
              f"{len(state.cards)} sound cards")
        for label, nodes, default in (("output", state.sinks, state.default_sink),
                                      ("input", state.sources, state.default_source)):
            for n in nodes:
                vol = "--" if n.volume is None else f"{round(n.volume * 100)}%"
                print(f"{label}:    {n.title} [{n.detail}] {vol}{' muted' if n.mute else ''}"
                      f"{' (default)' if n.id == default else ''}")
        for c in state.cards:
            usable = [p.description for p in c.profiles if p.available]
            print(f"card:      {c.title}: {c.current or 'no mode'}; {len(usable)} usable mode(s)")
    runner = fake_runner(fake_dir) if fake_dir else default_runner
    cards = None
    if fake_dir:
        try:
            with open(os.path.join(fake_dir, 'proc-asound-cards.txt'), encoding='utf-8') as f:
                cards = f.read()
        except OSError:
            pass
    if fake_dir or shutil.which('amixer'):
        found = find_interfaces(runner, cards)
        print("scarlett:  " + (", ".join(f"card {i.card} {i.name}" for i in found) or "none found"))
    else:
        print("scarlett:  not checked (amixer missing)")
    manager = eq.EqManager(fake=True)
    print(f"eq:        {len(eq.BANDS)} bands, {len(eq.PRESETS)} presets, "
          f"{'service installed' if not fake_dir and eq.EqManager().installed() else 'not installed'}")
    del manager
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_SLUG, description=f"{APP_NAME}: the SparkOS sound "
                                     "mixer.")
    parser.add_argument('--tab', choices=('outputs', 'inputs', 'apps', 'eq', 'scarlett'),
                        help="open on this tab")
    parser.add_argument('--self-test', action='store_true',
                        help="read PipeWire once and report what was found; no display needed")
    parser.add_argument('--remove-eq', action='store_true',
                        help="stop and delete the equalizer service and its files, then exit")
    parser.add_argument('--fake', metavar='DIR',
                        help="use the test data in DIR (pw-dump.json, amixer-contents.txt) "
                             "instead of this PC's sound system (tests and screenshots)")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test(args.fake)
    if args.remove_eq:
        from . import eq
        eq.EqManager().remove_all()
        print("The equalizer service and its files are removed.")
        return 0
    if not args.fake:
        from .instance import ask_running_to_show
        if ask_running_to_show():
            return 0
    try:
        import tkinter as tk
    except ImportError as exc:
        print(f"{APP_NAME} needs Python's tkinter: {exc}", file=sys.stderr)
        return 1
    from . import core
    from .app import App
    core.setup_logging()
    try:
        app = App(args.fake, args.tab)
    except tk.TclError as exc:
        print(f"{APP_NAME} needs a display: {exc}", file=sys.stderr)
        return 1
    app.run()
    return 0
