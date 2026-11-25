"""Talking to libvirt: the list of machines, power, snapshots, USB, disks and settings.

Everything goes through python3-libvirt. SPARK_BOXES_URI points it somewhere else (the tests use
test:///default, libvirt's built-in fake hypervisor); the default is qemu:///system, the one
`spark virt setup` turns on. No window code in here."""

import datetime
import logging
import os
import re
import threading
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from . import APP_SLUG, usbdev, virtio, xmlgen
from .xmlgen import NS, VmSpec

try:
    import libvirt
except ImportError:                 # self-test says so; the window shows "libvirt is missing"
    libvirt = None

ET.register_namespace('sparkboxes', NS)
if libvirt is not None:
    libvirt.registerErrorHandler(lambda _ctx, _err: None, None)    # errors come back as exceptions
DEFAULT_URI = 'qemu:///system'
POOL_NAME = 'default'
POOL_PATH = '/var/lib/libvirt/images'
log = logging.getLogger(APP_SLUG)

STATES = ('off', 'running', 'paused', 'other')


class BoxesError(Exception):
    """Something the person should read: the message is plain English."""


class Unavailable(BoxesError):
    """libvirt can't be reached. kind: 'missing' (python3-libvirt), 'off' (daemon not running),
    'group' (not allowed yet: log out and in)."""

    def __init__(self, kind: str, detail: str = ''):
        super().__init__(detail or kind)
        self.kind = kind
        self.detail = detail


def uri() -> str:
    return os.environ.get('SPARK_BOXES_URI') or DEFAULT_URI


def state_dir() -> str:
    base = os.environ.get('XDG_STATE_HOME') or os.path.expanduser('~/.local/state')
    path = os.path.join(base, APP_SLUG)
    os.makedirs(path, exist_ok=True)
    return path


def cache_dir() -> str:
    base = os.environ.get('XDG_CACHE_HOME') or os.path.expanduser('~/.cache')
    path = os.path.join(base, APP_SLUG)
    os.makedirs(path, exist_ok=True)
    return path


def setup_logging() -> None:
    handler = logging.FileHandler(os.path.join(state_dir(), f'{APP_SLUG}.log'), encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


@dataclass
class VmInfo:
    name: str
    uuid: str
    state: str                      # off, running, paused, other
    cpus: int
    memory_mb: int
    preset: str = 'other'
    disk_bytes: int = 0             # the disk's size as the machine sees it
    disk_used: int = 0              # what it takes on the PC so far
    drivers: bool = False
    usb: List[str] = field(default_factory=list)       # 'vvvv:pppp' of what it was given


@dataclass
class SnapshotInfo:
    name: str
    created: float
    running: bool                   # taken with the machine on (has memory)
    current: bool = False
    description: str = ''


def _state(code: int) -> str:
    if libvirt is None:
        return 'other'
    if code in (libvirt.VIR_DOMAIN_RUNNING, libvirt.VIR_DOMAIN_BLOCKED):
        return 'running'
    if code == libvirt.VIR_DOMAIN_PAUSED:
        return 'paused'
    if code in (libvirt.VIR_DOMAIN_SHUTOFF, libvirt.VIR_DOMAIN_SHUTDOWN):
        return 'off'
    return 'other'


def classify_open_error(message: str) -> Unavailable:
    low = message.lower()
    if 'permission denied' in low or 'authentication' in low or 'access denied' in low:
        return Unavailable('group', message)
    return Unavailable('off', message)


def _text(node, path: str, default: str = '') -> str:
    found = node.find(path)
    return found.text.strip() if found is not None and found.text else default


def _can_traverse(path: str) -> bool:
    """True when 'other' users (the qemu user) can read the file and walk its folders."""
    try:
        if not os.stat(path).st_mode & 0o004:
            return False
        folder = os.path.dirname(os.path.abspath(path))
        while True:
            if not os.stat(folder).st_mode & 0o001:
                return False
            parent = os.path.dirname(folder)
            if parent == folder:
                return True
            folder = parent
    except OSError:
        return False


class Manager:
    """One connection to libvirt."""

    def __init__(self, connection_uri: Optional[str] = None, glib_events: bool = False):
        self.glib_events = glib_events      # the window runs libvirt's events on the GLib loop
        self.uri = connection_uri or uri()
        self.conn = None
        self._events_started = False
        self._lock = threading.Lock()
        self._callback: Optional[Callable[[str, str], None]] = None
        self._event_id = None
        self._close_cb = False

    # --- connecting ---

    def connect(self) -> None:
        if libvirt is None:
            raise Unavailable('missing', "python3-libvirt isn't installed")
        if self.conn is not None:
            try:
                if self.conn.isAlive():
                    return
            except libvirt.libvirtError:
                pass
            self.conn = None
        if not self._events_started:
            try:
                from . import eventloop
                if eventloop.active() or (self.glib_events and eventloop.install()):
                    pass
                else:
                    libvirt.virEventRegisterDefaultImpl()
            except libvirt.libvirtError as exc:
                log.warning("event loop: %s", exc)
            self._events_started = True
        try:
            self.conn = libvirt.open(self.uri)
        except libvirt.libvirtError as exc:
            raise classify_open_error(str(exc)) from exc
        if self.conn is None:
            raise Unavailable('off', f"couldn't open {self.uri}")
        log.info("connected to %s (libvirt %s)", self.uri, self.conn.getLibVersion())

    def close(self) -> None:
        if self.conn is not None:
            self._callback = None
            try:
                if self._event_id is not None:
                    self.conn.domainEventDeregisterAny(self._event_id)
                if self._close_cb:
                    self.conn.unregisterCloseCallback()
            except libvirt.libvirtError:
                pass
            self._event_id = None
            self._close_cb = False
            try:
                self.conn.close()
            except libvirt.libvirtError:
                pass
            self.conn = None

    def libvirt_version(self) -> Tuple[int, int, int]:
        v = self.conn.getLibVersion()
        return v // 1000000, v // 1000 % 1000, v % 1000

    def host(self) -> Tuple[int, int]:
        """(CPU threads, memory in MiB) of the machine the VMs run on."""
        info = self.conn.getInfo()
        return max(1, int(info[2])), int(info[1])

    # --- events ---

    def watch(self, callback: Callable[[str, str], None]) -> None:
        """Call callback(name, what) from libvirt's own thread on every lifecycle change and
        when the connection drops (name is '' then). Replaces polling."""
        self._callback = callback
        self._event_id = self.conn.domainEventRegisterAny(
            None, libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE, self._on_lifecycle, None)
        try:
            self.conn.registerCloseCallback(self._on_close, None)
            self._close_cb = True
        except libvirt.libvirtError:
            pass                    # the test driver has no connection to lose
        from . import eventloop
        if not eventloop.active() and not getattr(Manager, '_loop', None):
            def run():
                while True:
                    try:
                        libvirt.virEventRunDefaultImpl()
                    except libvirt.libvirtError:
                        break
            Manager._loop = threading.Thread(target=run, name='libvirt-events', daemon=True)
            Manager._loop.start()

    def _on_lifecycle(self, _conn, dom, event, _detail, _opaque):
        if self._callback:
            self._callback(dom.name(), str(event))

    def _on_close(self, _conn, _reason, _opaque):
        if self._callback:
            self._callback('', 'closed')

    # --- the list ---

    def lookup(self, name: str):
        try:
            return self.conn.lookupByName(name)
        except libvirt.libvirtError as exc:
            raise BoxesError(f"no machine called {name}") from exc

    @staticmethod
    def parse(dom_xml: str) -> ET.Element:
        return ET.fromstring(dom_xml)

    def xml_of(self, dom, inactive: bool = False) -> ET.Element:
        flags = libvirt.VIR_DOMAIN_XML_INACTIVE if inactive else 0
        return self.parse(dom.XMLDesc(flags))

    def info(self, dom) -> VmInfo:
        code, _reason = dom.state()
        root = self.xml_of(dom)
        vm = root.find(f'metadata/{{{NS}}}vm')
        preset = vm.get('preset', 'other') if vm is not None else 'other'
        drivers = vm is not None and vm.get('drivers') == 'yes'
        capacity = used = 0
        for disk in root.findall("devices/disk[@device='disk']"):
            source = disk.find('source')
            path = source.get('file') if source is not None else None
            if not path:
                continue
            try:
                cap, alloc, _phys = dom.blockInfo(path)
                capacity, used = capacity + cap, used + alloc
            except libvirt.libvirtError:
                pass
        usb = [f"{h.find('source/vendor').get('id', '')[2:]}:{h.find('source/product').get('id', '')[2:]}"
               for h in root.findall("devices/hostdev[@type='usb']")
               if h.find('source/vendor') is not None and h.find('source/product') is not None]
        memory_kib = int(_text(root, 'currentMemory', _text(root, 'memory', '0')) or 0)
        unit = (root.find('currentMemory') if root.find('currentMemory') is not None
                else root.find('memory'))
        memory_mb = _to_mib(memory_kib, unit.get('unit', 'KiB') if unit is not None else 'KiB')
        return VmInfo(name=dom.name(), uuid=dom.UUIDString(), state=_state(code),
                      cpus=int(_text(root, 'vcpu', '1') or 1), memory_mb=memory_mb, preset=preset,
                      disk_bytes=capacity, disk_used=used, drivers=drivers, usb=usb)

    def list_vms(self) -> List[VmInfo]:
        found = []
        for dom in self.conn.listAllDomains():
            try:
                found.append(self.info(dom))
            except libvirt.libvirtError as exc:
                log.warning("couldn't read %s: %s", dom.name(), exc)
        return sorted(found, key=lambda v: v.name.lower())

    # --- power ---

    def start(self, name: str) -> None:
        self._do(self.lookup(name).create, f"start {name}")

    def shutdown(self, name: str) -> None:
        self._do(self.lookup(name).shutdown, f"shut down {name}")

    def force_off(self, name: str) -> None:
        self._do(self.lookup(name).destroy, f"force off {name}")

    def pause(self, name: str) -> None:
        self._do(self.lookup(name).suspend, f"pause {name}")

    def resume(self, name: str) -> None:
        self._do(self.lookup(name).resume, f"resume {name}")

    def send_keys(self, name: str, keys: List[int]) -> None:
        """Keycodes (Linux input codes) pressed together, e.g. Ctrl+Alt+Del."""
        self._do(lambda: self.lookup(name).sendKey(libvirt.VIR_KEYCODE_SET_LINUX, 100, keys, 0),
                 f"send keys to {name}")

    def _do(self, call, what: str):
        try:
            return call()
        except libvirt.libvirtError as exc:
            log.warning("couldn't %s: %s", what, exc)
            raise BoxesError(f"couldn't {what}: {exc.get_error_message()}") from exc

    # --- storage ---

    def ensure_pool(self):
        """libvirt's 'default' directory pool; defined the way virt-manager does when missing."""
        try:
            pool = self.conn.storagePoolLookupByName(POOL_NAME)
        except libvirt.libvirtError:
            xml = (f"<pool type='dir'><name>{POOL_NAME}</name><target><path>{POOL_PATH}</path>"
                   "</target></pool>")
            pool = self._do(lambda: self.conn.storagePoolDefineXML(xml, 0), "define the storage pool")
            try:
                pool.build(0)
            except libvirt.libvirtError:
                pass                    # the folder is already there
            pool.setAutostart(1)
        if not pool.isActive():
            self._do(lambda: pool.create(0), "start the storage pool")
        return pool

    def pool_path(self) -> str:
        pool = self.ensure_pool()
        target = self.parse(pool.XMLDesc(0)).find('target/path')
        return target.text.strip() if target is not None and target.text else POOL_PATH

    def unique_volume(self, pool, wanted: str) -> str:
        names = set(pool.listVolumes())
        if wanted not in names:
            return wanted
        stem, dot, ext = wanted.rpartition('.')
        n = 2
        while f"{stem}-{n}{dot}{ext}" in names:
            n += 1
        return f"{stem}-{n}{dot}{ext}"

    def create_disk(self, vm_name: str, gigabytes: int, suffix: str = '') -> str:
        pool = self.ensure_pool()
        safe = re.sub(r'[^A-Za-z0-9._-]+', '-', vm_name).strip('-') or 'vm'
        name = self.unique_volume(pool, f"{safe}{suffix}.qcow2")
        volume = self._do(lambda: pool.createXML(xmlgen.volume_xml(name, gigabytes), 0),
                          "make the disk")
        return volume.path()

    def import_iso(self, path: str, progress: Optional[Callable[[int, int], None]] = None) -> str:
        """The path qemu should use for this ISO. A file qemu can already read stays where it
        is; one in a private folder (a home folder) is copied into the storage pool, through
        libvirt, because the qemu user can't walk into /home."""
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            raise BoxesError(f"{path} isn't a file")
        if _can_traverse(path):
            return path
        pool = self.ensure_pool()
        name = self.unique_volume(pool, re.sub(r'[^A-Za-z0-9._-]+', '-', os.path.basename(path)))
        size = os.path.getsize(path)
        xml = (f"<volume type='file'><name>{name}</name><capacity unit='bytes'>{size}</capacity>"
               "<target><format type='raw'/></target></volume>")
        volume = self._do(lambda: pool.createXML(xml, 0), "make room for the ISO")
        stream = self.conn.newStream(0)
        done = [0]
        try:
            volume.upload(stream, 0, size, 0)
            with open(path, 'rb') as source:
                def feed(_stream, nbytes, _opaque):
                    data = source.read(nbytes)
                    done[0] += len(data)
                    if progress:
                        progress(done[0], size)
                    return data
                stream.sendAll(feed, None)
            stream.finish()
        except (libvirt.libvirtError, OSError) as exc:
            try:
                stream.abort()
            except libvirt.libvirtError:
                pass
            try:
                volume.delete(0)
            except libvirt.libvirtError:
                pass
            raise BoxesError(f"couldn't copy the ISO into libvirt's storage: {exc}") from exc
        return volume.path()

    # --- making and deleting ---

    def vm_exists(self, name: str) -> bool:
        try:
            self.conn.lookupByName(name)
            return True
        except libvirt.libvirtError:
            return False

    def create_vm(self, spec: VmSpec, disk_gb: int,
                  progress: Optional[Callable[[int, int], None]] = None) -> VmInfo:
        if self.vm_exists(spec.name):
            raise BoxesError(f"there is already a machine called {spec.name}")
        if spec.iso_path:
            spec.iso_path = self.import_iso(spec.iso_path, progress)
        spec.disk_path = self.create_disk(spec.name, disk_gb)
        try:
            dom = self._do(lambda: self.conn.defineXML(xmlgen.build_xml(spec)),
                           f"define {spec.name}")
        except BoxesError:
            self._delete_path(spec.disk_path)
            raise
        log.info("made %s (%s, %d CPUs, %d MiB, %d GB)", spec.name, spec.preset, spec.cpus,
                 spec.memory_mb, disk_gb)
        return self.info(dom)

    def _delete_path(self, path: str) -> None:
        try:
            self.conn.storageVolLookupByPath(path).delete(0)
        except libvirt.libvirtError as exc:
            log.warning("couldn't delete %s: %s", path, exc)

    def delete_vm(self, name: str, delete_disks: bool) -> None:
        dom = self.lookup(name)
        root = self.xml_of(dom, inactive=True)
        files = [d.find('source').get('file') for d in root.findall("devices/disk[@device='disk']")
                 if d.find('source') is not None and d.find('source').get('file')]
        pool_dir = self.pool_path()
        # a disc image this app copied into the pool goes with the machine
        files += [d.find('source').get('file') for d in root.findall("devices/disk[@device='cdrom']")
                  if d.find('source') is not None and d.find('source').get('file', '').startswith(pool_dir + '/')
                  and d.find('source').get('file').endswith('.iso')
                  and not os.path.basename(d.find('source').get('file')).startswith('virtio-win')]
        if dom.isActive():
            self._do(dom.destroy, f"force {name} off")
        self._undefine(dom)
        if delete_disks:
            for path in files:
                self._delete_path(path)
        log.info("deleted %s (disks %s)", name, 'deleted' if delete_disks else 'kept')

    @staticmethod
    def _undefine(dom) -> None:
        flags = 0
        for const in ('VIR_DOMAIN_UNDEFINE_MANAGED_SAVE', 'VIR_DOMAIN_UNDEFINE_SNAPSHOTS_METADATA',
                      'VIR_DOMAIN_UNDEFINE_NVRAM', 'VIR_DOMAIN_UNDEFINE_TPM'):
            flags |= getattr(libvirt, const, 0)
        try:
            dom.undefineFlags(flags)
        except libvirt.libvirtError:
            try:
                dom.undefine()
            except libvirt.libvirtError as exc:
                raise BoxesError(f"couldn't delete the machine: {exc.get_error_message()}") from exc

    # --- editing the definition (the machine is off) ---

    def _edit(self, name: str, change: Callable[[ET.Element], None], needs_off: bool = True):
        dom = self.lookup(name)
        if needs_off and dom.isActive():
            raise BoxesError("Turn the machine off first: this change needs it.")
        root = self.xml_of(dom, inactive=True)
        change(root)
        self._do(lambda: self.conn.defineXML(ET.tostring(root, encoding='unicode')),
                 f"save the changes to {name}")

    def set_cpus(self, name: str, cpus: int) -> None:
        def change(root):
            root.find('vcpu').text = str(int(cpus))
            cpu = root.find('cpu')
            topo = cpu.find('topology') if cpu is not None else None
            if topo is not None:
                cpu.remove(topo)
        self._edit(name, change)

    def set_memory(self, name: str, memory_mb: int) -> None:
        _threads, host_mb = self.host()
        if memory_mb > host_mb // 2 and memory_mb > xmlgen.MIN_MEMORY_MB:
            raise BoxesError("A machine can have at most half of this PC's memory "
                             f"({host_mb // 2} MiB).")

        def change(root):
            for tag in ('memory', 'currentMemory'):
                node = root.find(tag)
                if node is not None:
                    node.text, node.attrib['unit'] = str(int(memory_mb)), 'MiB'
        self._edit(name, change)

    def set_boot_first(self, name: str, first: str) -> None:
        """'cdrom' or 'disk': which one the machine tries first."""
        def change(root):
            for dev in root.findall('devices/disk'):
                for old in dev.findall('boot'):
                    dev.remove(old)
            ordered = [('cdrom', 'cdrom'), ('disk', 'disk')]
            if first == 'disk':
                ordered.reverse()
            n = 1
            for kind, _ in ordered:
                for dev in root.findall(f"devices/disk[@device='{kind}']"):
                    if kind == 'cdrom' and dev.find('target').get('dev') != 'sdb':
                        continue            # only the install disc, not the driver disc
                    ET.SubElement(dev, 'boot', order=str(n))
                    n += 1
        self._edit(name, change)

    def boot_first(self, name: str) -> str:
        root = self.xml_of(self.lookup(name), inactive=True)
        for dev in root.findall('devices/disk'):
            boot = dev.find('boot')
            if boot is not None and boot.get('order') == '1':
                return 'cdrom' if dev.get('device') == 'cdrom' else 'disk'
        return 'disk'

    def add_disk(self, name: str, gigabytes: int) -> str:
        dom = self.lookup(name)
        if dom.isActive():
            raise BoxesError("Turn the machine off first: this change needs it.")
        root = self.xml_of(dom, inactive=True)
        used = {t.get('dev') for t in root.findall('devices/disk/target')} | {'sdb', 'sdc'}   # the two CD drives
        existing = root.find("devices/disk[@device='disk']/target")
        bus = existing.get('bus') if existing is not None else 'sata'
        prefix = 'vd' if bus == 'virtio' else 'sd'
        dev = next(f"{prefix}{c}" for c in 'abcdefghijklmnop' if f"{prefix}{c}" not in used)
        count = len(root.findall("devices/disk[@device='disk']"))
        path = self.create_disk(name, gigabytes, suffix=f"-disk{count + 1}")
        disk = ET.fromstring(xmlgen.disk_xml(path, dev, bus))

        def change(r):
            devices = r.find('devices')
            devices.insert(len(r.findall('devices/disk')), disk)
        self._edit(name, change)
        return path

    def cdrom(self, name: str, target: str = 'sdb') -> str:
        root = self.xml_of(self.lookup(name), inactive=True)
        for dev in root.findall("devices/disk[@device='cdrom']"):
            if dev.find('target').get('dev') == target:
                source = dev.find('source')
                return source.get('file', '') if source is not None else ''
        return ''

    def set_cdrom(self, name: str, iso_path: Optional[str], target: str = 'sdb',
                  progress: Optional[Callable[[int, int], None]] = None) -> None:
        """Put a disc in the drive (or take it out when iso_path is empty). Works while the
        machine runs: the drive's door is simply opened."""
        dom = self.lookup(name)
        path = self.import_iso(iso_path, progress) if iso_path else None
        root = self.xml_of(dom, inactive=True)
        present = any(d.find('target').get('dev') == target
                      for d in root.findall("devices/disk[@device='cdrom']"))
        if not present and dom.isActive():
            raise BoxesError("Turn the machine off first: this change needs it.")
        drive = ET.fromstring(xmlgen.cdrom_xml(target, path))

        def change(r):
            devices = r.find('devices')
            for old in r.findall("devices/disk[@device='cdrom']"):
                if old.find('target').get('dev') == target:
                    for extra in old.findall('boot') + old.findall('address'):
                        drive.append(extra)         # keep its boot order and its slot
                    devices.remove(old)
            devices.insert(len(r.findall('devices/disk')), drive)
        self._edit(name, change, needs_off=False)
        if dom.isActive():
            self._do(lambda: dom.updateDeviceFlags(xmlgen.cdrom_xml(target, path),
                                                   libvirt.VIR_DOMAIN_AFFECT_LIVE),
                     "change the disc")

    def set_network(self, name: str, on: bool) -> None:
        dom = self.lookup(name)

        def change(root):
            nic = root.find('devices/interface')
            if nic is None:
                raise BoxesError("This machine has no network card.")
            for old in nic.findall('link'):
                nic.remove(old)
            if not on:
                ET.SubElement(nic, 'link', state='down')
        self._edit(name, change, needs_off=False)
        if dom.isActive():
            nic = self.xml_of(dom).find('devices/interface')
            for old in nic.findall('link'):
                nic.remove(old)
            if not on:
                ET.SubElement(nic, 'link', state='down')
            xml = ET.tostring(nic, encoding='unicode')
            self._do(lambda: dom.updateDeviceFlags(xml, libvirt.VIR_DOMAIN_AFFECT_LIVE),
                     "change the network")

    def network_on(self, name: str) -> bool:
        root = self.xml_of(self.lookup(name), inactive=True)
        link = root.find('devices/interface/link')
        return link is None or link.get('state') != 'down'

    def attach_virtio_win(self, name: str, iso_path: str) -> None:
        """The driver disc as a second CD drive (sdc)."""
        self.set_cdrom(name, iso_path, target='sdc')

    # --- snapshots ---

    def snapshots(self, name: str) -> List[SnapshotInfo]:
        dom = self.lookup(name)
        try:
            current = dom.snapshotCurrent(0).getName()
        except libvirt.libvirtError:
            current = ''
        found = []
        for snap in dom.listAllSnapshots(0):
            root = self.parse(snap.getXMLDesc(0))
            memory = root.find('memory')
            found.append(SnapshotInfo(
                name=snap.getName(), created=float(_text(root, 'creationTime', '0') or 0),
                running=memory is not None and memory.get('snapshot', 'no') != 'no',
                current=snap.getName() == current, description=_text(root, 'description')))
        return sorted(found, key=lambda s: s.created)

    def take_snapshot(self, name: str, label: str) -> str:
        """Takes an external snapshot (UEFI machines can't have internal ones): memory and disks
        when the machine runs, disks only when it is off. The name is the label and the date."""
        dom = self.lookup(name)
        stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        label = re.sub(r'[/\n]+', ' ', label).strip() or 'Snapshot'
        snap_name = f"{label} ({stamp})"
        if any(s.name == snap_name for s in self.snapshots(name)):
            snap_name = f"{label} ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
        root = self.xml_of(dom, inactive=True)
        disks = ''.join(f"<disk name='{d.find('target').get('dev')}' snapshot='external'/>"
                        for d in root.findall("devices/disk[@device='disk']"))
        flags = 0
        external = not self.uri.startswith('test:')     # the test driver has no external ones
        if not external:
            memory, disks = '', ''
        elif dom.isActive():
            flags = libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_ATOMIC
            pool_dir = self.pool_path()
            safe = re.sub(r'[^A-Za-z0-9._-]+', '-', f"{name}-{snap_name}")
            memory = f"<memory snapshot='external' file={_q(os.path.join(pool_dir, safe + '.mem'))}/>"
        else:
            flags = libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_ATOMIC | libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_DISK_ONLY
            memory = "<memory snapshot='no'/>"
        xml = (f"<domainsnapshot><name>{_esc(snap_name)}</name>{memory}"
               f"<disks>{disks}</disks></domainsnapshot>")
        self._do(lambda: dom.snapshotCreateXML(xml, flags), f"take a snapshot of {name}")
        log.info("snapshot %s of %s", snap_name, name)
        return snap_name

    def revert_snapshot(self, name: str, snap_name: str) -> None:
        dom = self.lookup(name)
        snap = self._do(lambda: dom.snapshotLookupByName(snap_name, 0), "find the snapshot")
        self._do(lambda: dom.revertToSnapshot(snap, 0), f"go back to {snap_name}")

    def delete_snapshot(self, name: str, snap_name: str) -> None:
        """Forgets the snapshot. libvirt can't merge an external snapshot's disk back by itself,
        so the overlay file stays on disk (the machine keeps using it)."""
        dom = self.lookup(name)
        snap = self._do(lambda: dom.snapshotLookupByName(snap_name, 0), "find the snapshot")
        flags = 0 if self.uri.startswith('test:') else libvirt.VIR_DOMAIN_SNAPSHOT_DELETE_METADATA_ONLY
        self._do(lambda: snap.delete(flags), f"delete {snap_name}")

    # --- USB ---

    def usb_list(self, sysfs: str = '/sys') -> List[usbdev.UsbDevice]:
        return usbdev.list_devices(sysfs)

    def usb_give(self, name: str, device: usbdev.UsbDevice) -> None:
        if not device.allowed:
            raise BoxesError(f"{device.name} can't be given away: it holds this PC's "
                             "system or D: drive, or is mounted here.")
        dom = self.lookup(name)
        if not dom.isActive():
            raise BoxesError("Start the machine first: a USB device goes to a running machine.")
        self._do(lambda: dom.attachDeviceFlags(usbdev.hostdev_xml(device),
                                               libvirt.VIR_DOMAIN_AFFECT_LIVE),
                 f"give {device.name} to {name}")

    def usb_take_back(self, name: str, device: usbdev.UsbDevice) -> None:
        dom = self.lookup(name)
        self._do(lambda: dom.detachDeviceFlags(usbdev.hostdev_xml(device),
                                               libvirt.VIR_DOMAIN_AFFECT_LIVE),
                 f"take {device.name} back from {name}")

    # --- the screen ---

    def graphics_fd(self, name: str) -> int:
        """A file descriptor on the machine's SPICE display; libvirt hands it over, so no
        port or socket file is needed."""
        dom = self.lookup(name)
        return self._do(lambda: dom.openGraphicsFD(0, 0), f"open {name}'s screen")


def _q(value: str) -> str:
    from xml.sax.saxutils import quoteattr
    return quoteattr(value)


def _esc(value: str) -> str:
    from xml.sax.saxutils import escape
    return escape(value)


def _to_mib(amount: int, unit: str) -> int:
    """libvirt writes memory in KiB unless the XML says otherwise."""
    factor = {'kib': 1 / 1024, 'k': 1 / 1024, 'mib': 1, 'm': 1, 'gib': 1024, 'g': 1024,
              'b': 1 / 1048576, 'bytes': 1 / 1048576}.get(unit.lower(), 1 / 1024)
    return int(round(amount * factor))


def download_virtio_win(manager: Manager, progress: Optional[Callable[[int, int], None]] = None) -> Tuple[str, str, bool]:
    """Download the driver ISO, check it, copy it into libvirt's pool and remove the download.
    Returns (path qemu reads, sha256, pinned)."""
    path, digest, pinned = virtio.download(cache_dir(), progress)
    in_pool = manager.import_iso(path)
    if in_pool != path:
        os.unlink(path)
    return in_pool, digest, pinned
