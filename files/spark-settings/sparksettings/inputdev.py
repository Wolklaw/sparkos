"""Mouse, touchpad and keyboard. The Spark compositor owns the input devices: settings are kept in
~/.config/spark/input.json and written to the keyboard/mouse/touchpad/cursor/idle lines of
~/.config/spark/compositor/compositor.conf, then a SIGHUP makes it read them again. The list of
devices comes from /proc/bus/input/devices.

Not set here: per-device button mapping, calibration matrices, tablet and touchscreen mapping.
Game controllers are Spark Controller's."""

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from . import core

POINTER_DEFAULTS = {'pointerAcceleration': 0.0, 'pointerAccelerationProfileFlat': False,
                    'naturalScroll': False, 'leftHanded': False, 'tapToClick': True,
                    'disableWhileTyping': True}

# (property, saved key, kind)
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

    def supports(self, prop: str) -> bool:
        key = SUPPORT.get(prop)
        return True if key is None else bool(self.props.get(key))

    def settings(self) -> List[Tuple[str, str, str]]:
        return [p for p in (TOUCHPAD_PROPS if self.touchpad else POINTER_PROPS)
                if self.supports(p[0])]


# ── /proc/bus/input/devices for the list, compositor.conf for the settings ──
def _proc_pointers() -> Tuple[List[str], List[str]]:
    """(mouse names, touchpad names) from the kernel's input device list."""
    mice, pads = [], []
    try:
        blocks = open('/proc/bus/input/devices', encoding='utf-8', errors='replace').read().split('\n\n')
    except OSError:
        return mice, pads
    for b in blocks:
        name = re.search(r'^N: Name="(.*)"$', b, re.M)
        handlers = re.search(r'^H: Handlers=(.*)$', b, re.M)
        if not name or not handlers or not re.search(r'\bmouse\d+', handlers.group(1)):
            continue
        prop = re.search(r'^B: PROP=(\w+)$', b, re.M)
        is_pad = bool(prop and int(prop.group(1).split()[-1], 16) & 1)     # INPUT_PROP_POINTER
        n = name.group(1)
        (pads if is_pad else mice).append(n)
    dedup = lambda xs: list(dict.fromkeys(xs))
    return dedup(mice), dedup(pads)


def _pointer_devices() -> List[Device]:
    """One entry for all mice and one for all touchpads: the compositor sets them by kind."""
    mice, pads = _proc_pointers()
    saved = core.spark_load('input')
    out = []
    for kind, names in (('mouse', mice), ('touchpad', pads)):
        if not names:
            continue
        props = dict(POINTER_DEFAULTS)
        props.update(saved.get(kind) or {})
        props.update(name=', '.join(names), touchpad=kind == 'touchpad', supportsPointerAcceleration=True,
                     supportsNaturalScroll=True, supportsLeftHanded=True, supportsDisableWhileTyping=True)
        out.append(Device(kind, props))
    return out


CONF_KEYS = (('pointerAcceleration', 'accel'), ('pointerAccelerationProfileFlat', 'profile'),
             ('naturalScroll', 'natural'), ('leftHanded', 'left_handed'),
             ('tapToClick', 'tap'), ('disableWhileTyping', 'dwt'))


def _conf_line(kind: str, values: Dict[str, Any]) -> str:
    parts = [kind]
    for prop, key in CONF_KEYS:
        if prop not in values or (kind == 'mouse' and key in ('tap', 'dwt')):
            continue
        v = values[prop]
        if key == 'accel':
            parts.append(f'accel={float(v):.3f}')
        elif key == 'profile':
            parts.append('profile=' + ('flat' if v else 'adaptive'))
        else:
            parts.append(f'{key}=' + ('on' if v else 'off'))
    return ' '.join(parts)


def _idle_line() -> str:
    """The Power page's timers, in seconds, for the compositor's idle timer (0 is never)."""
    from . import power
    t, lk = power.timers(), power.lock_get()
    lock = int(lk['minutes']) * 60 if lk.get('autolock') else 0
    return (f"idle lock={lock} screen_off={int(t['screen_off']) * 60} "
            f"suspend={int(t['sleep']) * 60}")


def _compositor_write() -> bool:
    """Rewrite only the input, cursor, idle and workspaces lines of compositor.conf, then tell the compositor."""
    saved = core.spark_load('input')
    lines = []
    for kind in ('mouse', 'touchpad'):
        if saved.get(kind):
            lines.append(_conf_line(kind, saved[kind]))
    ap = core.spark_load('appearance')
    if ap.get('cursor'):
        lines.append(f"cursor theme={ap['cursor']} size={int(ap.get('cursor_size') or 24)}")
    kb = saved.get('keyboard') or {}
    if kb:
        layouts = kb.get('layouts') or 'us'
        kl = f"keyboard layout={layouts} variant={kb.get('variants', '')}"
        if ',' in layouts:
            kl += ' options=grp:alt_shift_toggle'
        kl += f" repeat_rate={int(kb.get('rate') or 25)} repeat_delay={int(kb.get('delay') or 600)}"
        lines.append(kl)
    lines.append(_idle_line())
    if ap.get('workspaces') is not None:
        from . import taskbar
        lines.append(f"workspaces count={taskbar.clamp_workspaces(ap['workspaces'])}")
    path = os.path.join(core.xdg_config_home(), 'spark', 'compositor', 'compositor.conf')
    try:
        old = open(path, encoding='utf-8').read().splitlines()
    except OSError:
        old = []
    keep = [l for l in old if not re.match(r'\s*(keyboard|mouse|touchpad|cursor|idle|workspaces)\s', l)
            and l.strip() != '# input: written by Spark Settings']
    while keep and not keep[-1].strip():
        keep.pop()
    text = '\n'.join(keep + ([''] if keep else []) + ['# input: written by Spark Settings'] + lines) + '\n'
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + '.tmp', 'w', encoding='utf-8') as f:
            f.write(text)
        os.replace(path + '.tmp', path)
    except OSError:
        return False
    return _compositor_reload()


def compositor_cursor(theme: str, size: int) -> bool:
    """appearance.json already holds the theme; rewrite the compositor's lines from it."""
    return _compositor_write()


def _compositor_reload() -> bool:
    """SIGHUP the compositor, but only one that wrote its pid file: older builds die from SIGHUP."""
    import signal
    rt = os.environ.get('XDG_RUNTIME_DIR', '')
    try:
        pid = int(open(os.path.join(rt, 'spark-compositor.pid')).read().strip())
        comm = open(f'/proc/{pid}/comm').read().strip()
    except (OSError, ValueError):
        return True          # saved; it takes effect at the next login
    if comm != 'spark-composito' and comm != 'spark-compositor':
        return True
    try:
        os.kill(pid, signal.SIGHUP)
    except OSError:
        return False
    return True


def devices() -> List[Device]:
    """One mouse entry and one touchpad entry, when the kernel lists such a device."""
    return _pointer_devices()


def set_property(dev: Device, prop: str, kind: str, value: Any) -> bool:
    dev.props[prop] = value
    return True


def save(dev: Device) -> bool:
    """Keep the device's current settings in input.json and hand them to the compositor."""
    mine: Dict[str, Any] = {}
    for prop, _key, _kind in dev.settings():
        v = dev.props.get(prop)
        if v is not None:
            mine[prop] = v
    core.spark_save('input', **{dev.sysname: mine})
    return _compositor_write()


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
    saved = core.spark_load('input').get('keyboard', {})     # the compositor's default is US
    layouts = (saved.get('layouts') or 'us').split(',')
    variants = (saved.get('variants') or '').split(',')
    variants += [''] * (len(layouts) - len(variants))
    return {'layouts': [l for l in layouts if l] or ['us'], 'variants': variants,
            'delay': int(saved.get('delay') or 600), 'rate': int(saved.get('rate') or 25)}


def keyboard_set(layouts: List[str], variants: Optional[List[str]], delay: int, rate: int) -> bool:
    variants = (variants or []) + [''] * (len(layouts) - len(variants or []))
    core.spark_save('input', keyboard={'layouts': ','.join(layouts), 'variants': ','.join(variants[:len(layouts)]),
                                       'delay': delay, 'rate': rate})
    return _compositor_write()
