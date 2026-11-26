"""The clipboard watcher.

`spark-notes --watch` runs `wl-paste --watch spark-notes --capture`. wl-paste (from the
wl-clipboard package) talks to the compositor through the Wayland data-control protocol, which
the Spark compositor implements, and starts `--capture` once for every change of the clipboard. Between copies
nothing runs, so it costs no CPU.

`--capture` reads what was copied and adds it to the history, with these rules:

- paused ("don't keep"): read nothing, keep nothing
- the program marked it as a password (x-kde-passwordManagerHint): keep nothing
- text: kept (up to 1 MB); an image (png, jpeg, bmp): kept if images are on (up to 8 MB)
- the clipboard became empty (the program that copied it closed; Wayland drops the copy with
  it): the newest item in the history is put back, as other clipboard managers do. Off with keep_alive=false.

No GTK in this file, so a capture starts fast.
"""

import os
import shutil
import subprocess
import sys
from typing import List, Optional

from . import core
from .core import log

TEXT_TYPES = ('text/plain;charset=utf-8', 'text/plain', 'UTF8_STRING', 'STRING', 'TEXT')
TIMEOUT = 5


def have_wl_clipboard() -> bool:
    return bool(shutil.which('wl-paste') and shutil.which('wl-copy'))


def _paste(args: List[str]) -> Optional[bytes]:
    try:
        r = subprocess.run(['wl-paste', '--no-newline'] + args, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def offered_types() -> List[str]:
    """What the program that copied offers; empty when the clipboard is empty."""
    try:
        r = subprocess.run(['wl-paste', '--list-types'], stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if r.returncode != 0:
        return []
    return [ln.strip() for ln in r.stdout.decode('utf-8', 'replace').splitlines() if ln.strip()]


def capture(history: Optional[core.History] = None,
            settings: Optional[dict] = None) -> str:
    """Handle one clipboard change. Returns what happened: 'paused', 'empty', 'restored',
    'password', 'text', 'image', 'skipped' or 'error'."""
    settings = settings if settings is not None else core.load_settings()
    if settings.get('paused'):
        return 'paused'
    history = history or core.History()
    types = offered_types()
    if not types:
        if settings.get('keep_alive') and restore_newest(history):
            return 'restored'
        return 'empty'
    if core.PASSWORD_HINT in types:
        return 'password'
    limit = settings.get('max_items', core.DEFAULTS['max_items'])
    text_type = next((t for t in TEXT_TYPES if t in types), None)
    if text_type:
        data = _paste(['--type', text_type])
        if data is None:
            return 'error'
        item = history.add_text(data.decode('utf-8', 'replace'), limit)
        return 'text' if item else 'skipped'
    image_type = next((t for t in core.IMAGE_TYPES if t in types), None)
    if image_type and settings.get('images', True):
        data = _paste(['--type', image_type])
        if data is None:
            return 'error'
        item = history.add_image(data, image_type, limit)
        return 'image' if item else 'skipped'
    return 'skipped'


def copy_item(item: core.Item, history: Optional[core.History] = None) -> bool:
    """Put an item on the clipboard. wl-copy keeps serving it after this program exits."""
    history = history or core.History()
    try:
        if item.kind == 'image':
            data, mime = history.image_bytes(item), item.mime
        else:
            data, mime = item.text.encode('utf-8'), 'text/plain;charset=utf-8'
        r = subprocess.run(['wl-copy', '--type', mime], input=data, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=TIMEOUT)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("couldn't copy: %s", exc)
        return False


def restore_newest(history: core.History) -> bool:
    item = history.newest()
    return bool(item) and copy_item(item, history)


def watch_command() -> List[str]:
    """What the background service runs."""
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'spark_notes.py')
    return ['wl-paste', '--watch', sys.executable, script, '--capture']


def watch() -> int:
    """Replace this process with wl-paste --watch. It returns only if that can't start."""
    exe = shutil.which('wl-paste')
    if not exe:
        print("Spark Notes needs wl-paste (the wl-clipboard package) to watch the clipboard.\n"
              "On Fedora: sudo dnf install wl-clipboard", file=sys.stderr)
        return 1
    if not os.environ.get('WAYLAND_DISPLAY'):
        print("Spark Notes watches the clipboard on Wayland; WAYLAND_DISPLAY is not set.",
              file=sys.stderr)
        return 1
    cmd = watch_command()
    os.execv(exe, cmd)
    return 1


def _drain_stdin() -> None:
    """wl-paste --watch pipes the new clipboard into this process. Read it to the end first:
    left unread, anything over the pipe buffer (64 KB, so every screenshot) blocks the program
    that copied it, and every paste waits until this capture gives up (Qt apps get 0 bytes)."""
    def drain():
        try:
            while os.read(0, 1 << 20):
                pass
        except OSError:
            pass
    try:
        if os.isatty(0):
            return
    except OSError:
        return
    # in the background: a stdin that never ends (a test run) must not hold the capture up
    import threading
    threading.Thread(target=drain, daemon=True).start()


def capture_main() -> int:
    core.setup_logging()
    _drain_stdin()
    try:
        what = capture()
    except Exception as exc:    # never let one bad copy stop the watcher
        log.exception("capture failed: %s", exc)
        return 0
    log.info("clipboard changed: %s", what)
    return 0
