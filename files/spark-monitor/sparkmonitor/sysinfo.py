"""The System tab's data: what this PC is, in sections of label and value rows. No Tk here.

Most of it is read from /proc and /sys. A few things need a program, run once on a thread when
the tab opens (rpm-ostree, udevadm, vulkaninfo); see fetch(). Serial numbers are
kept in rows marked `secret` and left out of the screen and the copy unless asked for. The
machine ID, host name, user name and network addresses are never read."""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import core
from .host import Host
from .source import Source, listdir, read_bytes, read_int, read_line, read_text
from .system import SystemSampler, natural, disk_usage
from .text import t

PLACEHOLDERS = {'', 'unknown', 'default string', 'system product name', 'system version',
                'to be filled by o.e.m.', 'not specified', 'none', 'n/a', 'not applicable',
                'o.e.m.', 'type1productconfigid', 'base board serial number',
                '0', '00000000', '0000000000000000'}
IMAGE_PREFIX = re.compile(r'^ostree-(?:image-)?(?:signed|unverified-registry|unverified-image)?'
                          r':(?:docker://|registry:)?')


@dataclass
class Row:
    label: str
    value: str
    secret: bool = False
    full: str = ""                    # what the copy says when the screen shows a short form


@dataclass
class Section:
    key: str
    title: str
    rows: List[Row] = field(default_factory=list)


def real(value: Optional[str]) -> str:
    """A DMI or serial value, or '' for the placeholders firmware leaves in."""
    value = (value or '').strip()
    return '' if value.lower() in PLACEHOLDERS else value


# ─── Programs, run once on a thread ───────────────────────────

def fetch(host: Host, gpu_ids: Optional[List[Tuple[int, int]]] = None) -> Dict[str, Optional[str]]:
    """The output of the programs this tab uses. Slow ones, so call it off the window's thread."""
    out: Dict[str, Optional[str]] = {}
    out['ostree'] = host.run('rpm-ostree.json', ['rpm-ostree', 'status', '--json'], 20) \
        if host.have('rpm-ostree') else None
    out['udev'] = host.run('udev-dmi.txt', ['udevadm', 'info', '-p',
                                             '/devices/virtual/dmi/id'], 10) \
        if host.have('udevadm') else None
    out['vulkan'] = host.run('vulkaninfo.txt', ['vulkaninfo', '--summary'], 15) \
        if host.have('vulkaninfo') else None
    out['glx'] = None
    if not out['vulkan'] and host.have('glxinfo'):
        out['glx'] = host.run('glxinfo.txt', ['glxinfo', '-B'], 15)
    return out


# ─── Parsers for those outputs ────────────────────────────────

def parse_ostree(text: Optional[str]) -> Dict[str, str]:
    """The booted deployment of `rpm-ostree status --json`: version, image, digest, date,
    and the version waiting for a restart, if any."""
    try:
        deployments = json.loads(text or '')['deployments']
    except (ValueError, KeyError, TypeError):
        return {}
    booted = next((d for d in deployments if d.get('booted')), None)
    if booted is None:
        return {}
    info = {'version': str(booted.get('version') or ''),
            'image': IMAGE_PREFIX.sub('', str(booted.get('container-image-reference') or '')),
            'digest': str(booted.get('container-image-reference-digest') or ''),
            'timestamp': str(booted.get('base-timestamp') or booted.get('timestamp') or '')}
    staged = next((d for d in deployments if d.get('staged')), None)
    if staged is not None:
        info['staged'] = str(staged.get('version') or '?')
    return info


def parse_vulkan(text: Optional[str]) -> List[Dict[str, str]]:
    """The devices in `vulkaninfo --summary`: one dict of key = value per GPU."""
    devices: List[Dict[str, str]] = []
    current: Optional[Dict[str, str]] = None
    for line in (text or '').splitlines():
        if re.match(r'^GPU\d+:', line):
            current = {}
            devices.append(current)
        elif current is not None:
            match = re.match(r'^\s+(\w+)\s*=\s*(.*?)\s*$', line)
            if match:
                current[match.group(1)] = match.group(2)
    return devices


def vulkan_for(devices: List[Dict[str, str]], vendor: int, device: int) -> Optional[Dict[str, str]]:
    for d in devices:
        try:
            if int(d.get('vendorID', ''), 0) == vendor and int(d.get('deviceID', ''), 0) == device:
                return d
        except ValueError:
            continue
    return None


def parse_glx(text: Optional[str]) -> str:
    match = re.search(r'^OpenGL version string:\s*(.+)$', text or '', re.M)
    return match.group(1).strip() if match else ''


def parse_udev_memory(text: Optional[str]) -> List[Dict[str, str]]:
    """The memory modules udev read from the firmware's tables at boot (as root), which any
    user can read afterwards: MEMORY_DEVICE_<n>_<FIELD>=value. Empty slots are left out."""
    mods: Dict[int, Dict[str, str]] = {}
    for line in (text or '').splitlines():
        match = re.match(r'^E: MEMORY_DEVICE_(\d+)_([A-Z_]+)=(.*)$', line)
        if match:
            mods.setdefault(int(match.group(1)), {})[match.group(2)] = match.group(3).strip()
    out = []
    for n in sorted(mods):
        mod = mods[n]
        if mod.get('PRESENT') == '0':
            continue
        try:
            if int(mod.get('SIZE', '0') or 0) <= 0:
                continue
        except ValueError:
            continue
        out.append(mod)
    return out


# ─── EDID ─────────────────────────────────────────────────────

def parse_edid(data: Optional[bytes]) -> Dict[str, str]:
    """Model name, serial text and size in cm from a monitor's EDID block."""
    if not data or len(data) < 128 or data[:8] != b'\x00\xff\xff\xff\xff\xff\xff\x00':
        return {}
    info: Dict[str, str] = {}
    code = (data[8] << 8) | data[9]
    info['maker'] = ''.join(chr(((code >> s) & 0x1F) + 64) for s in (10, 5, 0))
    if data[21] and data[22]:
        info['width_cm'], info['height_cm'] = str(data[21]), str(data[22])
    for at in (54, 72, 90, 108):
        block = data[at:at + 18]
        if block[:3] != b'\x00\x00\x00':
            continue
        text = block[5:].split(b'\n', 1)[0].decode('latin-1').strip()
        if block[3] == 0xFC and text:
            info['name'] = text
        elif block[3] == 0xFF and text:
            info['serial'] = text
    number = int.from_bytes(data[12:16], 'little')
    if 'serial' not in info and number:
        info['serial'] = str(number)
    return info


# ─── Building the sections ────────────────────────────────────

def read_os_release(src: Source) -> Dict[str, str]:
    out = {}
    for line in (read_text(src.path('etc/os-release')) or '').splitlines():
        key, _, value = line.partition('=')
        if key and value:
            out[key] = value.strip().strip('"')
    return out


def os_line(src: Source, ostree: Dict[str, str]) -> str:
    rel = read_os_release(src)
    name = rel.get('NAME') or 'Linux'
    version = ostree.get('version') or rel.get('VERSION') or ''
    return f"{name} {version}".strip()


def cpu_section(src: Source, sampler: SystemSampler) -> Section:
    sampler.find_sensors()
    rows = [Row(t('sys.model'), sampler.model)]
    base = os.path.join(src.sys, 'devices', 'system', 'cpu')
    cores = set()
    for entry in listdir(base):
        if re.fullmatch(r'cpu\d+', entry):
            core_id = read_int(os.path.join(base, entry, 'topology', 'core_id'))
            package = read_int(os.path.join(base, entry, 'topology', 'physical_package_id'))
            if core_id is not None:
                cores.add((package or 0, core_id))
    threads = sampler.threads or os.cpu_count() or 0
    if cores:
        rows.append(Row(t('sys.cores'), t('sys.cores_threads', cores=len(cores), threads=threads)))
    elif threads:
        rows.append(Row(t('sys.threads'), str(threads)))
    if sampler.cpu_max_mhz:
        rows.append(Row(t('sys.max_clock'), core.mhz(sampler.cpu_max_mhz)))
    l3 = read_line(os.path.join(base, 'cpu0', 'cache', 'index3', 'size'))
    if l3:
        m3 = re.match(r'^(\d+)([KMG])$', l3)
        if m3:
            l3 = core.size(int(m3.group(1)) * 1024 ** ('KMG'.index(m3.group(2)) + 1), 0)
        rows.append(Row(t('sys.l3'), l3))
    return Section('cpu', t('sys.cpu'), rows)


def gpu_sections(src: Source, sampler: SystemSampler, cmds: Dict[str, Optional[str]]) -> List[Section]:
    vulkan = parse_vulkan(cmds.get('vulkan'))
    glx = parse_glx(cmds.get('glx'))
    sections = []
    for i, gpu in enumerate(sampler.gpus):
        rows = [Row(t('sys.model'), gpu.name)]
        driver = ''
        for line in (read_text(os.path.join(gpu.folder, 'uevent')) or '').splitlines():
            if line.startswith('DRIVER='):
                driver = line[7:]
        vk = vulkan_for(vulkan, gpu.vendor, gpu.device)
        if driver:
            rows.append(Row(t('sys.kernel_driver'), driver))
        if vk:
            name = {'radv': 'RADV', 'anv': 'ANV', 'nvk': 'NVK'}.get(vk.get('driverName', ''),
                                                                    vk.get('driverName', ''))
            rows.append(Row(t('sys.vulkan_driver'), ' '.join(
                x for x in (name, vk.get('driverInfo', '')) if x) +
                (f" (Vulkan {vk['apiVersion']})" if vk.get('apiVersion') else '')))
        elif glx and i == 0:
            rows.append(Row(t('sys.opengl'), glx))
        elif not cmds.get('vulkan') and not glx:
            rows.append(Row(t('sys.vulkan_driver'), t('sys.not_found')))
        vram = read_int(os.path.join(gpu.folder, 'mem_info_vram_total'))
        if vram:
            rows.append(Row(t('perf.vram'), core.size(vram, 0)))
        rows.append(Row(t('sys.pci_id'), f"{gpu.vendor:04x}:{gpu.device:04x}"))
        title = t('sys.gpu_n', n=i) if len(sampler.gpus) > 1 else t('sys.gpu')
        sections.append(Section(f'gpu{i}', title, rows))
    if not sampler.gpus:
        sections.append(Section('gpu0', t('sys.gpu'), [Row(t('sys.model'), t('sys.none_found'))]))
    return sections


def memory_section(src: Source, sampler: SystemSampler, cmds: Dict[str, Optional[str]]) -> Section:
    from .system import memory
    mem = memory(src, sampler.zram)
    rows = [Row(t('sys.usable'), core.size(mem.total, 1) if mem.total else '—')]
    mods = parse_udev_memory(cmds.get('udev'))
    if mods:
        total = sum(int(m['SIZE']) for m in mods)
        kinds = sorted({m.get('TYPE', '') for m in mods if real(m.get('TYPE'))})
        sizes = sorted({int(m['SIZE']) for m in mods})
        per = (f"{len(mods)} × {core.size(sizes[0], 0)}" if len(sizes) == 1 else
               ' + '.join(core.size(int(m['SIZE']), 0) for m in mods))
        rows.append(Row(t('sys.installed'), f"{core.size(total, 0)} ({per}"
                        f"{' ' + '/'.join(kinds) if kinds else ''})"))
        rated = sorted({m.get('SPEED_MTS', '') for m in mods if real(m.get('SPEED_MTS'))})
        running = sorted({m.get('CONFIGURED_SPEED_MTS', '') for m in mods
                          if real(m.get('CONFIGURED_SPEED_MTS'))})
        if running or rated:
            text = ('/'.join(running) if running else '/'.join(rated)) + ' MT/s'
            if running and rated and rated != running:
                text += ' ' + t('sys.rated', speed='/'.join(rated))
            rows.append(Row(t('sys.speed'), text))
        for m in mods:
            maker = real(m.get('MANUFACTURER'))
            part = real(m.get('PART_NUMBER'))
            label = f"{maker} {part}".strip()
            where = real(m.get('LOCATOR'))
            bank = real(m.get('BANK_LOCATOR'))
            if where and bank and sum(1 for o in mods if real(o.get('LOCATOR')) == where) > 1:
                where = f"{where} ({bank.title().replace('P0 ', '')})"
            if label or where:
                rows.append(Row(where or t('sys.module'), label or core.size(int(m['SIZE']), 0)))
            serial = real(m.get('SERIAL_NUMBER'))
            if serial:
                rows.append(Row(f"{where or t('sys.module')} {t('sys.serial').lower()}", serial,
                                secret=True))
    else:
        rows.append(Row(t('sys.installed'), t('sys.memory_unreadable')))
    return Section('memory', t('sys.memory'), rows)


def board_section(src: Source) -> Section:
    d = os.path.join(src.sys, 'class', 'dmi', 'id')

    def get(name: str) -> str:
        return real(read_line(os.path.join(d, name)))
    rows: List[Row] = []
    board = ' '.join(x for x in (get('board_vendor'), get('board_name')) if x)
    if board:
        rows.append(Row(t('sys.board'), board))
    system = ' '.join(x for x in (get('sys_vendor'), get('product_name')) if x)
    if system and system != board:
        rows.append(Row(t('sys.system'), system))
    bios = ' '.join(x for x in (get('bios_vendor'), get('bios_version')) if x)
    if bios:
        rows.append(Row(t('sys.bios'), bios))
    if get('bios_date'):
        rows.append(Row(t('sys.bios_date'), get('bios_date')))
    for name, label in (('board_serial', 'sys.board_serial'), ('product_serial', 'sys.system_serial'),
                        ('chassis_serial', 'sys.chassis_serial'), ('product_uuid', 'sys.uuid')):
        if get(name):
            rows.append(Row(t(label), get(name), secret=True))
    if not rows:
        rows.append(Row(t('sys.board'), t('sys.not_readable')))
    return Section('board', t('sys.board_bios'), rows)


def disks_section(src: Source, sampler: SystemSampler) -> Section:
    rows = []
    for d in sampler.disks:
        rows.append(Row(d.name, f"{d.model}, {d.kind}, {core.size(d.size, 0)}"))
        serial = real(read_line(os.path.join(src.sys, 'block', d.name, 'device', 'serial')))
        if serial:
            rows.append(Row(f"{d.name} {t('sys.serial').lower()}", serial, secret=True))
    if not rows:
        rows.append(Row(t('sys.disks'), t('sys.none_found')))
    return Section('disks', t('sys.disks'), rows)


def displays_section(src: Source, cmds: Dict[str, Optional[str]]) -> Section:
    drm = os.path.join(src.sys, 'class', 'drm')
    rows = []
    for entry in sorted(listdir(drm), key=natural):
        match = re.fullmatch(r'card\d+-(.+)', entry)
        if not match or read_line(os.path.join(drm, entry, 'status')) != 'connected':
            continue
        connector = match.group(1)
        edid = parse_edid(read_bytes(os.path.join(drm, entry, 'edid')))
        name = edid.get('name') or t('sys.display')
        parts = []
        first = (read_line(os.path.join(drm, entry, 'modes')) or '')    # the preferred mode
        if first:
            parts.append(first)
        if edid.get('width_cm'):
            w, h = int(edid['width_cm']), int(edid['height_cm'])
            parts.append(f"{(w * w + h * h) ** 0.5 / 2.54:.0f}\"")
        rows.append(Row(connector, ', '.join([name] + parts)))
        if edid.get('serial') and real(edid['serial']):
            rows.append(Row(f"{connector} {t('sys.serial').lower()}", edid['serial'], secret=True))
    if not rows:
        rows.append(Row(t('sys.displays'), t('sys.none_found')))
    return Section('displays', t('sys.displays'), rows)


def os_section(src: Source, ostree: Dict[str, str]) -> Section:
    rel = read_os_release(src)
    rows = [Row(t('sys.os'), os_line(src, ostree))]
    if ostree.get('image'):
        rows.append(Row(t('sys.image'), ostree['image']))
    if ostree.get('digest'):
        digest = ostree['digest']
        rows.append(Row(t('sys.digest'), digest[:19] + '…' if len(digest) > 20 else digest,
                        full=digest))
    if ostree.get('timestamp', '').isdigit():
        from datetime import datetime
        built = datetime.fromtimestamp(int(ostree['timestamp'])).astimezone()
        rows.append(Row(t('sys.built'), built.strftime('%Y-%m-%d %H:%M ') + (built.tzname() or '')))
    if ostree.get('staged'):
        rows.append(Row(t('sys.waiting'), t('sys.waiting_text', version=ostree['staged'])))
    if not ostree:
        rows.append(Row(t('sys.image'), t('sys.ostree_unreadable')))
    if rel.get('VARIANT') or rel.get('VERSION_ID'):
        rows.append(Row(t('sys.fedora'), rel.get('VERSION_ID', '')))
    kernel = read_line(os.path.join(src.proc, 'sys', 'kernel', 'osrelease')) or '?'
    rows.append(Row(t('sys.kernel'), kernel))
    return Section('os', t('sys.sparkos'), rows)


def read_uptime(src: Source) -> float:
    try:
        return float((read_line(os.path.join(src.proc, 'uptime')) or '').split()[0])
    except (IndexError, ValueError):
        return 0.0


def uptime_text(seconds: float) -> str:
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m = s // 60
    if d:
        return t('sys.uptime_d', d=d, h=h, m=m)
    if h:
        return t('sys.uptime_h', h=h, m=m)
    return t('sys.uptime_m', m=m)


def build(src: Source, sampler: SystemSampler, cmds: Dict[str, Optional[str]]) -> List[Section]:
    """Every section, in the order the tab shows them."""
    ostree = parse_ostree(cmds.get('ostree'))
    disk_usage(src, sampler.disks)
    sections = [os_section(src, ostree), cpu_section(src, sampler)]
    sections += gpu_sections(src, sampler, cmds)
    sections += [memory_section(src, sampler, cmds), board_section(src),
                 disks_section(src, sampler), displays_section(src, cmds)]
    sections.append(Section('uptime', t('sys.uptime'),
                            [Row(t('sys.up_for'), uptime_text(read_uptime(src)))]))
    return sections


def report(sections: List[Section], serials: bool, when: str) -> str:
    """The text "Copy all" puts on the clipboard, for a support request."""
    from . import VERSION
    lines = [f"Spark Monitor {VERSION} — {t('sys.report')}", when, '']
    for s in sections:
        rows = [r for r in s.rows if serials or not r.secret]
        if not rows:
            continue
        lines.append(f"[{s.title}]")
        width = max(len(r.label) for r in rows)
        lines += [f"{r.label.ljust(width)}  {r.full or r.value}" for r in rows]
        lines.append('')
    if not serials:
        lines.append(t('sys.report_no_serials'))
    return '\n'.join(lines).rstrip() + '\n'
