"""Mouse, touchpad and keyboard. KWin owns the input devices, so the live change goes to KWin's
own D-Bus objects (org.kde.KWin /org/kde/KWin/InputDevice/eventN), and the saved copy goes where
KWin reads it at the next start (plasma.libinput_write, plasma.keyboard_write). Both are also
kept in ~/.config/spark/input.json for the Spark shell.

What KWin gives and this page doesn't set: per-device button mapping, calibration matrices,
tablet and touchscreen mapping. Game controllers are Spark Controller's."""

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from . import core, dbus, plasma

BUS = dbus.SESSION
KWIN = 'org.kde.KWin'
DEV_IFACE = 'org.kde.KWin.InputDevice'
MANAGER = ('org.kde.KWin', '/org/kde/KWin/InputDevice', 'org.kde.KWin.InputDeviceManager')

# (property on the KWin device, kcminputrc key, kind)
POINTER_PROPS = (('pointerAcceleration', 'PointerAcceleration', 'd'),
                 ('pointerAccelerationProfileFlat', 'PointerAccelerationProfileFlat', 'b'),
                 ('naturalScroll', 'NaturalScroll', 'b'), ('leftHanded', 'LeftHanded', 'b'))
TOUCHPAD_PROPS = POINTER_PROPS + (('tapToClick', 'TapToClick', 'b'),
                                  ('disableWhileTyping', 'DisableWhileTyping', 'b'))
SUPPORT = {'pointerAcceleration': 'supportsPointerAcceleration', 'naturalScroll': 'supportsNaturalScroll',
           'leftHanded': 'supportsLeftHanded', 'disableWhileTyping': 'supportsDisableWhileTyping',
           'tapToClick': None, 'pointerAccelerationProfileFlat': 'supportsPointerAcceleration'}


class Device:
    def __init__(self, sysname: str, props: Dict[str, Any]):
        self.sysname = sysname
        self.props = props
        self.name = str(props.get('name', sysname))
        self.touchpad = bool(props.get('touchpad'))
        self.vendor = int(props.get('vendor', 0))
        self.product = int(props.get('product', 0))

    @property
    def path(self) -> str:
        return f'/org/kde/KWin/InputDevice/{self.sysname}'

    def supports(self, prop: str) -> bool:
        key = SUPPORT.get(prop)
        return True if key is None else bool(self.props.get(key))

    def settings(self) -> List[Tuple[str, str, str]]:
        return [p for p in (TOUCHPAD_PROPS if self.touchpad else POINTER_PROPS)
                if self.supports(p[0])]


def _plain(v: Any) -> Any:
    if isinstance(v, dict) and 'data' in v and 'type' in v:
        return _plain(v['data'])
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    return v


def devices() -> List[Device]:
    """The real mice and touchpads KWin knows (keyboards, buttons and virtual devices left out)."""
    v = _plain(dbus.get(BUS, *MANAGER[:2], MANAGER[2], 'devicesSysNames'))
    found = []
    for sysname in sorted(v if isinstance(v, list) else [], key=lambda s: int(re.sub(r'\D', '', s) or 0)):
        ok, props, _ = dbus.call(BUS, KWIN, f'/org/kde/KWin/InputDevice/{sysname}',
                                 'org.freedesktop.DBus.Properties', 'GetAll', 's', DEV_IFACE)
        props = _plain(props) if ok else None
        if not isinstance(props, dict) or not props.get('pointer') or props.get('isVirtual'):
            continue
        found.append(Device(sysname, props))
    # one mouse can show as several event nodes; keep the first of each name
    seen, unique = set(), []
    for d in found:
        if d.name not in seen:
            seen.add(d.name)
            unique.append(d)
    return unique


def set_property(dev: Device, prop: str, kind: str, value: Any) -> bool:
    text = 'true' if value is True else 'false' if value is False else repr(float(value)) \
        if kind == 'd' else str(value)
    ok, _err = dbus.set_(BUS, KWIN, dev.path, DEV_IFACE, prop, kind, text)
    if ok:
        dev.props[prop] = value
    return ok


def save(dev: Device) -> bool:
    """Write the device's current settings where KWin reads them at start, and for Spark."""
    values: Dict[str, str] = {}
    mine: Dict[str, Any] = {}
    for prop, key, kind in dev.settings():
        v = dev.props.get(prop)
        if v is None:
            continue
        mine[prop] = v
        values[key] = ('true' if v else 'false') if kind == 'b' else f"{float(v):.3f}"
    saved = core.spark_load('input').get('devices', {})
    saved[f'{dev.vendor}:{dev.product}:{dev.name}'] = mine
    core.spark_save('input', devices=saved)
    return plasma.libinput_write(dev.vendor, dev.product, dev.name, values)


# ── keyboard ──
XKB_LISTS = ('/usr/share/X11/xkb/rules/evdev.lst', '/usr/share/X11/xkb/rules/base.lst')
REPEAT_DELAYS = (150, 250, 400, 600, 800)           # ms before a held key repeats
REPEAT_RATES = (10, 15, 25, 35, 50)                 # repeats a second


def layouts_available() -> List[Tuple[str, str]]:
    """(name, code) from the XKB rules, e.g. ("French (Canada)", "ca")."""
    path = os.environ.get('SPARK_SETTINGS_XKB_LIST') or next((p for p in XKB_LISTS if os.path.exists(p)), '')
    found, inside = [], False
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            for line in f:
                if line.startswith('!'):
                    inside = line.strip() == '! layout'
                    continue
                m = re.match(r'^\s+(\S+)\s+(.+?)\s*$', line)
                if inside and m:
                    found.append((m.group(2), m.group(1)))
    except OSError:
        pass
    return sorted(found)


def keyboard_get() -> Dict[str, Any]:
    saved = core.spark_load('input').get('keyboard', {})
    layouts = (saved.get('layouts') or core.kread('kxkbrc', 'Layout', 'LayoutList', 'us')).split(',')
    variants = (saved.get('variants') if 'variants' in saved else
                core.kread('kxkbrc', 'Layout', 'VariantList', '')).split(',')
    variants += [''] * (len(layouts) - len(variants))
    delay = saved.get('delay') or int(core.kread('kcminputrc', 'Keyboard', 'RepeatDelay', '600') or 600)
    rate = saved.get('rate') or int(core.kread('kcminputrc', 'Keyboard', 'RepeatRate', '25') or 25)
    return {'layouts': [l for l in layouts if l] or ['us'], 'variants': variants,
            'delay': int(delay), 'rate': int(rate)}


def keyboard_set(layouts: List[str], variants: Optional[List[str]], delay: int, rate: int) -> bool:
    variants = (variants or []) + [''] * (len(layouts) - len(variants or []))
    core.spark_save('input', keyboard={'layouts': ','.join(layouts), 'variants': ','.join(variants[:len(layouts)]),
                                       'delay': delay, 'rate': rate})
    return plasma.keyboard_write(','.join(layouts), ','.join(variants[:len(layouts)]), delay, rate)
