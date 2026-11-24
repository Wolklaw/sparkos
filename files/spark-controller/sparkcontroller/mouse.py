"""Gaming mice through libratbag's ratbagd (D-Bus, system bus, org.freedesktop.ratbag1).

What the Mouse tab shows and writes: the onboard profiles of a mouse, the DPI slots of each
(value, on or off, the active one, the default one), and the report rate. ratbagd keeps a mouse's
settings as a tree of objects: Manager -> Device -> Profile -> Resolution. Nothing here writes
while reading. Changes are made on a copy of what was read (`diff_ops` turns the difference into
a short list of writes), and `RatbagBackend.apply` runs those and then the device's Commit,
which saves them on the mouse itself (so they also hold on Windows).

The bus is a parameter: `GioBus` talks to the real daemon through PyGObject's Gio, and the tests
hand in a fake with the same three methods (tests/fakeratbag.py). Gio is imported only when the
real bus is opened, so this module loads without PyGObject.
"""

import copy
import time
from typing import Any, Dict, List, Optional, Tuple

from .log import log

BUS_NAME = "org.freedesktop.ratbag1"
MANAGER_PATH = "/org/freedesktop/ratbag1"
I_PROPS = "org.freedesktop.DBus.Properties"
I_MANAGER = "org.freedesktop.ratbag1.Manager"
I_DEVICE = "org.freedesktop.ratbag1.Device"
I_PROFILE = "org.freedesktop.ratbag1.Profile"
I_RESOLUTION = "org.freedesktop.ratbag1.Resolution"

CAP_SEPARATE_XY = 1          # Resolution.Capabilities: x and y are set apart: (uu)
CAP_DISABLE = 2              # Resolution.Capabilities: the slot can be switched off

LOW_DPI = 400                # below this a mouse is hard to use; the tab warns
SUGGESTED_DPI = 2400         # what the warning offers (the nearest value the mouse allows)
SETTLE_S = 1.5               # ratbagd writes to the mouse after Commit returns; wait, then check

# Error kinds, in the order the tab explains them.
NO_GIO, NO_DAEMON, DENIED, BUSY, FAILED = "no_gio", "no_daemon", "denied", "busy", "failed"
EBUSY = 16


class MouseError(Exception):
    """kind is one of NO_GIO, NO_DAEMON, DENIED, BUSY, FAILED; the message is for the log."""

    def __init__(self, kind: str, message: str = ""):
        super().__init__(message or kind)
        self.kind = kind


class Slot:
    def __init__(self, index: int, value: int, allowed: List[int], enabled: bool = True,
                 active: bool = False, default: bool = False, can_disable: bool = True,
                 xy: bool = False):
        self.index, self.value, self.allowed = index, value, sorted(set(allowed))
        self.enabled, self.active, self.default = enabled, active, default
        self.can_disable, self.xy = can_disable, xy
        self.path = ""                       # the D-Bus object, set when read from ratbagd


class Profile:
    def __init__(self, index: int, name: str = "", enabled: bool = True, active: bool = False,
                 rate: int = 0, rates: Optional[List[int]] = None,
                 slots: Optional[List[Slot]] = None):
        self.index, self.name, self.enabled, self.active = index, name, enabled, active
        self.rate, self.rates = rate, sorted(set(rates or []))
        self.slots: List[Slot] = slots or []
        self.path = ""

    @property
    def active_slot(self) -> Optional[Slot]:
        return next((s for s in self.slots if s.active), None)

    @property
    def default_slot(self) -> Optional[Slot]:
        return next((s for s in self.slots if s.default), None)


class Mouse:
    def __init__(self, key: str, name: str, model: str = "",
                 profiles: Optional[List[Profile]] = None):
        self.key, self.name, self.model = key, name, model
        self.profiles: List[Profile] = profiles or []

    @property
    def active_profile(self) -> Optional[Profile]:
        return next((p for p in self.profiles if p.active), None)

    def clone(self) -> "Mouse":
        return copy.deepcopy(self)


# — reading what ratbagd says —

def dpi_of(value: Any) -> int:
    """Resolution is 'u', or '(uu)' when the mouse sets x and y apart; the tab uses x."""
    if isinstance(value, (tuple, list)):
        value = value[0] if value else 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def parse_slot(props: Dict[str, Any]) -> Slot:
    caps = [int(c) for c in props.get("Capabilities") or []]
    raw = props.get("Resolution")
    return Slot(index=int(props.get("Index", 0)), value=dpi_of(raw),
                allowed=[int(v) for v in props.get("Resolutions") or [] if int(v) > 0],
                enabled=not bool(props.get("IsDisabled", False)),
                active=bool(props.get("IsActive", False)),
                default=bool(props.get("IsDefault", False)),
                can_disable=CAP_DISABLE in caps,
                xy=isinstance(raw, (tuple, list)) or CAP_SEPARATE_XY in caps)


def parse_profile(props: Dict[str, Any], slots: List[Slot]) -> Profile:
    return Profile(index=int(props.get("Index", 0)), name=str(props.get("Name") or ""),
                   enabled=not bool(props.get("Disabled", False)),
                   active=bool(props.get("IsActive", False)),
                   rate=int(props.get("ReportRate") or 0),
                   rates=[int(r) for r in props.get("ReportRates") or [] if int(r) > 0],
                   slots=sorted(slots, key=lambda s: s.index))


def profile_label(profile: Profile) -> str:
    """The profile's number as people count it (ratbagd starts at 0)."""
    return str(profile.index + 1)


# — what is wrong with a setup, and how to fix it —

def nearest(allowed: List[int], value: int) -> int:
    """The allowed value closest to this one (the value itself when the list is unknown)."""
    return min(allowed, key=lambda a: (abs(a - value), a)) if allowed else value


def step(allowed: List[int], value: int, direction: int) -> int:
    """The next allowed value up (direction > 0) or down; stays at the ends."""
    if not allowed:
        return value
    if direction > 0:
        return next((a for a in allowed if a > value), allowed[-1])
    return next((a for a in reversed(allowed) if a < value), allowed[0])


def low_dpi_problem(profile: Profile) -> Optional[Tuple[str, int]]:
    """None when the active slot is fine, otherwise ('off' | 'low', its value). 'off' means the
    mouse is sitting on a disabled slot (the 100 DPI that made a wrist hurt), 'low' that the
    value is under LOW_DPI."""
    slot = profile.active_slot
    if slot is None:
        return None
    if not slot.enabled:
        return "off", slot.value
    if slot.value < LOW_DPI:
        return "low", slot.value
    return None


def suggestion(profile: Profile) -> int:
    slot = profile.active_slot
    return nearest(slot.allowed if slot else [], SUGGESTED_DPI)


def apply_low_dpi_fix(profile: Profile) -> None:
    """Make the active slot usable: switched on, at the suggested value."""
    slot = profile.active_slot
    if slot is None:
        return
    slot.value = suggestion(profile)
    slot.enabled = True


def set_active_slot(profile: Profile, index: int) -> None:
    for slot in profile.slots:
        slot.active = slot.index == index


def set_default_slot(profile: Profile, index: int) -> None:
    for slot in profile.slots:
        slot.default = slot.index == index


def set_active_profile(mouse: Mouse, index: int) -> None:
    for profile in mouse.profiles:
        profile.active = profile.index == index


def validate(mouse: Mouse, old: Optional[Mouse] = None) -> List[Tuple[str, Dict[str, Any]]]:
    """What stops a setup from being written, as (text key, blanks) pairs; empty when fine.
    Values the mouse already has are left alone even when its own list doesn't contain them (a
    G502 sits on 6400 with 6500 as the nearest allowed step): only a changed value is checked."""
    was = {(p.index, s.index): s.value for p in (old.profiles if old else []) for s in p.slots}
    was_rate = {p.index: p.rate for p in (old.profiles if old else [])}
    problems: List[Tuple[str, Dict[str, Any]]] = []
    active = [p for p in mouse.profiles if p.active]
    if len(active) != 1 or not active[0].enabled:
        problems.append(("mouse.bad_profile", {}))
    for profile in mouse.profiles:
        if not profile.enabled:
            continue
        n = profile_label(profile)
        if profile.rates and profile.rate not in profile.rates \
                and was_rate.get(profile.index) != profile.rate:
            problems.append(("mouse.bad_rate", {"n": n, "rate": profile.rate}))
        for slot in profile.slots:
            if slot.allowed and slot.value not in slot.allowed \
                    and was.get((profile.index, slot.index)) != slot.value:
                problems.append(("mouse.bad_dpi", {"n": n, "slot": slot.index + 1,
                                                   "dpi": slot.value}))
        on = [s for s in profile.slots if s.enabled]
        active_slot, default_slot = profile.active_slot, profile.default_slot
        if profile.slots and not on:
            problems.append(("mouse.no_slot_on", {"n": n}))
        if active_slot is not None and not active_slot.enabled and on:
            problems.append(("mouse.active_off", {"n": n, "slot": active_slot.index + 1}))
        if default_slot is not None and not default_slot.enabled and on:
            problems.append(("mouse.default_off", {"n": n, "slot": default_slot.index + 1}))
    return problems


# — the writes —

Op = Tuple[Any, ...]
# ("value", profile, slot, dpi) ("enable", profile, slot, bool) ("slot_active", profile, slot)
# ("slot_default", profile, slot) ("rate", profile, hz) ("profile_active", profile)


def diff_ops(old: Mouse, new: Mouse) -> List[Op]:
    """The writes that turn `old` into `new`, in an order the daemon accepts: values first,
    slots switched on, then the active and default choices, and slots switched off last (so a
    slot is never off while it is still the active one). Only what changed."""
    values: List[Op] = []
    ons: List[Op] = []
    choices: List[Op] = []
    offs: List[Op] = []
    rates: List[Op] = []
    profile_ops: List[Op] = []
    old_profiles = {p.index: p for p in old.profiles}
    for profile in new.profiles:
        before = old_profiles.get(profile.index)
        if before is None:
            continue
        if profile.rate != before.rate:
            rates.append(("rate", profile.index, profile.rate))
        old_slots = {s.index: s for s in before.slots}
        for slot in profile.slots:
            prev = old_slots.get(slot.index)
            if prev is None:
                continue
            if slot.value != prev.value:
                values.append(("value", profile.index, slot.index, slot.value))
            if slot.enabled != prev.enabled:
                (ons if slot.enabled else offs).append(
                    ("enable", profile.index, slot.index, slot.enabled))
            if slot.active and not prev.active:
                choices.append(("slot_active", profile.index, slot.index))
            if slot.default and not prev.default:
                choices.append(("slot_default", profile.index, slot.index))
        if profile.active and not before.active:
            profile_ops.append(("profile_active", profile.index))
    return values + ons + choices + offs + rates + profile_ops


def describe_changes(old: Mouse, new: Mouse) -> int:
    """How many things differ (zero means Apply has nothing to do)."""
    return len(diff_ops(old, new))


# — the backend —

class GioBus:
    """ratbagd on the system bus through Gio. Three calls are all the backend needs."""

    def __init__(self, read_timeout_ms: int = 5000, commit_timeout_ms: int = 20000):
        try:
            import gi
            gi.require_version("Gio", "2.0")
            from gi.repository import Gio, GLib
        except (ImportError, ValueError) as exc:
            raise MouseError(NO_GIO, str(exc))
        self.Gio, self.GLib = Gio, GLib
        self.read_ms, self.commit_ms = read_timeout_ms, commit_timeout_ms
        try:
            self.conn = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error as exc:
            raise MouseError(NO_DAEMON, exc.message)

    def _call(self, path: str, iface: str, method: str, params, reply: str, timeout: int):
        try:
            return self.conn.call_sync(BUS_NAME, path, iface, method, params,
                                       self.GLib.VariantType(reply),
                                       self.Gio.DBusCallFlags.NONE, timeout, None)
        except self.GLib.Error as exc:
            raise self._error(exc)

    def _error(self, exc) -> MouseError:
        remote = ""
        try:
            remote = self.Gio.DBusError.get_remote_error(exc) or ""
        except Exception:  # noqa: BLE001 - not a remote error
            pass
        text = f"{remote} {exc.message}"
        low = text.lower()
        if any(w in low for w in ("serviceunknown", "namehasnoowner", "service files",
                                  "could not activate", "spawn")):
            return MouseError(NO_DAEMON, text)
        if "accessdenied" in low or "not allowed" in low or "permission" in low:
            return MouseError(DENIED, text)
        if "busy" in low or "ebusy" in low:
            return MouseError(BUSY, text)
        return MouseError(FAILED, text)

    def get_all(self, path: str, iface: str) -> Dict[str, Any]:
        out = self._call(path, I_PROPS, "GetAll", self.GLib.Variant("(s)", (iface,)),
                         "(a{sv})", self.read_ms)
        return out.unpack()[0]

    def set(self, path: str, iface: str, prop: str, sig: str, value: Any) -> None:
        """Properties.Set. A property typed 'v' (Resolution) is a variant inside a variant."""
        GLib = self.GLib
        inner = GLib.Variant(sig, value)
        if prop == "Resolution":
            inner = GLib.Variant("v", inner)
        self._call(path, I_PROPS, "Set", GLib.Variant("(ssv)", (iface, prop, inner)), "()",
                   self.commit_ms)

    def call(self, path: str, iface: str, method: str) -> int:
        out = self._call(path, iface, method, None, "(u)", self.commit_ms)
        return int(out.unpack()[0])


class RatbagBackend:
    def __init__(self, bus: Any = None, settle_s: float = SETTLE_S):
        self._bus = bus
        self.settle_s = settle_s

    @property
    def bus(self) -> Any:
        if self._bus is None:
            self._bus = GioBus()
        return self._bus

    def list_mice(self) -> List[Mouse]:
        """Every mouse ratbagd supports (an empty list when it knows none). Raises MouseError
        when the daemon can't be reached."""
        bus = self.bus
        manager = bus.get_all(MANAGER_PATH, I_MANAGER)
        mice: List[Mouse] = []
        for path in manager.get("Devices") or []:
            try:
                mice.append(self._read_device(bus, str(path)))
            except MouseError:
                raise
            except Exception as exc:  # noqa: BLE001 - one odd device must not hide the others
                log.warning("mouse: could not read %s: %s", path, exc)
        return mice

    @staticmethod
    def _read_device(bus: Any, path: str) -> Mouse:
        device = bus.get_all(path, I_DEVICE)
        profiles: List[Profile] = []
        for ppath in device.get("Profiles") or []:
            props = bus.get_all(str(ppath), I_PROFILE)
            slots = []
            for rpath in props.get("Resolutions") or []:
                slot = parse_slot(bus.get_all(str(rpath), I_RESOLUTION))
                slot.path = str(rpath)
                slots.append(slot)
            profile = parse_profile(props, slots)
            profile.path = str(ppath)
            profiles.append(profile)
        profiles.sort(key=lambda p: p.index)
        return Mouse(path, str(device.get("Name") or path), str(device.get("Model") or ""),
                     profiles)

    def apply(self, original: Mouse, edited: Mouse) -> int:
        """Write the difference, Commit, and check the mouse kept it. Returns the number of
        writes. Raises MouseError (and, if some writes went through but the commit did not,
        says so in the message)."""
        problems = validate(edited, original)
        if problems:
            raise MouseError(FAILED, "; ".join(key for key, _ in problems))
        ops = diff_ops(original, edited)
        if not ops:
            return 0
        bus = self.bus
        by_profile = {p.index: p for p in original.profiles}
        for op in ops:
            kind, pi = op[0], op[1]
            profile = by_profile[pi]
            ppath = profile.path
            if kind == "rate":
                bus.set(ppath, I_PROFILE, "ReportRate", "u", int(op[2]))
            elif kind == "profile_active":
                self._check(bus.call(ppath, I_PROFILE, "SetActive"))
            else:
                slot = next(s for s in profile.slots if s.index == op[2])
                rpath = slot.path
                if kind == "value":
                    value: Any = (int(op[3]), int(op[3])) if slot.xy else int(op[3])
                    bus.set(rpath, I_RESOLUTION, "Resolution", "(uu)" if slot.xy else "u", value)
                elif kind == "enable":
                    bus.set(rpath, I_RESOLUTION, "IsDisabled", "b", not op[3])
                elif kind == "slot_active":
                    self._check(bus.call(rpath, I_RESOLUTION, "SetActive"))
                elif kind == "slot_default":
                    self._check(bus.call(rpath, I_RESOLUTION, "SetDefault"))
        self._check(bus.call(original.key, I_DEVICE, "Commit"))
        return len(ops)

    @staticmethod
    def _check(code: int) -> None:
        """Methods answer 0, or a negative errno as an unsigned number."""
        if code == 0:
            return
        errno = (1 << 32) - code if code > (1 << 31) else code
        raise MouseError(BUSY if errno == EBUSY else FAILED, f"ratbagd answered {code}")

    def reread(self, mouse: Mouse) -> Optional[Mouse]:
        """After a Commit: wait for the daemon to finish writing, then read the mouse again."""
        time.sleep(self.settle_s)
        for found in self.list_mice():
            if found.key == mouse.key:
                return found
        return None


def differences(wanted: Mouse, actual: Mouse) -> List[Op]:
    """What `wanted` has that `actual` doesn't (the mouse refused or lost it)."""
    return diff_ops(actual, wanted)
