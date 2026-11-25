"""Test helpers: two private D-Bus daemons (a system bus and a session bus, never this PC's), the
python-dbusmock services on them, and a way to let the GLib main loop run while a test waits.

Everything here talks to buses that exist only for the test run. Nothing touches the real
NetworkManager, BlueZ, UPower, logind, CUPS or the tray."""

import atexit
import subprocess
import os
import sys
import time
import unittest
from typing import Callable, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)
sys.path.insert(0, APP)
SPARK_AUDIO = os.path.join(os.path.dirname(APP), 'spark-audio')
AUDIO_FIXTURES = os.path.join(SPARK_AUDIO, 'tests', 'fixtures')

os.environ.setdefault('SPARK_LANG', 'en')

try:
    import dbus                                   # noqa: F401
    from dbusmock import DBusTestCase
    HAVE_MOCK = True
except ImportError:                               # python-dbusmock isn't installed here
    HAVE_MOCK = False
    DBusTestCase = object

MOCK = 'org.freedesktop.DBus.Mock'
_started = False


def _private_bus() -> tuple:
    import subprocess
    proc = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--print-address=1'],
                            stdout=subprocess.PIPE, text=True)
    address = proc.stdout.readline().strip()
    if not address:
        proc.kill()
        raise RuntimeError("dbus-daemon didn't start")
    atexit.register(proc.terminate)
    return proc, address


def start_buses() -> None:
    """One system bus and one session bus for the whole run (GIO keeps the first connection
    it makes, so they can't change between test classes). Both are private dbus-daemons
    started here; the addresses go in the environment before anything connects."""
    global _started
    if _started or not HAVE_MOCK:
        return
    _started = True
    os.environ['DBUS_SYSTEM_BUS_ADDRESS'] = _private_bus()[1]
    os.environ['DBUS_SESSION_BUS_ADDRESS'] = _private_bus()[1]


def pump(cond: Optional[Callable[[], bool]] = None, timeout: float = 4.0) -> bool:
    """Run the GLib main context until cond() is true or the time is up."""
    from gi.repository import GLib
    ctx = GLib.MainContext.default()
    end = time.time() + timeout
    while time.time() < end:
        while ctx.pending():
            ctx.iteration(False)
        if cond is not None and cond():
            return True
        time.sleep(0.01)
    return bool(cond()) if cond is not None else True


def call_async(conn, dest, path, iface, method, params=None, timeout=4.0):
    """Call a method from a second connection without blocking this thread, so the service
    under test (in this same process) can answer. Returns (result, error)."""
    from gi.repository import Gio, GLib
    box = {}

    def done(c, res):
        try:
            box['out'] = c.call_finish(res).unpack()
        except GLib.Error as exc:
            box['err'] = exc
    conn.call(dest, path, iface, method, params, None, Gio.DBusCallFlags.NONE, 8000, None, done)
    pump(lambda: box, timeout)
    return box.get('out'), box.get('err')


def second_connection():
    """A fresh connection to the test system bus (what NetworkManager or BlueZ would use to
    call our agents)."""
    from gi.repository import Gio
    return Gio.DBusConnection.new_for_address_sync(
        os.environ['DBUS_SYSTEM_BUS_ADDRESS'],
        Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
        None, None)


def session_connection():
    from gi.repository import Gio
    return Gio.DBusConnection.new_for_address_sync(
        os.environ['DBUS_SESSION_BUS_ADDRESS'],
        Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
        None, None)


class MockCase(unittest.TestCase):
    """Starts the buses once and stops the mock services each test started."""

    @classmethod
    def setUpClass(cls):
        if not HAVE_MOCK:
            raise unittest.SkipTest("python-dbusmock isn't installed")
        start_buses()

    @staticmethod
    def _kill(proc) -> None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:                         # noqa: BLE001
            proc.kill()
        pump(timeout=0.2)

    def mock(self, template: str, system: bool = True, params=None):
        env = 'DBUS_SYSTEM_BUS_ADDRESS' if system else 'DBUS_SESSION_BUS_ADDRESS'
        assert os.environ.get(env, '').startswith('unix:'), "refusing to mock on the real bus"
        proc, obj = DBusTestCase.spawn_server_template(template, params or {}, system_bus=system,
                                                         stdout=subprocess.DEVNULL)
        self.addCleanup(self._kill, proc)
        return obj


def mock_object(name: str, path: str):
    """A dbus-python proxy for an object of a mock service on the private system bus, with the
    generic mock interface (AddProperty, AddProperties, GetCalls) ready to call."""
    import dbus
    bus = dbus.bus.BusConnection(os.environ['DBUS_SYSTEM_BUS_ADDRESS'])
    return dbus.Interface(bus.get_object(name, path), MOCK)
