"""udisks2 over D-Bus: the service GNOME Disks uses. udisks asks polkit before each
change, so the password prompt is the system's and Spark Disks never runs as root.

`Backend` is the list of things ops.py may ask for; `Udisks` is the real one (PyGObject's Gio,
imported only when it is used so the tests and --version don't need it). Tests use a fake that
records its calls. Nothing in this file decides whether an action is allowed: that is safety.py,
checked again by ops.py before any of these methods runs."""

import os
import re
from typing import Any, Dict, List, Optional, Tuple

BUS = 'org.freedesktop.UDisks2'
ROOT = '/org/freedesktop/UDisks2'
IFACE = 'org.freedesktop.UDisks2'

GPT_DATA = 'ebd0a0a2-b9e5-4433-87c0-68b6b72699c7'      # Windows and cross-platform file systems
GPT_LINUX = '0fc63daf-8483-4772-8e79-3d69d8477de4'
GPT_SWAP = '0657fd6d-a4ab-43c4-84e5-0933c84b4f4f'

# libblockdev's resize capability bits (what Manager.CanResize reports)
OFFLINE_SHRINK, OFFLINE_GROW, ONLINE_SHRINK, ONLINE_GROW = 2, 4, 8, 16


class DiskError(Exception):
    """udisks said no, or could not do it. `key` is a text.py key; `detail` is udisks' own words."""

    def __init__(self, key: str, detail: str = ''):
        super().__init__(detail or key)
        self.key, self.detail = key, detail


def partition_type(table: str, fstype: str) -> str:
    """The partition type id for a new partition of this file system."""
    if table == 'dos':
        return {'ntfs': '0x07', 'exfat': '0x07', 'vfat': '0x0c', 'swap': '0x82'}.get(fstype, '0x83')
    return {'ntfs': GPT_DATA, 'exfat': GPT_DATA, 'vfat': GPT_DATA,
            'swap': GPT_SWAP}.get(fstype, GPT_LINUX)


class Backend:
    """What the rest of the app may ask a disk service to do. Every path is a /dev/ path."""

    def mount(self, dev: str) -> str: raise NotImplementedError
    def unmount(self, dev: str) -> None: raise NotImplementedError
    def format(self, dev: str, fstype: str, label: str = '', zero: bool = False,
               own: bool = True) -> None: raise NotImplementedError
    def new_table(self, dev: str, table: str) -> None: raise NotImplementedError
    def create_partition(self, disk: str, offset: int, size: int, fstype: str, label: str,
                         table: str) -> None: raise NotImplementedError
    def delete_partition(self, dev: str) -> None: raise NotImplementedError
    def resize_partition(self, dev: str, size: int) -> None: raise NotImplementedError
    def resize_filesystem(self, dev: str, size: int) -> None: raise NotImplementedError
    def can_resize(self, fstype: str) -> Tuple[bool, int, str]: raise NotImplementedError
    def formats(self) -> List[str]: raise NotImplementedError
    def eject(self, dev: str) -> None: raise NotImplementedError
    def open_device(self, dev: str, mode: str) -> int: raise NotImplementedError
    def smart(self, dev: str) -> Dict[str, Any]: raise NotImplementedError
    def smart_update(self, dev: str) -> None: raise NotImplementedError
    def smart_selftest(self, dev: str) -> None: raise NotImplementedError


def _friendly(message: str) -> Tuple[str, str]:
    """(text key, udisks' words) for a D-Bus error message."""
    detail = re.sub(r'^GDBus\.Error:[\w.]+: ?', '', message or '').strip()
    text = (message or '')
    if 'NotAuthorizedDismissed' in text or 'Cancelled' in text or 'dismissed' in text.lower():
        return 'err.cancelled', detail
    if 'NotAuthorized' in text:
        return 'err.not_authorized', detail
    if 'DeviceBusy' in text or 'busy' in text.lower():
        return 'err.busy', detail
    if 'NotSupported' in text:
        return 'err.not_supported', detail
    return 'err.failed', detail


class Udisks(Backend):
    def __init__(self):
        import gi
        gi.require_version('Gio', '2.0')
        from gi.repository import Gio, GLib
        self.Gio, self.GLib = Gio, GLib
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error as exc:
            raise DiskError('err.no_udisks', str(exc))
        self.flags = Gio.DBusCallFlags.ALLOW_INTERACTIVE_AUTHORIZATION

    # --- plumbing
    def _call(self, path: str, iface: str, method: str, signature: str = '', args: tuple = (),
              reply: Optional[str] = None, fds: Any = None, timeout: int = 2147483647):
        # no timeout: a password prompt or a large format can take minutes (the UI thread is free)
        GLib, Gio = self.GLib, self.Gio
        params = GLib.Variant(f'({signature})', args) if signature or args else None
        try:
            if fds is not None:
                result, _out = self.bus.call_with_unix_fd_list_sync(
                    BUS, path, iface, method, params, GLib.VariantType(reply) if reply else None,
                    self.flags, timeout, fds, None)
                return result, _out
            result = self.bus.call_sync(BUS, path, iface, method, params,
                                        GLib.VariantType(reply) if reply else None,
                                        self.flags, timeout, None)
            return result.unpack() if result is not None else None
        except GLib.Error as exc:
            key, detail = _friendly(exc.message)
            raise DiskError(key, detail) from None

    def _props(self, path: str, iface: str) -> Dict[str, Any]:
        value = self._call(path, 'org.freedesktop.DBus.Properties', 'GetAll', 's', (iface,),
                           '(a{sv})')
        return value[0] if value else {}

    @staticmethod
    def _block(dev: str) -> str:
        return f'{ROOT}/block_devices/{os.path.basename(dev)}'

    def _opts(self, **kw) -> Dict[str, Any]:
        GLib = self.GLib
        out = {}
        for key, value in kw.items():
            key = key.replace('_', '-')
            if isinstance(value, bool):
                out[key] = GLib.Variant('b', value)
            elif isinstance(value, int):
                out[key] = GLib.Variant('i', value)
            else:
                out[key] = GLib.Variant('s', str(value))
        return out

    # --- file systems
    def mount(self, dev: str) -> str:
        value = self._call(self._block(dev), f'{IFACE}.Filesystem', 'Mount', 'a{sv}',
                           (self._opts(),), '(s)')
        return value[0]

    def unmount(self, dev: str) -> None:
        self._call(self._block(dev), f'{IFACE}.Filesystem', 'Unmount', 'a{sv}', (self._opts(),))

    def format(self, dev: str, fstype: str, label: str = '', zero: bool = False,
               own: bool = True) -> None:
        options = {}
        if label:
            options['label'] = label
        if zero:
            options['erase'] = 'zero'
        if own and fstype in ('ext2', 'ext3', 'ext4', 'xfs', 'btrfs'):
            options['take_ownership'] = True
        self._call(self._block(dev), f'{IFACE}.Block', 'Format', 'sa{sv}',
                   (fstype, self._opts(**options)))

    def new_table(self, dev: str, table: str) -> None:
        self._call(self._block(dev), f'{IFACE}.Block', 'Format', 'sa{sv}',
                   (table, self._opts()))

    def create_partition(self, disk: str, offset: int, size: int, fstype: str, label: str,
                         table: str) -> None:
        options = {'label': label} if label else {}
        fs = '' if fstype == 'empty' else fstype
        if fs:
            self._call(self._block(disk), f'{IFACE}.PartitionTable', 'CreatePartitionAndFormat',
                       'ttssa{sv}sa{sv}',
                       (offset, size, partition_type(table, fs), '', self._opts(),
                        fs, self._opts(**options)))
        else:
            self._call(self._block(disk), f'{IFACE}.PartitionTable', 'CreatePartition',
                       'ttssa{sv}', (offset, size, partition_type(table, ''), '', self._opts()))

    def delete_partition(self, dev: str) -> None:
        self._call(self._block(dev), f'{IFACE}.Partition', 'Delete', 'a{sv}', (self._opts(),))

    def resize_partition(self, dev: str, size: int) -> None:
        self._call(self._block(dev), f'{IFACE}.Partition', 'Resize', 'ta{sv}',
                   (size, self._opts()))

    def resize_filesystem(self, dev: str, size: int) -> None:
        self._call(self._block(dev), f'{IFACE}.Filesystem', 'Resize', 'ta{sv}',
                   (size, self._opts()))

    def can_resize(self, fstype: str) -> Tuple[bool, int, str]:
        try:
            ok, mode, tool = self._call(f'{ROOT}/Manager', f'{IFACE}.Manager', 'CanResize', 's',
                                        (fstype,), '((bts))')[0]
        except DiskError:
            return False, 0, ''
        return bool(ok), int(mode), tool

    def formats(self) -> List[str]:
        """The file systems udisks says it can make here (mkfs tool installed)."""
        supported = self._props(f'{ROOT}/Manager', f'{IFACE}.Manager').get('SupportedFilesystems', [])
        out = []
        for fs in supported:
            try:
                ok, _why = self._call(f'{ROOT}/Manager', f'{IFACE}.Manager', 'CanFormat', 's',
                                      (fs,), '((bs))')[0]
            except DiskError:
                ok = False
            if ok:
                out.append(fs)
        return out

    # --- drives
    def _drive(self, dev: str) -> str:
        drive = self._props(self._block(dev), f'{IFACE}.Block').get('Drive', '/')
        if not drive or drive == '/':
            raise DiskError('err.not_supported', 'no drive behind ' + dev)
        return drive

    def eject(self, dev: str) -> None:
        drive = self._drive(dev)
        self._call(drive, f'{IFACE}.Drive', 'Eject', 'a{sv}', (self._opts(),))
        try:
            self._call(drive, f'{IFACE}.Drive', 'PowerOff', 'a{sv}', (self._opts(),))
        except DiskError:
            pass                          # a stick that can't power off is still ejected

    def open_device(self, dev: str, mode: str) -> int:
        """A file descriptor for the block device, opened by udisks ('r' or 'w'); the caller
        closes it. O_EXCL makes the kernel refuse when something has the device mounted."""
        Gio, GLib = self.Gio, self.GLib
        options = self._opts(flags=os.O_EXCL) if mode == 'w' else self._opts()
        try:
            result, out = self._call(self._block(dev), f'{IFACE}.Block', 'OpenDevice', 'sa{sv}',
                                     (mode, options), '(h)', fds=Gio.UnixFDList.new())
        except DiskError as first:
            if first.key in ('err.cancelled', 'err.not_authorized') or mode != 'w':
                raise
            result, out = self._call(self._block(dev), f'{IFACE}.Block', 'OpenDevice', 'sa{sv}',
                                     (mode, self._opts()), '(h)', fds=Gio.UnixFDList.new())
        return out.get(result.unpack()[0])

    # --- SMART
    def smart(self, dev: str) -> Dict[str, Any]:
        drive = self._drive(dev)
        for kind, iface in (('ata', f'{IFACE}.Drive.Ata'), ('nvme', f'{IFACE}.NVMe.Controller')):
            try:
                props = self._props(drive, iface)
            except DiskError:
                continue
            if not props:
                continue
            attributes: Any = [] if kind == 'ata' else {}
            try:
                value = self._call(drive, iface, 'SmartGetAttributes', 'a{sv}', (self._opts(),),
                                   '(a(ysqiiixia{sv}))' if kind == 'ata' else '(a{sv})')
                attributes = value[0]
                if kind == 'nvme':
                    attributes = {k: v for k, v in attributes.items()}
            except DiskError:
                pass
            return {'kind': kind, 'props': {k: v for k, v in props.items()},
                    'attributes': attributes}
        return {'kind': 'none', 'props': {}, 'attributes': []}

    def smart_update(self, dev: str) -> None:
        drive = self._drive(dev)
        try:
            self._call(drive, f'{IFACE}.Drive.Ata', 'SmartUpdate', 'a{sv}',
                       (self._opts(nowakeup=True),))
        except DiskError as exc:
            if exc.key in ('err.cancelled', 'err.not_authorized'):
                raise
            self._call(drive, f'{IFACE}.NVMe.Controller', 'SmartUpdate', 'a{sv}',
                       (self._opts(),))

    def smart_selftest(self, dev: str) -> None:
        drive = self._drive(dev)
        try:
            self._call(drive, f'{IFACE}.Drive.Ata', 'SmartSelftestStart', 'sa{sv}',
                       ('short', self._opts()))
        except DiskError as exc:
            if exc.key in ('err.cancelled', 'err.not_authorized'):
                raise
            self._call(drive, f'{IFACE}.NVMe.Controller', 'SmartSelftestStart', 'sa{sv}',
                       ('short', self._opts()))


class Unavailable(Backend):
    """Stands in when udisks can't be reached: the window still lists drives (lsblk) but every
    change says why it can't happen."""

    def __init__(self, error: DiskError):
        self.error = error

    def _fail(self, *_args, **_kw):
        raise self.error

    def formats(self) -> List[str]:
        return []


for _name in ('mount', 'unmount', 'format', 'new_table', 'create_partition', 'delete_partition',
              'resize_partition', 'resize_filesystem', 'can_resize', 'eject', 'open_device',
              'smart', 'smart_update', 'smart_selftest'):
    setattr(Unavailable, _name, Unavailable._fail)
