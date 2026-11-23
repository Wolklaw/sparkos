"""USB lighting and cooling controllers through liquidctl (the Python library, imported
directly): NZXT, Corsair, and other AIO coolers and fan hubs.

liquidctl is optional at run time: without it, nothing here finds a device. The finder is a
parameter so the tests can hand in fake devices; no test touches real USB.
"""

import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from .log import log

# A pump must never be driven below this; most AIO pumps stall or lose flow under it.
PUMP_MIN_DUTY = 50
# What a liquidctl fan gets when the daemon lets go: these controllers have no "automatic"
# mode the daemon can switch back to, so it settles on a quiet but safe speed.
RELEASE_DUTY = 60


def default_finder() -> Iterable[Any]:
    from liquidctl.driver import find_liquidctl_devices   # imported late: it's optional
    return find_liquidctl_devices()


def library_version() -> Optional[str]:
    try:
        import liquidctl
        return getattr(liquidctl, "__version__", None) or "installed"
    except Exception:                       # not installed, or broken
        return None


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


class LiquidDevice:
    """One liquidctl device, with its handle kept open while in use."""

    def __init__(self, driver: Any, index: int = 0):
        self.driver = driver
        self.index = index
        self.error: Optional[str] = None
        self.connected = False
        self.initialised = False
        self.status_cache: Dict[str, Tuple[Any, str]] = {}

    @property
    def name(self) -> str:
        return str(getattr(self.driver, "description", "liquidctl device"))

    @property
    def vendor_id(self) -> int:
        return int(getattr(self.driver, "vendor_id", 0) or 0)

    @property
    def product_id(self) -> int:
        return int(getattr(self.driver, "product_id", 0) or 0)

    @property
    def key(self) -> str:
        base = f"liquidctl:{self.vendor_id:04x}:{self.product_id:04x}"
        return base if self.index == 0 else f"{base}#{self.index + 1}"

    @property
    def color_channels(self) -> List[str]:
        channels = getattr(self.driver, "_color_channels", None) or {}
        return list(channels)

    @property
    def speed_channels(self) -> List[str]:
        channels = getattr(self.driver, "_speed_channels", None) or {}
        return [c for c in channels if c != "sync"]

    def connect(self) -> bool:
        if self.connected:
            return True
        try:
            self.driver.connect()
            self.connected = True
            self.error = None
        except Exception as exc:
            self.error = str(exc) or exc.__class__.__name__
            log.warning("liquidctl: can't open %s: %s", self.name, self.error)
        return self.connected

    def initialise(self) -> None:
        if self.connect() and not self.initialised:
            try:
                self.driver.initialize()
                self.initialised = True
            except Exception as exc:
                self.error = str(exc) or exc.__class__.__name__
                log.warning("liquidctl: can't initialise %s: %s", self.name, self.error)

    def status(self) -> Dict[str, Tuple[Any, str]]:
        """Readings as {name: (value, unit)}; the last good set if this read fails."""
        if self.connect():
            try:
                rows = self.driver.get_status() or []
                self.status_cache = {str(k): (v, str(u)) for k, v, u in rows}
                self.error = None
            except Exception as exc:
                self.error = str(exc) or exc.__class__.__name__
        return self.status_cache

    def close(self) -> None:
        if self.connected:
            try:
                self.driver.disconnect()
            except Exception:
                pass
            self.connected = False
            self.initialised = False


class LiquidFan:
    """A fan or pump channel of a liquidctl device, in the same shape as HwmonFan."""
    kind = "liquidctl"
    controllable = True

    def __init__(self, device: LiquidDevice, channel: str):
        self.device, self.channel = device, channel
        self.key = f"{device.key}/{channel}"
        self.chip = device.name
        self.label = f"{device.name} {channel}"
        self.is_pump = "pump" in channel.lower()

    def _find(self, suffix: str) -> Optional[Any]:
        wanted = _slug(self.channel)
        for name, (value, _unit) in self.device.status_cache.items():
            slug = _slug(name)
            if slug.startswith(wanted) and slug.endswith(suffix):
                return value
        return None

    def rpm(self) -> Optional[int]:
        value = self._find("speed")
        return int(value) if isinstance(value, (int, float)) else None

    def duty(self) -> Optional[float]:
        value = self._find("duty")
        return float(value) if isinstance(value, (int, float)) else None

    def mode(self) -> Optional[int]:
        return None

    @property
    def floor(self) -> float:
        return PUMP_MIN_DUTY if self.is_pump else 0.0

    def takeover(self) -> Optional[int]:
        self.device.initialise()
        return None

    def set_duty(self, percent: float) -> None:
        percent = max(self.floor, min(100.0, percent))
        self.device.driver.set_fixed_speed(self.channel, int(round(percent)))

    def release(self, _original: Optional[int]) -> None:
        self.set_duty(RELEASE_DUTY)


class LiquidHub:
    def __init__(self, finder: Optional[Callable[[], Iterable[Any]]] = None):
        self.finder = finder or default_finder
        self.devices: List[LiquidDevice] = []
        self.error: Optional[str] = None
        self.scan()

    def scan(self) -> None:
        for device in self.devices:
            device.close()
        self.devices = []
        self.error = None
        try:
            counts: Dict[Tuple[int, int], int] = {}
            for driver in self.finder():
                ids = (int(getattr(driver, "vendor_id", 0) or 0),
                       int(getattr(driver, "product_id", 0) or 0))
                self.devices.append(LiquidDevice(driver, counts.get(ids, 0)))
                counts[ids] = counts.get(ids, 0) + 1
        except ImportError:
            self.error = "liquidctl is not installed"
        except Exception as exc:               # a USB or permission problem must not stop the app
            self.error = str(exc) or exc.__class__.__name__
            log.warning("liquidctl: scan failed: %s", self.error)

    def refresh(self) -> None:
        for device in self.devices:
            if device.speed_channels or device.color_channels:
                device.status()

    def fans(self) -> List[LiquidFan]:
        return [LiquidFan(d, c) for d in self.devices for c in d.speed_channels]

    def liquid_temp(self) -> Optional[float]:
        for device in self.devices:
            for name, (value, unit) in device.status_cache.items():
                if "liquid" in name.lower() and "temp" in name.lower() \
                        and isinstance(value, (int, float)):
                    return float(value)
        return None

    def close(self) -> None:
        for device in self.devices:
            device.close()
