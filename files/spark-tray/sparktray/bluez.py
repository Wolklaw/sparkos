"""BlueZ over D-Bus: power, scan, pair, trust, connect, disconnect, battery level where the
device reports one, and the pairing agent BlueZ asks for a PIN or a "does this number match".

The agent asks a `prompter` (ui.Prompter, or a fake in the tests): confirm(text, done(bool)),
ask(text, numeric, done(str|None)) and notify(text)."""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from gi.repository import Gio, GLib

from .core import log
from .dbusutil import Bus, BusError

BLUEZ = 'org.bluez'
ADAPTER = 'org.bluez.Adapter1'
DEVICE = 'org.bluez.Device1'
BATTERY = 'org.bluez.Battery1'
AGENT_MANAGER = 'org.bluez.AgentManager1'
AGENT_IFACE = 'org.bluez.Agent1'
AGENT_PATH = '/dev/wolklaw/SparkTray/agent'
REJECTED = 'org.bluez.Error.Rejected'
CANCELED = 'org.bluez.Error.Canceled'


@dataclass
class Device:
    path: str
    name: str
    address: str
    paired: bool = False
    trusted: bool = False
    connected: bool = False
    battery: Optional[int] = None
    icon: str = ''
    rssi: Optional[int] = None


@dataclass
class BtState:
    available: bool = False
    adapter: str = ''
    powered: bool = False
    discovering: bool = False
    devices: List[Device] = field(default_factory=list)

    @property
    def connected(self) -> List[Device]:
        return [d for d in self.devices if d.connected]


class Bluetooth:
    def __init__(self, bus: Bus, on_change: Callable[[], None] = lambda: None):
        self.bus, self.on_change = bus, on_change
        self._subs: List[int] = []

    def available(self) -> bool:
        return self.bus.has_owner(BLUEZ)

    def start(self) -> bool:
        if not self.available():
            return False
        if not self._subs:
            for member in ('InterfacesAdded', 'InterfacesRemoved'):
                self._subs.append(self.bus.subscribe(BLUEZ, 'org.freedesktop.DBus.ObjectManager',
                                                     member, None, self._signal))
            self._subs.append(self.bus.subscribe(BLUEZ, 'org.freedesktop.DBus.Properties',
                                                 'PropertiesChanged', None, self._signal))
        return True

    def stop(self) -> None:
        for sub in self._subs:
            self.bus.unsubscribe(sub)
        self._subs = []

    def _signal(self, *_args) -> None:
        self.on_change()

    def state(self) -> BtState:
        s = BtState()
        try:
            objects = self.bus.call(BLUEZ, '/', 'org.freedesktop.DBus.ObjectManager',
                                    'GetManagedObjects')[0]
        except BusError:
            return s
        for path in sorted(objects):
            ifaces = objects[path]
            if ADAPTER in ifaces and not s.adapter:
                a = ifaces[ADAPTER]
                s.adapter, s.powered = path, bool(a.get('Powered', False))
                s.discovering = bool(a.get('Discovering', False))
        s.available = bool(s.adapter)         # the service can run on a PC with no radio
        for path, ifaces in objects.items():
            if DEVICE not in ifaces:
                continue
            d = ifaces[DEVICE]
            if s.adapter and d.get('Adapter') not in (None, s.adapter):
                continue
            bat = ifaces.get(BATTERY, {}).get('Percentage')
            s.devices.append(Device(
                path=path, name=str(d.get('Alias') or d.get('Name') or d.get('Address', '')),
                address=str(d.get('Address', '')), paired=bool(d.get('Paired', False)),
                trusted=bool(d.get('Trusted', False)), connected=bool(d.get('Connected', False)),
                battery=int(bat) if bat is not None else None, icon=str(d.get('Icon', '')),
                rssi=int(d['RSSI']) if 'RSSI' in d else None))
        # connected first, then paired, then what is nearby by signal, then by name
        s.devices.sort(key=lambda x: (not x.connected, not x.paired,
                                      -(x.rssi if x.rssi is not None else -200), x.name.lower()))
        return s

    def _done(self, done):
        def finished(_out, err):
            if err:
                log.warning("BlueZ: %s", err)
            self.on_change()
            if done:
                done(err)
        return finished

    def set_power(self, adapter: str, on: bool) -> None:
        self.bus.set(BLUEZ, adapter, ADAPTER, 'Powered', GLib.Variant('b', on))
        self.on_change()

    def scan(self, adapter: str, on: bool, done=None) -> None:
        self.bus.call_async(BLUEZ, adapter, ADAPTER, 'StartDiscovery' if on else 'StopDiscovery',
                            None, self._done(done), 10000)

    def pair(self, device: Device, done=None) -> None:
        """Pair, then trust it, so it reconnects by itself. Waits for the person (the agent)."""
        def paired(_out, err):
            if not err:
                try:
                    self.bus.set(BLUEZ, device.path, DEVICE, 'Trusted', GLib.Variant('b', True))
                except BusError:
                    pass
            self._done(done)(None, err)
        self.bus.call_async(BLUEZ, device.path, DEVICE, 'Pair', None, paired, 120000)

    def set_trusted(self, device: Device, on: bool) -> None:
        self.bus.set(BLUEZ, device.path, DEVICE, 'Trusted', GLib.Variant('b', on))
        self.on_change()

    def connect(self, device: Device, done=None) -> None:
        self.bus.call_async(BLUEZ, device.path, DEVICE, 'Connect', None, self._done(done), 60000)

    def disconnect(self, device: Device, done=None) -> None:
        self.bus.call_async(BLUEZ, device.path, DEVICE, 'Disconnect', None, self._done(done),
                            20000)

    def forget(self, adapter: str, device: Device, done=None) -> None:
        self.bus.call_async(BLUEZ, adapter, ADAPTER, 'RemoveDevice',
                            GLib.Variant('(o)', (device.path,)), self._done(done), 10000)


# ─── The pairing agent ───────────────────────────────────────

AGENT_XML = f"""
<node>
  <interface name="{AGENT_IFACE}">
    <method name="Release"/>
    <method name="RequestPinCode"><arg type="o" direction="in"/><arg type="s" direction="out"/></method>
    <method name="DisplayPinCode"><arg type="o" direction="in"/><arg type="s" direction="in"/></method>
    <method name="RequestPasskey"><arg type="o" direction="in"/><arg type="u" direction="out"/></method>
    <method name="DisplayPasskey"><arg type="o" direction="in"/><arg type="u" direction="in"/><arg type="q" direction="in"/></method>
    <method name="RequestConfirmation"><arg type="o" direction="in"/><arg type="u" direction="in"/></method>
    <method name="RequestAuthorization"><arg type="o" direction="in"/></method>
    <method name="AuthorizeService"><arg type="o" direction="in"/><arg type="s" direction="in"/></method>
    <method name="Cancel"/>
  </interface>
</node>"""


class PairingAgent:
    def __init__(self, bus: Bus, prompter, name_of: Callable[[str], str],
                 text: Callable[..., str]):
        """name_of(device path) gives the device's name; text(key, **kw) is the translation."""
        self.bus, self.prompter, self.name_of, self.t = bus, prompter, name_of, text
        self._reg: Optional[int] = None
        self.registered = False
        self.cancel_open: Optional[Callable[[], None]] = None

    def start(self) -> bool:
        info = Gio.DBusNodeInfo.new_for_xml(AGENT_XML).interfaces[0]
        try:
            self._reg = self.bus.conn.register_object(AGENT_PATH, info, self._method, None, None)
            self.bus.call(BLUEZ, '/org/bluez', AGENT_MANAGER, 'RegisterAgent',
                          GLib.Variant('(os)', (AGENT_PATH, 'KeyboardDisplay')))
            self.bus.call(BLUEZ, '/org/bluez', AGENT_MANAGER, 'RequestDefaultAgent',
                          GLib.Variant('(o)', (AGENT_PATH,)))
        except (BusError, GLib.Error) as exc:
            log.warning("pairing agent not registered: %s", exc)
            return False
        self.registered = True
        return True

    def stop(self) -> None:
        if self.registered:
            try:
                self.bus.call(BLUEZ, '/org/bluez', AGENT_MANAGER, 'UnregisterAgent',
                              GLib.Variant('(o)', (AGENT_PATH,)))
            except BusError:
                pass
        if self._reg is not None:
            self.bus.conn.unregister_object(self._reg)
        self._reg, self.registered = None, False

    def _method(self, _conn, _sender, _path, _iface, method, params, invocation) -> None:
        args = params.unpack()
        device = args[0] if args and isinstance(args[0], str) else ''
        name = self.name_of(device) if device else ''
        t, p = self.t, self.prompter

        def yes_no(ok: bool) -> None:
            if ok:
                invocation.return_value(None)
            else:
                invocation.return_dbus_error(REJECTED, "rejected")

        if method == 'RequestConfirmation':
            self.cancel_open = p.confirm(t('bt.confirm', name=name, passkey=f"{args[1]:06d}"),
                                         yes_no)
        elif method in ('RequestAuthorization', 'AuthorizeService'):
            self.cancel_open = p.confirm(t('bt.authorize', name=name), yes_no)
        elif method == 'RequestPinCode':
            def pin(value: Optional[str]) -> None:
                if value:
                    invocation.return_value(GLib.Variant('(s)', (value,)))
                else:
                    invocation.return_dbus_error(REJECTED, "rejected")
            self.cancel_open = p.ask(t('bt.pin', name=name), False, pin)
        elif method == 'RequestPasskey':
            def passkey(value: Optional[str]) -> None:
                if value and value.isdigit() and int(value) <= 999999:
                    invocation.return_value(GLib.Variant('(u)', (int(value),)))
                else:
                    invocation.return_dbus_error(REJECTED, "rejected")
            self.cancel_open = p.ask(t('bt.passkey', name=name), True, passkey)
        elif method == 'DisplayPinCode':
            p.notify(t('bt.show_pin', name=name, pin=args[1]))
            invocation.return_value(None)
        elif method == 'DisplayPasskey':
            p.notify(t('bt.show_pin', name=name, pin=f"{args[1]:06d}"))
            invocation.return_value(None)
        elif method == 'Cancel':
            if self.cancel_open:
                self.cancel_open()
                self.cancel_open = None
            invocation.return_value(None)
        else:                                          # Release
            invocation.return_value(None)


def agent_names(state_fn: Callable[[], BtState]) -> Callable[[str], str]:
    def name_of(path: str) -> str:
        for d in state_fn().devices:
            if d.path == path:
                return d.name
        return path.rsplit('/', 1)[-1].replace('dev_', '').replace('_', ':')
    return name_of


def by_path(devices: List[Device]) -> Dict[str, Device]:
    return {d.path: d for d in devices}
