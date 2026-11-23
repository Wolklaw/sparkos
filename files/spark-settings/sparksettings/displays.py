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
