"""Focusrite Scarlett (and Clarett) interfaces, through the kernel's scarlett2 ALSA controls.

The kernel driver (snd-usb-audio, mixer_scarlett2.c) exposes the interface's own settings as
ALSA mixer controls: "Line In 1 Level Capture Enum", "Direct Monitor Playback Switch",
"Mix A Input 01 Playback Volume", "Analogue Output 01 Playback Enum" and so on. This module
reads them with `amixer contents`, sorts them into the groups the page shows, and writes one
with `amixer cset`.

Not tried on a real Scarlett: the names come from the driver's source and the tests use a fake
amixer. Controls this module does not recognize are listed under "Other" rather than hidden."""

import os
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .core import log, run

Runner = Callable[[Sequence[str]], Tuple[int, str]]

SCARLETT_NAME = re.compile(
    r"^(Line In \d|Direct Monitor|Mix [A-Z] Input \d|Analogue Output \d|PCM \d+ Capture|"
    r"Mixer Input \d|Master \d|Level Meter|Sync Status|Clock Source|Phantom Power|"
    r"Speaker Switching|Talkback|Standalone|Input Select|Headphone \d)", re.I)


@dataclass
class Control:
    numid: int
    name: str
    kind: str                       # BOOLEAN, INTEGER, ENUMERATED, other
    count: int = 1
    values: List[str] = field(default_factory=list)
    items: List[str] = field(default_factory=list)
    lo: int = 0
    hi: int = 1
    db_lo: Optional[float] = None
    db_hi: Optional[float] = None
    writable: bool = True

    @property
    def on(self) -> bool:
        return bool(self.values) and self.values[0].lower() in ('on', 'true', '1')

    @property
    def value(self) -> int:
        try:
            return int(self.values[0])
        except (ValueError, IndexError):
            return 0


def default_runner(argv: Sequence[str]) -> Tuple[int, str]:
    r = run(argv, timeout=5)
    return r.returncode, r.stdout if r.returncode == 0 else r.stderr


def parse_contents(text: str) -> List[Control]:
    """`amixer -c N contents` into controls."""
    controls: List[Control] = []
    cur: Optional[Control] = None
    for line in text.splitlines():
        head = re.match(r"numid=(\d+),iface=\w+,name='(.*)'", line)
        if head:
            cur = Control(int(head.group(1)), head.group(2), 'other')
            controls.append(cur)
            continue
        if cur is None:
            continue
        s = line.strip()
        if s.startswith('; type='):
            fields = dict(p.split('=', 1) for p in s[2:].split(',') if '=' in p)
            cur.kind = fields.get('type', 'other')
            cur.count = int(fields.get('values', '1') or 1)
            cur.writable = fields.get('access', 'rw------')[1:2] == 'w'
            if 'min' in fields:
                cur.lo, cur.hi = int(fields['min']), int(fields.get('max', fields['min']))
        elif s.startswith("; Item #"):
            m = re.match(r"; Item #\d+ '(.*)'", s)
            if m:
                cur.items.append(m.group(1))
        elif s.startswith(': values='):
            cur.values = s[len(': values='):].split(',')
        elif s.startswith('| dBminmax'):
            m = re.search(r'min=(-?[\d.]+)dB,max=(-?[\d.]+)dB', s)
            if m:
                cur.db_lo, cur.db_hi = float(m.group(1)), float(m.group(2))
    return controls


@dataclass
class Page:
    """The controls sorted into what the page shows."""
    inputs: Dict[int, List[Control]] = field(default_factory=dict)        # input number -> controls
    phantom: List[Control] = field(default_factory=list)
    monitor: List[Control] = field(default_factory=list)                  # direct monitor, headphones, master
    outputs: List[Control] = field(default_factory=list)                  # output volumes and switches
    mix: Dict[str, Dict[int, Control]] = field(default_factory=dict)      # "A" -> input number -> volume
    routing: List[Control] = field(default_factory=list)
    status: List[Control] = field(default_factory=list)
    other: List[Control] = field(default_factory=list)


def classify(controls: Sequence[Control]) -> Page:
    page = Page()
    for c in controls:
        n = c.name
        m = re.match(r'^Line In (\d+)(?:-(\d+))? ', n)
        mix = re.match(r'^Mix ([A-Z]) Input (\d+) Playback Volume$', n)
        if mix:
            page.mix.setdefault(mix.group(1), {})[int(mix.group(2))] = c
        elif 'Phantom' in n or '48V' in n:
            page.phantom.append(c)
        elif m:
            page.inputs.setdefault(int(m.group(1)), []).append(c)
        elif re.search(r'(Playback|Capture) Enum$', n) and re.match(
                r'^(Analogue|Analog|S/PDIF|ADAT|PCM|Mixer|Output|Headphone)\b', n):
            page.routing.append(c)
        elif n.startswith('Direct Monitor') or n.startswith('Talkback') or 'Speaker Switching' in n:
            page.monitor.append(c)
        elif re.match(r'^(Master|Headphone|Line Out)\b', n) or n.endswith('Playback Volume') \
                or n.endswith('Playback Switch'):
            page.outputs.append(c)
        elif n in ('Sync Status', 'Clock Source', 'Sample Clock Source', 'Level Meter') \
                or not c.writable:
            page.status.append(c)
        else:
            page.other.append(c)
    return page


def card_list(proc_cards: Optional[str] = None) -> List[Tuple[int, str]]:
    """(card number, name) from /proc/asound/cards."""
    if proc_cards is None:
        try:
            with open('/proc/asound/cards', encoding='utf-8', errors='replace') as f:
                proc_cards = f.read()
        except OSError:
            return []
    return [(int(m.group(1)), m.group(2).strip())
            for m in re.finditer(r'^\s*(\d+)\s+\[.*?\]:\s*(.*)$', proc_cards, re.M)]


class Interface:
    """One Scarlett card: read its controls, change one."""

    def __init__(self, card: int, name: str, runner: Runner = default_runner):
        self.card, self.name, self.runner = card, name, runner

    def read(self) -> List[Control]:
        code, out = self.runner(['amixer', '-c', str(self.card), 'contents'])
        return parse_contents(out) if code == 0 else []

    def set(self, control: Control, value) -> bool:
        if isinstance(value, bool):
            value = 'on' if value else 'off'
        code, out = self.runner(['amixer', '-c', str(self.card), 'cset', f'numid={control.numid}',
                                 str(value)])
        if code != 0:
            log.warning("amixer cset numid=%s %s: %s", control.numid, value, out.strip())
        return code == 0


def find_interfaces(runner: Runner = default_runner,
                    proc_cards: Optional[str] = None) -> List[Interface]:
    """Cards whose controls look like a Scarlett's: at least two names from the scarlett2
    driver (a card that only has "Master Playback Volume" is not one)."""
    found = []
    for number, name in card_list(proc_cards):
        code, out = runner(['amixer', '-c', str(number), 'controls'])
        if code != 0:
            continue
        hits = sum(1 for m in re.finditer(r"name='(.*)'", out) if SCARLETT_NAME.match(m.group(1)))
        if hits >= 2:
            found.append(Interface(number, name, runner))
    return found


def fake_runner(folder: str, card: int = 1) -> Runner:
    """Answers amixer for one card from <folder>/amixer-contents.txt; cset edits a copy in
    memory. Other card numbers have no controls."""
    path = os.path.join(folder, 'amixer-contents.txt')
    state: Dict[str, str] = {}

    def text() -> str:
        with open(path, encoding='utf-8') as f:
            body = f.read()
        controls = parse_contents(body)
        lines = body.splitlines()
        out, cur = [], None
        for line in lines:
            head = re.match(r"numid=(\d+),", line)
            if head:
                cur = head.group(1)
            if line.strip().startswith(': values=') and cur in state:
                line = '  : values=' + state[cur]
            out.append(line)
        del controls
        return '\n'.join(out) + '\n'

    def runner(argv: Sequence[str]) -> Tuple[int, str]:
        if argv[:2] != ['amixer', '-c']:
            return 1, 'not amixer'
        if argv[2] != str(card):
            return 1, 'no such card'
        if argv[3] == 'controls':
            return 0, '\n'.join(l for l in text().splitlines() if l.startswith('numid='))
        if argv[3] == 'contents':
            return 0, text()
        if argv[3] == 'cset':
            numid = argv[4].split('=', 1)[1]
            state[numid] = argv[5]
            return 0, ''
        return 1, 'unknown'

    runner.state = state          # type: ignore[attr-defined]
    return runner
