"""Displays through kscreen-doctor: read the outputs (-j), build the commands for each change,
and the commands that put an output back as it was (the 15 second revert)."""

import json
from typing import Any, Dict, List, Optional

from .core import run

ROTATIONS = {1: 'normal', 2: 'left', 4: 'inverted', 8: 'right'}
VRR = {0: 'never', 1: 'always', 2: 'automatic'}
SCALES = [1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]


class Mode:
    def __init__(self, d: Dict[str, Any]):
        self.id = str(d.get('id', ''))
        size = d.get('size') or {}
        self.w, self.h = int(size.get('width', 0)), int(size.get('height', 0))
        self.hz = float(d.get('refreshRate', 0) or 0)

    @property
    def res(self) -> str:
        return f"{self.w}x{self.h}"

    @property
    def rate(self) -> str:
        return f"{self.hz:.2f}".rstrip('0').rstrip('.') if abs(self.hz - round(self.hz)) > 0.05 \
            else str(round(self.hz))


class Output:
    def __init__(self, d: Dict[str, Any]):
        self.name = str(d.get('name', ''))
        self.enabled = bool(d.get('enabled', False))
        self.connected = bool(d.get('connected', True))
        pos = d.get('pos') or {}
        self.x, self.y = int(pos.get('x', 0)), int(pos.get('y', 0))
        self.scale = float(d.get('scale', 1.0) or 1.0)
        self.rotation = ROTATIONS.get(int(d.get('rotation', 1) or 1), 'normal')
        self.vrr: Optional[str] = VRR.get(int(d['vrrPolicy'])) if 'vrrPolicy' in d else None
        self.hdr: Optional[bool] = bool(d['hdr']) if 'hdr' in d else None
        self.priority = int(d.get('priority', 0) or 0)
        self.modes = [Mode(m) for m in d.get('modes', [])]
        self.mode_id = str(d.get('currentModeId', ''))
        self.model = str(d.get('model') or d.get('name') or '')
        self.vendor = str(d.get('vendor') or '')

    @property
    def mode(self) -> Optional[Mode]:
        for m in self.modes:
            if m.id == self.mode_id:
                return m
        return self.modes[0] if self.modes else None

    @property
    def label(self) -> str:
        label = ' '.join(x for x in (self.vendor, self.model) if x and x != self.name)
        return f"{self.name}: {label}" if label else self.name

    @property
    def logical_size(self):
        """Size on the desktop: the mode over the scale, swapped when turned sideways."""
        m = self.mode
        w, h = (m.w, m.h) if m else (1920, 1080)
        if self.rotation in ('left', 'right'):
            w, h = h, w
        return round(w / self.scale), round(h / self.scale)

    def resolutions(self) -> List[str]:
        seen: List[str] = []
        for m in sorted(self.modes, key=lambda m: (-m.w, -m.h)):
            if m.res not in seen:
                seen.append(m.res)
        return seen

    def rates(self, res: str) -> List[Mode]:
        return sorted((m for m in self.modes if m.res == res), key=lambda m: -m.hz)


def parse(text: str) -> List[Output]:
    try:
        data = json.loads(text)
    except ValueError:
        return []
    outs = [Output(o) for o in data.get('outputs', []) if isinstance(o, dict)]
    return [o for o in outs if o.connected]


def load() -> List[Output]:
    rc, text, _ = run(['kscreen-doctor', '-j'], timeout=10)
    return parse(text) if rc == 0 else []


# ── what each change runs ──
def a_mode(o: Output, mode_id: str) -> str:
    return f"output.{o.name}.mode.{mode_id}"


def a_scale(o: Output, scale: float) -> str:
    return f"output.{o.name}.scale.{scale:g}"


def a_rotation(o: Output, rotation: str) -> str:
    return f"output.{o.name}.rotation.{rotation}"


def a_vrr(o: Output, policy: str) -> str:
    return f"output.{o.name}.vrrpolicy.{policy}"


def a_hdr(o: Output, on: bool) -> str:
    return f"output.{o.name}.hdr.{'enable' if on else 'disable'}"


def a_primary(o: Output) -> str:
    return f"output.{o.name}.priority.1"


def a_position(o: Output, x: int, y: int) -> str:
    return f"output.{o.name}.position.{x},{y}"


def a_enable(o: Output, on: bool) -> str:
    return f"output.{o.name}.{'enable' if on else 'disable'}"


def restore_args(old: List[Output], names: List[str]) -> List[str]:
    """Everything that puts the named outputs back as they were in `old`."""
    args: List[str] = []
    for o in old:
        if o.name not in names:
            continue
        if not o.enabled:
            args.append(a_enable(o, False))
            continue
        args.append(a_enable(o, True))
        if o.mode_id:
            args.append(a_mode(o, o.mode_id))
        args += [a_scale(o, o.scale), a_rotation(o, o.rotation), a_position(o, o.x, o.y)]
        if o.vrr:
            args.append(a_vrr(o, o.vrr))
        if o.hdr is not None:
            args.append(a_hdr(o, o.hdr))
        if o.priority == 1:
            args.append(a_primary(o))
    return args


def apply(args: List[str]) -> bool:
    return bool(args) and run(['kscreen-doctor', *args], timeout=15)[0] == 0


def snap(moving: Output, x: int, y: int, others: List[Output], limit: int = 120):
    """Put a dragged output against its neighbours: edges meet, tops or lefts line up."""
    w, h = moving.logical_size
    for _ in (0, 1):
        best_x, best_y = None, None
        for o in others:
            ow, oh = o.logical_size
            for cx in (o.x + ow, o.x - w, o.x, o.x + ow - w):
                if abs(cx - x) <= limit and (best_x is None or abs(cx - x) < abs(best_x - x)):
                    best_x = cx
            for cy in (o.y + oh, o.y - h, o.y, o.y + oh - h):
                if abs(cy - y) <= limit and (best_y is None or abs(cy - y) < abs(best_y - y)):
                    best_y = cy
        x = best_x if best_x is not None else x
        y = best_y if best_y is not None else y
    return max(0, x), max(0, y)


# ── Spark compositor session: wlr-randr, no kscreen ──
# The same Output objects and the same "output.NAME.KEY.VALUE" change strings, so the page and
# the 15 second revert work unchanged. Each apply also writes the compositor's outputs.conf, so
# the layout is what the compositor sets up at the next login.
import os  # noqa: E402

WL_ROT = {'normal': 'normal', '90': 'left', '180': 'inverted', '270': 'right'}
WL_TRANSFORM = {v: k for k, v in WL_ROT.items()}


def on_sparkwl() -> bool:
    return 'sparkwl' in os.environ.get('XDG_CURRENT_DESKTOP', '').lower().split(':')


def _wl_mode_id(m: Dict[str, Any]) -> str:
    return f"{m['width']}x{m['height']}@{float(m['refresh']):.3f}"


def parse_wlr(text: str) -> List[Output]:
    try:
        data = json.loads(text)
    except ValueError:
        return []
    outs = []
    for d in data if isinstance(data, list) else []:
        modes, current, seen = [], '', set()
        for m in d.get('modes', []):
            mid = _wl_mode_id(m)
            if m.get('current'):
                current = mid
            if mid in seen:
                continue
            seen.add(mid)
            modes.append({'id': mid, 'size': {'width': m['width'], 'height': m['height']},
                          'refreshRate': m['refresh']})
        pos = d.get('position') or {}
        o = Output({'name': d.get('name', ''), 'enabled': d.get('enabled', False),
                    'pos': pos, 'scale': d.get('scale', 1.0), 'modes': modes,
                    'currentModeId': current, 'model': d.get('model', ''),
                    'vendor': d.get('make', ''),
                    'vrrPolicy': 1 if d.get('adaptive_sync') else 0})
        o.rotation = WL_ROT.get(str(d.get('transform', 'normal')), 'normal')
        outs.append(o)
    return outs


def _wl_args(args: List[str]) -> List[List[str]]:
    """kscreen-style change strings to one wlr-randr argument list per output."""
    per: Dict[str, List[str]] = {}
    for a in args:
        parts = a.split('.', 3)
        if len(parts) < 3 or parts[0] != 'output':
            continue
        name, key = parts[1], parts[2]
        val = a.split('.', 3)[3] if len(parts) == 4 else ''
        if key in ('mode', 'scale', 'rotation', 'position', 'vrrpolicy'):
            # values may hold dots (1.25, 59.940): take everything after "output.NAME.KEY."
            val = a[len(f"output.{name}.{key}."):]
        flags = per.setdefault(name, ['--output', name])
        if key == 'enable':
            flags.append('--on')
        elif key == 'disable':
            flags.append('--off')
        elif key == 'mode':
            flags += ['--mode', val.replace('@', '@') + 'Hz' if '@' in val else val]
        elif key == 'scale':
            flags += ['--scale', val]
        elif key == 'rotation':
            flags += ['--transform', WL_TRANSFORM.get(val, 'normal')]
        elif key == 'position':
            flags += ['--pos', val]
        elif key == 'vrrpolicy':
            flags += ['--adaptive-sync', 'disabled' if val == 'never' else 'enabled']
        # priority (primary) and hdr: the compositor has neither yet
    return [f for f in per.values() if len(f) > 2]


def _conf_path() -> str:
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    return os.path.join(base, 'spark', 'compositor', 'outputs.conf')


# Keys this page does not edit (HDR) are carried over from the existing file.
_KEEP_KEYS = ('hdr', 'sdr_white')


def _kept_keys() -> dict:
    kept = {}
    try:
        with open(_conf_path(), encoding='utf-8') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == 'output':
                    extra = [kv for kv in parts[2:] if kv.split('=', 1)[0] in _KEEP_KEYS]
                    if extra:
                        kept[parts[1]] = ' ' + ' '.join(extra)
    except OSError:
        pass
    return kept


def save_conf(outs: List[Output]) -> None:
    kept = _kept_keys()
    lines = ['# Written by Spark Settings > Displays. Read by spark-compositor at login.']
    for o in outs:
        if not o.enabled:
            lines.append(f"output {o.name} enabled=off")
            continue
        m = o.mode
        mode = f" mode={m.w}x{m.h}@{m.hz:.3f}" if m else ''
        rot = WL_TRANSFORM.get(o.rotation, 'normal')
        lines.append(f"output {o.name}{mode} scale={o.scale:g} transform={rot} "
                     f"pos={o.x},{o.y}" + (' vrr=on' if o.vrr == 'always' else '')
                     + kept.get(o.name, ''))
    path = _conf_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    os.replace(tmp, path)


_kscreen_load, _kscreen_apply = load, apply


def load() -> List[Output]:  # noqa: F811
    if not on_sparkwl():
        return _kscreen_load()
    rc, text, _ = run(['wlr-randr', '--json'], timeout=10)
    return parse_wlr(text) if rc == 0 else []


def apply(args: List[str]) -> bool:  # noqa: F811
    if not on_sparkwl():
        return _kscreen_apply(args)
    groups = _wl_args(args)
    if not groups:
        return False
    flat = [x for g in groups for x in g]
    ok = run(['wlr-randr', *flat], timeout=15)[0] == 0
    if ok:
        outs = load()
        if outs:
            save_conf(outs)
    return ok
