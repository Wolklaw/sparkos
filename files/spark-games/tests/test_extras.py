"""Spark Games tests for the 0.2 additions: controllers, the big screen, the new sources
(Steam shortcuts, itch, Bottles, Minecraft and Prism) and French.

    python -m unittest discover -s files/spark-games/tests -v

Controller tests feed recorded events (tests/fixtures/gamepad/*.evtest) through the real
reader: the decoder anywhere, and on Linux through a FIFO standing in for /dev/input/eventN,
with Tk's event loop doing the reading (uinput isn't available in CI). UI tests need a display
(on CI: xvfb-run).
"""

import os
import shutil
import sqlite3
import string
import struct
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
sys.path.insert(0, APP_DIR)
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
    if 'spark-games' not in os.environ.get(var, ''):
        os.environ[var] = tempfile.mkdtemp(prefix=f'spark-games-{var.lower()}-')
os.environ['SPARK_LANG'] = 'en'

import logging  # noqa: E402

from sparkgames import (bottles, fixtures, gamepad, itch, launch, library,  # noqa: E402
                        minecraft, steam, strings, vdf)
from sparkgames.core import Game  # noqa: E402

logging.getLogger('spark-games').addHandler(logging.NullHandler())

LINUX = sys.platform.startswith('linux')
XBOX = ['down', 'right', 'left', 'a', 'y', 'b', 'start', 'guide']
DUALSENSE = ['up', 'a', 'y', 'down', 'b']


def fake_which(*present):
    return lambda name: f'/usr/bin/{name}' if name in present else None


class FixtureHome(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='spark-games-home-')
        self.home = fixtures.materialize(os.path.join(self.tmp, 'home'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


# ─── Binary VDF and Steam shortcuts ───────────────────────────

class BinaryVDFTests(unittest.TestCase):
    def test_round_trip_and_types(self):
        data = {'shortcuts': {'0': {'appid': -1652113466, 'AppName': 'Été', 'tags': {'0': 'x'}}}}
        raw = vdf.dumps_binary(data)
        self.assertEqual(vdf.loads_binary(raw), data)
        self.assertEqual(vdf.loads_binary(raw[:-1]), data)        # last 0x08 left out
        extra = b'\x00a\x00\x03f\x00' + struct.pack('<f', 1.5) + b'\x07q\x00' + \
            struct.pack('<Q', 2 ** 40) + b'\x08\x08'
        self.assertEqual(vdf.loads_binary(extra), {'a': {'f': 1.5, 'q': 2 ** 40}})

    def test_broken(self):
        raw = vdf.dumps_binary({'shortcuts': {'0': {'AppName': 'X'}}})
        for bad in (raw[:5], raw[:12], b'\x09key\x00', b'\x02n\x00\x01'):
            with self.assertRaises(vdf.VDFError, msg=repr(bad)):
                vdf.loads_binary(bad)


class ShortcutTests(FixtureHome):
    def test_shortcuts_listed(self):
        games = {g.key: g for g in steam.scan(self.home, [])}
        doom = games[f'steam-shortcut:{fixtures.SHORTCUT_ID}']
        self.assertEqual(doom.title, 'Shortcut Example Doom')
        self.assertEqual(doom.source, 'steam')
        self.assertEqual(doom.last_played, 1720000000)
        self.assertEqual(doom.install_dir, '/usr/bin/')
        self.assertTrue(doom.cover.endswith(f'{fixtures.SHORTCUT_ID}p.jpg'))
        self.assertEqual(doom.launch['appid'], str((fixtures.SHORTCUT_ID << 32) | 0x02000000))
        # an old shortcut with no appid: Steam's CRC of program + name
        cave = [g for g in games.values() if g.title == 'Shortcut Example Cave'][0]
        import zlib
        crc = zlib.crc32(b'"/opt/cave/CaveGame"Shortcut Example Cave') | 0x80000000
        self.assertEqual(cave.key, f'steam-shortcut:{crc}')
        # Heroic's "add to Steam" (already listed under Epic) and hidden shortcuts are left out
        titles = {g.title for g in games.values()}
        self.assertNotIn('Added by Heroic', titles)
        self.assertNotIn('Hidden Shortcut', titles)

    def test_launch_and_words(self):
        doom = [g for g in steam.scan(self.home, []) if g.key.startswith('steam-shortcut:')][0]
        plan = launch.plan(doom, which=fake_which('flatpak'))
        self.assertEqual(plan.argv[-1], f'steam://rungameid/{doom.launch["appid"]}')
        from sparkgames.views import launcher_line
        self.assertIn(strings.tr('shortcut'), launcher_line(doom))

    def test_broken_shortcuts_file_keeps_steam_games(self):
        path = os.path.join(self.home, fixtures.STEAM, 'userdata', '12345678', 'config',
                            'shortcuts.vdf')
        with open(path, 'wb') as f:
            f.write(b'\x00shortcuts\x00\x00\x30\x00\x01AppName\x00Cut off')
        games = steam.scan(self.home, [])
        self.assertEqual(len(games), 5)
        self.assertFalse(any(g.key.startswith('steam-shortcut:') for g in games))


# ─── itch ─────────────────────────────────────────────────────

class ItchTests(FixtureHome):
    def test_installed_games(self):
        games = {g.key: g for g in itch.scan(self.home, [])}
        self.assertEqual(sorted(games), ['itch:101', 'itch:103'])       # assets left out
        hike = games['itch:101']
        self.assertEqual(hike.title, 'Itch Example Hike')
        self.assertEqual(hike.playtime, 90)
        self.assertEqual(hike.last_played, 1748802125)     # nanosecond text time
        self.assertTrue(hike.install_dir.endswith(os.path.join('apps', 'itch-example-hike')))
        self.assertFalse(hike.flatpak)
        self.assertTrue(games['itch:103'].install_dir.endswith('jam-game'))   # custom folder
        self.assertEqual(games['itch:103'].last_played, 0)

    def test_launch(self):
        hike = {g.key: g for g in itch.scan(self.home, [])}['itch:101']
        self.assertEqual(launch.plan(hike, which=fake_which('xdg-open')).argv,
                         ['xdg-open', 'itch://install?game_id=101&launch'])
        with self.assertRaises(launch.LaunchError):
            launch.plan(hike, which=fake_which())
        # the regular itch app's own launcher, when it is there: no prompt
        setup = os.path.join(self.home, '.itch', 'itch-setup')
        os.makedirs(os.path.dirname(setup))
        with open(setup, 'w') as f:
            f.write('#!/bin/sh\n')
        os.chmod(setup, 0o755)
        hike = {g.key: g for g in itch.scan(self.home, [])}['itch:101']
        self.assertEqual(launch.plan(hike, which=fake_which()).argv,
                         [setup, '--appname', 'itch', '--run-game', '101'])

    def test_time_formats(self):
        self.assertEqual(itch._time('2025-06-01 18:22:05+00:00'), 1748802125)
        self.assertEqual(itch._time('2025-06-01T18:22:05.5Z'), 1748802125)
        self.assertEqual(itch._time('2025-06-01 18:22:05'), 1748802125)       # no zone: UTC
        self.assertEqual(itch._time('soon'), 0)
        self.assertEqual(itch._time(None), 0)

    def test_changed_schema_and_lock_are_skipped(self):
        db = os.path.join(self.home, '.config', 'itch', 'db', 'butler.db')
        con = sqlite3.connect(db)
        con.execute('ALTER TABLE caves RENAME TO caves_v2')
        con.commit()
        con.close()
        self.assertEqual(itch.scan(self.home, []), [])
        self.assertNotIn('itch', library.scan_all(self.home).problems)

    def test_flatpak_itch(self):
        flat = os.path.join(self.home, '.var', 'app', 'io.itch.itch', 'config')
        os.makedirs(flat)
        shutil.move(os.path.join(self.home, '.config', 'itch'), flat)
        games = itch.scan(self.home, [])
        self.assertEqual(len(games), 2)
        self.assertTrue(all(g.flatpak for g in games))


# ─── Bottles ──────────────────────────────────────────────────

class BottlesTests(FixtureHome):
    def test_programs(self):
        games = sorted(bottles.scan(self.home, []), key=lambda g: g.title)
        self.assertEqual([g.title for g in games], ['Battle.net', 'Bottles Example: "Deluxe"'])
        bnet = games[0]
        self.assertEqual(bnet.key, 'bottles:Games:0f1e2d3c-1111-4aaa-9bbb-000000000001')
        self.assertTrue(bnet.install_dir.endswith('Battle.net'))
        self.assertTrue(bnet.flatpak)
        self.assertEqual(launch.plan(bnet, which=fake_which('flatpak')).argv,
                         ['flatpak', 'run', '--command=bottles-cli', 'com.usebottles.bottles',
                          'run', '-b', 'Games', '-p', 'Battle.net'])

    def test_regular_bottles(self):
        game = Game('bottles:x:1', 'Thing', 'bottles',
                    launch={'bottle': 'My Bottle', 'program': 'Thing', 'flatpak': False})
        self.assertEqual(launch.plan(game, which=fake_which('bottles-cli')).argv,
                         ['bottles-cli', 'run', '-b', 'My Bottle', '-p', 'Thing'])
        with self.assertRaises(launch.LaunchError) as caught:
            launch.plan(game, which=fake_which())
        self.assertEqual(caught.exception.detail, 'bottles-cli')

    def test_yaml_reader(self):
        data = bottles.loads(
            "# comment\nA: 1\nB: 'it''s'\nC: \"q \\\"x\\\"\"\nD: plain # note\nE:\n"
            "  F: true\n  G:\n    H: ~\nL:\n- one\n- two\nM: {}\nN:\n")
        self.assertEqual(data, {'A': 1, 'B': "it's", 'C': 'q "x"', 'D': 'plain',
                                'E': {'F': True, 'G': {'H': None}}, 'L': None, 'M': {},
                                'N': None})
        with self.assertRaises(bottles.YAMLError):
            bottles.loads("just a line with no colon")

    def test_broken_bottle_is_skipped(self):
        root = os.path.join(self.home, '.var', 'app', 'com.usebottles.bottles', 'data',
                            'bottles', 'bottles')
        os.makedirs(os.path.join(root, 'Broken'))
        with open(os.path.join(root, 'Broken', 'bottle.yml'), 'w') as f:
            f.write("External_Programs:\n  x:\n    this is not yaml\n")
        self.assertEqual(len(bottles.scan(self.home, [])), 2)


# ─── Minecraft ────────────────────────────────────────────────

class MinecraftTests(FixtureHome):
    def test_official_launcher(self):
        games = minecraft.official(self.home, [])
        self.assertEqual(len(games), 1)
        java = games[0]
        self.assertEqual((java.key, java.title), ('minecraft:java', 'Minecraft: Java Edition'))
        self.assertEqual(java.last_played, 1741114800)            # 1970 profiles ignored
        self.assertEqual(launch.plan(java, which=fake_which('minecraft-launcher')).argv,
                         ['minecraft-launcher'])
        flat = Game('minecraft:java-flatpak', 'M', 'minecraft', launch={'flatpak': True})
        self.assertEqual(launch.plan(flat, which=fake_which('flatpak')).argv,
                         ['flatpak', 'run', 'com.mojang.Minecraft'])
        with self.assertRaises(launch.LaunchError):
            launch.plan(java, which=fake_which())

    def test_prism_instances(self):
        games = {g.key: g for g in minecraft.prism(self.home, [])}
        self.assertEqual(sorted(games), ['prism:Fabric 1.21', 'prism:Vanilla'])   # temp skipped
        fabric = games['prism:Fabric 1.21']
        self.assertEqual(fabric.playtime, 121)
        self.assertEqual(fabric.last_played, 1735000000)          # milliseconds in the file
        self.assertTrue(fabric.cover.endswith('fabric-icon.png'))
        self.assertEqual(games['prism:Vanilla'].title, 'Vanilla')
        self.assertEqual(launch.plan(fabric, which=fake_which('prismlauncher')).argv,
                         ['prismlauncher', '--launch', 'Fabric 1.21'])
        fabric.launch['flatpak'] = True
        self.assertEqual(launch.plan(fabric, which=fake_which('flatpak')).argv,
                         ['flatpak', 'run', 'org.prismlauncher.PrismLauncher', '--launch',
                          'Fabric 1.21'])

    def test_prism_moved_instances(self):
        root = os.path.join(self.home, '.local', 'share', 'PrismLauncher')
        elsewhere = os.path.join(self.tmp, 'mc-instances')
        shutil.move(os.path.join(root, 'instances'), elsewhere)
        with open(os.path.join(root, 'prismlauncher.cfg'), 'w') as f:
            f.write(f'[General]\nInstanceDir={elsewhere}\n')
        self.assertEqual(len(minecraft.prism(self.home, [])), 2)

    def test_broken_profiles_file(self):
        with open(os.path.join(self.home, '.minecraft', 'launcher_profiles.json'), 'w') as f:
            f.write('[1, 2')
        self.assertEqual(minecraft.official(self.home, []), [])


# ─── French ───────────────────────────────────────────────────

class LanguageTests(unittest.TestCase):
    VARS = ('SPARK_LANG', 'LC_ALL', 'LC_MESSAGES', 'LANG')

    def setUp(self):
        self.saved = {v: os.environ.get(v) for v in self.VARS}

    def tearDown(self):
        for var, value in self.saved.items():
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value
        strings.set_language('en')

    def lang(self, **env):
        for var in self.VARS:
            os.environ.pop(var, None)
        os.environ.update(env)
        return strings.language()

    def test_choice(self):
        self.assertEqual(self.lang(), 'en')
        self.assertEqual(self.lang(LANG='fr_CA.UTF-8'), 'fr')
        self.assertEqual(self.lang(LANG='fr_CA.UTF-8', LC_ALL='en_US.UTF-8'), 'en')
        self.assertEqual(self.lang(LANG='en_CA.UTF-8', LC_MESSAGES='fr_CA.UTF-8'), 'fr')
        self.assertEqual(self.lang(LANG='C.UTF-8'), 'en')
        self.assertEqual(self.lang(LANG='en_CA.UTF-8', SPARK_LANG='fr'), 'fr')
        self.assertEqual(self.lang(LANG='fr_CA.UTF-8', SPARK_LANG='en'), 'en')
        self.assertEqual(self.lang(LANG='fr_FR.UTF-8', SPARK_LANG='de'), 'fr')    # unknown: locale

    def test_every_string_has_french(self):
        fmt = string.Formatter()

        def fields(text):
            return {f[1] for f in fmt.parse(text) if f[1]}

        self.assertEqual(sorted(set(strings.EN) - set(strings.FR)), [])
        self.assertEqual(sorted(set(strings.FR) - set(strings.EN)), [])
        for key, text in strings.EN.items():
            self.assertEqual(fields(text), fields(strings.FR[key]), key)

    def test_french_words(self):
        strings.set_language('fr')
        self.assertEqual(strings.tr('play'), 'Jouer')
        self.assertEqual(strings.tr('games_n', n=4), '4 JEUX')
        self.assertEqual(strings.last_played(int(time.time()) - 1), "Aujourd'hui")
        self.assertEqual(strings.playtime(125), '2 h 5 min')
        from sparkgames.bigscreen import build_rows
        rows = build_rows([Game('steam:1', 'A', 'steam', last_played=5),
                           Game('own:1', 'B', 'own')])
        self.assertEqual([r.title for r in rows], ['CONTINUER', 'STEAM', 'LES MIENS',
                                                   'TOUS LES JEUX'])


# ─── Controllers: decoding ────────────────────────────────────

def pressed(decoder, events):
    out = []
    for _t, ev_type, code, value in events:
        out += [name for kind, name in decoder.feed(ev_type, code, value) if kind == 'press']
    return out


def bitmap(*bits):
    """A sysfs capability bitmap with these bits set, highest word first."""
    word = struct.calcsize('l') * 8
    words = [0] * (max(bits) // word + 1)
    for bit in bits:
        words[bit // word] |= 1 << (bit % word)
    return ' '.join(f'{w:x}' for w in reversed(words))


def add_sysfs(sys_root, name, bits, label):
    device = os.path.join(sys_root, name, 'device')
    os.makedirs(os.path.join(device, 'capabilities'))
    os.makedirs(os.path.join(device, 'id'))
    with open(os.path.join(device, 'capabilities', 'key'), 'w') as f:
        f.write(bitmap(*bits) + '\n')
    with open(os.path.join(device, 'name'), 'w') as f:
        f.write(label + '\n')
    with open(os.path.join(device, 'id', 'vendor'), 'w') as f:
        f.write('045e\n')


class DecoderTests(unittest.TestCase):
    def test_recorded_xbox_pad(self):
        self.assertEqual(pressed(gamepad.Decoder(), fixtures.recorded_events('xbox')), XBOX)

    def test_recorded_dualsense(self):
        decoder = gamepad.Decoder({gamepad.ABS_X: (0, 255), gamepad.ABS_Y: (0, 255)})
        self.assertEqual(pressed(decoder, fixtures.recorded_events('dualsense')), DUALSENSE)

    def test_stick_hysteresis(self):
        d = gamepad.Decoder()
        full = 32767
        self.assertEqual(d.feed(3, gamepad.ABS_X, int(full * 0.6)), [('press', 'right')])
        self.assertEqual(d.feed(3, gamepad.ABS_X, int(full * 0.45)), [])      # still held
        self.assertEqual(d.feed(3, gamepad.ABS_X, int(full * 0.2)), [('release', 'right')])
        self.assertEqual(d.feed(3, gamepad.ABS_X, int(full * 0.5)), [])       # below press point

    def test_dpad_and_stick_together(self):
        d = gamepad.Decoder()
        self.assertEqual(d.feed(3, gamepad.ABS_HAT0Y, 1), [('press', 'down')])
        self.assertEqual(d.feed(3, gamepad.ABS_Y, 32767), [])                 # already down
        self.assertEqual(d.feed(3, gamepad.ABS_HAT0Y, 0), [])                 # stick still down
        self.assertEqual(d.feed(3, gamepad.ABS_Y, 0), [('release', 'down')])
        # D-pad as buttons (Nintendo pads), and the kernel's key repeat (value 2) ignored
        self.assertEqual(d.feed(1, gamepad.BTN_DPAD_LEFT, 1), [('press', 'left')])
        self.assertEqual(d.feed(1, gamepad.BTN_DPAD_LEFT, 0), [('release', 'left')])
        self.assertEqual(d.feed(1, gamepad.BTN_SOUTH, 2), [])
        self.assertEqual(d.feed(1, gamepad.BTN_TR, 1), [('press', 'rb')])
        d.feed(3, gamepad.ABS_HAT0X, -1)
        self.assertEqual(d.release_all(), [('release', 'left')])

    def test_event_bytes(self):
        raw = gamepad.pack(1, 304, 1, 12.5) + gamepad.pack(0, 0, 0, 12.5)
        self.assertEqual(len(raw), 2 * gamepad.EVENT.size)
        self.assertEqual(gamepad.parse(raw + raw[:5]), [(1, 304, 1), (0, 0, 0)])

    def test_find_pads(self):
        tmp = tempfile.mkdtemp(prefix='spark-games-input-')
        self.addCleanup(shutil.rmtree, tmp, True)
        sys_root, dev_root = os.path.join(tmp, 'sys'), os.path.join(tmp, 'dev')
        os.makedirs(dev_root)
        add_sysfs(sys_root, 'event3', (gamepad.BTN_SOUTH, gamepad.BTN_EAST, gamepad.BTN_MODE),
                  'Xbox Wireless Controller')
        add_sysfs(sys_root, 'event4', (30, 31, 32), 'AT Translated Set 2 keyboard')
        for name in ('event3', 'event4', 'mouse0'):
            open(os.path.join(dev_root, name), 'w').close()
        pads = gamepad.find_pads(sys_root, dev_root)
        self.assertEqual([(os.path.basename(p.node), p.name, p.vendor) for p in pads],
                         [('event3', 'Xbox Wireless Controller', '045e')])
        self.assertEqual(gamepad.find_pads(sys_root, os.path.join(tmp, 'missing')), [])
        self.assertEqual(gamepad._bits('zz'), set())


# ─── Controllers and the window ───────────────────────────────

def have_display() -> bool:
    if LINUX and not os.environ.get('DISPLAY'):
        return False
    try:
        import tkinter
        root = tkinter.Tk()
        root.destroy()
        return True
    except Exception:          # noqa: BLE001
        return False


DISPLAY = have_display()


def pump(root, seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.01)


@unittest.skipUnless(LINUX and DISPLAY, "needs Linux (evdev, FIFOs, inotify) and a display")
class GamepadReaderTests(unittest.TestCase):
    """The real reader in Tk's event loop, fed recorded events through a FIFO per pad."""

    def setUp(self):
        import tkinter
        self.tmp = tempfile.mkdtemp(prefix='spark-games-pads-')
        self.sys_root = os.path.join(self.tmp, 'sys')
        self.dev_root = os.path.join(self.tmp, 'dev')
        os.makedirs(self.sys_root)
        os.makedirs(self.dev_root)
        self.root = tkinter.Tk()
        self.actions, self.changes, self.writers = [], [], []
        self.pads = gamepad.Gamepads(self.root, self.actions.append, self.sys_root,
                                     self.dev_root,
                                     on_change=lambda n, c: self.changes.append((n, c)))

    def tearDown(self):
        self.pads.set_active(False)
        for fd in self.writers:
            os.close(fd)
        self.root.destroy()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def plug(self, name='event7', label='Xbox Wireless Controller') -> int:
        add_sysfs(self.sys_root, name, (gamepad.BTN_SOUTH, gamepad.BTN_EAST), label)
        node = os.path.join(self.dev_root, name)
        os.mkfifo(node)
        fd = os.open(node, os.O_RDWR | os.O_NONBLOCK)     # a writer that is always there
        self.writers.append(fd)
        return fd

    def play(self, fd, name):
        for stamp, ev_type, code, value in fixtures.recorded_events(name):
            os.write(fd, gamepad.pack(ev_type, code, value, stamp))

    def test_recorded_events_through_the_reader(self):
        fd = self.plug()
        self.pads.set_active(True)
        self.assertEqual(len(self.pads.open), 1)
        self.assertEqual(self.pads.names(), ['Xbox Wireless Controller'])
        self.play(fd, 'xbox')
        pump(self.root, 0.3)
        self.assertEqual(self.actions, XBOX)

    def test_held_direction_repeats_until_released(self):
        fd = self.plug()
        self.pads.set_active(True)
        os.write(fd, gamepad.pack(3, gamepad.ABS_HAT0Y, 1) + gamepad.pack(0, 0, 0))
        pump(self.root, 0.8)
        held = self.actions.count('down')
        self.assertGreaterEqual(held, 3)                   # press, then repeats after 400 ms
        os.write(fd, gamepad.pack(3, gamepad.ABS_HAT0Y, 0) + gamepad.pack(0, 0, 0))
        pump(self.root, 0.4)
        self.assertLessEqual(self.actions.count('down'), held + 1)
        count = self.actions.count('down')
        pump(self.root, 0.4)
        self.assertEqual(self.actions.count('down'), count)

    def test_plugged_in_later_and_unplugged(self):
        self.pads.set_active(True)
        self.assertEqual(self.pads.open, {})
        self.assertGreaterEqual(self.pads.watch.fd, 0)     # inotify on the device folder
        fd = self.plug(label='Late Pad')
        pump(self.root, 0.8)                               # inotify, then a rescan after 250 ms
        self.assertEqual(self.pads.names(), ['Late Pad'])
        self.assertEqual(self.changes, [('Late Pad', True)])
        self.play(fd, 'xbox')
        pump(self.root, 0.3)
        self.assertEqual(self.actions, XBOX)
        shutil.rmtree(os.path.join(self.sys_root, 'event7'))
        os.unlink(os.path.join(self.dev_root, 'event7'))
        pump(self.root, 0.8)
        self.assertEqual(self.pads.open, {})
        self.assertEqual(self.changes[-1], ('Late Pad', False))

    def test_nothing_open_while_inactive(self):
        fd = self.plug()
        self.pads.set_active(True)
        self.pads.set_active(False)
        self.assertEqual(self.pads.open, {})
        self.assertIsNone(self.pads.watch)
        self.play(fd, 'xbox')
        pump(self.root, 0.3)
        self.assertEqual(self.actions, [])                 # the game gets the buttons, not us

    def test_unreadable_pad_is_retried(self):
        node_fd = self.plug()
        node = os.path.join(self.dev_root, 'event7')
        if os.geteuid() == 0:
            self.skipTest("root can read anything")
        os.chmod(node, 0)
        self.pads.set_active(True)
        self.assertEqual(self.pads.open, {})
        os.chmod(node, 0o660)                              # udev grants access: IN_ATTRIB
        pump(self.root, 0.8)
        self.assertEqual(len(self.pads.open), 1)
        self.play(node_fd, 'xbox')
        pump(self.root, 0.3)
        self.assertEqual(self.actions, XBOX)


@unittest.skipUnless(DISPLAY, "needs a display")
class WindowTests(unittest.TestCase):
    def setUp(self):
        from sparkgames import anticheat
        from sparkgames import app as appmod
        self.appmod = appmod
        self.tmp = tempfile.mkdtemp(prefix='spark-games-ui2-')
        os.environ['SPARK_GAMES_REDUCED_MOTION'] = '1'
        for path in (library.cache_path(), anticheat.cache_path()):
            if os.path.exists(path):
                os.remove(path)
        self.app = None

    def tearDown(self):
        if self.app is not None:
            try:
                self.app.pads.set_active(False)
                self.app.root.destroy()
            except Exception:      # noqa: BLE001
                pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def start(self, big=False):
        home = fixtures.materialize(os.path.join(self.tmp, 'home'))
        self.app = self.appmod.App(home, big_screen=big)
        self.app._apply_focus = lambda: None        # the tests decide when pads are read
        self.app.settings['anticheat'] = False
        if not big:
            self.app.root.geometry('1100x760')
        pump(self.app.root, 0.3)
        deadline = time.time() + 15
        while self.app.scanning and time.time() < deadline:
            pump(self.app.root, 0.05)
        self.assertFalse(self.app.scanning)
        pump(self.app.root, 0.3)
        return self.app

    def test_controller_in_the_window(self):
        app = self.start()
        lib = app.library
        app.pad_action('right')
        self.assertEqual(lib.selected, 1)
        app.pad_action('rb')
        self.assertEqual(lib.source, 'steam')
        app.pad_action('lb')
        self.assertEqual(lib.source, 'all')
        app.pad_action('start')
        pump(app.root, 0.2)
        self.assertEqual(type(app.view).__name__, 'GamePage')
        app.pad_action('b')
        self.assertIs(app.view, lib)
        app.pad_action('guide')
        pump(app.root, 0.2)
        self.assertIsNotNone(app.big)
        app.pad_action('b')
        self.assertIsNone(app.big)

    def test_big_screen(self):
        app = self.start()
        app.enter_big()
        app.root.geometry('1920x1080')
        pump(app.root, 0.5)
        big = app.big
        self.assertIs(app.view, big)
        self.assertEqual(app.head.winfo_manager(), '')           # the window's header is hidden
        self.assertEqual([r.title for r in big.rows],
                         ['KEEP PLAYING', 'STEAM', 'EPIC', 'GOG', 'AMAZON', 'LUTRIS', 'ITCH',
                          'BOTTLES', 'MINECRAFT', 'PRISM', 'ALL GAMES'])
        self.assertEqual(big.current().key, 'epic:Sugar')        # the last game played
        c = big.canvas
        texts = [i for i in c.find_all() if c.type(i) == 'text']
        self.assertTrue(texts)
        # readable from across the room: sized from the height (1080 lines is the design size),
        # covers a third of the screen tall, no text under 20 px at 1080 lines
        h = c.winfo_height()
        if h >= 700:
            smallest = min(int(c.tk.call('font', 'metrics', c.itemcget(i, 'font'),
                                         '-linespace')) for i in texts)
            self.assertGreaterEqual(smallest, 20 * h / 1080 - 1)
            self.assertAlmostEqual(big.metrics()['cover_h'] / h, 330 / 1080, delta=0.01)
        # rows and covers
        big.pad('right')
        self.assertEqual(big.rows[0].col, 1)
        big.pad('down')
        self.assertEqual(big.row, 1)
        self.assertEqual(big.current().source, 'steam')
        for _ in range(20):                                       # held right: stops at the end
            big.pad('right')
        self.assertEqual(big.rows[1].col, len(big.rows[1].games) - 1)
        big.pad('rb')
        self.assertEqual(big.row, 2)
        # the game page, and back
        big.pad('start')
        self.assertEqual(big.layer, 'page')
        pump(app.root, 0.2)
        big.pad('b')
        self.assertEqual(big.layer, 'rows')
        # searching with the on-screen keyboard: down, right, right is P
        big.pad('y')
        self.assertEqual(big.layer, 'search')
        for action in ('down', 'right', 'right', 'a'):
            big.pad(action)
        self.assertEqual(big.query, 'p')
        self.assertTrue(big.rows and all('p' in g.title.lower() for g in big.rows[0].games))
        big.pad('y')
        self.assertEqual((big.layer, big.query), ('rows', 'p'))
        pump(app.root, 0.2)
        big.pad('b')                                              # first B clears the search
        self.assertEqual(big.query, '')
        big.pad('b')                                              # then leaves
        pump(app.root, 0.2)
        self.assertIsNone(app.big)
        self.assertIs(app.view, app.library)
        self.assertEqual(app.head.winfo_manager(), 'pack')
        self.assertEqual(app.back.winfo_manager(), '')
        # F11 goes in and out too
        app._key(self.appmod.PadEvent('F11'))
        self.assertIsNotNone(app.big)
        app._key(self.appmod.PadEvent('Escape'))
        self.assertIsNone(app.big)

    def test_big_screen_flag_and_keyboard(self):
        app = self.start(big=True)
        self.assertIsNotNone(app.big)
        big = app.big
        pump(app.root, 0.3)
        self.assertTrue(big.canvas.find_all())
        ev = self.appmod.PadEvent
        app._key(ev('slash'))
        self.assertEqual(big.layer, 'search')
        for char in 'fab':
            e = ev(char)
            e.char = char
            app._key(e)
        self.assertEqual(big.query, 'fab')
        self.assertEqual([g.key for g in big.rows[0].games], ['prism:Fabric 1.21'])
        app._key(ev('Return'))
        self.assertEqual(big.layer, 'rows')
        app._key(ev('space'))
        self.assertEqual(big.layer, 'page')
        app._key(ev('Escape'))
        app._key(ev('Escape'))
        app._key(ev('Escape'))
        self.assertIsNone(app.big)

    @unittest.skipUnless(LINUX, "process CPU time is measured on Linux")
    def test_no_cpu_when_idle(self):
        """No controller and nothing to do: the process sleeps, both with the window in front
        (pads read, the device folder watched) and in the background (nothing open)."""
        app = self.start()
        empty = os.path.join(self.tmp, 'input')
        os.makedirs(os.path.join(empty, 'sys'))
        os.makedirs(os.path.join(empty, 'dev'))
        app.pads.set_active(False)
        app.pads.sys_root, app.pads.dev_root = os.path.join(empty, 'sys'), \
            os.path.join(empty, 'dev')
        pump(app.root, 3.0)                     # let the status line settle
        for active in (True, False):
            app.pads.set_active(active)
            self.assertEqual(app.pads.watch is not None, active)
            pump(app.root, 0.3)
            before = time.process_time()
            app.root.after(3000, app.root.quit)
            app.root.mainloop()
            used = time.process_time() - before
            self.assertLess(used, 0.15, f"{used:.3f} s of CPU in 3 s idle (active={active})")
        # the big screen idles too
        app.enter_big()
        pump(app.root, 1.0)
        before = time.process_time()
        app.root.after(3000, app.root.quit)
        app.root.mainloop()
        self.assertLess(time.process_time() - before, 0.15)

    def test_settings_lists_controllers(self):
        app = self.start()
        app.show_settings()
        pump(app.root, 0.2)
        texts = []

        def walk(widget):
            for child in widget.winfo_children():
                try:
                    texts.append(child.cget('text'))
                except Exception:      # noqa: BLE001
                    pass
                walk(child)
        walk(app.view)
        self.assertIn(strings.tr('set_pads'), texts)
        self.assertIn(strings.tr('set_pads_none'), texts)


if __name__ == '__main__':
    unittest.main()
