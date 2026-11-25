"""NetworkManager over D-Bus: Wi-Fi list with signal, connect (new network with a password, or
a saved one), disconnect, wired status, VPN connections NM knows, airplane mode, and the secrets
agent NM asks when a saved connection needs a password.

Nothing here knows about windows. The agent asks a `prompter` (ui.Prompter, or a fake in the
tests) for what the person types."""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from gi.repository import Gio, GLib

from .core import log
from .dbusutil import Bus, BusError

NM = 'org.freedesktop.NetworkManager'
NM_PATH = '/org/freedesktop/NetworkManager'
NM_SETTINGS = 'org.freedesktop.NetworkManager.Settings'
NM_SETTINGS_PATH = '/org/freedesktop/NetworkManager/Settings'
DEVICE = NM + '.Device'
WIRELESS = NM + '.Device.Wireless'
AP = NM + '.AccessPoint'
ACTIVE = NM + '.Connection.Active'
AGENT_MANAGER = NM + '.AgentManager'
AGENT_MANAGER_PATH = '/org/freedesktop/NetworkManager/AgentManager'
AGENT_IFACE = NM + '.SecretAgent'
AGENT_PATH = '/org/freedesktop/NetworkManager/SecretAgent'

DEV_ETHERNET, DEV_WIFI = 1, 2
STATE_ACTIVATED, STATE_UNAVAILABLE, STATE_PREPARE = 100, 20, 40
KEY_MGMT_PSK, KEY_MGMT_8021X, KEY_MGMT_SAE = 0x100, 0x200, 0x400
VPN_TYPES = ('vpn', 'wireguard')
OFF = '/'


@dataclass
class AccessPoint:
    path: str
    ssid: str
    strength: int
    secured: bool
    enterprise: bool = False     # 802.1X: needs more than a password, which this applet can't ask
    sae: bool = False
    active: bool = False
    known: str = ''              # path of the saved connection for this network, if any


@dataclass
class Wired:
    interface: str
    state: int
    connection: str = ''

    @property
    def connected(self) -> bool:
        return self.state == STATE_ACTIVATED

    @property
    def cable(self) -> bool:
        return self.state > STATE_UNAVAILABLE


@dataclass
class Vpn:
    name: str
    uuid: str
    kind: str
    path: str
    active_path: str = ''

    @property
    def active(self) -> bool:
        return bool(self.active_path)


@dataclass
class NetState:
    available: bool = False
    wifi_enabled: bool = False
    wifi_device: str = ''
    wifi_present: bool = False
    wired: List[Wired] = field(default_factory=list)
    aps: List[AccessPoint] = field(default_factory=list)
    vpns: List[Vpn] = field(default_factory=list)
    active_ssid: str = ''
    active_path: str = ''           # the Wi-Fi's active connection, to disconnect it
    connectivity: int = 4
    nm_state: int = 70

    @property
    def online(self) -> bool:
        return self.nm_state >= 50


def _ssid_text(raw: Any) -> str:
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw).decode('utf-8', errors='replace')
    if isinstance(raw, (list, tuple)):
        return bytes(raw).decode('utf-8', errors='replace')
    return str(raw)


class Network:
    def __init__(self, bus: Bus, on_change: Callable[[], None] = lambda: None):
        self.bus = bus
        self.on_change = on_change
        self._subs: List[int] = []
        self._bound = False

    # — reading —
    def available(self) -> bool:
        return self.bus.has_owner(NM)

    def start(self) -> bool:
        if not self.available():
            return False
        if not self._bound:
            self._bound = True
            for iface in (NM, DEVICE, WIRELESS, ACTIVE, AP, NM_SETTINGS):
                self._subs.append(self.bus.subscribe(NM, iface, None, None, self._signal))
            self._subs.append(self.bus.subscribe(NM, 'org.freedesktop.DBus.Properties',
                                                 'PropertiesChanged', None, self._signal))
        return True

    def stop(self) -> None:
        for sub in self._subs:
            self.bus.unsubscribe(sub)
        self._subs, self._bound = [], False

    def _signal(self, *_args) -> None:
        self.on_change()

    def _props(self, path: str, iface: str) -> Dict[str, Any]:
        try:
            return self.bus.get_all(NM, path, iface)
        except BusError:
            return {}

    def _saved_wifi(self) -> Dict[str, str]:
        """ssid -> path of the saved connection."""
        found: Dict[str, str] = {}
        for path, settings in self._connections():
            if settings.get('connection', {}).get('type') == '802-11-wireless':
                ssid = _ssid_text(settings.get('802-11-wireless', {}).get('ssid', b''))
                found.setdefault(ssid, path)
        return found

    def _connections(self):
        try:
            paths = self.bus.call(NM, NM_SETTINGS_PATH, NM_SETTINGS, 'ListConnections')[0]
        except BusError:
            return
        for path in paths:
            try:
                yield path, self.bus.call(NM, path, NM + '.Settings.Connection', 'GetSettings')[0]
            except BusError:
                continue

    def state(self) -> NetState:
        s = NetState()
        top = self._props(NM_PATH, NM)
        if not top:
            return s
        s.available = True
        s.wifi_enabled = bool(top.get('WirelessEnabled', False))
        s.nm_state = int(top.get('State', 70))
        s.connectivity = int(top.get('Connectivity', 4))
        active_paths = list(top.get('ActiveConnections', []))
        actives = {p: self._props(p, ACTIVE) for p in active_paths}
        saved = self._saved_wifi()
        for dev in top.get('Devices', []):
            dprops = self._props(dev, DEVICE)
            kind = int(dprops.get('DeviceType', 0))
            if kind == DEV_ETHERNET:
                conn = actives.get(str(dprops.get('ActiveConnection', OFF)), {}).get('Id', '')
                s.wired.append(Wired(str(dprops.get('Interface', '')),
                                     int(dprops.get('State', 0)), conn))
            elif kind == DEV_WIFI and not s.wifi_present:
                s.wifi_present, s.wifi_device = True, dev
                self._read_aps(s, dev, dprops, actives, saved)
        for path, settings in self._connections():
            kind = settings.get('connection', {}).get('type', '')
            if kind in VPN_TYPES:
                uuid = settings['connection'].get('uuid', '')
                act = next((p for p, a in actives.items()
                            if a.get('Uuid') == uuid
                            and int(a.get('State', 0)) in (1, 2)), '')
                s.vpns.append(Vpn(settings['connection'].get('id', uuid), uuid, kind, path, act))
        s.vpns.sort(key=lambda v: v.name.lower())
        return s

    def _read_aps(self, s: NetState, dev: str, dprops, actives, saved) -> None:
        wprops = self._props(dev, WIRELESS)
        act_conn = str(dprops.get('ActiveConnection', OFF))
        active_ap = str(wprops.get('ActiveAccessPoint', OFF))
        if act_conn != OFF:
            s.active_path = act_conn
            if active_ap == OFF:
                active_ap = str(actives.get(act_conn, {}).get('SpecificObject', OFF))
        best: Dict[str, AccessPoint] = {}
        for path in wprops.get('AccessPoints', []):
            a = self._props(path, AP)
            ssid = _ssid_text(a.get('Ssid', b''))
            if not ssid:
                continue
            wpa, rsn, flags = (int(a.get(k, 0)) for k in ('WpaFlags', 'RsnFlags', 'Flags'))
            both = wpa | rsn
            item = AccessPoint(
                path=str(path), ssid=ssid, strength=int(a.get('Strength', 0)),
                secured=bool(flags & 1) or both != 0,
                enterprise=bool(both & KEY_MGMT_8021X) and not both & (KEY_MGMT_PSK | KEY_MGMT_SAE),
                sae=bool(both & KEY_MGMT_SAE) and not both & KEY_MGMT_PSK,
                active=str(path) == active_ap, known=saved.get(ssid, ''))
            old = best.get(ssid)
            if old is None or item.active or (not old.active and item.strength > old.strength):
                best[ssid] = item
        s.aps = sorted(best.values(), key=lambda x: (not x.active, -x.strength, x.ssid.lower()))
        s.active_ssid = next((x.ssid for x in s.aps if x.active), '')

    # — writing —
    def _done(self, done: Optional[Callable[[Optional[BusError]], None]]):
        def finished(_out, err):
            if err:
                log.warning("NetworkManager: %s", err)
            self.on_change()
            if done:
                done(err)
        return finished

    def rescan(self, device: str) -> None:
        self.bus.call_async(NM, device, WIRELESS, 'RequestScan', GLib.Variant('(a{sv})', ({},)),
                            lambda *_: None, 10000)

    def connect(self, ap: AccessPoint, device: str, password: Optional[str] = None,
                done=None) -> None:
        """A saved network connects with what NM kept (and the agent asks for what is missing);
        a new one is created with the password given, or none for an open network."""
        if ap.known:
            self.bus.call_async(NM, NM_PATH, NM, 'ActivateConnection',
                                GLib.Variant('(ooo)', (ap.known, device, ap.path)),
                                self._done(done))
            return
        if ap.enterprise:
            if done:
                done(BusError("802.1X networks aren't set up from here", 'enterprise'))
            return
        wireless: Dict[str, GLib.Variant] = {
            'ssid': GLib.Variant('ay', ap.ssid.encode('utf-8'))}
        settings = {'connection': {'id': GLib.Variant('s', ap.ssid),
                                   'type': GLib.Variant('s', '802-11-wireless')},
                    '802-11-wireless': wireless}
        if ap.secured:
            settings['802-11-wireless-security'] = {
                'key-mgmt': GLib.Variant('s', 'sae' if ap.sae else 'wpa-psk'),
                'psk': GLib.Variant('s', password or '')}
        self.bus.call_async(NM, NM_PATH, NM, 'AddAndActivateConnection',
                            GLib.Variant('(a{sa{sv}}oo)', (settings, device, ap.path)),
                            self._done(done))

    def disconnect(self, active_path: str, done=None) -> None:
        self.bus.call_async(NM, NM_PATH, NM, 'DeactivateConnection',
                            GLib.Variant('(o)', (active_path,)), self._done(done))

    def set_vpn(self, vpn: Vpn, on: bool, done=None) -> None:
        if on:
            self.bus.call_async(NM, NM_PATH, NM, 'ActivateConnection',
                                GLib.Variant('(ooo)', (vpn.path, OFF, OFF)), self._done(done))
        elif vpn.active_path:
            self.disconnect(vpn.active_path, done)

    def set_wifi(self, on: bool) -> None:
        self.bus.set(NM, NM_PATH, NM, 'WirelessEnabled', GLib.Variant('b', on))
        self.on_change()

    def set_airplane(self, on: bool) -> None:
        """Airplane mode is the radios off: Wi-Fi and mobile data here, Bluetooth in items.py."""
        self.bus.set(NM, NM_PATH, NM, 'WirelessEnabled', GLib.Variant('b', not on))
        try:
            self.bus.set(NM, NM_PATH, NM, 'WwanEnabled', GLib.Variant('b', not on))
        except BusError:
            pass        # no mobile modem
        self.on_change()


# ─── The secrets agent ───────────────────────────────────────

AGENT_XML = f"""
<node>
  <interface name="{AGENT_IFACE}">
    <method name="GetSecrets">
      <arg type="a{{sa{{sv}}}}" name="connection" direction="in"/>
      <arg type="o" name="connection_path" direction="in"/>
      <arg type="s" name="setting_name" direction="in"/>
      <arg type="as" name="hints" direction="in"/>
      <arg type="u" name="flags" direction="in"/>
      <arg type="a{{sa{{sv}}}}" name="secrets" direction="out"/>
    </method>
    <method name="CancelGetSecrets">
      <arg type="o" name="connection_path" direction="in"/>
      <arg type="s" name="setting_name" direction="in"/>
    </method>
    <method name="SaveSecrets">
      <arg type="a{{sa{{sv}}}}" name="connection" direction="in"/>
      <arg type="o" name="connection_path" direction="in"/>
    </method>
    <method name="DeleteSecrets">
      <arg type="a{{sa{{sv}}}}" name="connection" direction="in"/>
      <arg type="o" name="connection_path" direction="in"/>
    </method>
  </interface>
</node>"""

FLAG_ALLOW_INTERACTION = 0x1
FLAG_REQUEST_NEW = 0x2
NO_SECRETS = AGENT_IFACE + '.NoSecrets'
CANCELED = AGENT_IFACE + '.UserCanceled'
KNOWN_FIELDS = {'psk': 'wifi.password', 'password': 'vpn.password', 'leap-password': 'wifi.password',
                'wep-key0': 'wifi.wep'}


class SecretAgent:
    """Answers NM's "this connection needs a secret". `prompter.ask_secrets(title, fields,
    done)` shows the questions, fields being [(key, label)], and calls done({key: value}) or
    done(None) when cancelled. Secrets are asked every time and never stored by the agent;
    NM keeps the ones it was given with the connection."""

    def __init__(self, bus: Bus, prompter, label_for: Callable[[str], str] = lambda k: k):
        self.bus, self.prompter, self.label_for = bus, prompter, label_for
        self._reg: Optional[int] = None
        self.pending: Dict[tuple, Any] = {}
        self.registered = False

    def start(self) -> bool:
        info = Gio.DBusNodeInfo.new_for_xml(AGENT_XML).interfaces[0]
        try:
            self._reg = self.bus.conn.register_object(AGENT_PATH, info, self._method, None, None)
            self.bus.call(NM, AGENT_MANAGER_PATH, AGENT_MANAGER, 'Register',
                          GLib.Variant('(s)', ('dev.wolklaw.SparkTray',)))
        except (BusError, GLib.Error) as exc:
            log.warning("secrets agent not registered: %s", exc)
            return False
        self.registered = True
        return True

    def stop(self) -> None:
        if self.registered:
            try:
                self.bus.call(NM, AGENT_MANAGER_PATH, AGENT_MANAGER, 'Unregister')
            except BusError:
                pass
        if self._reg is not None:
            self.bus.conn.unregister_object(self._reg)
        self._reg, self.registered = None, False

    def _method(self, _conn, _sender, _path, _iface, method, params, invocation) -> None:
        if method == 'GetSecrets':
            conn, path, setting, hints, flags = params.unpack()
            self.get_secrets(conn, path, setting, list(hints), flags, invocation)
        elif method == 'CancelGetSecrets':
            path, setting = params.unpack()
            cancel = self.pending.pop((path, setting), None)
            if cancel:
                cancel()
            invocation.return_value(None)
        else:                                         # SaveSecrets, DeleteSecrets
            invocation.return_value(None)

    def wanted(self, setting: str, hints: List[str], conn: Dict[str, Any]) -> List[tuple]:
        """What to ask for: the hints NM gave (they look like 'psk' or 'vpn.secrets.password'),
        or the usual field of the setting when it gave none."""
        keys = [h.split('.')[-1] for h in hints if h]
        if not keys:
            keys = {'802-11-wireless-security': ['psk'], 'vpn': ['password'],
                    '802-1x': ['password']}.get(setting, [])
        return [(k, self.label_for(KNOWN_FIELDS.get(k, 'secret'))) for k in keys]

    def get_secrets(self, conn, path, setting, hints, flags, invocation) -> None:
        fields = self.wanted(setting, hints, conn)
        if not (flags & FLAG_ALLOW_INTERACTION) or not fields:
            invocation.return_dbus_error(NO_SECRETS, "no secrets without asking")
            return
        name = conn.get('connection', {}).get('id', '')
        key = (path, setting)

        def answered(values: Optional[Dict[str, str]]) -> None:
            self.pending.pop(key, None)
            if not values:
                invocation.return_dbus_error(CANCELED, "cancelled")
                return
            if setting == 'vpn':
                body = {'secrets': GLib.Variant('a{ss}', values)}
            else:
                body = {k: GLib.Variant('s', v) for k, v in values.items()}
            invocation.return_value(GLib.Variant('(a{sa{sv}})', ({setting: body},)))

        self.pending[key] = self.prompter.ask_secrets(name, fields, answered) or (lambda: None)
