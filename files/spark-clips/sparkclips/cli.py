"""The command line: --daemon runs the replay service, --save and --status talk to it, and
--version and --self-test never load a window or touch your files (the self-test records a few
seconds of test pattern into a temporary folder it makes and removes, so it needs no display,
no GPU and no game)."""

import argparse
import json
import os
import shutil
import signal
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional

from . import APP_NAME, APP_SLUG, VERSION

EXIT_OK, EXIT_PROBLEM, EXIT_NO_SERVICE = 0, 1, 2


def _say_status(st: Dict[str, Any]) -> None:
    from .core import duration_text, human_size
    from .text import t
    print(f"{APP_NAME} {st.get('version', VERSION)}")
    print(t('cli.state', state=t('state.' + st.get('state', 'off'))))
    if st.get('game'):
        print(t('cli.game', name=st['game'], source=st.get('source') or ''))
    if st.get('state') == 'recording':
        print(t('cli.held', held=duration_text(st.get('held', 0)),
                keep=duration_text(st.get('seconds', 0)), size=human_size(st.get('bytes', 0))))
    if st.get('problem'):
        print(t('cli.problem', text=t('problem.' + st['problem'], detail=st.get('detail') or '')))
    print(t('cli.encoder', name=st.get('encoder') or t('encoder.none_short'),
            audio=st.get('audio') or t('encoder.none_short')))


def cmd_status(as_json: bool) -> int:
    from . import ipc
    from .text import t
    st = ipc.ask('status', timeout=3.0)
    if st is None or not st.get('ok'):
        if as_json:
            print(json.dumps({'ok': False, 'state': 'service_off'}))
        else:
            print(t('cli.service_off'))
        return EXIT_NO_SERVICE
    if as_json:
        print(json.dumps(st))
    else:
        _say_status(st)
    return EXIT_OK if st.get('state') == 'recording' else EXIT_PROBLEM


def cmd_save() -> int:
    from . import ipc
    from .text import t
    reply = ipc.ask('save', timeout=120.0)
    if reply is None:
        print(t('cli.service_off'), file=sys.stderr)
        return EXIT_NO_SERVICE
    if reply.get('ok'):
        print(reply['path'])
        return EXIT_OK
    print(t('problem.' + reply.get('problem', 'save_failed'), detail=reply.get('detail') or ''),
          file=sys.stderr)
    return EXIT_PROBLEM


def cmd_toggle(command: str) -> int:
    from . import ipc
    from .text import t
    reply = ipc.ask(command, timeout=5.0)
    if reply is None:
        print(t('cli.service_off'), file=sys.stderr)
        return EXIT_NO_SERVICE
    return EXIT_OK


def cmd_daemon() -> int:
    from . import core
    core.setup_logging()
    from .daemon import Service
    notifier = None
    try:
        from .notify import Notifier
        notifier = Notifier()
    except Exception as exc:                       # noqa: BLE001 - no bus, no GObject: stay quiet
        core.log.info("no notifications: %s", exc)
    return Service(notifier).run()


# ─── The self-test ───

def _isolate(tmp: str) -> Dict[str, Optional[str]]:
    """Point every folder at the temporary one; return what to put back."""
    changes = {
        'HOME': tmp, 'XDG_CONFIG_HOME': os.path.join(tmp, 'config'),
        'XDG_STATE_HOME': os.path.join(tmp, 'state'), 'XDG_CACHE_HOME': os.path.join(tmp, 'cache'),
        'XDG_DATA_HOME': os.path.join(tmp, 'data'), 'XDG_RUNTIME_DIR': os.path.join(tmp, 'run'),
        'SPARK_CLIPS_SHM': os.path.join(tmp, 'shm'), 'SPARK_CLIPS_FAKE': '1',
    }
    saved = {key: os.environ.get(key) for key in changes}
    saved['SPARK_CLIPS_ENCODER'] = os.environ.pop('SPARK_CLIPS_ENCODER', None)
    os.environ.update(changes)
    return saved


def _restore(saved: Dict[str, Optional[str]]) -> None:
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _pipeline(failures: List[str], tmp: str) -> None:
    """The service on a test pattern: record, save five seconds, look at the file, trim it."""
    from . import clipfile, library
    from .core import DEFAULTS, human_size, save_settings
    from .daemon import Service
    settings = dict(DEFAULTS, only_in_game=False, seconds=15)
    save_settings(settings)
    service = Service(notifier=None, probe=lambda: None)
    try:
        end = time.monotonic() + 25
        while time.monotonic() < end and service.state != 'recording':
            service.tick()
            time.sleep(0.25)
        if service.state != 'recording':
            print(f"recording: NOT STARTED ({service.problem} {service.detail})")
            failures.append("recording")
            return
        time.sleep(7)
        service.tick()
        reply = service.save()
        if not reply.get('ok'):
            print(f"save:      FAILED ({reply.get('problem')} {reply.get('detail', '')})")
            failures.append("save")
            return
        info = clipfile.probe(reply['path'])
        size = os.path.getsize(reply['path'])
        ok = info['video'] and 3 <= info['duration'] <= 9
        print(f"save:      {info['duration']:.1f} s, {info['size'][0]}x{info['size'][1]} "
              f"{info['codec']}, {info['audio']} audio track(s), {human_size(size)}"
              f"{'' if ok else '  (WRONG)'}")
        if not ok:
            failures.append("save")
        trimmed = library.trimmed_name(os.path.dirname(reply['path']), 'selftest')
        clipfile.trim_clip(reply['path'], trimmed, 1.0, 3.0)
        cut = clipfile.probe(trimmed)['duration']
        ok = 1.0 <= cut <= 4.5
        print(f"trim:      {cut:.1f} s from 2.0 s asked (lossless: starts on a keyframe)"
              f"{'' if ok else '  (WRONG)'}")
        if not ok:
            failures.append("trim")
        thumb = os.path.join(tmp, 'thumb.jpg')
        got = clipfile.thumbnail(reply['path'], thumb, 160)
        print(f"thumbnail: {'ok' if got and os.path.getsize(thumb) > 0 else 'NONE'}")
        if not got:
            failures.append("thumbnail")
    finally:
        service.shutdown()


def self_test() -> int:
    from . import text
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
        import PIL
        print(f"pillow:    {PIL.__version__}")
    except ImportError as exc:
        print(f"pillow:    MISSING ({exc})")
        failures.append("pillow")
    missing = [k for k in text.EN if k not in text.FR]
    print(f"text:      {len(text.EN)} strings, French "
          f"{'complete' if not missing else 'missing ' + ', '.join(missing)}")
    if missing:
        failures.append("text")

    from . import clipfile, games, pipeline
    err = clipfile.init()
    if err:
        print(f"gstreamer: MISSING ({err})")
        print("FAILED: gstreamer")
        return 1
    print(f"gstreamer: {clipfile.Gst.version_string()}")
    gone = pipeline.missing_elements()
    print("elements:  " + ("all there" if not gone else "MISSING " + ", ".join(gone)))
    if gone:
        failures.append("elements")
    for codec in ('h264', 'hevc'):
        enc = pipeline.pick_encoder(codec)
        print(f"{codec}:".ljust(11) + (enc.label if enc else "none (fine for hevc, not for h264)"))
        if enc is None and codec == 'h264':
            failures.append("h264 encoder")
    audio = pipeline.pick_audio_encoder()
    print("audio:     " + (audio[2] if audio else "NO ENCODER"))
    if audio is None:
        failures.append("audio encoder")
    found = games.detect({})
    print(f"games:     detection runs ({'nothing running' if found is None else found.name})"
          if found is None else f"games:     WRONG, found {found.name} in nothing")
    if found is not None:
        failures.append("games")

    tmp = tempfile.mkdtemp(prefix='spark-clips-selftest-')
    saved = _isolate(tmp)
    # a SIGTERM (a CI timeout, a closed terminal) unwinds through the finally below, which
    # stops the pipeline
    for number in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(number, lambda *_: sys.exit(1))
    try:
        if not failures or all(f in ('hevc',) for f in failures):
            _pipeline(failures, tmp)
    except Exception as exc:                       # noqa: BLE001 - say what broke
        print(f"pipeline:  FAILED ({exc})")
        failures.append("pipeline")
    finally:
        _restore(saved)
        shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        print("FAILED: " + ", ".join(failures))
        return 1
    print("self-test passed")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog=APP_SLUG, description=f"{APP_NAME}: an instant replay for games. The service keeps "
        "the last seconds of play; Meta+Alt+G (or --save) turns them into a clip.")
    parser.add_argument('--daemon', action='store_true', help="run the replay service")
    parser.add_argument('--save', action='store_true', help="save a clip now")
    parser.add_argument('--status', action='store_true', help="say what the service is doing")
    parser.add_argument('--json', action='store_true', help="with --status: print JSON")
    parser.add_argument('--start', action='store_true', help="turn the replay buffer on")
    parser.add_argument('--stop', action='store_true', help="turn the replay buffer off")
    parser.add_argument('--self-test', action='store_true',
                        help="check the install with a test pattern in a temporary folder; "
                             "needs no display, GPU or game")
    parser.add_argument('--version', action='version', version=f"{APP_NAME} {VERSION}")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.daemon:
        return cmd_daemon()
    if args.save:
        return cmd_save()
    if args.status:
        return cmd_status(args.json)
    if args.start or args.stop:
        return cmd_toggle('start' if args.start else 'stop')
    try:
        import tkinter as tk
    except ImportError as exc:
        print(f"{APP_NAME} needs Python's tkinter: {exc}", file=sys.stderr)
        return 1
    from . import core
    core.setup_logging()
    from .app import App
    try:
        app = App()
    except tk.TclError as exc:
        print(f"{APP_NAME} needs a display: {exc}", file=sys.stderr)
        return 1
    app.run()
    return 0
