"""Spark Games tests. Plain unittest:

    python -m unittest discover -s files/spark-games/tests -v

Parser, launch and playtime tests run anywhere. UI tests need a display (on CI: xvfb-run).
The fixtures are in tests/fixtures/ (see sparkgames/fixtures.py for what they hold).
"""

import json
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
sys.path.insert(0, APP_DIR)
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
    os.environ[var] = tempfile.mkdtemp(prefix=f'spark-games-{var.lower()}-')
os.environ['SPARK_LANG'] = 'en'          # the words below are checked in English

from sparkgames import (VERSION, anticheat, covers, fixtures, heroic, launch,  # noqa: E402
                        library, lutris, owngames, steam, strings, vdf)
from sparkgames.core import Game, matches, sort_recent, sort_title  # noqa: E402

logging.getLogger('spark-games').addHandler(logging.NullHandler())   # expected warnings stay quiet

BACKSLASH = chr(92)


def fake_which(*present):
    return lambda name: f'/usr/bin/{name}' if name in present else None


class FixtureHome(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='spark-games-home-')
        self.home = fixtures.materialize(os.path.join(self.tmp, 'home'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def by_key(self, games):
        return {g.key: g for g in games}


# ─── VDF ──────────────────────────────────────────────────────

class VDFTests(unittest.TestCase):
    def test_nested_and_case_insensitive(self):
        data = vdf.loads('"Root" { "Child" { "Value" "42" } "other" "x" }')
        self.assertEqual(vdf.get(data, 'root', 'child', 'value'), '42')
        self.assertEqual(vdf.get(data, 'ROOT', 'Other'), 'x')
        self.assertIsNone(vdf.get(data, 'root', 'missing'))
        self.assertEqual(vdf.get(data, 'root', 'other', 'deeper', default='d'), 'd')

    def test_escapes_comments_conditions(self):
        text = ('// comment\n"a"\n{\n\t"name"\t"say ' + BACKSLASH + '"hi' + BACKSLASH +
                '" ' + BACKSLASH + BACKSLASH + ' done"\n\t"tab"\t"x' + BACKSLASH + 'ty"\n'
                '\t"opt"\t"-w"\t[$WIN32]\n\tunquoted value\n}\n')
        data = vdf.loads(text)
        self.assertEqual(vdf.get(data, 'a', 'name'), 'say "hi" ' + BACKSLASH + ' done')
        self.assertEqual(vdf.get(data, 'a', 'tab'), 'x\ty')
        self.assertEqual(vdf.get(data, 'a', 'opt'), '-w')
        self.assertEqual(vdf.get(data, 'a', 'unquoted'), 'value')

    def test_bom_and_errors(self):
        self.assertEqual(vdf.loads(chr(0xFEFF) + '"a" "b"'), {'a': 'b'})
        for bad in ('"a" {', '"a" { "b" }', '}', '"a" "unclosed', '"a"'):
            with self.assertRaises(vdf.VDFError, msg=bad):
                vdf.loads(bad)

    def test_to_int(self):
        self.assertEqual(vdf.to_int('17'), 17)
        self.assertEqual(vdf.to_int(None), 0)
        self.assertEqual(vdf.to_int('x', 5), 5)


# ─── Sources ──────────────────────────────────────────────────

class SteamTests(FixtureHome):
    def test_flatpak_steam_two_libraries(self):
        roots = steam.roots(self.home)
        self.assertEqual(len(roots), 1)
        root, flatpak = roots[0]
        self.assertTrue(flatpak)
        self.assertIn('com.valvesoftware.Steam', root)
        folders = steam.library_folders(root)
        self.assertEqual(len(folders), 2)
        self.assertTrue(folders[1].replace(BACKSLASH, '/').endswith('Games/SteamLibrary'))

    def test_games_tools_and_stats(self):
        games = self.by_key(steam.scan(self.home, []))
        self.assertEqual(sorted(k for k in games if k.startswith('steam:')),
                         ['steam:1086940', 'steam:1145360', 'steam:413150', 'steam:620',
                          'steam:999990'])
        # Proton (known appid and name), the redistributables, a tool found by its
        # toolmanifest.vdf, and a game still downloading are all left out
        for skipped in ('1493710', '228980', '3000010', '999001'):
            self.assertNotIn(f'steam:{skipped}', games)
        portal = games['steam:620']
        self.assertEqual(portal.title, 'Portal 2')
        self.assertEqual(portal.playtime, 754)
        self.assertEqual(portal.last_played, 1710000000)      # localconfig is newer
        self.assertTrue(portal.cover.endswith('library_600x900.jpg'))
        self.assertTrue(portal.flatpak)
        self.assertEqual(portal.launch, {'appid': '620', 'flatpak': True})
        self.assertTrue(games['steam:1145360'].cover)          # hashed sub-folder layout
        self.assertTrue(games['steam:413150'].cover)           # old flat layout
        self.assertEqual(games['steam:1086940'].last_played, 1715000000)   # from the manifest
        self.assertEqual(games['steam:999990'].title, 'The "Quoted" Game ' + BACKSLASH + ' Deluxe')
        self.assertIn('SteamLibrary', games['steam:1145360'].install_dir)

    def test_regular_steam(self):
        native = os.path.join(self.tmp, 'native')
        shutil.copytree(os.path.join(self.home, fixtures.STEAM),
                        os.path.join(native, '.local', 'share', 'Steam'))
        games = steam.scan(native, [])
        portal = self.by_key(games)['steam:620']
        self.assertFalse(portal.flatpak)
        # the second library is listed by its absolute path, so it is found here too
        self.assertEqual(len(games), fixtures.EXPECTED['steam'])

    def test_broken_manifest_is_skipped(self):
        bad = os.path.join(self.home, fixtures.STEAM, 'steamapps', 'appmanifest_1.acf')
        with open(bad, 'w', encoding='utf-8') as f:
            f.write('"AppState" { "appid" ')
        watch = []
        games = steam.scan(self.home, watch)
        self.assertEqual(len(games), fixtures.EXPECTED['steam'])
        self.assertTrue(any(w.endswith('libraryfolders.vdf') for w in watch))

    def test_old_libraryfolders_format(self):
        root = os.path.join(self.home, fixtures.STEAM)
        second = os.path.join(self.home, 'Games', 'SteamLibrary').replace(BACKSLASH, '/')
        with open(os.path.join(root, 'steamapps', 'libraryfolders.vdf'), 'w') as f:
            f.write('"LibraryFolders" { "TimeNextStatsReport" "1" "1" "%s" }' % second)
        self.assertEqual(len(steam.library_folders(root)), 2)


# Steam's binary caches, written the way Steam writes them (tests only)

def binary_kv(data, strings=None):
    """KeyValues as Steam writes them in appinfo.vdf (strings: the v29 string table, filled in
    as keys are met) and packageinfo.vdf (strings None: keys inline)."""
    import struct
    out = bytearray()
    for key, value in data.items():
        if strings is None:
            name = key.encode() + b'\x00'
        else:
            if key not in strings:
                strings.append(key)
            name = struct.pack('<I', strings.index(key))
        if isinstance(value, dict):
            out += b'\x00' + name + binary_kv(value, strings)
        elif isinstance(value, str):
            out += b'\x01' + name + value.encode() + b'\x00'
        else:
            out += b'\x02' + name + struct.pack('<i', value)
    return bytes(out) + b'\x08'


def write_packageinfo(path, packages):
    import struct
    out = bytearray(struct.pack('<II', 0x06565528, 1))
    for package, apps in packages.items():
        out += struct.pack('<I', package) + b'\x11' * 20 + struct.pack('<IQ', 7, 0)
        out += binary_kv({str(package): {'packageid': package,
                                         'appids': {str(i): a for i, a in enumerate(apps)}}})
    out += struct.pack('<I', 0xFFFFFFFF)
    with open(path, 'wb') as f:
        f.write(out)


def write_appinfo(path, apps, version=29):
    """apps: appid -> (name, type)."""
    import struct
    strings = [] if version == 29 else None
    body = bytearray()
    for appid, (name, kind) in apps.items():
        data = binary_kv({'appinfo': {'appid': appid, 'common': {'name': name, 'type': kind}}},
                         strings)
        head = struct.pack('<IIQ', 2, 1700000000, 0) + b'\x22' * 20 + struct.pack('<I', 9) \
            + b'\x33' * 20
        body += struct.pack('<II', appid, len(head) + len(data)) + head + data
    body += struct.pack('<I', 0)
    if version == 29:
        table = struct.pack('<I', len(strings)) + b''.join(k.encode() + b'\x00' for k in strings)
        header = struct.pack('<IIq', 0x07564429, 1, 16 + len(body))
        out = header + bytes(body) + table
    else:
        out = struct.pack('<II', 0x07564428, 1) + bytes(body)
    with open(path, 'wb') as f:
        f.write(out)


class SteamOwnedTests(FixtureHome):
    """Games you own on Steam and haven't installed, from Steam's binary caches."""
    APPS = {620: ('Portal 2', 'game'), 400: ('Portal', 'game'), 8930: ('Civilization V', 'Game'),
            65980: ('Civ V: Gods and Kings', 'dlc'), 393380: ('Squad', 'game'),
            480: ('Spacewar', 'game'), 228980: ('Steamworks Common Redistributables', 'game')}

    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.home, fixtures.STEAM)
        self.cache = os.path.join(self.root, 'appcache')
        # 393380 is a free weekend that ended: a package, but no art in the library
        write_packageinfo(os.path.join(self.cache, 'packageinfo.vdf'),
                          {0: [480], 7: [620, 400, 228980], 31: [8930, 65980], 9001: [393380]})
        for appid in (620, 400, 8930, 65980, 480, 228980):
            os.makedirs(os.path.join(self.cache, 'librarycache', str(appid)), exist_ok=True)
        with open(os.path.join(self.cache, 'librarycache', '400', 'library_600x900.jpg'),
                  'wb') as f:
            f.write(b'jpg')

    def check(self):
        games = self.by_key(steam.scan(self.home, []))
        owned = {k for k, g in games.items() if not g.installed}
        # the DLC, the free weekend, package 0's Spacewar and the redistributables are left out
        self.assertEqual(owned, {'steam:400', 'steam:8930'})
        self.assertTrue(games['steam:620'].installed)          # installed wins
        self.assertEqual(games['steam:8930'].title, 'Civilization V')
        portal = games['steam:400']
        self.assertTrue(portal.cover.endswith('library_600x900.jpg'))
        self.assertEqual(portal.launch, {'appid': '400', 'flatpak': True})
        self.assertEqual(launch.plan(portal, which=fake_which('flatpak')).argv,
                         ['flatpak', 'run', 'com.valvesoftware.Steam', 'steam://install/400'])

    def test_appinfo_29(self):
        write_appinfo(os.path.join(self.cache, 'appinfo.vdf'), self.APPS, 29)
        self.check()

    def test_appinfo_28(self):
        write_appinfo(os.path.join(self.cache, 'appinfo.vdf'), self.APPS, 28)
        self.check()

    def test_broken_caches_keep_the_installed_games(self):
        with open(os.path.join(self.cache, 'appinfo.vdf'), 'wb') as f:
            f.write(b'\x29\x44\x56\x07\x01\x00\x00\x00\xff\xff\xff\x7f\x00\x00\x00\x00')
        watch = []
        games = steam.scan(self.home, watch)
        self.assertEqual(len(games), fixtures.EXPECTED['steam'])
        self.assertTrue(all(g.installed for g in games))
        self.assertTrue(any(w.endswith('packageinfo.vdf') for w in watch))
        with open(os.path.join(self.cache, 'appinfo.vdf'), 'wb') as f:
            f.write(b'\x99\x99\x99\x99\x01\x00\x00\x00')        # a version we don't know
        self.assertEqual(len(steam.scan(self.home, [])), fixtures.EXPECTED['steam'])

    def test_no_caches_yet(self):
        os.remove(os.path.join(self.cache, 'packageinfo.vdf'))
        self.assertEqual(steam.owned(self.root), {})

    def test_art_listing_matches_the_old_glob(self):
        lib = os.path.join(self.cache, 'librarycache')
        for name in ('1000_header.jpg', '1000_library_600x900.jpg', '2000_icon.jpg',
                     '.3000_hidden.jpg', '30000_header.jpg', '4000'):
            path = os.path.join(lib, name)
            if name == '4000':
                os.makedirs(path)
            else:
                with open(path, 'wb') as f:
                    f.write(b'x')
        listing = steam.art_listing(self.root)
        for appid, expected in (('1000', True), ('2000', True), ('4000', True), ('620', True),
                                ('3000', False), ('30000', True), ('300', False),
                                ('99999', False)):
            self.assertEqual(steam.has_art(self.root, appid, listing), expected, appid)
            self.assertEqual(steam.has_art(self.root, appid), expected, appid)
        self.assertFalse(steam.has_art(os.path.join(self.tmp, 'nowhere'), '1000'))

    def test_scan_lists_librarycache_once(self):
        write_appinfo(os.path.join(self.cache, 'appinfo.vdf'), self.APPS, 29)
        lib = os.path.join(self.cache, 'librarycache')
        with mock.patch.object(steam.os, 'scandir', wraps=os.scandir) as scan:
            steam.owned(self.root)
        self.assertEqual(sum(1 for c in scan.call_args_list if c.args[0] == lib), 1)

    def test_names_are_not_parsed_again_until_the_files_change(self):
        info = os.path.join(self.cache, 'appinfo.vdf')
        write_appinfo(info, self.APPS, 29)
        with mock.patch.object(steam, 'app_names', wraps=steam.app_names) as parse:
            first = steam.owned(self.root)
            self.assertEqual(steam.owned(self.root), first)
            self.assertEqual(parse.call_count, 1)
            steam._names_memory.clear()            # a new process reads the cache file
            self.assertEqual(steam.owned(self.root), first)
            self.assertEqual(parse.call_count, 1)
            self.assertEqual(first['400'], 'Portal')
            # new art for an app the last parse never looked at: parse again
            os.makedirs(os.path.join(self.cache, 'librarycache', '393380'))
            self.assertIn('393380', steam.owned(self.root))
            self.assertEqual(parse.call_count, 2)
            # appinfo.vdf changed: parse again and use the new names
            apps = dict(self.APPS)
            apps[400] = ('Portal Reloaded', 'game')
            write_appinfo(info, apps, 29)
            self.assertEqual(steam.owned(self.root)['400'], 'Portal Reloaded')
            self.assertEqual(parse.call_count, 3)

    def test_damaged_names_cache_is_ignored(self):
        write_appinfo(os.path.join(self.cache, 'appinfo.vdf'), self.APPS, 29)
        first = steam.owned(self.root)
        steam._names_memory.clear()
        path = os.path.join(steam.cache_dir(), 'steam-names.json')
        with open(path, 'w', encoding='utf-8') as f:
            f.write('{"%s": {"sig": 1}}' % self.root)
        self.assertEqual(steam.owned(self.root), first)

    def test_owned_steam_games_in_the_library(self):
        write_appinfo(os.path.join(self.cache, 'appinfo.vdf'), self.APPS, 29)
        games = self.by_key(library.scan_all(self.home).games)
        self.assertFalse(games['steam:400'].installed)
        self.assertTrue(games['steam:620'].installed)


class HeroicTests(FixtureHome):
    def test_each_store(self):
        games = self.by_key(heroic.scan(self.home, []))
        self.assertEqual(sorted(games), ['amazon:amzn1.adg.product.0000-example',
                                         'epic:Sugar', 'gog:1207658930'])
        celeste = games['epic:Sugar']
        self.assertEqual(celeste.title, 'Celeste')
        self.assertEqual(celeste.playtime, 95)
        self.assertGreater(celeste.last_played, 1700000000)
        self.assertTrue(celeste.cover)                     # from images-cache
        self.assertEqual(celeste.launch['runner'], 'legendary')
        self.assertTrue(celeste.flatpak)
        self.assertEqual(games['gog:1207658930'].title, 'The Witcher: Enhanced Edition')
        self.assertEqual(games['gog:1207658930'].launch['runner'], 'gog')
        amazon = games['amazon:amzn1.adg.product.0000-example']
        self.assertEqual(amazon.title, 'Amazon Example Game')
        self.assertEqual(amazon.launch['runner'], 'nile')

    def test_dlc_skipped(self):
        keys = [g.key for g in heroic.scan(self.home, [])]
        self.assertNotIn('epic:SugarSoundtrack', keys)

    def test_changed_format_is_skipped(self):
        root = os.path.join(self.home, fixtures.HEROIC)
        with open(os.path.join(root, 'gog_store', 'installed.json'), 'w') as f:
            json.dump({'something': 'else'}, f)
        keys = [g.key for g in heroic.scan(self.home, [])]
        self.assertEqual(len(keys), 2)
        self.assertNotIn('gog:1207658930', keys)

    def test_regular_heroic(self):
        native = os.path.join(self.tmp, 'native')
        shutil.copytree(os.path.join(self.home, fixtures.HEROIC),
                        os.path.join(native, '.config', 'heroic'))
        games = heroic.scan(native, [])
        self.assertEqual(len(games), 3)
        self.assertFalse(any(g.flatpak for g in games))


class LutrisTests(FixtureHome):
    def test_installed_games(self):
        games = self.by_key(lutris.scan(self.home, []))
        self.assertEqual(sorted(games), ['lutris:1', 'lutris:4'])     # not Steam's, not removed
        bnet = games['lutris:1']
        self.assertEqual(bnet.title, 'Battle.net')
        self.assertEqual(bnet.playtime, 150)                          # 2.5 hours
        self.assertEqual(bnet.last_played, 1730000000)
        self.assertTrue(bnet.cover.endswith('battlenet.jpg'))
        self.assertFalse(bnet.flatpak)
        self.assertEqual(games['lutris:4'].playtime, 0)               # NULL playtime

    def test_flatpak_lutris(self):
        flat = os.path.join(self.tmp, 'flat')
        shutil.copytree(os.path.join(self.home, fixtures.LUTRIS),
                        os.path.join(flat, '.var', 'app', 'net.lutris.Lutris', 'data', 'lutris'))
        games = lutris.scan(flat, [])
        self.assertEqual(len(games), 2)
        self.assertTrue(all(g.flatpak and g.launch['flatpak'] for g in games))

    def test_changed_schema_is_skipped(self):
        db = os.path.join(self.home, fixtures.LUTRIS, 'pga.db')
        os.remove(db)
        con = sqlite3.connect(db)
        con.execute('CREATE TABLE games (title TEXT)')
        con.commit()
        con.close()
        self.assertEqual(lutris.scan(self.home, []), [])

    def test_database_untouched(self):
        db = os.path.join(self.home, fixtures.LUTRIS, 'pga.db')
        before = os.stat(db).st_mtime_ns
        lutris.scan(self.home, [])
        self.assertEqual(os.stat(db).st_mtime_ns, before)


class LibraryTests(FixtureHome):
    def test_scan_all_finds_every_fixture(self):
        result = library.scan_all(self.home)
        counts = {}
        for g in result.games:
            counts[g.source] = counts.get(g.source, 0) + 1
        self.assertEqual(counts, fixtures.EXPECTED)
        self.assertEqual(result.launchers, {'steam', 'heroic', 'lutris', 'itch', 'bottles',
                                            'minecraft'})
        self.assertEqual(result.problems, [])

    def test_no_launchers(self):
        empty = os.path.join(self.tmp, 'empty')
        os.makedirs(empty)
        result = library.scan_all(empty)
        self.assertEqual(result.games, [])
        self.assertEqual(result.launchers, set())

    def test_cache_round_trip(self):
        result = library.scan_all(self.home)
        library.save_cache(result)
        cached = library.load_cache()
        self.assertEqual([g.to_json() for g in cached.games], [g.to_json() for g in result.games])
        self.assertEqual(cached.launchers, result.launchers)

    def test_signature_sees_changes(self):
        result = library.scan_all(self.home)
        sig = library.signature(result.watch)
        self.assertEqual(sig, library.signature(result.watch))
        lib = os.path.join(self.home, 'Games', 'SteamLibrary', 'steamapps')
        path = os.path.join(lib, 'appmanifest_1.acf')
        with open(path, 'w') as f:
            f.write('"AppState" { "appid" "1" "name" "New" "StateFlags" "4" }')
        future = time.time() + 5
        os.utime(lib, (future, future))
        self.assertNotEqual(sig, library.signature(result.watch))

    def test_own_games(self):
        exe = os.path.join(self.tmp, 'game.sh')
        with open(exe, 'w') as f:
            f.write('#!/bin/sh\n')
        item = owngames.add('My Game', exe)
        self.assertFalse(item['windows'])
        self.assertTrue(owngames.add('Win', os.path.join(self.tmp, 'Setup.EXE'))['windows'])
        keys = [g.key for g in library.scan_all(self.home).games if g.source == 'own']
        self.assertEqual(len(keys), 2)
        owngames.remove(item['id'])
        self.assertEqual(len(owngames.load()), 1)
        owngames.save([])

    def test_merge_sessions(self):
        a = Game('steam:1', 'A', 'steam', playtime=10, last_played=100)
        b = Game('own:x', 'B', 'own')
        library.merge_sessions([a, b], {'steam:1': {'minutes': 99, 'last': 500},
                                        'own:x': {'minutes': 7, 'last': 50}})
        self.assertEqual((a.playtime, a.last_played), (10, 500))    # Steam's own count wins
        self.assertEqual((b.playtime, b.last_played), (7, 50))


# ─── Sorting, search, words ───────────────────────────────────

class OrderTests(unittest.TestCase):
    def test_sort_and_search(self):
        games = [Game('a', 'The Zed', 'steam', last_played=5), Game('b', 'alpha', 'gog'),
                 Game('c', "Baldur's Gate 3", 'steam', last_played=9)]
        self.assertEqual([g.key for g in sort_recent(games)], ['c', 'a', 'b'])
        self.assertEqual([g.key for g in sort_title(games)], ['b', 'c', 'a'])
        self.assertTrue(matches(games[2], 'baldurs 3'))
        self.assertTrue(matches(games[2], "BALDUR'S"))
        self.assertFalse(matches(games[2], 'gate 2'))
        self.assertTrue(matches(games[0], ''))

    def test_words(self):
        self.assertEqual(strings.playtime(0), '—')
        self.assertEqual(strings.playtime(45), '45 min')
        self.assertEqual(strings.playtime(125), '2 h 5 min')
        self.assertEqual(strings.playtime(6000), '100 h')
        now = time.time()
        self.assertEqual(strings.last_played(0), 'Not played yet')
        self.assertEqual(strings.last_played(int(now) - 1, now), 'Today')
        self.assertEqual(strings.last_played(int(now) - 3 * 86400, now), '3 days ago')
        self.assertRegex(strings.last_played(1600000000, now), r'^\d{4}-\d{2}-\d{2}$')

    def test_every_error_code_has_words(self):
        for code in ('missing_program', 'missing_file', 'not_executable', 'no_umu',
                     'start_failed', 'unknown_source', 'unexpected'):
            self.assertIn('err_' + code, strings.EN)


# ─── Launching and playtime ───────────────────────────────────

class LaunchTests(FixtureHome):
    def setUp(self):
        super().setUp()
        self.games = self.by_key(library.scan_all(self.home).games)

    def test_steam_flatpak_and_regular(self):
        portal = self.games['steam:620']
        p = launch.plan(portal, which=fake_which('flatpak'))
        self.assertEqual(p.argv, ['flatpak', 'run', 'com.valvesoftware.Steam',
                                  'steam://rungameid/620'])
        self.assertFalse(p.wait)
        self.assertEqual(p.watch_dir, portal.install_dir)
        portal.launch['flatpak'] = False
        self.assertEqual(launch.plan(portal, which=fake_which('steam')).argv,
                         ['steam', 'steam://rungameid/620'])
        self.assertEqual(launch.plan(portal, which=fake_which('xdg-open')).argv,
                         ['xdg-open', 'steam://rungameid/620'])
        with self.assertRaises(launch.LaunchError):
            launch.plan(portal, which=fake_which())

    def test_heroic(self):
        self.assertEqual(launch.plan(self.games['epic:Sugar'], which=fake_which('xdg-open')).argv,
                         ['xdg-open', 'heroic://launch/legendary/Sugar'])
        self.assertEqual(launch.plan(self.games['gog:1207658930'],
                                     which=fake_which('xdg-open')).argv,
                         ['xdg-open', 'heroic://launch/gog/1207658930'])
        amazon = self.games['amazon:amzn1.adg.product.0000-example']
        self.assertEqual(launch.plan(amazon, which=fake_which('xdg-open')).argv[1],
                         'heroic://launch/nile/amzn1.adg.product.0000-example')

    def test_lutris_regular_and_flatpak(self):
        bnet = self.games['lutris:1']
        self.assertEqual(launch.plan(bnet, which=fake_which('lutris')).argv,
                         ['lutris', 'lutris:rungameid/1'])
        bnet.launch['flatpak'] = True
        self.assertEqual(launch.plan(bnet, which=fake_which('flatpak')).argv,
                         ['flatpak', 'run', 'net.lutris.Lutris', 'lutris:rungameid/1'])

    def test_own_native_and_windows(self):
        exe = os.path.join(self.tmp, 'run.sh')
        with open(exe, 'w') as f:
            f.write('#!/bin/sh\n')
        os.chmod(exe, 0o755)
        game = Game('own:a', 'A', 'own', launch={'id': 'a', 'exe': exe, 'args': ['-x'],
                                                 'windows': False})
        p = launch.plan(game, {'mangohud': True, 'gamemode': True},
                        which=fake_which('gamemoderun'))
        self.assertEqual(p.argv, ['gamemoderun', exe, '-x'])
        self.assertEqual(p.env, {'MANGOHUD': '1'})
        self.assertTrue(p.wait)
        self.assertEqual(launch.plan(game, {'gamemode': True}, which=fake_which()).argv,
                         [exe, '-x'])                      # no GameMode installed: plain start
        win = Game('own:w', 'W', 'own', launch={'id': 'w', 'exe': exe, 'windows': True})
        p = launch.plan(win, which=fake_which('umu-run'))
        self.assertEqual(p.argv, ['umu-run', exe])
        self.assertTrue(p.env['WINEPREFIX'].endswith(os.path.join('prefixes', 'w')))
        with self.assertRaises(launch.LaunchError) as ctx:
            launch.plan(win, which=fake_which())
        self.assertEqual(ctx.exception.code, 'no_umu')
        gone = Game('own:g', 'G', 'own', launch={'exe': os.path.join(self.tmp, 'nope')})
        with self.assertRaises(launch.LaunchError) as ctx:
            launch.plan(gone, which=fake_which())
        self.assertEqual(ctx.exception.code, 'missing_file')

    def test_steam_paste_line(self):
        self.assertEqual(launch.steam_paste_line(True, True), 'MANGOHUD=1 gamemoderun %command%')
        self.assertEqual(launch.steam_paste_line(False, False), '%command%')

    def test_running_from(self):
        proc = os.path.join(self.tmp, 'proc')
        game_dir = os.path.join(self.tmp, 'Games', 'Hades')
        for pid, cmd in (('10', b'/usr/bin/steam\0-silent'),
                         ('11', b'reaper\0SteamLaunch\0--\0' + game_dir.encode() + b'/Hades\0'),
                         ('self', b'x')):
            os.makedirs(os.path.join(proc, pid))
            with open(os.path.join(proc, pid, 'cmdline'), 'wb') as f:
                f.write(cmd)
        self.assertTrue(launch.running_from(game_dir, proc))
        self.assertFalse(launch.running_from(game_dir, proc, skip={'11'}))
        self.assertFalse(launch.running_from(os.path.join(self.tmp, 'Other'), proc))
        self.assertFalse(launch.running_from('', proc))


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


class PlaytimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='spark-games-play-')
        if os.path.exists(launch.playtime_path()):
            os.remove(launch.playtime_path())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_record_and_totals(self):
        launch.record('own:a', 'A', 1000, 1000 + 3600)
        launch.record('own:a', 'A', 5000, 5000 + 600)
        launch.record('steam:1', 'B', 100, 160)
        totals = launch.totals()
        self.assertEqual(totals['own:a'], {'minutes': 70, 'last': 5600})
        self.assertEqual(totals['steam:1']['minutes'], 1)
        with open(launch.playtime_path(), encoding='utf-8') as f:
            data = json.load(f)
        self.assertEqual(len(data['sessions']), 3)
        self.assertEqual(data['sessions'][0], {'game': 'own:a', 'title': 'A', 'start': 1000,
                                               'end': 4600})

    def test_totals_ignore_bad_rows(self):
        self.assertEqual(launch.totals([{'game': 'x'}, {'start': 'a', 'end': 2}, {}]), {})

    def test_track_own_game_waits_for_exit(self):
        spec = {'key': 'own:t', 'title': 'T', 'argv': [sys.executable, '-c', 'pass'],
                'wait': True}
        clock = iter([0.0, 120.0])
        session = launch.track(spec, clock=lambda: next(clock))
        self.assertEqual(session['end'] - session['start'], 120)
        self.assertEqual(launch.totals()['own:t']['minutes'], 2)

    def test_track_short_run_not_counted(self):
        spec = {'key': 'own:s', 'argv': [sys.executable, '-c', 'pass'], 'wait': True}
        clock = iter([0.0, 5.0])
        self.assertIsNone(launch.track(spec, clock=lambda: next(clock)))
        self.assertNotIn('own:s', launch.totals())

    def test_track_launcher_game_through_proc(self):
        proc = os.path.join(self.tmp, 'proc')
        os.makedirs(proc)
        game_dir = os.path.join(self.tmp, 'Hades')
        clock = FakeClock()
        looks = {'n': 0}

        def sleep(seconds):
            clock.sleep(seconds)
            looks['n'] += 1
            path = os.path.join(proc, '500')
            if looks['n'] == 3:                 # the game appears on the third look
                os.makedirs(path)
                with open(os.path.join(path, 'cmdline'), 'wb') as f:
                    f.write(game_dir.encode() + b'/game\0')
            elif looks['n'] == 30:              # and exits 27 looks (270 s) later
                shutil.rmtree(path)

        spec = {'key': 'steam:9', 'title': 'H', 'argv': [sys.executable, '-c', 'pass'],
                'watch_dir': game_dir}
        session = launch.track(spec, proc=proc, poll=10, clock=clock, sleep=sleep)
        self.assertIsNotNone(session)
        self.assertEqual(session['end'] - session['start'], 260)    # first seen to last seen
        self.assertEqual(launch.totals()['steam:9']['minutes'], 4)

    def test_track_with_nothing_to_watch_returns_at_once(self):
        # Battle.net and the other added launchers: no folder, no scanning /proc for 10 minutes
        slept = []
        spec = {'key': 'battlenet:x', 'argv': [sys.executable, '-c', 'pass'],
                'watch_dir': '', 'wait': False}
        self.assertIsNone(launch.track(spec, proc=os.path.join(self.tmp, 'proc'),
                                       sleep=slept.append))
        self.assertEqual(slept, [])
        self.assertNotIn('battlenet:x', launch.totals())

    def test_track_gives_up_when_game_never_appears(self):
        os.makedirs(os.path.join(self.tmp, 'proc'))
        clock = FakeClock()
        spec = {'key': 'steam:8', 'argv': [sys.executable, '-c', 'pass'],
                'watch_dir': os.path.join(self.tmp, 'Nothing')}
        self.assertIsNone(launch.track(spec, proc=os.path.join(self.tmp, 'proc'), poll=10,
                                       appear=60, clock=clock, sleep=clock.sleep))


# ─── Anti-cheat, covers, metadata ─────────────────────────────

class AntiCheatTests(FixtureHome):
    def test_mark_from_list(self):
        games = library.scan_all(self.home).games
        with open(fixtures.anticheat_list(), encoding='utf-8') as f:
            entries = json.load(f)
        self.assertEqual(anticheat.mark(games, entries), 2)
        marked = {g.key: g.anticheat for g in games if g.anticheat}
        self.assertEqual(marked, {'steam:999990': 'Denied', 'lutris:4': 'Broken'})
        self.assertEqual(anticheat.mark(games, []), 0)
        self.assertFalse(any(g.anticheat for g in games))

    def test_offline_shows_nothing(self):
        if os.path.exists(anticheat.cache_path()):
            os.remove(anticheat.cache_path())
        self.assertIsNone(anticheat.load(online=False))

    def test_cached_copy_used(self):
        shutil.copy(fixtures.anticheat_list(), anticheat.cache_path())
        self.assertEqual(len(anticheat.load(online=False)), 3)
        os.remove(anticheat.cache_path())


class CoverTests(FixtureHome):
    def test_thumbnail_cached_at_tile_size(self):
        src = os.path.join(self.home, fixtures.LUTRIS, 'coverart', 'battlenet.jpg')
        thumb = covers.thumbnail(src, 148, 222)
        self.assertEqual(thumb.size, (148, 222))
        path = covers.thumb_path(src, 148, 222)
        self.assertTrue(os.path.isfile(path))
        self.assertEqual(covers.thumbnail(src, 148, 222).size, (148, 222))   # from the cache
        self.assertIsNone(covers.thumbnail(os.path.join(self.tmp, 'missing.jpg'), 10, 15))
        broken = os.path.join(self.tmp, 'broken.jpg')
        with open(broken, 'wb') as f:
            f.write(b'not a picture')
        self.assertIsNone(covers.thumbnail(broken, 10, 15))


class PackageTests(unittest.TestCase):
    def test_spark_app_json(self):
        with open(os.path.join(APP_DIR, 'spark-app.json'), encoding='utf-8') as f:
            meta = json.load(f)
        self.assertEqual(meta['id'], 'dev.wolklaw.SparkGames')
        self.assertEqual(meta['version'], VERSION)
        self.assertFalse(meta['needs']['root'])
        size = 0
        for folder in ('sparkgames', 'icons', os.path.join('tests', 'fixtures')):
            for base, _dirs, files in os.walk(os.path.join(APP_DIR, folder)):
                size += sum(os.path.getsize(os.path.join(base, n)) for n in files
                            if '__pycache__' not in base)
        size += os.path.getsize(os.path.join(APP_DIR, 'spark_games.py'))
        kib = size / 1024
        self.assertTrue(kib * 0.7 <= meta['size_kb'] <= kib * 1.6,
                        f"spark-app.json size_kb {meta['size_kb']}, files are {kib:.0f} KiB")

    def test_desktop_entry(self):
        with open(os.path.join(APP_DIR, 'dev.wolklaw.SparkGames.desktop'), encoding='utf-8') as f:
            text = f.read()
        self.assertIn('Exec=spark-games', text)
        self.assertIn('Icon=dev.wolklaw.SparkGames', text)
        self.assertIn('StartupWMClass=SparkGames', text)


# ─── The window ───────────────────────────────────────────────

def have_display() -> bool:
    if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'):
        return False
    try:
        import tkinter
        root = tkinter.Tk()
        root.destroy()
        return True
    except Exception:          # noqa: BLE001
        return False


@unittest.skipUnless(have_display(), "needs a display")
class UITests(unittest.TestCase):
    def setUp(self):
        from sparkgames import app as appmod
        self.appmod = appmod
        self.tmp = tempfile.mkdtemp(prefix='spark-games-ui-')
        os.environ['SPARK_GAMES_REDUCED_MOTION'] = '1'
        for path in (library.cache_path(), anticheat.cache_path()):
            if os.path.exists(path):
                os.remove(path)
        self.app = None

    def tearDown(self):
        if self.app is not None:
            try:
                self.app.root.destroy()
            except Exception:      # noqa: BLE001
                pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def start(self, home):
        self.app = self.appmod.App(home)
        self.app.settings['anticheat'] = False
        self.app.root.geometry('1100x760')
        self.pump(0.3)
        deadline = time.time() + 15
        while self.app.scanning and time.time() < deadline:
            self.pump(0.05)
        self.assertFalse(self.app.scanning)
        self.pump(0.3)
        return self.app

    def pump(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            self.app.root.update()
            time.sleep(0.01)

    def key(self, keysym, char=''):
        lib = self.app.library
        event = type('E', (), {'keysym': keysym, 'char': char, 'state': 0,
                               'widget': lib.canvas})()
        return self.app._key(event)

    def test_fixtures_listed_and_search(self):
        home = fixtures.materialize(os.path.join(self.tmp, 'home'))
        app = self.start(home)
        lib = app.library
        self.assertEqual(len(lib.shown), sum(fixtures.EXPECTED.values()))
        self.assertEqual(lib.shown[0].key, 'epic:Sugar')            # most recently played
        self.assertTrue(lib.canvas.find_all())
        lib.query.set('witcher')
        self.pump(0.1)
        self.assertEqual([g.key for g in lib.shown], ['gog:1207658930'])
        lib.query.set('')
        lib.set_source('lutris')
        self.assertEqual({g.source for g in lib.shown}, {'lutris'})
        lib.set_source('all')
        # keyboard: arrows move, "/" goes to search, Esc clears it
        self.key('Right')
        self.assertEqual(lib.selected, 1)
        self.assertEqual(self.key('slash'), 'break')     # focus moves to the search box
        lib.query.set('portal')
        self.pump(0.05)
        event = type('E', (), {'keysym': 'Escape', 'char': '', 'state': 0})()
        lib.key(event)
        self.assertEqual(lib.query.get(), '')
        # the game page, and back
        app.show_game(lib.shown[0])
        self.pump(0.2)
        self.assertEqual(type(app.view).__name__, 'GamePage')
        self.key('Escape')
        self.assertIs(app.view, lib)
        # covers were cut in the background and are drawn
        self.pump(0.5)
        self.assertTrue(lib.photos)

    def test_grid_with_500_games_scrolls(self):
        home = os.path.join(self.tmp, 'many')
        os.makedirs(home)
        app = self.start(home)
        games = [Game(f'own:{i}', f'Game {i:03d}', 'own', last_played=i) for i in range(500)]
        started = time.time()
        app.library.set_games(games, scanning=False)
        self.pump(0.2)
        lib = app.library
        drawn = len(lib.canvas.find_all())
        self.assertGreater(drawn, 0)
        self.assertLess(drawn, 1000)               # only the rows on screen are drawn
        self.assertLess(time.time() - started, 3.0)
        lib.canvas.yview_moveto(0.5)
        self.pump(0.2)
        self.key('End')
        self.pump(0.2)
        self.assertEqual(lib.selected, 499)
        self.assertGreater(lib.canvas.canvasy(0), 0)
        lib.set_mode('list')
        self.pump(0.2)
        self.key('Home')
        self.assertEqual(lib.selected, 0)
        self.assertEqual(lib.canvas.canvasy(0), 0)

    def test_empty_state(self):
        home = os.path.join(self.tmp, 'empty')
        os.makedirs(home)
        app = self.start(home)
        self.assertIsNotNone(app.library.empty)
        texts = []

        def walk(widget):
            for child in widget.winfo_children():
                try:
                    texts.append(child.cget('text'))
                except Exception:      # noqa: BLE001
                    pass
                walk(child)
        walk(app.library.empty)
        self.assertIn(strings.tr('empty_body'), texts)

    def test_settings_and_add_screens(self):
        home = fixtures.materialize(os.path.join(self.tmp, 'home'))
        app = self.start(home)
        app.show_settings()
        self.pump(0.2)
        self.assertEqual(type(app.view).__name__, 'SettingsView')
        self.assertEqual(len(app.launchers_found()), 7)
        app.show_add()
        self.pump(0.2)
        self.assertEqual(type(app.view).__name__, 'AddGameView')
        self.assertFalse(app.view.save.enabled)
        app.go_back()


if __name__ == '__main__':
    unittest.main()
