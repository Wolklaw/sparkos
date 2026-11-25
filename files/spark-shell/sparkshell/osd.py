"""Volume and brightness: the keys' actions and the on-screen display.

Volume goes through PipeWire's wpctl (the same server Spark Audio drives). Brightness goes
through logind's SetBrightness for a laptop panel (no root needed), or ddcutil for a monitor
when it is installed."""

import glob
import logging
import os
import re
import shutil

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from . import layer  # noqa: E402
from .strings import tr  # noqa: E402

log = logging.getLogger('spark-shell')
STEP = 5


def parse_wpctl_volume(text: str):
    """'Volume: 0.45 [MUTED]' -> (0.45, True)."""
    m = re.search(r'Volume:\s*([0-9.]+)', text or '')
    if not m:
        return None
    return float(m.group(1)), '[MUTED]' in text


def parse_ddcutil(text: str):
    """'VCP code 0x10 (Brightness): current value = 40, max value = 100' -> 0.4."""
    m = re.search(r'current value\s*=\s*(\d+),\s*max value\s*=\s*(\d+)', text or '')
    if not m or int(m.group(2)) <= 0:
        return None
    return int(m.group(1)) / int(m.group(2))


def _run(argv, callback):
    try:
        proc = Gio.Subprocess.new(argv, Gio.SubprocessFlags.STDOUT_PIPE |
                                  Gio.SubprocessFlags.STDERR_SILENCE)
    except GLib.Error:
        callback(None)
        return

    def done(p, res):
        try:
            ok, out, _ = p.communicate_utf8_finish(res)
        except GLib.Error:
            callback(None)
            return
        callback(out if ok and p.get_exit_status() == 0 else None)
    proc.communicate_utf8_async(None, None, done)


def backlight():
    """(name, brightness path, max) of the first laptop backlight, or None."""
    for path in sorted(glob.glob('/sys/class/backlight/*')):
        try:
            with open(os.path.join(path, 'max_brightness')) as f:
                maximum = int(f.read())
            if maximum > 0:
                return os.path.basename(path), os.path.join(path, 'brightness'), maximum
        except (OSError, ValueError):
            continue
    return None


class Osd(Gtk.Window):
    def __init__(self):
        super().__init__()
        self.set_decorated(False)
        self.add_css_class('spark-transparent')
        layer.setup(self, 'overlay', ('bottom',), 'spark-osd', margins={'bottom': 90})
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.add_css_class('spark-osd')
        box.set_size_request(260, -1)
        self.title = Gtk.Label(xalign=0)
        self.title.add_css_class('spark-label')
        self.bar = Gtk.ProgressBar()
        box.append(self.title)
        box.append(self.bar)
        self.box = box
        self.set_child(box)
        self._timer = 0

    def show_level(self, kind, fraction, muted=False):
        names = {'volume': tr('volume'), 'brightness': tr('brightness')}
        text = names.get(kind, kind)
        if muted:
            text += '  ' + tr('muted')
        self.title.set_text(text)
        self.bar.set_fraction(max(0.0, min(1.0, fraction)))
        if muted:
            self.box.add_css_class('muted')
        else:
            self.box.remove_css_class('muted')
        self.present()
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add(1600, self._hide)

    def _hide(self):
        self._timer = 0
        self.set_visible(False)
        return False


class Controls:
    """Runs the key actions and tells the OSD."""

    def __init__(self, osd, conn):
        self.osd = osd
        self.conn = conn

    def key(self, name):
        if name == 'osd-test':          # shows the display with no audio or backlight (tests)
            self.osd.show_level('volume', 0.6)
            return
        if name.startswith('volume') or name == 'mute':
            self._volume(name)
        elif name.startswith('brightness'):
            self._brightness(1 if name.endswith('up') else -1)

    # volume ------------------------------------------------------------------------------
    def _volume(self, name):
        sink = '@DEFAULT_AUDIO_SINK@'
        if name == 'mute':
            argv = ['wpctl', 'set-mute', sink, 'toggle']
        elif name == 'volume-up':
            argv = ['wpctl', 'set-volume', '-l', '1.0', sink, '%d%%+' % STEP]
        else:
            argv = ['wpctl', 'set-volume', sink, '%d%%-' % STEP]
        _run(argv, lambda _out: _run(['wpctl', 'get-volume', sink], self._volume_shown))

    def _volume_shown(self, out):
        parsed = parse_wpctl_volume(out)
        if parsed:
            self.osd.show_level('volume', parsed[0], parsed[1])

    # brightness --------------------------------------------------------------------------
    def _brightness(self, direction):
        light = backlight()
        if light is not None:
            name, path, maximum = light
            try:
                with open(path) as f:
                    now = int(f.read())
            except (OSError, ValueError):
                return
            value = max(1, min(maximum, now + direction * max(1, maximum * STEP // 100)))
            self.conn.call(
                'org.freedesktop.login1', '/org/freedesktop/login1/session/auto',
                'org.freedesktop.login1.Session', 'SetBrightness',
                GLib.Variant('(ssu)', ('backlight', name, value)), None,
                Gio.DBusCallFlags.NONE, 2000, None, None)
            self.osd.show_level('brightness', value / maximum)
            return
        if shutil.which('ddcutil'):
            sign = '+' if direction > 0 else '-'
            _run(['ddcutil', 'setvcp', '10', sign, str(STEP)], lambda _o: _run(
                ['ddcutil', 'getvcp', '10'],
                self._ddc_shown))
        else:
            log.info('no backlight and no ddcutil: brightness keys do nothing')

    def _ddc_shown(self, out):
        fraction = parse_ddcutil(out)
        if fraction is not None:
            self.osd.show_level('brightness', fraction)
