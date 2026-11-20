"""Processes, and the apps they belong to.

Plasma 6 starts every app in its own systemd scope, so /proc/<pid>/cgroup says which app a
process belongs to: app-<desktop-id>@<random>.scope, or app-flatpak-<id>-<n>.scope for
Flatpak apps. Those become the rows of the Apps tab, named and iconed from the app's desktop
entry. Steam games get their own row, found through Steam's launcher process.

Cost, per sample: one listdir of /proc, then /proc/<pid>/stat and statm for every process
(kernel threads are skipped after the first look), and /proc/<pid>/io for your own. A
process's cgroup, owner and command line are read once, when it first appears."""

import os
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from .desktop import DesktopIndex
from .source import Source, listdir, read_bytes, read_text

PF_KTHREAD = 0x00200000
try:
    CLK_TCK = os.sysconf('SC_CLK_TCK')
    PAGE = os.sysconf('SC_PAGE_SIZE')
except (AttributeError, ValueError, OSError):
    CLK_TCK, PAGE = 100, 4096

APP, BACKGROUND, SYSTEM = 'app', 'background', 'system'
SECTIONS = (APP, BACKGROUND, SYSTEM)

# Parts of the desktop and the session. Ending them logs you out, freezes the screen or cuts
# the sound, so the Apps tab won't; Details still can, after a warning.
PROTECTED = re.compile(
    r'^(plasma|kwin|org\.kde\.(plasmashell|kwin|ksmserver|kded|kglobalaccel|polkit)|'
    r'ksmserver|kded|kglobalaccel|dbus|xdg-desktop-portal|xdg-document-portal|xdg-permission|'
    r'pipewire|wireplumber|systemd|at-spi|gvfs|xwayland|sddm|gdm|polkit)', re.I)
PROTECTED_COMM = re.compile(
    r'^(systemd|kwin_wayland|kwin_x11|kwin_wayland_wr|plasmashell|ksmserver|kded6|sddm|'
    r'startplasma|Xwayland|dbus-broker|dbus-daemon|pipewire|wireplumber)', re.I)

STEAM_IDS = ('steam', 'com.valvesoftware.steam', 'valve-steam')


@dataclass
class Proc:
    pid: int
    start: int                     # start time in clock ticks since boot: tells reused PIDs apart
    comm: str
    ppid: int
    state: str
    nice: int
    threads: int
    kthread: bool
    ticks: int = 0                 # utime + stime
    uid: int = -1
    cgroup: str = ""
    cmdline: Optional[str] = None
    group: str = ""
    cpu: float = 0.0               # % of the whole CPU
    mem: int = 0                   # private memory (RssAnon), bytes
    io: Optional[int] = None       # bytes read + written so far
    io_at: float = 0.0             # when io was read
    disk: float = 0.0              # bytes/s
    active: bool = True            # used CPU since the last sample
    io_ok: bool = True
    gpu: float = 0.0
    gpu_fds: List[int] = field(default_factory=list)
    gpu_ns: Dict[Tuple[str, str], Dict[str, int]] = field(default_factory=dict)
    gpu_scans: int = 0
    gpu_scan_at: float = 0.0
    seen: int = 0                  # samples since it appeared
    steam_app: Optional[str] = None


@dataclass
class Group:
    key: str
    section: str
    name: str
    desktop_id: Optional[str] = None
    icon: Optional[str] = None
    unit: str = ""
    pids: List[int] = field(default_factory=list)
    cpu: float = 0.0
    mem: int = 0
    disk: float = 0.0
    gpu: Optional[float] = None
    mine: bool = True              # all its processes are yours (so you may end them)

    @property
    def endable(self) -> bool:
        return self.section != SYSTEM


# ─── Reading one process ──────────────────────────────────────

def parse_stat(data: bytes):
    """(comm, state, ppid, flags, ticks, nice, threads, start) from /proc/<pid>/stat."""
    right = data.rfind(b')')
    comm = data[data.find(b'(') + 1:right].decode('utf-8', 'replace')
    f = data[right + 2:].split(None, 20)       # the fields after starttime aren't needed
    return (comm, f[0].decode(), int(f[1]), int(f[6]), int(f[11]) + int(f[12]), int(f[16]),
            int(f[17]), int(f[19]))


def parse_uid(status: Optional[str]) -> int:
    if status:
        match = re.search(r'^Uid:\s*(\d+)', status, re.M)
        if match:
            return int(match.group(1))
    return -1


def parse_cgroup(text: Optional[str]) -> str:
    """The cgroup v2 path ("0::/user.slice/..."). Empty on cgroup v1 or when unreadable."""
    if not text:
        return ""
    for line in text.splitlines():
        if line.startswith('0::'):
            return line[3:].strip()
    return ""


def unescape(name: str) -> str:
    """systemd escapes '-' and other bytes in unit names as \\xNN."""
    return re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)), name)


def desktop_id_from_unit(unit: str) -> Optional[str]:
    """app-org.kde.dolphin@3f2a.scope -> org.kde.dolphin;
    app-flatpak-com.valvesoftware.Steam-4021.scope -> com.valvesoftware.Steam."""
    if not unit.startswith('app-'):
        return None
    name = re.sub(r'\.(scope|service)$', '', unit[4:])
    if name.startswith('flatpak-'):
        return unescape(re.sub(r'-\d+$', '', name[8:]))
    if '@' in name:
        return unescape(name.split('@', 1)[0])
    return unescape(re.sub(r'-[0-9a-f]{1,32}$', '', name, flags=re.I))


def pretty_unit(unit: str) -> str:
    name = re.sub(r'\.(service|scope|slice)$', '', unescape(unit))
    return re.sub(r'@.*$', '', name)


def classify(cgroup: str, desktop: DesktopIndex) -> Tuple[str, str, str, Optional[str], str]:
    """(group key, section, name, desktop id, unit) for a cgroup path. An empty key means
    "not from a systemd session": the caller groups the process on its own."""
    segs = [s for s in cgroup.split('/') if s]
    if not segs:
        return "", BACKGROUND, "", None, ""
    if segs == ['init.scope']:
        return "/init.scope", SYSTEM, "systemd", None, "init.scope"
    if segs[0] == 'system.slice' and len(segs) > 1:
        key = '/' + '/'.join(segs[:2])
        return key, SYSTEM, pretty_unit(segs[1]), None, segs[1]
    for i, seg in enumerate(segs):
        if re.fullmatch(r'session-\w+\.scope', seg):
            return '/' + '/'.join(segs[:i + 1]), SYSTEM, "Login session", None, seg
        if not (seg.startswith('user@') and seg.endswith('.service')):
            continue
        rest = segs[i + 1:]
        if not rest:
            break
        if rest[0] == 'init.scope':
            return '/' + '/'.join(segs[:i + 2]), SYSTEM, "systemd (your session)", None, rest[0]
        if len(rest) < 2 or not rest[0].endswith('.slice'):
            # a unit straight under user@ (older systemd): treat it like app.slice
            rest = ['app.slice'] + rest
        slice_, unit = rest[0], rest[1]
        key = '/' + '/'.join(segs[:i + 1] + rest[:2])
        if unit.endswith('.slice'):           # a nested slice; its first unit is the group
            if len(rest) > 2:
                unit = rest[2]
                key = '/' + '/'.join(segs[:i + 1] + rest[:3])
        did = desktop_id_from_unit(unit)
        entry = desktop.lookup(did) if did else None
        name = entry.name if entry else pretty_unit(did or unit)
        protected = bool(PROTECTED.match(did or pretty_unit(unit)))
        if slice_ == 'session.slice' or protected:
            return key, SYSTEM, name, did if entry else None, unit
        if entry and not entry.no_display:
            return key, APP, name, entry.id, unit
        return key, BACKGROUND, name, entry.id if entry else None, unit
    return "", BACKGROUND, "", None, ""


# ─── Steam games ──────────────────────────────────────────────

class SteamLibrary:
    """Game names from Steam's app manifests, for the processes Steam starts."""

    def __init__(self, src: Source):
        self.src = src
        self.names: Dict[str, str] = {}
        self._libraries: Optional[List[str]] = None

    def libraries(self) -> List[str]:
        if self._libraries is None:
            roots = [os.path.join(self.src.home, p) for p in (
                '.local/share/Steam', '.steam/steam',
                '.var/app/com.valvesoftware.Steam/.local/share/Steam',
                '.var/app/com.valvesoftware.Steam/data/Steam')]
            libs: List[str] = []
            for root in roots:
                apps = os.path.join(root, 'steamapps')
                if os.path.isdir(apps) and apps not in libs:
                    libs.append(apps)
                vdf = read_text(os.path.join(apps, 'libraryfolders.vdf')) or ''
                for path in re.findall(r'"path"\s+"([^"]+)"', vdf):
                    path = os.path.join(self.src.host_path(path.replace('\\\\', '\\')),
                                        'steamapps')
                    if os.path.isdir(path) and path not in libs:
                        libs.append(path)
            self._libraries = libs
        return self._libraries

    def name(self, appid: str) -> str:
        if appid not in self.names:
            found = f"Steam game {appid}"
            for lib in self.libraries():
                text = read_text(os.path.join(lib, f'appmanifest_{appid}.acf'))
                match = re.search(r'"name"\s+"([^"]+)"', text or '')
                if match:
                    found = match.group(1)
                    break
            self.names[appid] = found
        return self.names[appid]


# ─── The sampler ──────────────────────────────────────────────

class ProcSampler:
    """Keeps every process and its numbers between samples, and groups them into apps."""

    GPU_SCAN_BUDGET = 3000        # fd links looked at per sample, at most
    GPU_RESCAN_S = (5.0, 30.0)    # look again for a GPU after this long (games start slowly)

    def __init__(self, src: Source, desktop: Optional[DesktopIndex] = None,
                 threads: int = 1):
        self.src = src
        self.desktop = desktop or DesktopIndex(src)
        self.steam = SteamLibrary(src)
        self.threads = max(1, threads)
        self.procs: Dict[int, Proc] = {}
        self.groups: Dict[str, Group] = {}
        self.prev_time: Optional[float] = None
        self.ticks = 0
        self.kernel_threads = 0
        self.self_pid = os.getpid()
        self.gpu_readable = False

    # — per process —
    def _new(self, pid: int, stat) -> Proc:
        comm, state, ppid, flags, ticks, nice, threads, start = stat
        p = Proc(pid=pid, start=start, comm=comm, ppid=ppid, state=state, nice=nice,
                 threads=threads, kthread=bool(flags & PF_KTHREAD) or ppid == 2 or pid == 2,
                 ticks=ticks)
        if not p.kthread:
            base = f'{self.src.proc}/{pid}/'
            p.uid = parse_uid(read_text(base + 'status'))
            p.cgroup = parse_cgroup(read_text(base + 'cgroup'))
        return p

    def cmdline(self, p: Proc) -> str:
        if p.cmdline is None:
            data = read_bytes(f'{self.src.proc}/{p.pid}/cmdline') or b''
            p.cmdline = data.rstrip(b'\0').replace(b'\0', b' ').decode('utf-8', 'replace')
        return p.cmdline

    def sample(self, now: float, gpu: bool = True) -> None:
        proc = self.src.proc
        dt = (now - self.prev_time) if self.prev_time is not None else 0.0
        self.ticks += 1
        old = self.procs
        procs: Dict[int, Proc] = {}
        kernel = 0
        uid = self.src.uid
        recheck = self.ticks % 10
        for name in listdir(proc):
            if not name.isdigit():
                continue
            pid = int(name)
            p = old.get(pid)
            if p is not None and p.kthread and pid % 10 != recheck:
                procs[pid] = p             # kernel threads: look again only every 10 s
                kernel += 1
                continue
            base = f'{proc}/{name}/'
            data = read_bytes(base + 'stat')
            if not data:
                continue                   # gone since the listdir
            try:
                stat = parse_stat(data)
            except (IndexError, ValueError):
                continue
            if p is None or p.start != stat[7]:
                p = self._new(pid, stat)
                prev_ticks = None
            else:
                prev_ticks = p.ticks
                p.comm, p.state, p.ppid, _flags, p.ticks, p.nice, p.threads, _s = stat
                p.seen += 1
                if p.seen == 2 and not p.kthread:
                    # launchers fork first and move the child into its app scope a moment later
                    p.cgroup = parse_cgroup(read_text(base + 'cgroup')) or p.cgroup
            procs[pid] = p
            if p.kthread:
                kernel += 1
                continue
            if prev_ticks is not None and dt > 0:
                p.cpu = min(100.0, 100.0 * (p.ticks - prev_ticks) / CLK_TCK / dt / self.threads)
            p.active = prev_ticks is None or p.ticks != prev_ticks
            if not p.active and (pid + self.ticks) % 10:
                # It didn't run, so its memory and disk use can't have changed (much): skip
                # two reads. Most processes sleep, so this halves the cost of a sample.
                # Each one is still looked at every 10 s, for swapping and late writeback.
                p.disk = 0.0
                continue
            statm = read_bytes(base + 'statm')
            if statm:
                parts = statm.split()
                try:
                    p.mem = max(0, int(parts[1]) - int(parts[2])) * PAGE
                except (IndexError, ValueError):
                    pass
            if p.uid == uid and p.io_ok:
                io = read_bytes(base + 'io')
                if io is None:
                    p.io_ok = False        # not allowed (setuid programs); don't try again
                else:
                    total = _io_total(io)
                    if p.io is not None and now > p.io_at and total >= p.io:
                        p.disk = (total - p.io) / (now - p.io_at)
                    p.io, p.io_at = total, now
        self.procs = procs
        self.kernel_threads = kernel
        if gpu:
            self._gpu(now, dt)
        self.prev_time = now
        self._group()

    # — GPU use per process (AMD and Intel publish it per open GPU file in fdinfo) —
    def _gpu(self, now: float, dt: float) -> None:
        budget = self.GPU_SCAN_BUDGET
        uid = self.src.uid
        proc = self.src.proc
        for p in self.procs.values():
            if p.kthread or p.uid != uid:
                continue
            # Only a process that is running can be drawing; idle daemons are never scanned.
            due = p.active and (p.gpu_scans == 0 or (
                p.gpu_scans <= len(self.GPU_RESCAN_S) and not p.gpu_fds
                and now >= p.gpu_scan_at))
            if due and budget > 0 and self.prev_time is not None:
                budget -= self._scan_fds(p)
                p.gpu_scan_at = now + self.GPU_RESCAN_S[min(p.gpu_scans - 1,
                                                            len(self.GPU_RESCAN_S) - 1)]
            if not p.gpu_fds:
                p.gpu = 0.0
                continue
            busy = 0.0
            keep = []
            seen_clients = set()
            for fd in p.gpu_fds:
                info = read_bytes(f'{proc}/{p.pid}/fdinfo/{fd}')
                if not info or b'drm-client-id' not in info:
                    continue               # closed, or the number now means another file
                keep.append(fd)
                client, engines = _drm_info(info)
                if client in seen_clients:
                    continue               # the same client through a duplicated fd
                seen_clients.add(client)
                self.gpu_readable = True
                before = p.gpu_ns.get(client)
                if before and dt > 0:
                    use = max((max(0, ns - before.get(e, ns)) for e, ns in engines.items()),
                              default=0)
                    busy += 100.0 * use / (dt * 1e9)
                p.gpu_ns[client] = engines
            p.gpu_fds = keep
            p.gpu = min(100.0, busy)

    def _scan_fds(self, p: Proc) -> int:
        p.gpu_scans += 1
        folder = f'{self.src.proc}/{p.pid}/fd'
        names = listdir(folder)
        found = []
        for name in names:
            path = f'{folder}/{name}'
            try:
                target = os.readlink(path)
            except OSError:
                target = (read_text(path) or '').strip() if self.src.fake else ''
            if target.startswith('/dev/dri/'):
                found.append(int(name))
        p.gpu_fds = found
        return len(names) + 1

    # — grouping —
    def _group(self) -> None:
        groups: Dict[str, Group] = {}
        procs = self.procs
        for p in procs.values():
            if p.kthread:
                continue
            key, section, name, did, unit = classify(p.cgroup, self.desktop) \
                if p.cgroup else ("", BACKGROUND, "", None, "")
            if not key:
                # not started by a systemd session (containers, other init systems)
                key, section, name, did, unit = f'pid:{p.pid}', BACKGROUND, p.comm, None, ""
                if PROTECTED_COMM.match(p.comm) or p.pid == 1:
                    section = SYSTEM
            elif did and did.lower() in STEAM_IDS:
                appid = self._steam_app(p)
                if appid:
                    key, section, name = f'{key}:game:{appid}', APP, self.steam.name(appid)
            p.group = key
            g = groups.get(key)
            if g is None:
                entry = self.desktop.lookup(did) if did else None
                g = groups[key] = Group(key=key, section=section, name=name, desktop_id=did,
                                        icon=entry.icon if entry else None, unit=unit)
            g.pids.append(p.pid)
            g.cpu += p.cpu
            g.mem += p.mem
            g.disk += p.disk
            if p.gpu_fds:
                g.gpu = (g.gpu or 0.0) + p.gpu
            if p.uid != self.src.uid:
                g.mine = False
        for g in groups.values():
            g.cpu = min(100.0, g.cpu)
            if g.gpu is not None:
                g.gpu = min(100.0, g.gpu)
            if len(g.pids) == 1 and g.key.startswith('pid:'):
                p = procs[g.pids[0]]
                if p.pid == self.self_pid:
                    g.name = "Spark Monitor"
        self.groups = groups

    def _steam_app(self, p: Proc) -> Optional[str]:
        """The Steam AppId a process was started for: Steam launches every game through its
        'reaper' helper with "SteamLaunch AppId=<n>" on the command line."""
        if p.steam_app is not None:
            return p.steam_app or None
        found = ""
        q: Optional[Proc] = p
        for _ in range(32):
            if q is None:
                break
            if q.comm == 'reaper' or 'SteamLaunch' in q.comm:
                match = re.search(r'SteamLaunch\b.*?\bAppId=(\d+)', self.cmdline(q))
                if match:
                    found = match.group(1)
                    break
            q = self.procs.get(q.ppid)
        p.steam_app = found
        return found or None

    # — queries the interface uses —
    def section_of(self, key: str) -> Optional[str]:
        g = self.groups.get(key)
        return g.section if g else None

    def children(self, pid: int) -> List[int]:
        """The PID and everything it started, deepest first."""
        kids: Dict[int, List[int]] = {}
        for p in self.procs.values():
            kids.setdefault(p.ppid, []).append(p.pid)
        out: List[int] = []

        def walk(q: int, depth: int = 0):
            if depth > 64:
                return
            for c in kids.get(q, []):
                walk(c, depth + 1)
            out.append(q)
        walk(pid)
        return out

    def group_pids(self, key: str) -> List[int]:
        g = self.groups.get(key)
        return list(g.pids) if g else []

    def totals(self) -> Tuple[int, int]:
        return len(self.procs) - self.kernel_threads, self.kernel_threads

    def protected_pid(self, pid: int) -> bool:
        p = self.procs.get(pid)
        if p is None:
            return False
        if pid == 1 or p.kthread or self.section_of(p.group) == SYSTEM:
            return True
        return bool(PROTECTED_COMM.match(p.comm))


def _io_total(io: bytes) -> int:
    total = 0
    for line in io.split(b'\n'):
        if line.startswith((b'read_bytes:', b'write_bytes:')):
            total += int(line.split()[1])
    return total


def _drm_info(info: bytes) -> Tuple[Tuple[str, str], Dict[str, int]]:
    client, pdev = '', ''
    engines: Dict[str, int] = {}
    for line in info.split(b'\n'):
        if line.startswith(b'drm-engine-') and b'capacity' not in line:
            key, _, value = line.partition(b':')
            parts = value.split()
            if parts and parts[0].isdigit():
                engines[key[11:].decode()] = int(parts[0])
        elif line.startswith(b'drm-client-id:'):
            client = line.split(b':', 1)[1].strip().decode()
        elif line.startswith(b'drm-pdev:'):
            pdev = line.split(b':', 1)[1].strip().decode()
    return (pdev, client), engines


def users() -> Dict[int, str]:
    try:
        import pwd
        return {u.pw_uid: u.pw_name for u in pwd.getpwall()}
    except (ImportError, OSError, KeyError):
        return {}


def iter_section(groups: Iterable[Group], section: str) -> List[Group]:
    return [g for g in groups if g.section == section]

