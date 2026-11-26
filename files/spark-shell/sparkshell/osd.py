"""Volume and brightness: the volume keys' actions and the on-screen display.

Volume goes through PipeWire's wpctl (the same server Spark Audio drives). Brightness keys move
every backlight in /sys/class/backlight through logind's SetBrightness, which needs no admin
rights for the signed-in seat. External monitors without a backlight device are left alone.
On a KDE machine powerdevil reports its own changes to org.kde.plasmashell /org/kde/osdService,
which the shell also answers with this display."""

import logging
import os
import re

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


BACKLIGHT_DIR = '/sys/class/backlight'


def next_brightness(current: int, maximum: int, up: bool) -> int:
    """One key press: STEP percent of the range, never fully dark, never past the maximum."""
    if maximum <= 0:
        return current
    step = max(1, round(maximum * STEP / 100))
    floor = max(1, round(maximum / 100))
    return min(maximum, current + step) if up else max(floor, current - step)


def read_backlights(root=BACKLIGHT_DIR):
    """[(device name, brightness, max_brightness)] for every backlight that can be read."""
    found = []
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return found
    for name in names:
        try:
            with open(os.path.join(root, name, 'brightness')) as f:
                cur = int(f.read().strip())
            with open(os.path.join(root, name, 'max_brightness')) as f:
                top = int(f.read().strip())
        except (OSError, ValueError):
            continue
        found.append((name, cur, top))
    return found


MPRIS_PREFIX = 'org.mpris.MediaPlayer2.'
MPRIS_PATH = '/org/mpris/MediaPlayer2'
MEDIA_METHODS = {'play-pause': 'PlayPause', 'next': 'Next', 'previous': 'Previous',
                 'stop': 'Stop'}


def choose_player(players):
    """[(bus name, PlaybackStatus)] -> the bus name a media key goes to."""
    for wanted in ('Playing', 'Paused'):
        for name, status in players:
            if status == wanted:
                return name
    return players[0][0] if players else None


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


# What powerdevil calls on org.kde.plasmashell (Plasma's osdService). Only the brightness calls
# are answered; plasma-pa's and KWin's calls never come, since the shell does volume itself.
OSD_SERVICE_XML = """
<node>
  <interface name="org.kde.osdService">
    <method name="brightnessChanged"><arg type="i" name="percent" direction="in"/></method>
    <method name="screenBrightnessChanged">
      <arg type="i" name="percent" direction="in"/>
      <arg type="(iiii)" name="screenRect" direction="in"/>
    </method>
    <method name="keyboardBrightnessChanged"><arg type="i" name="percent" direction="in"/></method>
    <method name="hide"/>
  </interface>
</node>
"""


def osd_service_call(osd, method, args):
    """One org.kde.osdService call -> the Spark display. Percent is 0-100."""
    if method in ('brightnessChanged', 'screenBrightnessChanged'):
        osd.show_level('brightness', max(0, min(100, int(args[0]))) / 100)
    elif method == 'keyboardBrightnessChanged':
        osd.show_level('keyboard', max(0, min(100, int(args[0]))) / 100)
    elif method == 'hide':
        osd.hide_now()


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
        self.last = None           # [kind, level] last shown, for the state call (tests)

    def show_level(self, kind, fraction, muted=False):
        self.last = [kind, round(fraction, 2)]
        names = {'volume': tr('volume'), 'brightness': tr('brightness'),
                 'keyboard': tr('keyboard')}
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

    def hide_now(self):
        if self._timer:
            GLib.source_remove(self._timer)
        self._hide()

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
        elif name in ('brightness-up', 'brightness-down'):
            self._brightness(name == 'brightness-up')
        elif name in MEDIA_METHODS:
            self._media(MEDIA_METHODS[name])

    # brightness: every backlight, through logind (no admin rights needed) ------------------
    def _brightness(self, up):
        lights = read_backlights()
        if not lights:
            log.info('brightness key: no backlight device')
            return
        try:
            system = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error as e:
            log.warning('brightness key: %s', e.message)
            return
        shown = None
        for name, cur, top in lights:
            value = next_brightness(cur, top, up)
            try:
                system.call_sync('org.freedesktop.login1', '/org/freedesktop/login1/session/auto',
                                 'org.freedesktop.login1.Session', 'SetBrightness',
                                 GLib.Variant('(ssu)', ('backlight', name, value)), None,
                                 Gio.DBusCallFlags.NONE, 1000, None)
            except GLib.Error as e:
                log.warning('brightness %s: %s', name, e.message)
                continue
            if shown is None:
                shown = value / top
        if shown is not None:
            self.osd.show_level('brightness', shown)

    # media keys: the MPRIS player that is playing, else the one paused, else the first ---------
    def _media(self, method):
        try:
            names = self.conn.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                                        'org.freedesktop.DBus', 'ListNames', None, None,
                                        Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]
        except GLib.Error as e:
            log.warning('media key: %s', e.message)
            return
        players = []
        for n in sorted(x for x in names if x.startswith(MPRIS_PREFIX)):
            try:
                status = self.conn.call_sync(
                    n, MPRIS_PATH, 'org.freedesktop.DBus.Properties', 'Get',
                    GLib.Variant('(ss)', (MPRIS_PREFIX.rstrip('.') + '.Player', 'PlaybackStatus')),
                    None, Gio.DBusCallFlags.NONE, 500, None).unpack()[0]
            except GLib.Error:
                status = ''
            players.append((n, status))
        target = choose_player(players)
        if not target:
            log.info('media key %s: no player', method)
            return
        self.conn.call(target, MPRIS_PATH, MPRIS_PREFIX.rstrip('.') + '.Player', method, None,
                       None, Gio.DBusCallFlags.NONE, 2000, None, None)

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
