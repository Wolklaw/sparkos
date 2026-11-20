"""Whole-machine numbers: CPU, memory, GPU, disks and network, read from /proc and /sys.

SystemSampler.sample() is called once a second. With full=False (Apps, Startup and Details
tabs) it reads only the five totals the column headings show; with full=True (Performance)
it also reads clocks, temperatures, power and fans."""

import os
import re
import shutil
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .source import Source, listdir, read_bytes, read_int, read_line, read_text

VENDORS = {0x1002: "AMD", 0x8086: "Intel", 0x10de: "NVIDIA"}
SECTOR = 512


# ─── Small helpers ────────────────────────────────────────────

def _num(line: str) -> int:
    try:
        return int(line)
    except ValueError:
        return 0


def hwmon_dirs(src: Source) -> Dict[str, List[str]]:
    """hwmon driver name -> its folders under /sys/class/hwmon."""
    base = os.path.join(src.sys, 'class', 'hwmon')
    found: Dict[str, List[str]] = {}
    for entry in sorted(listdir(base), key=natural):
        name = read_line(os.path.join(base, entry, 'name'))
        if name:
            found.setdefault(name, []).append(os.path.join(base, entry))
    return found


def natural(name: str):
    return [int(p) if p.isdigit() else p for p in re.split(r'(\d+)', name)]


def hwmon_find(folder: str, kind: str, labels: Tuple[str, ...] = ()) -> Optional[str]:
    """Path of the first <kind>N_input in an hwmon folder, preferring the given labels."""
    inputs = sorted((f for f in listdir(folder) if f.startswith(kind) and f.endswith('_input')),
                    key=natural)
    if not inputs:
        return None
    if labels:
        by_label = {}
        for f in inputs:
            label = read_line(os.path.join(folder, f[:-6] + '_label'))
            if label:
                by_label[label.lower()] = f
        for wanted in labels:
            if wanted.lower() in by_label:
                return os.path.join(folder, by_label[wanted.lower()])
    return os.path.join(folder, inputs[0])


def milli(path: Optional[str], scale: float = 1000.0) -> Optional[float]:
    if not path:
        return None
    value = read_int(path)
    return None if value is None else value / scale


# ─── CPU ──────────────────────────────────────────────────────

def cpu_model(src: Source) -> str:
    """Read once: /proc/cpuinfo is slow to generate on x86, so never every second."""
    text = read_text(os.path.join(src.proc, 'cpuinfo')) or ''
    for key in ('model name', 'Model', 'Hardware', 'cpu model'):
        match = re.search(rf'^{key}\s*:\s*(.+)$', text, re.M)
        if match:
            return re.sub(r'\s+', ' ', match.group(1)).strip()
    return "CPU"


def cpu_times(src: Source) -> List[Tuple[int, int]]:
    """(busy, total) jiffies for the whole CPU, then each thread, from /proc/stat."""
    data = read_bytes(os.path.join(src.proc, 'stat'))
    out: List[Tuple[int, int]] = []
    if not data:
        return out
    for line in data.split(b'\n'):
        if not line.startswith(b'cpu'):
            if out:
                break
            continue
        parts = line.split()
        # user nice system idle iowait irq softirq steal (guest is already inside user)
        values = [int(v) for v in parts[1:9]]
        total = sum(values)
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        out.append((total - idle, total))
    return out


def percent(new: Tuple[int, int], old: Tuple[int, int]) -> float:
    busy, total = new[0] - old[0], new[1] - old[1]
    if total <= 0:
        return 0.0
    return max(0.0, min(100.0, 100.0 * busy / total))


# ─── Memory ───────────────────────────────────────────────────

def meminfo(src: Source) -> Dict[str, int]:
    """/proc/meminfo in bytes."""
    data = read_bytes(os.path.join(src.proc, 'meminfo')) or b''
    out = {}
    for line in data.split(b'\n'):
        key, _, rest = line.partition(b':')
        parts = rest.split()
        if parts:
            value = int(parts[0])
            out[key.decode()] = value * 1024 if len(parts) > 1 else value
    return out


@dataclass
class Memory:
    total: int = 0
    available: int = 0
    used: int = 0
    cached: int = 0
    swap_total: int = 0
    swap_used: int = 0
    zram_data: Optional[int] = None      # what is stored in zram, and what it takes compressed
    zram_compressed: Optional[int] = None

    @property
    def percent(self) -> float:
        return 100.0 * self.used / self.total if self.total else 0.0


def memory(src: Source, zram: List[str]) -> Memory:
    info = meminfo(src)
    m = Memory(total=info.get('MemTotal', 0))
    m.available = info.get('MemAvailable', info.get('MemFree', 0))
    m.used = max(0, m.total - m.available)
    m.cached = info.get('Cached', 0) + info.get('Buffers', 0) + info.get('SReclaimable', 0)
    m.swap_total = info.get('SwapTotal', 0)
    m.swap_used = max(0, m.swap_total - info.get('SwapFree', 0))
    for dev in zram:
        stat = read_line(os.path.join(src.sys, 'block', dev, 'mm_stat'))
        if stat:
            parts = stat.split()
            m.zram_data = (m.zram_data or 0) + _num(parts[0])
            m.zram_compressed = (m.zram_compressed or 0) + _num(parts[2] if len(parts) > 2
                                                                  else parts[1])
    return m


# ─── GPU ──────────────────────────────────────────────────────

@dataclass
class Gpu:
    card: str
    folder: str                       # /sys/class/drm/cardN/device
    vendor: int
    device: int
    name: str
    hwmon: Optional[str] = None
    busy: Optional[float] = None
    vram_used: Optional[int] = None
    vram_total: Optional[int] = None
    gtt_used: Optional[int] = None
    gtt_total: Optional[int] = None
    clock_mhz: Optional[float] = None
    temp: Optional[float] = None
    temp_hot: Optional[float] = None  # AMD junction (hotspot)
    power_w: Optional[float] = None
    fan_rpm: Optional[int] = None
    note: str = ""

    @property
    def vendor_name(self) -> str:
        return VENDORS.get(self.vendor, f"{self.vendor:04x}")


def find_gpus(src: Source) -> List[Gpu]:
    base = os.path.join(src.sys, 'class', 'drm')
    gpus = []
    for card in sorted(listdir(base), key=natural):
        if not re.fullmatch(r'card\d+', card):
            continue                      # card1-DP-1 and friends are connectors
        folder = os.path.join(base, card, 'device')
        vendor = read_int(os.path.join(folder, 'vendor'))
        device = read_int(os.path.join(folder, 'device'))
        if vendor is None:
            continue
        gpu = Gpu(card=card, folder=folder, vendor=vendor, device=device or 0,
                  name=f"{VENDORS.get(vendor, 'Unknown')} GPU ({vendor:04x}:{device or 0:04x})")
        for entry in sorted(listdir(os.path.join(folder, 'hwmon')), key=natural):
            gpu.hwmon = os.path.join(folder, 'hwmon', entry)
            break
        product = read_line(os.path.join(folder, 'product_name'))
        if product:
            gpu.name = product
        if vendor == 0x10de and not os.path.exists(os.path.join(folder, 'gpu_busy_percent')):
            gpu.note = ("NVIDIA's driver doesn't publish usage, memory or temperature in /sys. "
                        "nvidia-smi can show them; Spark Monitor doesn't run it every second.")
        elif vendor == 0x8086:
            gpu.note = "Intel's driver doesn't publish GPU usage in /sys; clock is shown."
        gpus.append(gpu)
    # the dedicated card first: the one with the most video memory
    gpus.sort(key=lambda g: -(read_int(os.path.join(g.folder, 'mem_info_vram_total')) or 0))
    return gpus


def pci_names(src: Source, gpus: List[Gpu]) -> None:
    """Name each GPU from the PCI ID list (hwdata). Called once, after the window is up."""
    for rel in ('usr/share/hwdata/pci.ids', 'usr/share/misc/pci.ids', 'usr/share/pci.ids'):
        data = read_bytes(src.path(rel))
        if data:
            break
    else:
        return
    for gpu in gpus:
        if not gpu.name.endswith(')') or '(' not in gpu.name:
            continue                      # already has a product name
        name = pci_lookup(data, gpu.vendor, gpu.device,
                          read_int(os.path.join(gpu.folder, 'subsystem_vendor')),
                          read_int(os.path.join(gpu.folder, 'subsystem_device')))
        if name:
            gpu.name = name


def pci_lookup(data: bytes, vendor: int, device: int, sub_vendor: Optional[int] = None,
               sub_device: Optional[int] = None) -> Optional[str]:
    start = data.find(f'\n{vendor:04x}  '.encode())
    if start < 0:
        return None
    end = data.find(b'\n', start + 1)
    next_vendor = re.compile(rb'\n[0-9a-f]{4}  ').search(data, end)
    block = data[end:next_vendor.start() if next_vendor else len(data)]
    pos = block.find(f'\n\t{device:04x}  '.encode())
    if pos < 0:
        return None
    line_end = block.find(b'\n', pos + 1)
    device_name = block[pos + 8:line_end].decode('utf-8', 'replace').strip()
    if sub_vendor is not None and sub_device is not None:
        next_device = re.compile(rb'\n\t[0-9a-f]{4}  ').search(block, line_end)
        subs = block[line_end:next_device.start() if next_device else len(block)]
        sub = subs.find(f'\n\t\t{sub_vendor:04x} {sub_device:04x}  '.encode())
        if sub >= 0:
            sub_end = subs.find(b'\n', sub + 1)
            if sub_end < 0:
                sub_end = len(subs)
            sub_name = subs[sub + 14:sub_end].decode('utf-8', 'replace').strip()
            if sub_name and re.search(r'Radeon|GeForce|\bArc\b|\bR[TX]X? ?\d', sub_name):
                return _brand(vendor, sub_name)
    match = re.search(r'\[(.+)\]', device_name)
    return _brand(vendor, match.group(1) if match else device_name)


def _brand(vendor: int, name: str) -> str:
    short = VENDORS.get(vendor)
    return name if not short or name.startswith(short) else f"{short} {name}"


def read_gpu(gpu: Gpu, full: bool) -> None:
    f = gpu.folder
    gpu.busy = read_int(os.path.join(f, 'gpu_busy_percent'))
    if gpu.busy is not None:
        gpu.busy = float(gpu.busy)
    if not full:
        return
    gpu.vram_used = read_int(os.path.join(f, 'mem_info_vram_used'))
    gpu.vram_total = read_int(os.path.join(f, 'mem_info_vram_total'))
    gpu.gtt_used = read_int(os.path.join(f, 'mem_info_gtt_used'))
    gpu.gtt_total = read_int(os.path.join(f, 'mem_info_gtt_total'))
    gpu.clock_mhz = None
    h = gpu.hwmon
    if h:
        freq = hwmon_find(h, 'freq', ('sclk',))
        gpu.clock_mhz = milli(freq, 1e6)
        gpu.temp = milli(hwmon_find(h, 'temp', ('edge',)))
        hot = hwmon_find(h, 'temp', ('junction',))
        gpu.temp_hot = milli(hot) if hot and 'temp1_' not in hot else None
        power = os.path.join(h, 'power1_average')
        if not os.path.exists(power):
            power = os.path.join(h, 'power1_input')
        gpu.power_w = milli(power, 1e6)
        fan = read_int(os.path.join(h, 'fan1_input'))
        gpu.fan_rpm = fan
    if gpu.clock_mhz is None:
        sclk = read_text(os.path.join(f, 'pp_dpm_sclk'))
        if sclk:
            match = re.search(r'(\d+)\s*Mhz\s*\*', sclk, re.I)
            if match:
                gpu.clock_mhz = float(match.group(1))
    if gpu.clock_mhz is None and gpu.vendor == 0x8086:
        card = os.path.dirname(f)
        for rel in ('gt_cur_freq_mhz', 'gt/gt0/rps_cur_freq_mhz'):
            value = read_int(os.path.join(card, rel))
            if value is not None:
                gpu.clock_mhz = float(value)
                break


# ─── Disks ────────────────────────────────────────────────────

@dataclass
class Disk:
    name: str
    model: str
    kind: str                         # "NVMe SSD", "SSD", "HDD", "Removable"
    size: int
    temp_path: Optional[str] = None
    read_bps: float = 0.0
    write_bps: float = 0.0
    active: float = 0.0               # % of the time the disk was busy
    temp: Optional[float] = None
    usage: List[Tuple[str, int, int]] = field(default_factory=list)   # mount, used, total


def find_disks(src: Source) -> Tuple[List[Disk], List[str]]:
    """Physical disks, and the zram devices (which belong to memory, not disks)."""
    base = os.path.join(src.sys, 'block')
    disks, zram = [], []
    for name in sorted(listdir(base), key=natural):
        if name.startswith('zram'):
            zram.append(name)
            continue
        if re.match(r'(loop|ram|dm-|sr|nbd|fd|md\d+p)', name):
            continue
        folder = os.path.join(base, name)
        size = (read_int(os.path.join(folder, 'size')) or 0) * SECTOR
        if size == 0:
            continue                      # empty card reader slot
        model = (read_line(os.path.join(folder, 'device', 'model')) or name).strip()
        removable = read_int(os.path.join(folder, 'removable')) == 1
        rotational = read_int(os.path.join(folder, 'queue', 'rotational')) == 1
        if name.startswith('nvme'):
            kind = "NVMe SSD"
        elif removable:
            kind = "Removable"
        else:
            kind = "HDD" if rotational else "SSD"
        disk = Disk(name=name, model=model, kind=kind, size=size)
        match = re.match(r'(nvme\d+)n\d+', name)
        if match:
            ctrl = os.path.join(src.sys, 'class', 'nvme', match.group(1))
            for entry in sorted(listdir(ctrl), key=natural):
                if entry.startswith('hwmon'):
                    disk.temp_path = hwmon_find(os.path.join(ctrl, entry), 'temp',
                                                ('composite',))
                    break
        disks.append(disk)
    return disks, zram


def diskstats(src: Source) -> Dict[str, Tuple[int, int, int]]:
    """name -> (bytes read, bytes written, ms busy)."""
    data = read_bytes(os.path.join(src.proc, 'diskstats')) or b''
    out = {}
    for line in data.split(b'\n'):
        parts = line.split()
        if len(parts) >= 13:
            out[parts[2].decode()] = (int(parts[5]) * SECTOR, int(parts[9]) * SECTOR,
                                      int(parts[12]))
    return out


def disk_of(src: Source, dev: str, disks: List[str], depth: int = 0) -> Optional[str]:
    """Which physical disk a block device (partition, LUKS or LVM volume) lives on."""
    if dev in disks:
        return dev
    for disk in disks:
        if os.path.isdir(os.path.join(src.sys, 'block', disk, dev)):
            return disk               # partitions are folders inside their disk
    if depth < 4:
        for slave in listdir(os.path.join(src.sys, 'block', dev, 'slaves')):
            found = disk_of(src, slave, disks, depth + 1)
            if found:
                return found
    return None


def disk_usage(src: Source, disks: List[Disk]) -> None:
    """Fill in how full each disk's mounted filesystems are, one line per filesystem."""
    names = [d.name for d in disks]
    by_name = {d.name: d for d in disks}
    for d in disks:
        d.usage = []
    seen = set()
    data = read_text(os.path.join(src.proc, 'self', 'mounts')) or \
        read_text(os.path.join(src.proc, 'mounts')) or ''
    for line in data.splitlines():
        parts = line.split()
        if len(parts) < 3 or not parts[0].startswith('/dev/'):
            continue
        device = parts[0]
        if not src.fake:
            device = os.path.realpath(device)
        dev = os.path.basename(device)
        if dev in seen:
            continue                      # btrfs mounts the same volume many times
        disk = disk_of(src, dev, names)
        if not disk:
            continue
        mount = parts[1].replace('\\040', ' ')
        try:
            usage = shutil.disk_usage(src.host_path(mount))
        except OSError:
            continue
        seen.add(dev)
        by_name[disk].usage.append((mount, usage.used, usage.total))


# ─── Network ──────────────────────────────────────────────────

@dataclass
class Nic:
    name: str
    kind: str                         # "Ethernet", "Wi-Fi"
    up: bool = False
    speed_mbps: Optional[int] = None
    rx_bps: float = 0.0
    tx_bps: float = 0.0


def netdev(src: Source) -> Dict[str, Tuple[int, int]]:
    """interface -> (bytes received, bytes sent)."""
    data = read_bytes(os.path.join(src.proc, 'net', 'dev')) or b''
    out = {}
    for line in data.split(b'\n')[2:]:
        name, _, rest = line.partition(b':')
        parts = rest.split()
        if len(parts) >= 9:
            out[name.strip().decode()] = (int(parts[0]), int(parts[8]))
    return out


def find_nics(src: Source, counters: Dict[str, Tuple[int, int]]) -> List[Nic]:
    base = os.path.join(src.sys, 'class', 'net')
    virtual = set(listdir(os.path.join(src.sys, 'devices', 'virtual', 'net')))
    nics = []
    for name in sorted(counters, key=natural):
        if name == 'lo' or name in virtual:
            continue
        folder = os.path.join(base, name)
        kind = "Wi-Fi" if os.path.isdir(os.path.join(folder, 'wireless')) else "Ethernet"
        nics.append(Nic(name=name, kind=kind))
    if not nics:                      # containers and VMs: show the virtual ones
        nics = [Nic(name=n, kind="Network") for n in sorted(counters, key=natural) if n != 'lo']
    return nics


# ─── The sampler ──────────────────────────────────────────────

@dataclass
class Snapshot:
    time: float
    cpu: Optional[float] = None               # % of the whole CPU
    threads: List[float] = field(default_factory=list)
    cpu_mhz: Optional[float] = None
    cpu_temp: Optional[float] = None
    mem: Memory = field(default_factory=Memory)
    gpus: List[Gpu] = field(default_factory=list)
    disks: List[Disk] = field(default_factory=list)
    nics: List[Nic] = field(default_factory=list)

    @property
    def disk_active(self) -> Optional[float]:
        return max((d.active for d in self.disks), default=None)

    @property
    def gpu_busy(self) -> Optional[float]:
        values = [g.busy for g in self.gpus if g.busy is not None]
        return max(values) if values else None


class SystemSampler:
    def __init__(self, src: Source):
        self.src = src
        self.model = cpu_model(src)
        self.cpu_folders: List[str] = []
        self.cpu_max_mhz: Optional[float] = None
        self.cpu_temp_path: Optional[str] = None
        self.gpus = find_gpus(src)
        self.disks, self.zram = find_disks(src)
        self.nics = find_nics(src, netdev(src))
        self._prev_cpu: List[Tuple[int, int]] = []
        self._prev_disk: Dict[str, Tuple[int, int, int]] = {}
        self._prev_net: Dict[str, Tuple[int, int]] = {}
        self._prev_time: Optional[float] = None
        self._usage_at = -1e9
        self._sensors_found = False
        self.threads = 0
        self.last: Optional[Snapshot] = None

    def find_sensors(self) -> None:
        """The slower lookups the Performance tab needs; done once, on first use."""
        if self._sensors_found:
            return
        self._sensors_found = True
        base = os.path.join(self.src.sys, 'devices', 'system', 'cpu')
        cpus = sorted((c for c in listdir(base) if re.fullmatch(r'cpu\d+', c)), key=natural)
        self.cpu_folders = [os.path.join(base, c, 'cpufreq') for c in cpus
                            if os.path.isdir(os.path.join(base, c, 'cpufreq'))]
        if self.cpu_folders:
            self.cpu_max_mhz = milli(os.path.join(self.cpu_folders[0], 'cpuinfo_max_freq'))
        mons = hwmon_dirs(self.src)
        for name, labels in (('k10temp', ('tctl', 'tdie')), ('zenpower', ('tdie', 'tctl')),
                             ('coretemp', ('package id 0',)), ('cpu_thermal', ()),
                             ('acpitz', ())):
            if name in mons:
                self.cpu_temp_path = hwmon_find(mons[name][0], 'temp', labels)
                break
        pci_names(self.src, self.gpus)

    def sample(self, now: float, full: bool = False) -> Snapshot:
        src = self.src
        snap = Snapshot(time=now)
        dt = (now - self._prev_time) if self._prev_time is not None else 0.0

        times = cpu_times(src)
        self.threads = max(0, len(times) - 1)
        if self._prev_cpu and len(self._prev_cpu) == len(times):
            snap.cpu = percent(times[0], self._prev_cpu[0])
            snap.threads = [percent(n, o) for n, o in zip(times[1:], self._prev_cpu[1:])]
        self._prev_cpu = times

        snap.mem = memory(src, self.zram)

        for gpu in self.gpus:
            read_gpu(gpu, full)
        snap.gpus = self.gpus

        stats = diskstats(src)
        for disk in self.disks:
            new, old = stats.get(disk.name), self._prev_disk.get(disk.name)
            if new and old and dt > 0:
                disk.read_bps = max(0, new[0] - old[0]) / dt
                disk.write_bps = max(0, new[1] - old[1]) / dt
                disk.active = max(0.0, min(100.0, (new[2] - old[2]) / (dt * 10)))
        self._prev_disk = stats
        snap.disks = self.disks

        counters = netdev(src)
        for nic in self.nics:
            new, old = counters.get(nic.name), self._prev_net.get(nic.name)
            if new and old and dt > 0:
                nic.rx_bps = max(0, new[0] - old[0]) / dt
                nic.tx_bps = max(0, new[1] - old[1]) / dt
        self._prev_net = counters
        snap.nics = self.nics

        if full:
            self.find_sensors()
            if self.cpu_folders:
                freqs = [read_int(os.path.join(f, 'scaling_cur_freq')) for f in self.cpu_folders]
                freqs = [f for f in freqs if f]
                snap.cpu_mhz = sum(freqs) / len(freqs) / 1000 if freqs else None
            snap.cpu_temp = milli(self.cpu_temp_path)
            for disk in self.disks:
                disk.temp = milli(disk.temp_path)
            for nic in self.nics:
                folder = os.path.join(src.sys, 'class', 'net', nic.name)
                nic.up = read_line(os.path.join(folder, 'operstate')) == 'up'
                speed = read_int(os.path.join(folder, 'speed'))
                nic.speed_mbps = speed if speed and speed > 0 else None
            if now - self._usage_at > 10:   # free space changes slowly
                self._usage_at = now
                disk_usage(src, self.disks)

        self._prev_time = now
        self.last = snap
        return snap
