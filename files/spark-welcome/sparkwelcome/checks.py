"""Check this PC: graphics, sound, printers and scanners, network and Bluetooth, updates.

Read-only: each check runs a few programs, reads their output and says, in plain words, what
works and what to do about what doesn't. No window code, so the Spark Portal can reuse it."""

import datetime
import glob
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .core import run
from .strings import t

OK, WARN = 'ok', 'warn'

TEST_SOUNDS = ('/usr/share/sounds/freedesktop/stereo/audio-test-signal.oga',
               '/usr/share/sounds/freedesktop/stereo/complete.oga',
               '/usr/share/sounds/freedesktop/stereo/bell.oga')

VENDORS = {'0x1002': 'AMD', '0x10de': 'NVIDIA', '0x8086': 'Intel', '0x1af4': 'virtual',
           '0x15ad': 'VMware', '0x1234': 'virtual', '0x80ee': 'VirtualBox'}


@dataclass
class Check:
    key: str                   # graphics, sound, printers, network, updates
    title: str
    status: str                # OK (green) or WARN (amber)
    summary: str               # one line
    detail: str = ''           # what it means, what to do
    fixes: List[Tuple[str, str]] = field(default_factory=list)   # (button label, action key)


# ─── Parsers (pure, tested) ───────────────────────────────────

def parse_vulkan_summary(text: str) -> List[Dict[str, str]]:
    """GPUs from `vulkaninfo --summary`: one dict per GPU with deviceName, deviceType,
    driverName and friends."""
    gpus: List[Dict[str, str]] = []
    current: Optional[Dict[str, str]] = None
    for line in text.splitlines():
        if re.match(r'^\s*GPU\d+:\s*$', line):
            current = {}
            gpus.append(current)
            continue
        match = re.match(r'^\s*(\w+)\s*=\s*(.*?)\s*$', line)
        if current is not None and match:
            current[match.group(1)] = match.group(2)
    return [g for g in gpus if g.get('deviceName')]


def drm_cards(root: str = '/sys/class/drm') -> List[Tuple[str, str, str]]:
    """(card, vendor, kernel driver) for each graphics card the kernel sees."""
    cards = []
    for path in sorted(glob.glob(os.path.join(root, 'card[0-9]*'))):
        name = os.path.basename(path)
        if '-' in name:                                   # card0-HDMI-A-1: a connector
            continue
        vendor = ''
        try:
            with open(os.path.join(path, 'device', 'vendor'), encoding='ascii') as f:
                vendor = f.read().strip()
        except OSError:
            pass
        try:
            driver = os.path.basename(os.readlink(os.path.join(path, 'device', 'driver')))
        except OSError:
            driver = ''
        cards.append((name, VENDORS.get(vendor, vendor or '?'), driver))
    return cards


def parse_wpctl_sinks(text: str) -> List[str]:
    """Audio outputs ('sinks') from `wpctl status`, default first."""
    sinks: List[Tuple[bool, str]] = []
    section, sub = '', ''
    for raw in text.splitlines():
        line = raw.replace('│', ' ').replace('├─', ' ').replace('└─', ' ').rstrip()
        if not line.strip():
            continue
        if not raw.startswith((' ', '│', '├', '└')):
            section, sub = line.strip(), ''          # Audio, Video, Settings
            continue
        stripped = line.strip()
        if stripped.endswith(':') and not re.match(r'^\*?\s*\d+\.', stripped):
            sub = stripped[:-1]
            continue
        if section == 'Audio' and sub == 'Sinks':
            match = re.match(r'^(\*)?\s*\d+\.\s+(.+?)(\s+\[[^\]]*\])?$', stripped)
            if match:
                sinks.append((bool(match.group(1)), match.group(2).strip()))
    sinks.sort(key=lambda s: not s[0])
    return [name for _default, name in sinks]


def parse_lpstat(text: str) -> List[str]:
    """Printer names from `lpstat -e` (one per line)."""
    return [line.strip() for line in text.splitlines()
            if line.strip() and ' ' not in line.strip()]


def parse_scanimage(text: str) -> List[str]:
    """Scanner descriptions from `scanimage -L`."""
    found = []
    for line in text.splitlines():
        match = re.match(r"^device [`'](.+?)' is an? (.+)$", line.strip())
        if match:
            found.append(match.group(2).strip())
    return found


def parse_nmcli_devices(text: str) -> List[Tuple[str, str, str]]:
    """(type, state, connection) from `nmcli -t -f TYPE,STATE,CONNECTION device`."""
    out = []
    for line in text.splitlines():
        parts = re.split(r'(?<!\\):', line.strip())
        if len(parts) >= 3 and parts[0] in ('ethernet', 'wifi'):
            out.append((parts[0], parts[1], parts[2].replace('\\:', ':')))
    return out


def parse_rpm_ostree(text: str) -> Optional[Dict[str, object]]:
    """The booted image from `rpm-ostree status --json`: when it was built, its name, and
    whether a newer one is staged for the next restart."""
    try:
        data = json.loads(text)
    except ValueError:
        return None
    deployments = data.get('deployments') if isinstance(data, dict) else None
    if not isinstance(deployments, list):
        return None
    booted = next((d for d in deployments if isinstance(d, dict) and d.get('booted')), None)
    if booted is None:
        return None
    image = str(booted.get('container-image-reference') or booted.get('origin') or '')
    image = re.sub(r'^ostree-[\w-]+:(docker://)?', '', image)
    return {
        'timestamp': booted.get('timestamp'),
        'version': booted.get('version') or '',
        'image': image,
        'staged': any(isinstance(d, dict) and d.get('staged') for d in deployments),
    }


# ─── The checks ───────────────────────────────────────────────

def check_graphics() -> Check:
    cards = [c for c in drm_cards() if c[2]]
    gpus = []
    vulkan_ran = False
    if shutil.which('vulkaninfo'):
        code, out, _err = run(['vulkaninfo', '--summary'], timeout=20)
        vulkan_ran = code == 0
        gpus = parse_vulkan_summary(out) if code == 0 else []
    real = [g for g in gpus if 'CPU' not in g.get('deviceType', '').upper()]
    title = t('check.graphics')
    if real:
        gpu = real[0]
        driver = gpu.get('driverName') or gpu.get('driverInfo') or '?'
        return Check('graphics', title, OK, t('check.graphics.ok', gpu=gpu['deviceName'],
                                                driver=driver),
                     t('check.graphics.ok.detail'))
    if cards:
        names = ', '.join(f"{vendor} ({driver})" for _card, vendor, driver in cards)
        if not shutil.which('vulkaninfo'):
            return Check('graphics', title, WARN, t('check.graphics.novk', cards=names),
                         t('check.graphics.novk.detail'))
        return Check('graphics', title, WARN, t('check.graphics.vkfail', cards=names),
                     t('check.graphics.vkfail.detail' if vulkan_ran else
                       'check.graphics.vkerror.detail'))
    return Check('graphics', title, WARN, t('check.graphics.none'),
                 t('check.graphics.none.detail'))


def check_sound() -> Check:
    title = t('check.sound')
    fixes = [(t('fix.sound_settings'), 'sound_settings')]
    if not shutil.which('wpctl'):
        return Check('sound', title, WARN, t('check.sound.nowpctl'), '', fixes)
    code, out, err = run(['wpctl', 'status'], timeout=10)
    if code != 0:
        return Check('sound', title, WARN, t('check.sound.error'), err.strip(), fixes)
    sinks = [s for s in parse_wpctl_sinks(out) if 'dummy output' not in s.lower()]
    if sinks:
        return Check('sound', title, OK, t('check.sound.ok', device=sinks[0]),
                     t('check.sound.ok.detail', count=len(sinks)),
                     [(t('fix.test_sound'), 'test_sound')] + fixes)
    return Check('sound', title, WARN, t('check.sound.none'), t('check.sound.none.detail'), fixes)


def check_printers() -> Check:
    title = t('check.printers')
    fixes = [(t('fix.add_printer'), 'add_printer')]
    printers: List[str] = []
    if shutil.which('lpstat'):
        code, out, _err = run(['lpstat', '-e'], timeout=15)
        printers = parse_lpstat(out) if code == 0 else []
    scanners: List[str] = []
    scan_note = t('check.scanners.missing')
    if shutil.which('scanimage'):
        code, out, _err = run(['scanimage', '-L'], timeout=30)
        scanners = parse_scanimage(out)
        scan_note = (t('check.scanners.found', names=', '.join(scanners)) if scanners
                     else t('check.scanners.none'))
    if printers:
        return Check('printers', title, OK, t('check.printers.ok', names=', '.join(printers)),
                     scan_note, fixes)
    return Check('printers', title, WARN, t('check.printers.none'),
                 t('check.printers.none.detail') + ' ' + scan_note, fixes)


def check_network() -> Check:
    title = t('check.network')
    fixes = [(t('fix.network_settings'), 'network_settings')]
    connected: List[Tuple[str, str]] = []
    checked = False
    if shutil.which('nmcli'):
        code, out, _err = run(['nmcli', '-t', '-f', 'TYPE,STATE,CONNECTION', 'device'],
                              timeout=10)
        if code == 0:
            checked = True
            connected = [(kind, conn) for kind, state, conn in parse_nmcli_devices(out)
                         if state.startswith('connected')]
    bluetooth = bluetooth_state()
    bt_text = {'on': t('check.bt.on'), 'off': t('check.bt.off'),
               'none': t('check.bt.none')}[bluetooth]
    if bluetooth != 'none':
        fixes.append((t('fix.bluetooth_settings'), 'bluetooth_settings'))
    if connected:
        kind, conn = connected[0]
        how = t('check.network.wifi') if kind == 'wifi' else t('check.network.wired')
        return Check('network', title, OK, t('check.network.ok', how=how, name=conn),
                     bt_text, fixes)
    if not checked:
        return Check('network', title, WARN, t('check.network.nonmcli'), bt_text, fixes)
    return Check('network', title, WARN, t('check.network.none'),
                 t('check.network.none.detail') + ' ' + bt_text, fixes)


def bluetooth_state() -> str:
    """'on', 'off' or 'none' (no Bluetooth adapter)."""
    adapters = glob.glob('/sys/class/bluetooth/hci*')
    if not adapters:
        return 'none'
    if shutil.which('bluetoothctl'):
        code, out, _err = run(['bluetoothctl', 'show'], timeout=5)
        if code == 0 and re.search(r'Powered:\s*yes', out):
            return 'on'
        if code == 0 and re.search(r'Powered:\s*no', out):
            return 'off'
    try:
        for path in glob.glob('/sys/class/rfkill/rfkill*'):
            with open(os.path.join(path, 'type'), encoding='ascii') as f:
                if f.read().strip() != 'bluetooth':
                    continue
            with open(os.path.join(path, 'soft'), encoding='ascii') as f:
                return 'off' if f.read().strip() == '1' else 'on'
    except OSError:
        pass
    return 'on'


def check_updates() -> Check:
    title = t('check.updates')
    if not shutil.which('rpm-ostree'):
        return Check('updates', title, WARN, t('check.updates.noostree'),
                     t('check.updates.noostree.detail'))
    code, out, err = run(['rpm-ostree', 'status', '--json'], timeout=20)
    info = parse_rpm_ostree(out) if code == 0 else None
    if not info:
        return Check('updates', title, WARN, t('check.updates.error'), err.strip())
    when = '?'
    if isinstance(info['timestamp'], (int, float)):
        when = datetime.datetime.fromtimestamp(info['timestamp']).strftime('%Y-%m-%d')
    detail = t('check.updates.auto')
    if info['staged']:
        detail = t('check.updates.staged') + ' ' + detail
    return Check('updates', title, OK, t('check.updates.ok', date=when,
                                         image=info['image'] or info['version'] or 'SparkOS'),
                 detail)


CHECKS: Tuple[Callable[[], Check], ...] = (check_graphics, check_sound, check_printers,
                                           check_network, check_updates)


def run_all() -> List[Check]:
    out = []
    for fn in CHECKS:
        try:
            out.append(fn())
        except Exception as exc:          # noqa: BLE001 - one broken check mustn't hide the rest
            out.append(Check(fn.__name__[6:], fn.__name__[6:].title(), WARN,
                             t('check.crashed'), str(exc)))
    return out


# ─── Fix buttons ──────────────────────────────────────────────

def test_sound_cmd() -> Optional[List[str]]:
    sound = next((s for s in TEST_SOUNDS if os.path.isfile(s)), None)
    if sound is None:
        return None
    for player in ('pw-play', 'paplay', 'canberra-gtk-play'):
        if shutil.which(player):
            return [player, '-f', sound] if player == 'canberra-gtk-play' else [player, sound]
    return None


SETTINGS_PAGES = {
    'sound_settings': 'sound',
    'add_printer': 'printers',
    'network_settings': 'network',
    'bluetooth_settings': 'bluetooth',
}
