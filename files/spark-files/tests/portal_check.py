"""End to end through the real xdg-desktop-portal: an app calls
org.freedesktop.portal.FileChooser.OpenFile and SaveFile, the portal picks Spark Files because
of spark-portals.conf (XDG_CURRENT_DESKTOP=Spark:KDE), the chooser window opens, a file is
picked, and the app gets its Response. Nothing of yours is touched: it needs its own session
bus and display, so run it inside a virtual KWin:

    XDG_RUNTIME_DIR=$(mktemp -d) dbus-run-session -- kwin_wayland --virtual --xwayland \\
        --exit-with-session "python3 files/spark-files/tests/portal_check.py"

Prints one line per check and exits 1 if any failed (0 with "skipped" without the tools)."""

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
sys.path.insert(0, APP_DIR)
PORTAL = '/usr/libexec/xdg-desktop-portal'

if not (os.path.exists(PORTAL) and os.environ.get('DISPLAY') and
        os.environ.get('DBUS_SESSION_BUS_ADDRESS')):
    print('skipped: needs xdg-desktop-portal, a display and a session bus')
    sys.exit(0)

work = tempfile.mkdtemp(prefix='spark-portal-check-')
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
    os.environ[var] = os.path.join(work, var.lower())
    os.makedirs(os.environ[var])
os.environ['SPARK_FILES_REDUCED_MOTION'] = '1'
portals = os.path.join(work, 'portals')
os.makedirs(portals)
shutil.copy(os.path.join(APP_DIR, 'portal', 'spark.portal'), portals)
conf = os.path.join(os.environ['XDG_CONFIG_HOME'], 'xdg-desktop-portal')
os.makedirs(conf)
shutil.copy(os.path.join(APP_DIR, 'portal', 'spark-portals.conf'), conf)
files = os.path.join(work, 'files')
os.makedirs(os.path.join(files, 'sub'))
for n in ('a.png', 'b.txt'):
    open(os.path.join(files, n), 'w').close()

from gi.repository import Gio, GLib  # noqa: E402

from sparkfiles.app import App  # noqa: E402

app = App()
app.quit = lambda: None
env = dict(os.environ, XDG_CURRENT_DESKTOP='Spark:KDE', XDG_DESKTOP_PORTAL_DIR=portals)
portal = subprocess.Popen([PORTAL, '--replace'], env=env, stdout=subprocess.DEVNULL,
                          stderr=open(os.path.join(work, 'portal.log'), 'w'))
failed = []


def wait_for_our_portal():
    """Ask only once the portal started above owns the name: a call before that makes the bus
    start another xdg-desktop-portal from its .service file, without our config."""
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            pid = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                                'org.freedesktop.DBus', 'GetConnectionUnixProcessID',
                                GLib.Variant('(s)', ('org.freedesktop.portal.Desktop',)),
                                None, Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]
            if pid == portal.pid:
                return True
        except GLib.Error:
            pass                                        # not owned yet
        time.sleep(0.1)
    return False


if not wait_for_our_portal():
    print('FAIL  xdg-desktop-portal did not take its bus name', flush=True)
    portal.terminate()
    sys.exit(1)


def check(ok, what):
    print(('ok    ' if ok else 'FAIL  ') + what, flush=True)
    if not ok:
        failed.append(what)


def ask(method, options, act):
    """Call the portal from a thread (as an app would); act(window) runs once the chooser
    shows; returns (response, results) from the Request's Response signal."""
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    got, done = [], threading.Event()
    ctx = GLib.MainContext.new()

    def run():
        ctx.push_thread_default()
        token = f't{len(method)}{int(time.time() * 1000) % 100000}'
        sender = bus.get_unique_name()[1:].replace('.', '_')
        handle = f'/org/freedesktop/portal/desktop/request/{sender}/{token}'

        def response(_c, _s, _p, _i, _sig, params):
            got.append(params.unpack())
            done.set()
        bus.signal_subscribe('org.freedesktop.portal.Desktop',
                             'org.freedesktop.portal.Request', 'Response', handle, None,
                             Gio.DBusSignalFlags.NO_MATCH_RULE, response)
        bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                      'AddMatch', GLib.Variant('(s)', (
                          f"type='signal',interface='org.freedesktop.portal.Request',"
                          f"path='{handle}'",)), None, Gio.DBusCallFlags.NONE, 3000, None)
        opts = dict(options, handle_token=GLib.Variant('s', token))
        try:
            bus.call_sync('org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop',
                          'org.freedesktop.portal.FileChooser', method,
                          GLib.Variant('(ssa{sv})', ('', 'Check', opts)), None,
                          Gio.DBusCallFlags.NONE, 20000, None)
        except Exception as exc:                        # noqa: BLE001
            got.append(('error', str(exc)))
            done.set()
            return
        while not done.is_set():
            ctx.iteration(True)

    threading.Thread(target=run, daemon=True).start()
    deadline = time.monotonic() + 25
    acted = False
    while not done.is_set() and time.monotonic() < deadline:
        app.root.update()
        choosers = [w for w in app.windows if getattr(w, 'picking', False)]
        if choosers and not acted:
            app.root.update()
            act(choosers[-1])
            acted = True
        time.sleep(0.05)
    return got[0] if got else None


try:
    r = ask('OpenFile', {'filters': GLib.Variant('a(sa(us))', [('Images', [(0, '*.png')])]),
                         'current_folder': GLib.Variant('ay', os.fsencode(files) + b'\0')},
            lambda w: w.active.open_entries(
                [e for e in w.active.view.entries if e.name == 'a.png']))
    check(r is not None and r[0] == 0 and
          r[1].get('uris') == ['file://' + os.path.join(files, 'a.png')],
          f'OpenFile through xdg-desktop-portal picks a file ({r})')

    r = ask('SaveFile', {'current_name': GLib.Variant('s', 'new.txt'),
                         'current_folder': GLib.Variant('ay', os.fsencode(files) + b'\0')},
            lambda w: w.accept())
    check(r is not None and r[0] == 0 and
          r[1].get('uris') == ['file://' + os.path.join(files, 'new.txt')],
          f'SaveFile through xdg-desktop-portal returns the typed name ({r})')

    r = ask('OpenFile', {}, lambda w: w.close())
    check(r is not None and r[0] == 1, f'closing the chooser is a cancel ({r})')
finally:
    portal.terminate()
    portal.wait(5)
    if failed:
        with open(os.path.join(work, 'portal.log')) as f:
            print(f.read()[-3000:])
    for w in list(app.windows):
        w.destroy()
    app.shutdown()
    shutil.rmtree(work, ignore_errors=True)
sys.exit(1 if failed else 0)
