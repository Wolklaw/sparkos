"""Spark Welcome tests. Plain unittest:

    python -m unittest discover -s files/spark-welcome/tests -v

Logic tests run anywhere (the folder tests make symlinks and skip that part where the OS
won't). UI tests need a display (on CI: xvfb-run) and open real windows for a few seconds.
Nothing here touches the network or installs anything: flatpak is replaced by a fake.
"""

import glob
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from typing import Optional
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
sys.path.insert(0, APP_DIR)
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
    os.environ[var] = tempfile.mkdtemp(prefix=f'spark-welcome-{var.lower()}-')
os.environ['SPARK_WELCOME_TEST'] = '1'
os.environ['SPARK_WELCOME_REDUCED_MOTION'] = '0'

import sparkwelcome  # noqa: E402
from sparkwelcome import catalog, checks, core, flatpak, strings, windows  # noqa: E402

FROM = strings.t('win.renamed')       # copies that would clash: 'x (from Windows).txt'

logging.getLogger(sparkwelcome.APP_SLUG).addHandler(logging.NullHandler())

FAKE_FLATPAK = r'''
import os, sys, time
log = os.environ['FAKE_FLATPAK_LOG']
with open(log, 'a') as f:
    f.write(' '.join(sys.argv[1:]) + '\n')
args = sys.argv[1:]
if args[0] == 'remotes':
    sys.exit(0)                       # no user remotes yet
if args[0] == 'remote-add':
    sys.exit(0)
if args[0] == 'install':
    app = args[-1]
    if 'Broken' in app:
        print('Looking for matches…', flush=True)
        print('error: No remote refs found for ‘%s’' % app, flush=True)
        sys.exit(1)
    for pct in (5, 40, 100):
        sys.stdout.write('Installing 1/2… ███ %d%%  1.2 MB/s\r' % pct)
        sys.stdout.flush()
        time.sleep(0.05)
    print('\nInstallation complete.')
    sys.exit(0)
sys.exit(3)
'''


def touch(path: str, data: bytes = b'x') -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)
    return path


def read(path: str) -> bytes:
    with open(path, 'rb') as f:
        return f.read()


def text_value(text: str):
    return (windows.REG_EXPAND_SZ, (text + '\0').encode('utf-16-le'))


def uuid_bytes(guid: str) -> bytes:
    import uuid
    return uuid.UUID(guid).bytes_le


def make_hive(path: str, key_path: str, values) -> None:
    """A Windows registry file holding one key (key_path, under a root key) with values
    {name: (type, data)}, in the same layout Windows writes."""
    import struct
    cells = bytearray(b'hbin' + b'\0' * 28)

    def add(data: bytes) -> int:
        offset, size = len(cells), len(data) + 4
        size += (-size) % 8
        cells.extend(struct.pack('<i', -size) + data + b'\0' * (size - 4 - len(data)))
        return offset

    def nk(name: str, subkeys: Optional[int], value_list: Optional[int], n_values: int) -> int:
        raw = bytearray(0x4C)
        raw[0:2] = b'nk'
        struct.pack_into('<H', raw, 2, 0x20)
        struct.pack_into('<I', raw, 0x14, 1 if subkeys is not None else 0)
        struct.pack_into('<I', raw, 0x1C, subkeys if subkeys is not None else 0xFFFFFFFF)
        struct.pack_into('<I', raw, 0x24, n_values)
        struct.pack_into('<I', raw, 0x28, value_list if value_list is not None else 0xFFFFFFFF)
        struct.pack_into('<H', raw, 0x48, len(name))
        return add(bytes(raw) + name.encode('latin-1'))

    offsets = []
    for name, (vtype, data) in values.items():
        data_cell = add(data)
        offsets.append(add(b'vk' + struct.pack('<HIIIHH', len(name), len(data), data_cell,
                                               vtype, 1, 0) + name.encode('latin-1')))
    value_list = add(b''.join(struct.pack('<I', o) for o in offsets))
    parts = key_path.split('\\')
    child = nk(parts[-1], None, value_list, len(offsets))
    for name in reversed(['ROOT'] + parts[:-1]):
        sig = b'li' if len(name) % 2 else b'lh'       # both list kinds Windows uses
        entry = struct.pack('<I', child) + (b'' if sig == b'li' else b'\0' * 4)
        child = nk(name, add(sig + struct.pack('<H', 1) + entry), None, 0)
    header = bytearray(0x1000)
    header[0:4] = b'regf'
    struct.pack_into('<I', header, 0x24, child)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(bytes(header) + bytes(cells))


def try_symlink(target: str, link: str) -> bool:
    try:
        os.symlink(target, link, target_is_directory=os.path.isdir(target))
        return True
    except (OSError, NotImplementedError):
        return False


# ─── Catalog ──────────────────────────────────────────────────

class CatalogTests(unittest.TestCase):
    def test_the_list_loads(self):
        cat = catalog.load()
        ids = [e.id for e in cat.launchers]
        self.assertEqual(ids, ['com.valvesoftware.Steam', 'com.heroicgameslauncher.hgl',
                               'net.lutris.Lutris', 'net.davidotek.pupgui2'])
        names = {e.name for e in cat.all()}
        for wanted in ('Discord', 'Signal', 'Telegram', 'Spotify', 'OBS Studio', 'Zoom', 'GIMP',
                       'Krita', 'Kdenlive', 'Blender', 'KCalc', 'Bitwarden'):
            self.assertIn(wanted, names)
        for entry in cat.all():
            if entry.web:
                self.assertTrue(catalog.WEB_ID.match(entry.id), entry.id)
                self.assertTrue(entry.web.startswith('https://'), entry.id)
            else:
                self.assertTrue(catalog.FLATPAK_ID.match(entry.id), entry.id)
            self.assertTrue(entry.by and entry.blurb, entry.id)
        self.assertEqual(cat.find('org.gimp.GIMP').name, 'GIMP')
        self.assertEqual(cat.find('web.amazon-music').web, 'https://music.amazon.ca')

    def test_web_apps(self):
        """Amazon Music has no Linux app: Spark Welcome adds a menu entry for its web player."""
        good = {'id': 'web.amazon-music', 'name': 'Amazon Music', 'by': 'Amazon', 'blurb': 'C',
                'web': 'https://music.amazon.ca'}
        self.assertEqual(catalog.parse({'launchers': [good]}).launchers[0].web,
                         'https://music.amazon.ca')
        for bad in (dict(good, web='http://music.amazon.ca'), dict(good, id='com.amazon.Music'),
                    dict(good, web='https://x.ca" Exec=rm')):
            with self.assertRaises(catalog.CatalogError):
                catalog.parse({'launchers': [bad]})
        data = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {'XDG_DATA_HOME': data}):
            inst = flatpak.Installer(flatpak=['no-flatpak-here'])
            inst.add('web.amazon-music', 'Amazon Music', 'https://music.amazon.ca')
            self.assertTrue(inst.wait(10))
            inst.poll()
            self.assertEqual(inst.jobs['web.amazon-music'].state, flatpak.DONE)
            entry = read(flatpak.web_entry_path('web.amazon-music')).decode()
            self.assertIn('Name=Amazon Music\n', entry)
            self.assertIn('Exec=xdg-open https://music.amazon.ca\n', entry)
            self.assertIn('web.amazon-music', flatpak.installed_ids(['no-flatpak-here']))

    def test_bad_lists_are_refused(self):
        good = {'id': 'org.example.App', 'name': 'A', 'by': 'B', 'blurb': 'C'}
        with self.assertRaises(catalog.CatalogError):
            catalog.parse({'launchers': [good, dict(good)]})            # listed twice
        with self.assertRaises(catalog.CatalogError):
            catalog.parse({'launchers': [dict(good, id='steam')]})       # not an app id
        with self.assertRaises(catalog.CatalogError):
            catalog.parse({'launchers': [dict(good, by='')]})            # whose app?
        with self.assertRaises(catalog.CatalogError):
            catalog.parse({'launchers': []})
        path = os.path.join(tempfile.mkdtemp(), 'apps.json')
        touch(path, b'{not json')
        with self.assertRaises(catalog.CatalogError):
            catalog.load(path)

    def test_french_falls_back(self):
        entry = catalog.Entry('org.a.B', 'Name', 'Me', 'Blurb', blurb_fr='Texte')
        self.assertEqual(entry.text('fr'), 'Texte')
        self.assertEqual(entry.label('fr'), 'Name')


# ─── Flatpak ──────────────────────────────────────────────────

class FlatpakTests(unittest.TestCase):
    def test_commands(self):
        self.assertEqual(flatpak.install_cmd('com.valvesoftware.Steam'),
                         ['flatpak', 'install', '--user', '--noninteractive', 'flathub',
                          'com.valvesoftware.Steam'])
        self.assertEqual(flatpak.remote_add_cmd(),
                         ['flatpak', 'remote-add', '--user', '--if-not-exists', 'flathub',
                          'https://dl.flathub.org/repo/flathub.flatpakrepo'])
        self.assertEqual(flatpak.remotes_cmd()[-2:], ['--user', '--columns=name'])

    def test_parsing(self):
        self.assertTrue(flatpak.has_remote('fedora\nflathub\n'))
        self.assertFalse(flatpak.has_remote('flathub-beta\n'))
        self.assertEqual(flatpak.parse_list('org.a.B\ncom.c.D\n\n'), {'org.a.B', 'com.c.D'})
        self.assertEqual(flatpak.parse_progress('Installing 2/5… ████  45%  3.1 MB/s'),
                         (45, (2, 5)))
        self.assertEqual(flatpak.parse_progress('Looking for matches…'), (None, None))
        self.assertEqual(flatpak.error_from(['a', 'error: No remote refs found', '']),
                         'No remote refs found')
        self.assertEqual(flatpak.error_from(['a', 'last words']), 'last words')

    def test_installer_queue(self):
        folder = tempfile.mkdtemp()
        fake = touch(os.path.join(folder, 'fake_flatpak.py'), FAKE_FLATPAK.encode('utf-8'))
        log_file = os.path.join(folder, 'calls.log')
        changes = []
        with mock.patch.dict(os.environ, {'FAKE_FLATPAK_LOG': log_file,
                                          'PYTHONIOENCODING': 'utf-8'}):
            inst = flatpak.Installer([sys.executable, fake], on_change=changes.append)
            inst.add('org.example.Good', 'Good')
            inst.add('org.example.Broken', 'Broken')
            inst.add('org.example.Good', 'Good')                  # already queued: ignored
            deadline = time.time() + 30
            while inst.busy() and time.time() < deadline:
                inst.poll()
                time.sleep(0.05)
            inst.poll()
            self.assertTrue(inst.wait(10))
            self.assertEqual(inst.jobs['org.example.Good'].state, flatpak.DONE)
            broken = inst.jobs['org.example.Broken']
            self.assertEqual(broken.state, flatpak.FAILED)
            self.assertIn('No remote refs found', broken.error)
            self.assertIn(100, [c.percent for c in changes if c.app_id == 'org.example.Good'])
            # retry runs it again, and a new worker starts after the first one ended
            inst.retry('org.example.Broken')
            deadline = time.time() + 30
            while inst.busy() and time.time() < deadline:
                time.sleep(0.05)
            self.assertEqual(inst.jobs['org.example.Broken'].state, flatpak.FAILED)
        with open(log_file) as f:
            calls = f.read().splitlines()
        self.assertEqual(sum(1 for c in calls if c.startswith('remote-add')), 1)
        self.assertEqual(calls[0], 'remotes --user --columns=name')
        self.assertIn('install --user --noninteractive flathub org.example.Good', calls)
        self.assertEqual(sum(1 for c in calls if c.startswith('install')), 3)


# ─── Files from Windows ───────────────────────────────────────

LSBLK = json.dumps({"blockdevices": [
    {"name": "nvme0n1", "path": "/dev/nvme0n1", "fstype": None, "label": None,
     "mountpoint": None, "size": 1000204886016, "children": [
         {"name": "nvme0n1p1", "path": "/dev/nvme0n1p1", "fstype": "vfat", "label": None,
          "mountpoint": "/boot/efi", "size": 104857600},
         {"name": "nvme0n1p3", "path": "/dev/nvme0n1p3", "fstype": "ntfs", "label": "Windows",
          "mountpoint": None, "size": 500000000000},
         {"name": "nvme0n1p4", "path": "/dev/nvme0n1p4", "fstype": "BitLocker", "label": None,
          "mountpoint": None, "size": 200000000000}]},
    {"name": "sda", "fstype": None, "children": [
        {"name": "sda1", "fstype": "ntfs", "label": "Games", "mountpoint": "/run/media/u/Games",
         "size": "2000000000000"}]}]})


class WindowsTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-welcome-test-')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_partitions(self):
        parts = windows.parse_lsblk(LSBLK)
        self.assertEqual([p.name for p in parts], ['nvme0n1p3', 'nvme0n1p4', 'sda1'])
        self.assertFalse(parts[0].locked)
        self.assertTrue(parts[1].locked)
        self.assertEqual(parts[2].path, '/dev/sda1')
        self.assertEqual(parts[2].mountpoint, '/run/media/u/Games')
        self.assertEqual(parts[2].size, 2000000000000)
        self.assertEqual(windows.parse_lsblk('not json'), [])
        self.assertEqual(windows.parse_mount_output('Mounted /dev/sda3 at /run/media/u/Win.\n'),
                         '/run/media/u/Win')
        self.assertEqual(strings.t('win.err.hibernated'), windows.explain_mount_error(
            'Error mounting: wrong fs type... The disk contains an unclean file system (0, 0).'))
        locked = windows.Partition('x', '/dev/x', 'BitLocker', '', '', 1)
        point, problem = windows.mount_read_only(locked)
        self.assertIsNone(point)
        self.assertIn('BitLocker', problem)
        mounted = windows.Partition('y', '/dev/y', 'ntfs', '', '/mnt/win', 1)
        self.assertEqual(windows.mount_read_only(mounted), ('/mnt/win', ''))

    def _windows_tree(self):
        root = os.path.join(self.dir, 'win')
        users = os.path.join(root, 'Users')
        touch(os.path.join(users, 'Ann', 'Documents', 'letter.txt'), b'hello')
        touch(os.path.join(users, 'Ann', 'Music', 'Band', 'song.mp3'), b'12345678')
        touch(os.path.join(users, 'Ann', 'Desktop', 'desktop.ini'))      # clutter only
        os.makedirs(os.path.join(users, 'Ann', 'Pictures', 'Empty'))      # folders, no files
        touch(os.path.join(users, 'Ann', 'Downloads', 'setup.exe'), b'MZ')
        touch(os.path.join(users, 'Bob', 'videos', 'clip.mp4'), b'vid')   # lower-case name
        touch(os.path.join(users, 'Public', 'Documents', 'shared.txt'))
        touch(os.path.join(users, 'Default', 'Documents', 'template.txt'))
        os.makedirs(os.path.join(users, 'Empty', 'Documents'))
        touch(os.path.join(users, 'desktop.ini'))
        # junctions show up as symlinks on Linux
        linked = try_symlink(os.path.join(users, 'Default'), os.path.join(users, 'Default User'))
        try_symlink(os.path.join(users, 'Ann', 'Music'),
                    os.path.join(users, 'Ann', 'Documents', 'My Music'))
        try_symlink(os.path.join(users, 'Bob'), os.path.join(users, 'Carl'))
        return root, linked

    def test_find_users(self):
        root, _linked = self._windows_tree()
        found = windows.find_users(root)
        self.assertEqual([u.name for u in found], ['Ann', 'Bob'])
        ann, bob = found
        self.assertEqual([f.key for f in ann.folders], ['Documents', 'Music', 'Downloads'])
        self.assertEqual([f.key for f in bob.folders], ['Videos'])
        self.assertEqual(bob.folders[0].xdg, 'VIDEOS')
        # sizes skip junctions, so Ann's Music isn't counted twice through Documents/My Music
        self.assertEqual(windows.measure(ann.folders[0].path), (5, 1))
        self.assertEqual(windows.measure(ann.folders[1].path), (8, 1))
        self.assertEqual(windows.find_users(os.path.join(self.dir, 'nothing')), [])

    def test_registry_reader(self):
        values = {'Personal': text_value(r'%USERPROFILE%\OneDrive\Documentos'),
                  'My Video': text_value('D:\\Videos')}
        path = os.path.join(self.dir, 'NTUSER.DAT')
        make_hive(path, windows.SHELL_FOLDERS_KEY, values)
        hive = windows.read_hive(path)
        self.assertEqual(windows.reg_text(hive.values(windows.SHELL_FOLDERS_KEY)['personal']),
                         r'%USERPROFILE%\OneDrive\Documentos')
        self.assertEqual(hive.values(r'Software\Nothing'), {})
        self.assertIsNone(windows.read_hive(touch(os.path.join(self.dir, 'junk'), b'x' * 5000)))
        self.assertIsNone(windows.read_hive(os.path.join(self.dir, 'missing')))

    def _redirected_tree(self):
        """The layout Windows 11 often has: Desktop, Documents and Pictures in OneDrive (with
        Spanish names), Videos and Downloads on drive D:, the account's own folders empty."""
        root = os.path.join(self.dir, 'c')
        profile = os.path.join(root, 'Users', 'Ann')
        touch(os.path.join(profile, 'OneDrive', 'Desktop', 'notes.txt'), b'desk')
        touch(os.path.join(profile, 'OneDrive', 'Documentos', 'cv.pdf'), b'pdf')
        touch(os.path.join(profile, 'OneDrive', 'Pictures', 'cat.jpg'), b'jpg')
        os.makedirs(os.path.join(profile, 'Documents'))
        os.makedirs(os.path.join(profile, 'Music'))
        d = os.path.join(self.dir, 'd')
        touch(os.path.join(d, 'Videos', 'clip.mp4'), b'vid')
        touch(os.path.join(d, 'Downloads', 'setup.exe'), b'MZ')
        return root, profile, d

    def test_folders_where_windows_keeps_them(self):
        root, profile, d = self._redirected_tree()
        make_hive(os.path.join(profile, 'NTUSER.DAT'), windows.SHELL_FOLDERS_KEY, {
            'Desktop': text_value(r'%USERPROFILE%\OneDrive\Desktop'),
            'Personal': text_value(r'C:\Users\Ann\OneDrive\Documentos'),
            'My Pictures': text_value(r'%USERPROFILE%\OneDrive\Pictures'),
            'My Video': text_value('D:\\Videos'),
            'My Music': text_value(r'%USERPROFILE%\Music'),
            '{374DE290-123F-4565-9164-39C4925E467B}': text_value('d:\\downloads'),
        })
        c_guid, d_guid = '38c2cadb-0c51-4f5b-b136-fc35b957fd52', '3deaedc9-42ae-457d-bd5b-55e513f546d0'
        make_hive(os.path.join(root, 'Windows', 'System32', 'config', 'SYSTEM'), 'MountedDevices', {
            '\\DosDevices\\C:': (3, b'DMIO:ID:' + uuid_bytes(c_guid)),
            '\\DosDevices\\D:': (3, b'DMIO:ID:' + uuid_bytes(d_guid)),
            '\\DosDevices\\G:': (3, b'\x12\x34\x56\x78' + b'\0' * 8),     # an MBR disk
        })
        c = windows.Partition('nvme1n1p3', '/dev/nvme1n1p3', 'ntfs', '', root, 1, c_guid)
        dpart = windows.Partition('nvme0n1p2', '/dev/nvme0n1p2', 'ntfs', 'Scrap', d, 1, d_guid)
        self.assertEqual(windows.drive_letters(root), {'C': c_guid, 'D': d_guid})
        [user] = windows.find_users(root, c, [c, dpart])
        got = {f.key: (os.path.relpath(f.path, self.dir), f.where) for f in user.folders}
        self.assertEqual(got, {
            'Desktop': (os.path.join('c', 'Users', 'Ann', 'OneDrive', 'Desktop'),
                        r'C:\Users\Ann\OneDrive\Desktop'),
            'Documents': (os.path.join('c', 'Users', 'Ann', 'OneDrive', 'Documentos'),
                          r'C:\Users\Ann\OneDrive\Documentos'),
            'Pictures': (os.path.join('c', 'Users', 'Ann', 'OneDrive', 'Pictures'),
                         r'C:\Users\Ann\OneDrive\Pictures'),
            'Videos': (os.path.join('d', 'Videos'), 'D:\\Videos'),
            'Downloads': (os.path.join('d', 'Downloads'), 'd:\\downloads'),
        })
        # A drive that isn't there (or won't open) just leaves its folders out.
        [user] = windows.find_users(root, c, [c])
        self.assertEqual([f.key for f in user.folders], ['Desktop', 'Documents', 'Pictures'])

    def test_onedrive_without_the_registry_file(self):
        root, _profile, _d = self._redirected_tree()
        [user] = windows.find_users(root)
        self.assertEqual({f.key: f.where for f in user.folders}, {
            'Desktop': r'C:\Users\Ann\OneDrive\Desktop',
            'Documents': r'C:\Users\Ann\OneDrive\Documentos',
            'Pictures': r'C:\Users\Ann\OneDrive\Pictures',
        })

    def test_not_enough_space(self):
        src = os.path.join(self.dir, 'src')
        touch(os.path.join(src, 'big.bin'), b'0123456789')
        plan = windows.plan_copy(src, os.path.join(self.dir, 'dst'))
        with mock.patch.object(windows, 'free_space', return_value=windows.RESERVE + 5):
            self.assertEqual(windows.check_space(plan, self.dir), (10, windows.RESERVE + 5))
        with mock.patch.object(windows, 'free_space', return_value=windows.RESERVE + 10):
            self.assertIsNone(windows.check_space(plan, self.dir))
        self.assertIsNotNone(windows.free_space(os.path.join(self.dir, 'not', 'made', 'yet')))

    def test_copy_never_touches_a_users_part_file(self):
        src, dst = os.path.join(self.dir, 'src'), os.path.join(self.dir, 'dst')
        touch(os.path.join(src, 'movie.mkv'), b'new')
        plan = windows.plan_copy(src, dst)
        touch(os.path.join(dst, 'movie.mkv.part'), b'mine')
        summary = windows.copy_plan(plan)
        self.assertEqual(summary.copied, 1)
        with open(os.path.join(dst, 'movie.mkv.part'), 'rb') as f:
            self.assertEqual(f.read(), b'mine')
        self.assertEqual(sorted(os.listdir(dst)), ['movie.mkv', 'movie.mkv.part'])
        if os.name == 'posix':
            self.assertFalse(os.stat(os.path.join(dst, 'movie.mkv')).st_mode & 0o111)

    def test_plan_and_copy(self):
        src = os.path.join(self.dir, 'src')
        dst = os.path.join(self.dir, 'dst')
        touch(os.path.join(src, 'same.txt'), b'12345')
        touch(os.path.join(src, 'clash.txt'), b'windows version')
        touch(os.path.join(src, 'new.txt'), b'new')
        touch(os.path.join(src, 'sub', 'deep.txt'), b'deep')
        touch(os.path.join(src, 'Thumbs.db'), b'junk')
        touch(os.path.join(src, '.hidden'), b'h')
        touch(os.path.join(dst, 'same.txt'), b'abcde')                     # same size: skip
        touch(os.path.join(dst, 'clash.txt'), b'linux')                    # different: keep
        touch(os.path.join(dst, f'clash ({FROM}).txt'), b'older')            # taken too
        touch(os.path.join(dst, 'sub'), b'a file where the folder goes')
        plan = windows.plan_copy(src, dst)
        actions = {os.path.relpath(i.dst, dst): i.action for i in plan.items}
        self.assertEqual(actions, {
            'same.txt': windows.SKIP,
            f'clash ({FROM} 2).txt': windows.COPY,
            'new.txt': windows.COPY,
            '.hidden': windows.COPY,
            os.path.join(f'sub ({FROM})', 'deep.txt'): windows.COPY,
        })
        self.assertEqual(plan.bytes, len(b'windows version') + 3 + 4 + 1)
        before = {p: read(p) for p in glob.glob(os.path.join(src, '**'),
                                                              recursive=True)
                  if os.path.isfile(p)}
        seen = []
        summary = windows.copy_plan(plan, lambda d, t, n: seen.append((d, t)))
        self.assertEqual((summary.copied, summary.skipped, summary.renamed), (4, 1, 1))
        self.assertEqual(summary.failed, [])
        self.assertFalse(summary.cancelled)
        self.assertEqual(seen[-1], (plan.bytes, plan.bytes))
        with open(os.path.join(dst, f'clash ({FROM} 2).txt'), 'rb') as f:
            self.assertEqual(f.read(), b'windows version')
        with open(os.path.join(dst, 'clash.txt'), 'rb') as f:
            self.assertEqual(f.read(), b'linux')                          # never overwritten
        self.assertEqual(os.path.getmtime(os.path.join(dst, 'new.txt')),
                         os.path.getmtime(os.path.join(src, 'new.txt')))
        self.assertFalse(glob.glob(os.path.join(dst, '**', '*.part'), recursive=True))
        self.assertFalse(os.path.exists(os.path.join(dst, 'Thumbs.db')))
        after = {p: read(p) for p in before}
        self.assertEqual(before, after)                                   # source untouched
        # a second run finds every file already there, renamed copy included
        self.assertEqual(windows.plan_copy(src, dst).to_copy, [])

    def test_second_run_skips_everything_without_clashes(self):
        src = os.path.join(self.dir, 'src')
        dst = os.path.join(self.dir, 'dst')
        touch(os.path.join(src, 'a.txt'), b'aaa')
        touch(os.path.join(src, 'b', 'c.txt'), b'cc')
        windows.copy_plan(windows.plan_copy(src, dst))
        again = windows.plan_copy(src, dst)
        self.assertEqual(again.to_copy, [])
        self.assertEqual(len(again.skipped), 2)

    def test_cancel(self):
        src = os.path.join(self.dir, 'src')
        touch(os.path.join(src, 'a.txt'), b'aaa')
        stop = threading.Event()
        stop.set()
        summary = windows.copy_plan(windows.plan_copy(src, os.path.join(self.dir, 'dst')),
                                    cancel=stop)
        self.assertTrue(summary.cancelled)
        self.assertEqual(summary.copied, 0)
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'dst', 'a.txt')))

    def test_two_folders_into_one_plan(self):
        claimed = set()
        a = os.path.join(self.dir, 'a')
        b = os.path.join(self.dir, 'b')
        touch(os.path.join(a, 'x.txt'), b'1')
        touch(os.path.join(b, 'x.txt'), b'22')
        dst = os.path.join(self.dir, 'dst')
        plan = windows.plan_copy(a, dst, claimed)
        plan.extend(windows.plan_copy(b, dst, claimed))
        self.assertEqual(sorted(os.path.basename(i.dst) for i in plan.to_copy),
                         [f'x ({FROM}).txt', 'x.txt'])


# ─── Checks ───────────────────────────────────────────────────

VULKAN = """==========
VULKANINFO
==========
Devices:
========
GPU0:
\tapiVersion         = 1.4.311
\tdeviceType         = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
\tdeviceName         = AMD Radeon RX 7800 XT (RADV NAVI32)
\tdriverID           = DRIVER_ID_MESA_RADV
\tdriverName         = radv
GPU1:
\tdeviceType         = PHYSICAL_DEVICE_TYPE_CPU
\tdeviceName         = llvmpipe (LLVM 19.1.7, 256 bits)
\tdriverName         = llvmpipe
"""

WPCTL = """PipeWire 'pipewire-0' [1.4.2, user@pc, cookie:1]
 └─ Clients:
        33. WirePlumber                         [1.4.2, user@pc, pid:1400]

Audio
 ├─ Devices:
 │      48. Navi 31 HDMI/DP Audio               [alsa]
 │      49. Starship/Matisse HD Audio Controller [alsa]
 │
 ├─ Sinks:
 │      55. Navi 31 HDMI/DP Audio Digital Stereo (HDMI) [vol: 1.00]
 │  *   57. Starship/Matisse HD Audio Controller Analog Stereo [vol: 0.40]
 │
 ├─ Sources:
 │  *   58. Starship/Matisse HD Audio Controller Analog Stereo [vol: 1.00]
 │
 └─ Streams:

Video
 ├─ Devices:
 ├─ Sinks:
 │      70. Not audio                           [vol: 1.00]
 └─ Sources:
"""

OSTREE = json.dumps({"deployments": [
    {"booted": False, "staged": True, "timestamp": 1763600000},
    {"booted": True, "timestamp": 1763000000, "version": "45.20251113",
     "container-image-reference": "ostree-image-signed:docker://ghcr.io/wolklaw/sparkos:latest"},
]})


class CheckTests(unittest.TestCase):
    def test_vulkan(self):
        gpus = checks.parse_vulkan_summary(VULKAN)
        self.assertEqual([g['deviceName'] for g in gpus],
                         ['AMD Radeon RX 7800 XT (RADV NAVI32)', 'llvmpipe (LLVM 19.1.7, 256 bits)'])
        self.assertEqual(gpus[0]['driverName'], 'radv')

    def test_wpctl(self):
        self.assertEqual(checks.parse_wpctl_sinks(WPCTL),
                         ['Starship/Matisse HD Audio Controller Analog Stereo',
                          'Navi 31 HDMI/DP Audio Digital Stereo (HDMI)'])
        self.assertEqual(checks.parse_wpctl_sinks('Audio\n ├─ Sinks:\n │\n ├─ Sources:\n'), [])

    def test_printers_scanners_network(self):
        self.assertEqual(checks.parse_lpstat('Canon_TS5300_series\nOffice\n'),
                         ['Canon_TS5300_series', 'Office'])
        self.assertEqual(checks.parse_lpstat('No destinations added.\n'), [])
        self.assertEqual(checks.parse_scanimage(
            "device `airscan:e0:Canon TS5300 series' is a eSCL Canon TS5300 series ip=192.168.1.20\n"),
            ['eSCL Canon TS5300 series ip=192.168.1.20'])
        self.assertEqual(checks.parse_scanimage('No scanners were identified.\n'), [])
        self.assertEqual(checks.parse_nmcli_devices(
            'ethernet:connected:Wired connection 1\nwifi:disconnected:\nloopback:connected '
            '(externally):lo\nwifi:connected:Home\\:5G\n'),
            [('ethernet', 'connected', 'Wired connection 1'), ('wifi', 'disconnected', ''),
             ('wifi', 'connected', 'Home:5G')])

    def test_rpm_ostree(self):
        info = checks.parse_rpm_ostree(OSTREE)
        self.assertEqual(info['image'], 'ghcr.io/wolklaw/sparkos:latest')
        self.assertTrue(info['staged'])
        self.assertEqual(info['timestamp'], 1763000000)
        self.assertIsNone(checks.parse_rpm_ostree('{}'))
        self.assertIsNone(checks.parse_rpm_ostree('nope'))

    def test_checks_run_anywhere(self):
        found = checks.run_all()
        self.assertEqual([c.key for c in found],
                         ['graphics', 'sound', 'printers', 'network', 'updates'])
        for c in found:
            self.assertIn(c.status, (checks.OK, checks.WARN))
            self.assertTrue(c.summary)

    def test_graphics_with_fake_vulkaninfo(self):
        with mock.patch.object(checks.shutil, 'which', return_value='/usr/bin/vulkaninfo'), \
                mock.patch.object(checks, 'run', return_value=(0, VULKAN, '')):
            result = checks.check_graphics()
        self.assertEqual(result.status, checks.OK)
        self.assertIn('RX 7800 XT', result.summary)

    @unittest.skipUnless(sys.platform.startswith('linux'), "PCI slot names have ':' in them")
    def test_pci_display_and_build(self):
        root = tempfile.mkdtemp()
        for slot, cls, vendor, device, driver in (
                ('0000:01:00.0', '0x030000', '0x10de', '0x2684', ''),        # RTX 4090, no driver
                ('0000:00:02.0', '0x030000', '0x8086', '0x46a6', 'i915'),
                ('0000:00:1f.3', '0x040300', '0x8086', '0x51c8', 'snd_hda_intel')):
            folder = os.path.join(root, slot)
            os.makedirs(folder)
            for name, value in (('class', cls), ('vendor', vendor), ('device', device)):
                with open(os.path.join(folder, name), 'w', encoding='ascii') as f:
                    f.write(value + '\n')
            if driver and hasattr(os, 'symlink'):
                try:
                    os.symlink(os.path.join(root, 'drivers', driver), os.path.join(folder, 'driver'))
                except OSError:
                    pass                              # Windows without symlink rights
        found = checks.pci_display(root)
        self.assertEqual([(s, v, d) for s, v, d, _drv in found],
                         [('0000:00:02.0', 'Intel', 0x46a6), ('0000:01:00.0', 'NVIDIA', 0x2684)])
        release = os.path.join(root, 'release.json')
        for image, build in (('ghcr.io/wolklaw/sparkos-nvidia', 'nvidia'),
                             ('ghcr.io/wolklaw/sparkos', 'standard'), ('other', '')):
            with open(release, 'w', encoding='utf-8') as f:
                json.dump({'image': image}, f)
            self.assertEqual(checks.sparkos_build(release), build)
        self.assertEqual(checks.sparkos_build(os.path.join(root, 'missing.json')), '')

    def test_nvidia_advice(self):
        rtx = ('0000:01:00.0', 'NVIDIA', 0x2684, '')
        gtx1060 = ('0000:01:00.0', 'NVIDIA', 0x1c03, 'nouveau')
        amd = ('0000:03:00.0', 'AMD', 0x73bf, 'amdgpu')
        advice = checks.nvidia_advice
        self.assertIsNone(advice([amd], 'standard'))
        self.assertIsNone(advice([rtx], ''))                     # not SparkOS: say nothing
        self.assertEqual(advice([rtx, amd], 'standard')[0], 'check.graphics.nv_standard')
        self.assertEqual(advice([rtx], 'standard')[1][0][1], 'switch_nvidia')
        # Not released yet: no switch to an image that can't be downloaded
        self.assertEqual(advice([rtx], 'standard', released=False),
                         ('check.graphics.nv_standard_soon', []))
        self.assertFalse(checks.nvidia_released(os.path.join(tempfile.mkdtemp(), 'none')))
        self.assertEqual(advice([gtx1060], 'standard'), ('check.graphics.nv_old', []))
        self.assertIsNone(advice([rtx[:3] + ('nvidia',)], 'nvidia'))
        self.assertEqual(advice([rtx], 'nvidia'), ('check.graphics.nv_noload', []))
        self.assertEqual(advice([gtx1060], 'nvidia')[0], 'check.graphics.nv_old_on_nvidia')
        self.assertEqual(advice([amd], 'nvidia')[1][0][1], 'switch_standard')
        for key in ('switch_nvidia', 'switch_standard'):
            self.assertEqual(checks.SWITCH_COMMANDS[key][:2], ['rpm-ostree', 'rebase'])
        with mock.patch.object(checks, 'pci_display', return_value=[rtx]), \
                mock.patch.object(checks, 'sparkos_build', return_value='standard'):
            result = checks.check_graphics()
        self.assertEqual(result.status, checks.WARN)
        self.assertIn('NVIDIA', result.summary)
        self.assertTrue(result.detail)


# ─── First login, strings, packaging ──────────────────────────

class FirstLoginTests(unittest.TestCase):
    def setUp(self):
        self.config = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': self.config})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_markers(self):
        with mock.patch.object(core, 'live_session', return_value=False):
            self.assertIsNone(core.skip_first_login())
            core.mark_done(False)
            self.assertTrue(os.path.isfile(os.path.join(self.config, 'spark-welcome', 'done')))
            self.assertEqual(core.skip_first_login(), 'already done')
            core.mark_done(True)                    # "Show Spark Welcome at login" ticked
            self.assertIsNone(core.skip_first_login())
            core.mark_done(False)
            self.assertEqual(core.skip_first_login(), 'already done')

    def test_live_session(self):
        with mock.patch.object(core.getpass, 'getuser', return_value='liveuser'):
            self.assertTrue(core.live_session())
            self.assertEqual(core.skip_first_login(), 'live session')

    def test_first_login_exits_at_once(self):
        core.mark_done(False)
        env = dict(os.environ, XDG_CONFIG_HOME=self.config, DISPLAY=':nowhere',
                   WAYLAND_DISPLAY='')
        start = time.monotonic()
        done = subprocess.run([sys.executable, os.path.join(APP_DIR, 'spark_welcome.py'),
                               '--first-login'], env=env, capture_output=True, text=True,
                              timeout=30)
        took = time.monotonic() - start
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout + done.stderr, '')
        self.assertLess(took, 5)
        # and tkinter was never imported on the way out
        script = os.path.join(APP_DIR, 'spark_welcome.py')
        code = ("import runpy, sys\n"
                f"sys.argv = [{script!r}, '--first-login']\n"
                "try:\n"
                f"    runpy.run_path({script!r}, run_name='__main__')\n"
                "except SystemExit:\n"
                "    pass\n"
                "print('tkinter' in sys.modules)\n")
        probe = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True,
                               text=True, timeout=30, cwd=APP_DIR)
        self.assertEqual(probe.stdout.strip(), 'False', probe.stderr)


class PackagingTests(unittest.TestCase):
    def test_every_string_exists(self):
        used = set()
        for path in glob.glob(os.path.join(APP_DIR, 'sparkwelcome', '*.py')):
            with open(path, encoding='utf-8') as f:
                used |= set(re.findall(r"""\bt\(\s*f?['"]([\w.]+)['"]""", f.read()))
        used = {k for k in used if not k.endswith('.')}
        missing = sorted(k for k in used if k not in strings.EN)
        self.assertEqual(missing, [])
        for name in sparkwelcome.PAGES:
            self.assertIn(f'nav.{name}', strings.EN)
        for fn in checks.CHECKS:
            self.assertIn('check.' + fn.__name__[6:], strings.EN)
        for key in ('store', 'snip', 'settings'):
            for part in ('', '.title', '.button'):
                self.assertIn(f'done.{key}{part}', strings.EN)

    def test_language(self):
        from sparkwelcome.lang import ui_language
        self.assertEqual(ui_language({'LC_ALL': '', 'LC_MESSAGES': '', 'LANG': 'fr_CA.UTF-8'}),
                         'fr')
        self.assertEqual(ui_language({'LC_MESSAGES': 'en_CA', 'LANG': 'fr_CA.UTF-8'}), 'en')
        self.assertEqual(strings.t('status.installed', name='STEAM'),
                         {'en': 'STEAM INSTALLED', 'fr': 'STEAM INSTALLÉ'}[strings.LANG])
        self.assertEqual(strings.t('no.such.key'), 'no.such.key')

    def test_catalog_speaks_the_language(self):
        cat = catalog.load()
        steam = cat.find('com.valvesoftware.Steam')
        self.assertTrue(steam.text('fr') and steam.text('fr') != steam.text('en'))
        signal = cat.find('org.signal.Signal')
        self.assertEqual(signal.who('fr'), 'la Signal Foundation')
        self.assertEqual(signal.who('en'), 'the Signal Foundation')
        for entry in cat.all():
            self.assertTrue(entry.blurb_fr, entry.id)
        for cat_ in cat.categories:
            self.assertTrue(cat_.name_fr, cat_.name)

    def test_spark_app_json(self):
        with open(os.path.join(APP_DIR, 'spark-app.json'), encoding='utf-8') as f:
            meta = json.load(f)
        self.assertEqual(meta['id'], sparkwelcome.APP_ID)
        self.assertEqual(meta['slug'], sparkwelcome.APP_SLUG)
        self.assertEqual(meta['version'], sparkwelcome.VERSION)
        self.assertFalse(meta['needs']['root'])
        self.assertTrue(meta['description'] and len(meta['description']) < 160)

    def test_desktop_entries(self):
        with open(os.path.join(APP_DIR, f'{sparkwelcome.APP_ID}.desktop'), encoding='utf-8') as f:
            menu = f.read()
        with open(os.path.join(APP_DIR, f'{sparkwelcome.APP_ID}-autostart.desktop'),
                  encoding='utf-8') as f:
            auto = f.read()
        self.assertIn('Exec=spark-welcome\n', menu)
        self.assertIn(f'StartupWMClass={sparkwelcome.APP_CLASS}', menu)
        self.assertIn('Exec=spark-welcome --first-login\n', auto)
        self.assertIn('NoDisplay=true', auto)

    def test_icons_exist(self):
        for size in (16, 22, 24, 32, 48, 64, 128, 256, 512):
            self.assertTrue(os.path.isfile(os.path.join(APP_DIR, 'icons',
                                                        f'spark-welcome-{size}.png')))
        for size in (160, 240, 320):
            self.assertTrue(os.path.isfile(os.path.join(APP_DIR, 'icons',
                                                        f'sparkos-bot-{size}.png')))

    def test_self_test_runs(self):
        done = subprocess.run([sys.executable, os.path.join(APP_DIR, 'spark_welcome.py'),
                               '--self-test'], capture_output=True, text=True, timeout=60)
        self.assertIn('catalog: ok', done.stdout)
        self.assertIn(done.returncode, (0, 1))


# ─── UI (needs a display) ─────────────────────────────────────

def have_display() -> bool:
    try:
        import tkinter
        root = tkinter.Tk()
        root.destroy()
        return True
    except Exception:          # noqa: BLE001
        return False


@unittest.skipUnless(have_display(), "no display")
class UITests(unittest.TestCase):
    def setUp(self):
        self.config = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': self.config})
        self.env.start()
        from sparkwelcome.app import App
        self.App = App
        self.app = None

    def tearDown(self):
        if self.app is not None and not self.app.closing:
            self.app.close()
        self.env.stop()

    def pump(self, seconds: float = 0.3, until=None):
        deadline = time.time() + seconds
        while time.time() < deadline:
            self.app.root.update()
            if until and until():
                return True
            time.sleep(0.02)
        return bool(until and until())

    def done_file(self) -> str:
        return os.path.join(self.config, 'spark-welcome', 'done')

    def test_every_page_renders(self):
        self.app = self.App()
        self.pump()
        for name in sparkwelcome.PAGES:
            self.app.go(name)
            self.pump(0.2)
            page = self.app.pages[name]
            self.assertTrue(page.winfo_ismapped(), name)
            self.assertIsNotNone(page.heading, name)
            self.assertGreater(len(page.col.winfo_children()), 1, name)
        rows = self.app.pages['games'].rows
        self.assertEqual(len(rows), 4)
        self.assertGreaterEqual(len(self.app.pages['apps'].rows), 12)
        # the checks finish and every row gets a verdict
        checks_page = self.app.pages['checks']
        self.assertTrue(self.pump(60, until=lambda: not checks_page.running))
        self.pump(0.2)

    def test_next_through_every_page_writes_done(self):
        self.app = self.App()
        self.pump()
        self.assertFalse(os.path.exists(self.done_file()))
        for expected in sparkwelcome.PAGES[1:]:
            self.app.next()
            self.pump(0.1)
            self.assertEqual(self.app.page, expected)
        self.assertTrue(os.path.exists(self.done_file()))
        self.assertFalse(os.path.exists(os.path.join(self.config, 'spark-welcome',
                                                     'show-at-login')))
        self.app.next()                                     # "Close" on the last page
        self.assertTrue(self.app.closing)

    def test_closing_early_writes_done(self):
        self.app = self.App('games')
        self.pump()
        self.app.close()
        self.assertTrue(os.path.exists(self.done_file()))

    def test_show_at_login_box(self):
        self.app = self.App('done')
        self.pump()
        self.app.pages['done'].show_again.set(True, fire=True)
        self.assertTrue(os.path.exists(os.path.join(self.config, 'spark-welcome',
                                                    'show-at-login')))
        with mock.patch.object(core, 'live_session', return_value=False):
            self.assertIsNone(core.skip_first_login())

    def test_ticks_and_install_states(self):
        self.app = self.App('apps')
        self.pump()
        page = self.app.pages['apps']
        self.assertFalse(page.install_btn.enabled)
        row = page.rows[0]
        row.tick.set(True, fire=True)
        self.assertTrue(page.install_btn.enabled)
        self.assertIn('(1)', page.install_btn.label.cget('text'))
        # what the installer reports shows on the row
        job = flatpak.Job(row.entry.id, row.entry.name, flatpak.WORKING, 40)
        self.app.install_changed(job)
        self.assertIn('40%', row.state.cget('text'))
        self.assertTrue(row.tick.locked)
        job = flatpak.Job(row.entry.id, row.entry.name, flatpak.FAILED, error='no network')
        self.app.install_changed(job)
        self.pump(0.1)
        self.assertEqual(row.error.cget('text'), 'no network')
        self.assertTrue(row.retry_btn.winfo_ismapped())
        self.assertFalse(row.tick.locked)
        self.app.install_changed(flatpak.Job(row.entry.id, row.entry.name, flatpak.DONE))
        self.pump(0.1)
        self.assertTrue(row.tick.locked)
        self.assertFalse(row.retry_btn.winfo_ismapped())

    def test_windows_page_with_a_fake_drive(self):
        root = tempfile.mkdtemp()
        touch(os.path.join(root, 'Users', 'Ann', 'Documents', 'a.txt'), b'hello')
        touch(os.path.join(root, 'Users', 'Ann', 'Pictures', 'p.jpg'), b'jpg')
        home = tempfile.mkdtemp()
        part = windows.Partition('sdz1', '/dev/sdz1', 'ntfs', 'Windows', root, 10 ** 9)
        with mock.patch.object(windows, 'list_partitions', return_value=([part], '')), \
                mock.patch.object(windows, 'destination',
                                  side_effect=lambda f: os.path.join(home, f.fallback)):
            self.app = self.App('windows')
            page = self.app.pages['windows']
            self.assertTrue(self.pump(10, until=lambda: page.drives.winfo_children()
                                      and not self.app._busy))
            page.mount(part)
            self.assertTrue(self.pump(10, until=lambda: page.user is not None
                                      and not self.app._busy))
            self.assertEqual(sorted(page.ticks), ['Documents', 'Pictures'])
            page.copy()
            self.assertTrue(self.pump(10, until=lambda: not page.copying))
        with open(os.path.join(home, 'Documents', 'a.txt'), 'rb') as f:
            self.assertEqual(f.read(), b'hello')
        self.assertTrue(os.path.isfile(os.path.join(home, 'Pictures', 'p.jpg')))


if __name__ == '__main__':
    unittest.main()
