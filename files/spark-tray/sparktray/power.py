"""Power: the battery from UPower, the power profile from power-profiles-daemon (SparkOS runs
tuned-ppd, which answers the same D-Bus API), and sleep, restart and shut down through logind.
A desktop has no battery: has_battery() is then False and the tray hides the item."""

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from gi.repository import GLib

from .core import log
from .dbusutil import Bus, BusError

UPOWER = 'org.freedesktop.UPower'
DISPLAY_DEVICE = '/org/freedesktop/UPower/devices/DisplayDevice'
DEVICE = 'org.freedesktop.UPower.Device'
PPD_NAMES = (('net.hadess.PowerProfiles', '/net/hadess/PowerProfiles'),
             ('org.freedesktop.UPower.PowerProfiles', '/org/freedesktop/UPower/PowerProfiles'))
LOGIND = 'org.freedesktop.login1'
LOGIND_PATH = '/org/freedesktop/login1'
LOGIND_MANAGER = 'org.freedesktop.login1.Manager'

CHARGING, DISCHARGING, EMPTY, FULL, PENDING_CHARGE, PENDING_DISCHARGE = 1, 2, 3, 4, 5, 6
PROFILES = ('power-saver', 'balanced', 'performance')
ACTIONS = {'sleep': 'Suspend', 'restart': 'Reboot', 'shutdown': 'PowerOff'}


@dataclass
class Battery:
    present: bool = False
    percent: float = 0.0
    state: int = 0
    seconds: int = 0           # to empty when discharging, to full when charging

    @property
    def charging(self) -> bool:
        return self.state in (CHARGING, PENDING_CHARGE)

    @property
    def full(self) -> bool:
        return self.state == FULL


@dataclass
class PowerState:
    battery: Battery = field(default_factory=Battery)
    profiles: List[str] = field(default_factory=list)
    profile: str = ''
    can: dict = field(default_factory=dict)       # 'sleep' / 'restart' / 'shutdown' -> bool


class Power:
    def __init__(self, system_bus: Bus, on_change: Callable[[], None] = lambda: None):
        self.bus, self.on_change = system_bus, on_change
        self._subs: List[int] = []
        self._ppd = None

    def _find_ppd(self):
        for name, path in PPD_NAMES:
            if self.bus.has_owner(name):
                return name, path
        return None

    def start(self) -> bool:
        self._ppd = self._find_ppd()
        if not self._subs:
            self._subs.append(self.bus.subscribe(None, 'org.freedesktop.DBus.Properties',
                                                 'PropertiesChanged', None, self._signal))
        return True

    def stop(self) -> None:
        for sub in self._subs:
            self.bus.unsubscribe(sub)
        self._subs = []

    def _signal(self, _sender, path, _iface, _member, params) -> None:
        if path.startswith('/org/freedesktop/UPower') or path.startswith('/net/hadess'):
            self.on_change()

    def has_battery(self) -> bool:
        return self.battery().present

    def has_profiles(self) -> bool:
        self._ppd = self._ppd or self._find_ppd()
        return self._ppd is not None

    def battery(self) -> Battery:
        try:
            p = self.bus.get_all(UPOWER, DISPLAY_DEVICE, DEVICE)
        except BusError:
            return Battery()
        state = int(p.get('State', 0))
        seconds = int(p.get('TimeToFull' if state in (CHARGING, PENDING_CHARGE)
                            else 'TimeToEmpty', 0))
        return Battery(bool(p.get('IsPresent', False)), float(p.get('Percentage', 0.0)),
                       state, seconds)

    def state(self) -> PowerState:
        s = PowerState(battery=self.battery())
        ppd = self._ppd or self._find_ppd()
        if ppd:
            self._ppd = ppd
            try:
                props = self.bus.get_all(ppd[0], ppd[1], ppd[0])
                s.profile = str(props.get('ActiveProfile', ''))
                names = [str(p.get('Profile', '')) for p in props.get('Profiles', [])]
                s.profiles = [n for n in PROFILES if n in names] + \
                             [n for n in names if n not in PROFILES]
            except BusError as exc:
                log.warning("power profiles: %s", exc)
        for key, method in ACTIONS.items():
            try:
                s.can[key] = self.bus.call(LOGIND, LOGIND_PATH, LOGIND_MANAGER,
                                           'Can' + method)[0] in ('yes', 'challenge')
            except BusError:
                s.can[key] = False
        return s

    def set_profile(self, name: str) -> None:
        ppd = self._ppd or self._find_ppd()
        if not ppd:
            raise BusError("no power profile service")
        self.bus.set(ppd[0], ppd[1], ppd[0], 'ActiveProfile', GLib.Variant('s', name))
        self.on_change()

    def act(self, action: str, done: Optional[Callable[[Optional[BusError]], None]] = None) -> None:
        """sleep, restart or shutdown. The caller has already asked the person to confirm.
        interactive=True lets polkit ask for a password if this user may not do it."""
        method = ACTIONS[action]
        self.bus.call_async(LOGIND, LOGIND_PATH, LOGIND_MANAGER, method,
                            GLib.Variant('(b)', (True,)),
                            lambda _o, err: done(err) if done else None, 30000)


def format_time(seconds: int) -> str:
    """'1 h 05' or '12 min'; empty when unknown."""
    if seconds <= 0:
        return ''
    minutes = round(seconds / 60)
    return f"{minutes // 60} h {minutes % 60:02d}" if minutes >= 60 else f"{max(1, minutes)} min"


def battery_icon(b: Battery) -> str:
    level = max(0, min(100, int(round(b.percent / 10.0)) * 10))
    if b.full:
        return 'battery-full-charged' if not b.charging else 'battery-full-charging'
    return f"battery-{level:03d}" + ('-charging' if b.charging else '')
