"""Spark Store tests. Plain unittest:

    python -m unittest discover -s files/spark-store/tests -v

The catalog tests read fixtures/appstream.xml, a small catalog in Flathub's format with
invented apps. flatpak is replaced by tests/fake_flatpak.py, which answers from a JSON state
file and records every call, so installs, removals and updates run for real through the queue
without touching this PC. They run anywhere, Windows included; the Spark app install test
needs bash. UI tests need a display (on CI: xvfb-run).
"""

import glob
import gzip
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import zlib
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
REPO_FILES = os.path.dirname(APP_DIR)
FIXTURES = os.path.join(HERE, 'fixtures')
CATALOG_XML = os.path.join(FIXTURES, 'appstream.xml')
FAKE = os.path.join(HERE, 'fake_flatpak.py')
sys.path.insert(0, APP_DIR)

TMP = tempfile.mkdtemp(prefix='spark-store-tests-')
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
    os.environ[var] = os.path.join(TMP, var.lower())
    os.makedirs(os.environ[var], exist_ok=True)
os.environ['XDG_DATA_DIRS'] = os.path.join(TMP, 'system-share')
os.environ['SPARK_STORE_REDUCED_MOTION'] = '1'
os.environ['SPARK_STORE_SPARK_DIRS'] = os.path.join(FIXTURES, 'spark')
os.environ['SPARK_STORE_SOURCES'] = os.path.join(FIXTURES, 'sources')
os.environ['SPARK_STORE_OFFLINE'] = '1'
os.environ['LANG'] = 'en_CA.UTF-8'
for var in ('LC_ALL', 'LC_MESSAGES', 'SPARK_STORE_APPSTREAM', 'XDG_RUNTIME_DIR'):
    os.environ.pop(var, None)

from sparkstore import APP_ID, VERSION, flatpak, permissions, sparkapps  # noqa: E402
from sparkstore import text as text_mod  # noqa: E402
from sparkstore.lang import local_units  # noqa: E402
from sparkstore.appstream import (Source, find_sources, flatpak_arch, fold,  # noqa: E402
                                  licence_label, parse)
from sparkstore.catalog import Catalog  # noqa: E402
from sparkstore.core import parse_size  # noqa: E402
from sparkstore.jobs import CANCELLED, DONE, FAILED, Job, JobQueue, error_text  # noqa: E402

LINUX = sys.platform.startswith('linux')


def png_bytes(size: int = 8, rgb=(61, 232, 200)) -> bytes:
    """A small valid PNG, for the fixture icons."""
    raw = b''.join(b'\x00' + bytes(rgb) * size for _ in range(size))

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + \
            struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 2, 0,
                                                                 0, 0)) +
            chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def make_installation(base: str, gz: bool = True) -> str:
    """A Flatpak installation folder with the fixture catalog and one icon, like flatpak
    leaves it after `flatpak update --appstream`. Returns the catalog file's path."""
    active = os.path.join(base, 'appstream', 'flathub', flatpak_arch(), 'active')
    os.makedirs(os.path.join(active, 'icons', '64x64'), exist_ok=True)
    os.makedirs(os.path.join(active, 'icons', '128x128'), exist_ok=True)
    with open(os.path.join(active, 'icons', '64x64', 'org.example.Paint.png'), 'wb') as f:
        f.write(png_bytes(64))
    with open(os.path.join(active, 'icons', '128x128', 'org.example.Paint.png'), 'wb') as f:
        f.write(png_bytes(128))
    with open(CATALOG_XML, 'rb') as f:
        data = f.read()
    if gz:
        path = os.path.join(active, 'appstream.xml.gz')
        with gzip.open(path, 'wb') as f:
            f.write(data)
    else:
        path = os.path.join(active, 'appstream.xml')
        with open(path, 'wb') as f:
            f.write(data)
    return path


class FakeFlatpak:
    """Points SPARK_STORE_FLATPAK at tests/fake_flatpak.py with a fresh state."""

    def __init__(self, **state):
        self.dir = tempfile.mkdtemp(prefix='fake-flatpak-', dir=TMP)
        self.path = os.path.join(self.dir, 'state.json')
        self.write(state)
        os.environ['FAKE_FLATPAK_STATE'] = self.path
        os.environ['SPARK_STORE_FLATPAK'] = json.dumps([sys.executable, FAKE])

    def write(self, state):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(state, f)

    def read(self) -> dict:
        with open(self.path, encoding='utf-8') as f:
            return json.load(f)

    def update(self, **changes):
        state = self.read()
        state.update(changes)
        self.write(state)

    def calls(self):
        try:
            with open(self.path + '.log', encoding='utf-8') as f:
                return [json.loads(line) for line in f if line.strip()]
        except OSError:
            return []


# ─── The catalog ──────────────────────────────────────────────

class AppstreamTests(unittest.TestCase):
    def apps(self, langs=None, path=CATALOG_XML):
        return {app.id: (app, det) for app, det in parse(path, langs or [])}

    def test_lists_desktop_apps_only(self):
        ids = set(self.apps())
        self.assertEqual(ids, {'org.example.Paint', 'com.example.Chat', 'net.example.Blocks',
                               'org.example.Tunes', 'org.example.Old'})

    def test_fields(self):
        apps = self.apps()
        paint, det = apps['org.example.Paint']
        self.assertEqual(paint.name, 'Paint Pro')
        self.assertEqual(paint.developer, 'Example Studio')
        self.assertTrue(paint.verified)
        self.assertFalse(paint.proprietary)
        self.assertEqual(paint.icon, 'org.example.Paint.png')
        self.assertEqual(paint.keywords, ['draw', 'drawing', 'sketch'])
        self.assertEqual(paint.categories, ['Graphics', '2DGraphics'])
        self.assertEqual(det.version, '3.2.0')                 # the newest release
        self.assertEqual(det.urls['homepage'], 'https://paint.example.org')
        self.assertEqual(det.description, [
            ('p', 'Paint Pro is a simple drawing app.'), ('li', 'Layers and brushes'),
            ('li', 'Opens PNG, JPEG and WebP'), ('p', 'It works offline.')])
        self.assertEqual(det.runtime, 'org.freedesktop.Platform/x86_64/24.08')

    def test_verified_proprietary_and_developer_name(self):
        apps = self.apps()
        chat = apps['com.example.Chat'][0]
        self.assertTrue(chat.proprietary)
        self.assertTrue(chat.verified)
        self.assertEqual(licence_label(chat.license), 'Proprietary')
        blocks = apps['net.example.Blocks'][0]
        self.assertFalse(blocks.verified)
        self.assertEqual(blocks.developer, 'A. Hobbyist')
        self.assertEqual(blocks.branch, 'beta')
        self.assertTrue(apps['org.example.Tunes'][0].verified)    # in <metadata>
        self.assertEqual(licence_label('GPL-3.0-or-later'), 'GPL-3.0-or-later')
        self.assertEqual(licence_label('LicenseRef-Custom=https://x'), 'Custom')

    def test_screenshots(self):
        det = self.apps()['org.example.Paint'][1]
        self.assertEqual(len(det.screenshots), 2)
        first = det.screenshots[0]
        self.assertEqual(first.caption, 'The main window')
        self.assertTrue(first.url.endswith('image-1_752x423@1.png'))
        self.assertTrue(first.full.endswith('image-1_orig.png'))
        self.assertTrue(det.screenshots[1].url.endswith('image-2_624x351@1.png'))   # no http
        self.assertEqual(self.apps()['com.example.Chat'][1].screenshots, [])

    def test_translations(self):
        apps = self.apps(['fr_CA', 'fr'])
        paint, det = apps['org.example.Paint']
        self.assertEqual(paint.name, 'Peinture Pro')
        self.assertEqual(paint.summary, 'Dessiner et retoucher des images')
        self.assertIn('dessin', paint.keywords)
        self.assertEqual(det.description, [('p', 'Peinture Pro est une application de dessin.')])
        self.assertEqual(det.screenshots[0].caption, 'La fenêtre principale')
        self.assertEqual(apps['com.example.Chat'][0].name, 'Chatter')   # no French: English

    def test_addons(self):
        addons = []
        list(parse(CATALOG_XML, [], addons))
        self.assertEqual([(a.id, a.extends, a.branch) for a in addons],
                         [('org.example.Paint.Plugin.Extra', ['org.example.Paint'], 'stable')])
        self.assertEqual(addons[0].name, 'Extra brushes')

    def test_old_style_id(self):
        self.assertEqual(self.apps()['org.example.Old'][0].name, 'Old Editor')

    def test_fold(self):
        self.assertEqual(fold('Éditeur'), 'editeur')


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='catalog-', dir=TMP)
        self.xml = make_installation(os.path.join(self.dir, 'user'))
        self.db = os.path.join(self.dir, 'catalog.sqlite')

    def catalog(self, langs=None):
        src = Source(self.xml, 'user')
        src.stat()
        return Catalog([src], path=self.db, langs=langs or []).load()

    def test_indexes_once_then_reads_the_cache(self):
        first = self.catalog()
        self.assertTrue(first.rebuilt)
        self.assertEqual(len(first.apps), 5)
        second = self.catalog()
        self.assertFalse(second.rebuilt)
        self.assertEqual(set(second.apps), set(first.apps))
        self.assertEqual(second.details('org.example.Paint').version, '3.2.0')
        self.assertEqual([a.id for a in second.addons['org.example.Paint']],
                         ['org.example.Paint.Plugin.Extra'])
        self.assertEqual(second.details('nope.nope.Nope').description, [])

    def test_rebuilds_when_the_catalog_changes(self):
        self.catalog()
        later = time.time() + 120
        os.utime(self.xml, (later, later))
        self.assertTrue(self.catalog().rebuilt)
        self.assertTrue(self.catalog(['fr']).rebuilt)            # another language
        self.assertEqual(self.catalog(['fr']).apps['org.example.Paint'].name, 'Peinture Pro')

    def test_icons(self):
        cat = self.catalog()
        paint = cat.apps['org.example.Paint']
        self.assertTrue(cat.icon_path(paint, 48).endswith(os.path.join('64x64',
                                                                       'org.example.Paint.png')))
        self.assertTrue(cat.icon_path(paint, 96).endswith(os.path.join('128x128',
                                                                       'org.example.Paint.png')))
        self.assertIsNone(cat.icon_path(cat.apps['com.example.Chat']))   # listed, no file

    def test_search_ranking(self):
        cat = self.catalog()

        def ids(query):
            return [a.id for a in cat.search(query)[0]]
        self.assertEqual(ids('paint')[0], 'org.example.Paint')       # name
        self.assertEqual(ids('draw')[0], 'org.example.Paint')        # keyword
        self.assertEqual(ids('music player'), ['org.example.Tunes'])  # summary, every word
        self.assertEqual(ids('puzzle'), ['net.example.Blocks'])
        self.assertEqual(ids('chatter inc'), ['com.example.Chat'])    # developer
        self.assertEqual(ids('PAINT  pro'), ['org.example.Paint'])
        self.assertEqual(ids('zzzz'), [])
        self.assertEqual(ids('   '), [])
        self.assertEqual(ids('org.example.tunes')[0], 'org.example.Tunes')
        results, total = cat.search('e', limit=2)
        self.assertEqual(len(results), 2)
        self.assertGreater(total, 2)

    def test_search_folds_accents_and_ranks_spark_apps_first(self):
        cat = self.catalog(['fr'])
        self.assertEqual([a.id for a in cat.search('peinture')[0]], ['org.example.Paint'])
        self.assertEqual([a.id for a in cat.search('PÉINTURE')[0]], ['org.example.Paint'])
        spark = [s.as_app() for s in sparkapps.discover()]
        found = [a.id for a in cat.search('spark', extra=spark)[0]]
        self.assertEqual(set(found[:2]), {'dev.wolklaw.SparkAlpha', 'dev.wolklaw.SparkBeta'})

    def test_rows(self):
        cat = self.catalog()
        self.assertEqual([a.id for a in cat.row('games')], ['net.example.Blocks'])
        self.assertEqual([a.id for a in cat.row('chat')], ['com.example.Chat'])
        self.assertEqual([a.id for a in cat.row('creative')], ['org.example.Paint'])
        self.assertEqual(cat.row('creative', exclude=['org.example.Paint']), [])
        self.assertEqual(cat.row('nope'), [])

    def test_categories(self):
        cat = self.catalog()
        self.assertEqual([a.id for a in cat.category('graphics')], ['org.example.Paint'])
        self.assertEqual([a.id for a in cat.category('audio_video')], ['org.example.Tunes'])
        self.assertEqual([a.id for a in cat.category('internet')], ['com.example.Chat'])
        self.assertEqual(cat.category('nope'), [])

    def test_broken_catalog_is_reported_not_fatal(self):
        with open(self.xml, 'wb') as f:
            f.write(b'not gzip at all')
        cat = self.catalog()
        self.assertTrue(cat.error)
        self.assertEqual(cat.apps, {})

    def test_find_sources_newest_first(self):
        user = os.path.join(self.dir, 'u')
        system = os.path.join(self.dir, 's')
        upath = make_installation(user)
        spath = make_installation(system, gz=False)
        os.utime(upath, (1000, 1000))
        old = dict(os.environ)
        try:
            os.environ['FLATPAK_USER_DIR'] = user
            os.environ['FLATPAK_SYSTEM_DIR'] = system
            found = find_sources()
            self.assertEqual([(s.scope, s.path) for s in found],
                             [('system', spath), ('user', upath)])
            os.environ['SPARK_STORE_APPSTREAM'] = CATALOG_XML
            self.assertEqual([s.scope for s in find_sources()], ['file'])
            os.environ['SPARK_STORE_APPSTREAM'] = os.path.join(self.dir, 'missing.xml')
            self.assertEqual(find_sources(), [])
        finally:
            os.environ.clear()
            os.environ.update(old)


def T(key: str, **kw) -> str:
    """A sentence from text.py the way the window shows it in capitals."""
    return text_mod.t(key, **kw).upper()


def said(key: str, shown, **known) -> bool:
    """Is the sentence `key` on show? Blanks not given in `known` can be anything."""
    import string
    blanks = {f for _, f, _, _ in string.Formatter().parse(text_mod.EN[key]) if f}
    sample = text_mod.t(key, **{f: known.get(f, '\x01') for f in blanks})
    hay = ('\n'.join(shown) if isinstance(shown, (list, tuple)) else shown).upper()
    return all(part.strip().upper() in hay for part in sample.split('\x01') if part.strip())


# ─── Permissions in plain words ───────────────────────────────

class PermissionTests(unittest.TestCase):
    def setUp(self):
        text_mod.use('en')                  # these check the English wording
        self.addCleanup(text_mod.use, text_mod.LANG)

    def lines(self, context: str, extra: str = ''):
        return permissions.describe(f"[Application]\nname=x\n\n[Context]\n{context}\n{extra}")

    def test_sandboxed_app_has_nothing_to_say(self):
        self.assertEqual(permissions.describe("[Application]\nname=x\n"), [])
        self.assertEqual(self.lines("sockets=wayland;fallback-x11;"), [])

    def test_files(self):
        lines = self.lines("filesystems=xdg-download;xdg-music:ro;home;~/Games:create;"
                           "xdg-config/kdeglobals:ro;xdg-run/pipewire-0;!host;")
        texts = [s for _g, _l, s in lines]
        self.assertIn("Your Downloads folder", texts)
        self.assertIn("Your Music folder (read only)", texts)
        self.assertIn("Every file in your home folder", texts)
        self.assertIn("The folder ~/Games", texts)
        self.assertIn("The folder ~/.config/kdeglobals (read only)", texts)
        self.assertEqual(len(lines), 5)                       # xdg-run and !host say nothing
        self.assertTrue(permissions.broad(lines))             # home
        self.assertEqual([lvl for _g, lvl, s in lines if s.startswith('Every file')], ['warn'])

    def test_whole_system(self):
        lines = self.lines("filesystems=host;\nshared=network;ipc;\ndevices=all;\n"
                           "sockets=x11;pulseaudio;session-bus;ssh-auth;\nfeatures=devel;bluetooth;")
        by_group = {}
        for group, level, text in lines:
            by_group.setdefault(group, []).append((level, text))
        self.assertEqual(by_group['files'], [('warn', "All your files, and the system's")])
        self.assertIn(('warn', "All devices: game controllers, webcams, USB and more"),
                      by_group['devices'])
        self.assertIn(('info', "Sound: plays it, and can record from the microphone"),
                      by_group['devices'])
        self.assertIn(('info', "Bluetooth"), by_group['devices'])
        self.assertTrue(any('X11' in t for _l, t in by_group['devices']))
        self.assertEqual(by_group['network'], [('info', "The internet and your local network")])
        others = [t for _l, t in by_group['other']]
        self.assertTrue(any('desktop service' in t for t in others))
        self.assertTrue(any('SSH' in t for t in others))
        self.assertTrue(any('Debugging' in t for t in others))

    def test_bus_names(self):
        lines = self.lines("sockets=wayland;", "[Session Bus Policy]\n"
                           "org.freedesktop.Notifications=talk\norg.freedesktop.secrets=talk\n"
                           "org.kde.StatusNotifierWatcher=talk\norg.freedesktop.Flatpak=talk\n"
                           "org.mpris.MediaPlayer2.myapp=own\norg.example.Odd=talk\n"
                           "org.freedesktop.portal.Desktop=talk\n")
        texts = {s: lvl for _g, lvl, s in lines}
        self.assertEqual(texts["Notifications"], 'info')
        self.assertEqual(texts["Your saved passwords (the system's keyring)"], 'warn')
        self.assertEqual(texts["Running commands outside its sandbox"], 'warn')
        self.assertIn("An icon in the system tray", texts)
        self.assertIn("Media controls (play, pause)", texts)
        self.assertIn("Talks to 1 other desktop service(s)", texts)

    def test_french(self):
        text_mod.use('fr')
        try:
            lines = self.lines("shared=network;")
            self.assertEqual(lines, [('network', 'info', "Internet et votre réseau local")])
        finally:
            text_mod.use('en')

    def test_broken_metadata(self):
        self.assertEqual(permissions.describe("[Context\nnot a key file"), [])


# ─── The Spark apps ───────────────────────────────────────────

class SparkAppTests(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(os.environ['XDG_DATA_HOME'], ignore_errors=True)
        os.makedirs(os.environ['XDG_DATA_HOME'])
        shutil.rmtree(os.environ['XDG_DATA_DIRS'], ignore_errors=True)

    def test_reads_both_styles_of_spark_app_json(self):
        apps = {a.id: a for a in sparkapps.discover()}
        self.assertEqual(set(apps), {'dev.wolklaw.SparkAlpha', 'dev.wolklaw.SparkBeta'})
        alpha, beta = apps['dev.wolklaw.SparkAlpha'], apps['dev.wolklaw.SparkBeta']
        self.assertEqual((alpha.slug, alpha.version, alpha.size_kb), ('spark-alpha', '1.2.0', 420))
        self.assertTrue(alpha.in_image)
        self.assertEqual(beta.summary, "A test app described the way Spark Welcome describes "
                                       "itself.")
        self.assertEqual((beta.slug, beta.size_kb, beta.command), ('spark-beta', 200, 'spark-beta'))
        self.assertIsNone(alpha.installed)
        self.assertEqual(alpha.as_app().kind, 'spark')

    def test_installed_state_from_desktop_entries(self):
        system = os.path.join(os.environ['XDG_DATA_DIRS'], 'applications')
        os.makedirs(system)
        with open(os.path.join(system, 'dev.wolklaw.SparkAlpha.desktop'), 'w') as f:
            f.write("[Desktop Entry]\nName=Spark Alpha\n")
        user = os.path.join(os.environ['XDG_DATA_HOME'], 'applications')
        os.makedirs(user)
        with open(os.path.join(user, 'dev.wolklaw.SparkBeta.desktop'), 'w') as f:
            f.write("[Desktop Entry]\nName=Spark Beta\n")
        apps = {a.id: a for a in sparkapps.discover()}
        self.assertEqual(apps['dev.wolklaw.SparkAlpha'].installed, 'system')
        self.assertEqual(apps['dev.wolklaw.SparkBeta'].installed, 'user')
        self.assertIsNone(sparkapps.uninstall_command(apps['dev.wolklaw.SparkAlpha']))

    def test_finds_a_source_to_install_from(self):
        old = os.environ['SPARK_STORE_SPARK_DIRS']
        os.environ['SPARK_STORE_SPARK_DIRS'] = os.path.join(FIXTURES, 'sources')
        try:
            apps = {a.id: a for a in sparkapps.discover()}
        finally:
            os.environ['SPARK_STORE_SPARK_DIRS'] = old
        hello = apps['dev.wolklaw.SparkHello']
        self.assertTrue(hello.source.endswith('spark-hello'))
        self.assertEqual(sparkapps.install_command(hello)[-1], '--user')

    def test_every_spark_app_json_in_the_repo_reads(self):
        paths = glob.glob(os.path.join(REPO_FILES, 'spark-*', 'spark-app.json'))
        self.assertTrue(paths, "no spark-app.json found next to spark-store")
        for path in paths:
            app = sparkapps.read_file(path)
            self.assertIsNotNone(app, path)
            self.assertTrue(app.id.startswith('dev.wolklaw.'), path)
            self.assertTrue(app.name and app.summary, path)
        self.assertIn(os.path.join(REPO_FILES, 'spark-store', 'spark-app.json'), paths)

    def test_own_apps_fallback(self):
        old = os.environ.pop('SPARK_STORE_SPARK_DIRS')
        try:
            ids = {a.id for a in sparkapps.discover()}
        finally:
            os.environ['SPARK_STORE_SPARK_DIRS'] = old
        self.assertIn('dev.wolklaw.Soot', ids)
        self.assertIn('dev.wolklaw.SparkMonitor', ids)                  # from the repo
        self.assertNotIn(APP_ID, ids)                                   # not itself

    def test_remove_with_manifest_stays_in_home(self):
        home = tempfile.mkdtemp(prefix='home-', dir=TMP)
        outside = tempfile.mkdtemp(prefix='outside-', dir=TMP)
        old_home = os.environ.get('HOME')
        os.environ['HOME'] = home
        os.environ['USERPROFILE'] = home
        try:
            lib = os.path.join(home, '.local', 'lib', 'spark-alpha')
            os.makedirs(lib)
            mine = os.path.join(home, '.local', 'bin', 'spark-alpha')
            os.makedirs(os.path.dirname(mine))
            open(mine, 'w').close()
            theirs = os.path.join(outside, 'keep-me')
            open(theirs, 'w').close()
            with open(os.path.join(lib, 'installed-files'), 'w') as f:
                f.write(f"{mine}\n{theirs}\n")
            app = sparkapps.parse({'id': 'dev.wolklaw.SparkAlpha', 'slug': 'spark-alpha',
                                   'name': 'Spark Alpha'})
            self.assertEqual(sparkapps.remove_with_manifest(app), '')
            self.assertFalse(os.path.exists(mine))
            self.assertFalse(os.path.exists(lib))
            self.assertTrue(os.path.exists(theirs))
        finally:
            if old_home is None:
                os.environ.pop('HOME', None)
            else:
                os.environ['HOME'] = old_home


# ─── flatpak, through the fake ────────────────────────────────

class FlatpakTests(unittest.TestCase):
    def test_installed_updates_remotes(self):
        FakeFlatpak(installed=[
            {'id': 'org.example.Paint', 'name': 'Paint Pro', 'version': '3.1.0',
             'installation': 'system', 'size': '41.5 MB'},
            {'id': 'org.example.Paint', 'name': 'Paint Pro', 'version': '3.2.0',
             'installation': 'user', 'size': '41.6 MB'},
            {'id': 'com.example.Chat', 'name': 'Chatter', 'installation': 'system',
             'size': '1,2 GB'}],
            updates=[{'id': 'org.example.Paint', 'version': '3.3.0', 'scope': 'user'},
                     {'id': 'org.freedesktop.Platform', 'scope': 'user',
                      'ref': 'runtime/org.freedesktop.Platform/x86_64/24.08'}],
            remotes={'user': ['flathub'], 'system': ['flathub', 'fedora']})
        apps = flatpak.installed()
        self.assertEqual(apps['org.example.Paint'].scope, 'user')       # yours wins
        self.assertEqual(apps['org.example.Paint'].version, '3.2.0')
        self.assertEqual(apps['com.example.Chat'].size, int(1.2 * 1000 ** 3))
        ups, runtimes, error = flatpak.updates()
        self.assertEqual([(u.id, u.scope, u.version) for u in ups],
                         [('org.example.Paint', 'user', '3.3.0')])
        self.assertEqual((runtimes, error), (1, ''))
        self.assertEqual(flatpak.remotes(), {'user': ['flathub'], 'system': ['flathub', 'fedora']})
        fake = FakeFlatpak(runtimes=[{'id': 'org.example.Ext', 'installation': 'system'},
                                     {'id': 'org.example.Ext', 'installation': 'user'},
                                     {'id': 'org.freedesktop.Platform', 'installation': 'system'}])
        self.assertEqual(flatpak.installed_runtimes(), {'org.example.Ext': 'user',
                                                        'org.freedesktop.Platform': 'system'})
        self.assertEqual(flatpak.cmd_install_addon('org.example.Ext')[-1],
                         'runtime/org.example.Ext//stable')
        self.assertEqual(fake.calls()[-1], ['list', '--runtime',
                                            '--columns=application,installation'])
        self.assertTrue(flatpak.version().startswith('Flatpak'))

    def test_remote_info(self):
        fake = FakeFlatpak(remotes={'user': [], 'system': ['flathub']})
        info = flatpak.remote_info('org.example.Paint')
        self.assertEqual((info.download, info.installed), (41500000, 108300000))
        self.assertEqual(info.version, '2.0')
        self.assertIn('[Context]', info.metadata)
        self.assertEqual(info.error, '')
        self.assertIn(['--user', 'remote-info', 'flathub', 'app/org.example.Paint//stable'],
                      fake.calls())                   # tried yours first, then the system's
        fake.update(missing=['org.example.Gone'])
        self.assertIn('No remote refs', flatpak.remote_info('org.example.Gone').error)

    def test_flatpakref_and_links(self):
        path = os.path.join(TMP, 'paint.flatpakref')
        with open(path, 'w', encoding='utf-8') as f:
            f.write("[Flatpak Ref]\nTitle=Paint Pro\nName=org.example.Paint\nBranch=stable\n"
                    "Url=https://dl.flathub.org/repo/\nIsRuntime=false\n"
                    "GPGKey=mQINBFlD2sABEADsiUZUO...\n")
        ref = flatpak.read_flatpakref(path)
        self.assertEqual((ref.id, ref.title, ref.branch), ('org.example.Paint', 'Paint Pro',
                                                          'stable'))
        self.assertTrue(ref.from_flathub)
        other = os.path.join(TMP, 'other.flatpakref')
        with open(other, 'w', encoding='utf-8') as f:
            f.write("[Flatpak Ref]\nName=com.vendor.App\nUrl=https://repo.vendor.example/\n")
        self.assertFalse(flatpak.read_flatpakref(other).from_flathub)
        self.assertEqual(flatpak.read_flatpakref(other).host, 'repo.vendor.example')
        bad = os.path.join(TMP, 'bad.flatpakref')
        with open(bad, 'w', encoding='utf-8') as f:
            f.write("[Flatpak Ref]\nName=../../etc/passwd\n")
        self.assertIsNone(flatpak.read_flatpakref(bad))
        self.assertIsNone(flatpak.read_flatpakref(os.path.join(TMP, 'missing.flatpakref')))
        self.assertTrue(flatpak.is_flatpakref('file:///tmp/a%20b.flatpakref'))
        self.assertEqual(flatpak.local_path('file:///tmp/a%20b.flatpakref'), '/tmp/a b.flatpakref')
        for link in ('appstream://org.gimp.GIMP', 'appstream:org.gimp.GIMP.desktop',
                     'appstream:///org.gimp.GIMP', 'https://flathub.org/apps/org.gimp.GIMP',
                     'https://flathub.org/fr/apps/org.gimp.GIMP', 'org.gimp.GIMP'):
            self.assertEqual(flatpak.app_id_from_link(link), 'org.gimp.GIMP', link)
        for link in ('appstream://', 'https://example.com/org.gimp.GIMP', 'gimp', 'a;b.c.d'):
            self.assertIsNone(flatpak.app_id_from_link(link), link)

    def test_flatpakrepo(self):
        path = os.path.join(TMP, 'Some Games.flatpakrepo')
        with open(path, 'w', encoding='utf-8') as f:
            f.write("[Flatpak Repo]\nTitle=Some Games\nUrl=https://repo.games.example/\n"
                    "Homepage=https://games.example\nComment=Games, packaged by us\n"
                    "GPGKey=mQINBFlD2sABEADsiUZUO...\n")
        repo = flatpak.read_flatpakrepo(path)
        self.assertEqual((repo.name, repo.title, repo.host), ('some-games', 'Some Games',
                                                             'repo.games.example'))
        self.assertFalse(repo.is_flathub)
        self.assertTrue(flatpak.is_flatpakrepo('file:///x/Some%20Games.flatpakrepo'))
        self.assertEqual(flatpak.cmd_add_remote('some-games', path),
                         ['--user', 'remote-add', '--if-not-exists', '--from', 'some-games', path])
        bad = os.path.join(TMP, 'bad.flatpakrepo')
        with open(bad, 'w', encoding='utf-8') as f:
            f.write("[Flatpak Repo]\nUrl=javascript:alert(1)\n")
        self.assertIsNone(flatpak.read_flatpakrepo(bad))

    def test_parse_size(self):
        self.assertEqual(parse_size('41.5 MB'), 41500000)
        self.assertEqual(parse_size('812 kB'), 812000)
        self.assertEqual(parse_size('2,0 GB'), 2000000000)
        self.assertEqual(parse_size('3 MiB'), 3 * 1024 * 1024)
        self.assertIsNone(parse_size('unknown'))


# ─── The queue ────────────────────────────────────────────────

class QueueTests(unittest.TestCase):
    def install_job(self, app_id='org.example.Paint'):
        return Job('install', app_id, app_id, steps=[flatpak.cmd_install(app_id)],
                   needs_flathub=True)

    def test_installs_in_order_with_progress(self):
        fake = FakeFlatpak(delay=0.2)
        q = JobQueue()
        first = q.add(self.install_job('org.example.Paint'))
        second = q.add(self.install_job('com.example.Chat'))
        self.assertIs(q.add(self.install_job('org.example.Paint')), first)   # no duplicate
        seen = set()
        end = time.monotonic() + 30
        while q.busy() and time.monotonic() < end:
            for job in q.drain():
                if job is first and job.progress is not None:
                    seen.add(round(job.progress, 2))
            time.sleep(0.01)
        self.assertEqual((first.state, second.state), (DONE, DONE))
        self.assertLessEqual(first.ended, second.started + 0.05)            # one at a time
        self.assertTrue({0.25, 0.5, 0.75} & seen, seen)
        self.assertEqual(first.step_text, '1/1')
        installed = [a['id'] for a in fake.read()['installed']]
        self.assertEqual(installed, ['org.example.Paint', 'com.example.Chat'])
        self.assertIn(['--user', 'install', '-y', 'flathub',
                       'app/org.example.Paint//stable'], fake.calls())

    def test_failure_keeps_flatpaks_error_and_retries(self):
        fake = FakeFlatpak(fail=['org.example.Paint'])
        q = JobQueue()
        job = q.add(self.install_job())
        self.assertTrue(q.wait())
        self.assertEqual(job.state, FAILED)
        self.assertIn('Not enough disk space', job.error)
        self.assertTrue(job.error.startswith('error:'))
        fake.update(fail=[])
        again = q.retry(job)
        self.assertIsNot(again, job)
        self.assertTrue(q.wait())
        self.assertEqual(again.state, DONE)
        self.assertNotIn(job, q.jobs)

    def test_adds_your_flathub_remote_first_when_missing(self):
        fake = FakeFlatpak(remotes={'user': [], 'system': ['flathub']})
        q = JobQueue()
        job = q.add(self.install_job())
        self.assertTrue(q.wait())
        self.assertEqual(job.state, DONE)
        calls = fake.calls()
        add = ['--user', 'remote-add', '--if-not-exists', 'flathub', flatpak.FLATHUB_REPO]
        self.assertIn(add, calls)
        self.assertLess(calls.index(add), calls.index(
            ['--user', 'install', '-y', 'flathub',
             'app/org.example.Paint//stable']))

    def test_cancel_waiting_and_running(self):
        FakeFlatpak(delay=20)
        q = JobQueue()
        running = q.add(self.install_job('org.example.Paint'))
        waiting = q.add(self.install_job('com.example.Chat'))
        end = time.monotonic() + 10
        while running.proc is None and time.monotonic() < end:
            time.sleep(0.01)
        q.cancel(waiting)
        self.assertEqual(waiting.state, CANCELLED)
        q.cancel(running)
        self.assertTrue(q.wait(10))
        self.assertEqual(running.state, CANCELLED)
        self.assertEqual(q.active(), [])
        q.clear_finished()
        self.assertEqual(q.jobs, [])

    def test_remove_and_update(self):
        fake = FakeFlatpak(installed=[{'id': 'org.example.Paint', 'installation': 'user'}],
                           updates=[{'id': 'org.example.Tunes', 'scope': 'user'}])
        q = JobQueue()
        rm = q.add(Job('remove', 'org.example.Paint', 'Paint',
                       steps=[flatpak.cmd_remove('org.example.Paint', 'user', True)]))
        up = q.add(Job('update_all', 'all-user', 'your apps',
                       steps=[flatpak.cmd_update(None, 'user')]))
        gone = q.add(Job('remove', 'org.example.Nope', 'Nope',
                         steps=[flatpak.cmd_remove('org.example.Nope', 'user')]))
        self.assertTrue(q.wait())
        self.assertEqual((rm.state, up.state, gone.state), (DONE, DONE, FAILED))
        state = fake.read()
        self.assertEqual(state['installed'], [])
        self.assertEqual(state['deleted_data'], ['org.example.Paint'])
        self.assertEqual(state['updates'], [])
        self.assertIn('not installed', gone.error)

    def test_function_jobs(self):
        q = JobQueue()
        ok = q.add(Job('spark_remove', 'a', 'A', flatpak=False, func=lambda: ''))
        bad = q.add(Job('spark_remove', 'b', 'B', flatpak=False, func=lambda: 'no manifest'))
        self.assertTrue(q.wait())
        self.assertEqual((ok.state, bad.state, bad.error), (DONE, FAILED, 'no manifest'))

    def test_progress_over_several_steps(self):
        q = JobQueue()
        job = Job('install', 'a.b.C', 'C')
        for line in ('Looking for matches…', 'Installing 1/2… ███  50%  2.0 MB/s',
                     'Installing 1/2… 100%', 'Installing 2/2… 0%', 'Installing 2/2… 50%'):
            q._line(job, line)
        self.assertEqual(job.step_text, '2/2')
        self.assertAlmostEqual(job.progress, 0.75)
        lone = Job('remove', 'a.b.C', 'C')
        for line in ('Uninstalling… 30%', 'Uninstalling… 10%'):
            q._line(lone, line)
        self.assertAlmostEqual(lone.progress, 0.10)

    def test_error_text(self):
        self.assertEqual(error_text(['Installing… 50%  1 MB/serror: disk full']),
                         'error: disk full')
        self.assertEqual(error_text(['one', 'two', '']), 'one\ntwo')

    @unittest.skipUnless(LINUX and shutil.which('bash'), "needs bash")
    def test_spark_app_install_and_remove_for_one_user(self):
        home = tempfile.mkdtemp(prefix='home-', dir=TMP)
        env_before = dict(os.environ)
        os.environ['HOME'] = home
        os.environ['XDG_DATA_HOME'] = os.path.join(home, '.local', 'share')
        os.environ['SPARK_STORE_SPARK_DIRS'] = os.path.join(FIXTURES, 'sources')
        try:
            hello = next(a for a in sparkapps.discover() if a.slug == 'spark-hello')
            self.assertIsNone(hello.installed)
            q = JobQueue()
            job = q.add(Job('spark_install', hello.id, hello.name,
                            steps=[sparkapps.install_command(hello)], flatpak=False))
            self.assertTrue(q.wait())
            self.assertEqual(job.state, DONE, job.error)
            self.assertEqual(job.progress, 1.0)
            sparkapps.refresh_state(hello)
            self.assertEqual(hello.installed, 'user')
            job = q.add(Job('spark_remove', hello.id, hello.name,
                            steps=[sparkapps.uninstall_command(hello)], flatpak=False))
            self.assertTrue(q.wait())
            self.assertEqual(job.state, DONE, job.error)
            sparkapps.refresh_state(hello)
            self.assertIsNone(hello.installed)
            self.assertEqual(glob.glob(os.path.join(home, '.local', '**', '*hello*'),
                                       recursive=True), [])
        finally:
            os.environ.clear()
            os.environ.update(env_before)


# ─── The command line ─────────────────────────────────────────

class CliTests(unittest.TestCase):
    def run_cli(self, *args, env=None):
        full = dict(os.environ, **(env or {}))
        return subprocess.run([sys.executable, os.path.join(APP_DIR, 'spark_store.py'), *args],
                              capture_output=True, text=True, env=full, timeout=120,
                              encoding='utf-8', errors='replace')

    def test_version(self):
        out = self.run_cli('--version')
        self.assertEqual(out.stdout.strip(), f"Spark Store {VERSION}")

    def test_self_test_with_a_catalog(self):
        FakeFlatpak()
        out = self.run_cli('--self-test', env={'SPARK_STORE_APPSTREAM': CATALOG_XML,
                                               'XDG_CACHE_HOME': os.path.join(TMP, 'cli-cache'),
                                               'SPARK_STORE_REQUIRE_CATALOG': '1'})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("catalog:   5 apps indexed", out.stdout)
        self.assertIn("1 proprietary", out.stdout)
        self.assertIn("spark:     Spark Alpha 1.2.0", out.stdout)
        self.assertIn("self-test passed", out.stdout)

    def test_self_test_without_a_catalog(self):
        FakeFlatpak()
        from sparkstore.cli import self_test
        old = dict(os.environ)
        os.environ['FLATPAK_USER_DIR'] = os.path.join(TMP, 'no-user')
        os.environ['FLATPAK_SYSTEM_DIR'] = os.path.join(TMP, 'no-system')
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = self_test()
            self.assertEqual(code, 0, buf.getvalue())
            self.assertIn("catalog:   not on this PC yet", buf.getvalue())
            os.environ['SPARK_STORE_REQUIRE_CATALOG'] = '1'
            with redirect_stdout(io.StringIO()):
                self.assertEqual(self_test(), 1)
        finally:
            os.environ.clear()
            os.environ.update(old)


# ─── The window ───────────────────────────────────────────────

def have_display() -> bool:
    try:
        import tkinter
        root = tkinter.Tk()
        root.destroy()
        return True
    except Exception:     # noqa: BLE001 - no tkinter or no display
        return False


@unittest.skipUnless(have_display(), "needs a display")
class UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.mkdtemp(prefix='ui-', dir=TMP)
        cls.user = os.path.join(cls.base, 'user-flatpak')
        make_installation(cls.user)
        os.environ['FLATPAK_USER_DIR'] = cls.user
        os.environ['FLATPAK_SYSTEM_DIR'] = os.path.join(cls.base, 'system-flatpak')
        os.environ['XDG_CACHE_HOME'] = os.path.join(cls.base, 'cache')

    @classmethod
    def tearDownClass(cls):
        os.environ.pop('FLATPAK_USER_DIR', None)
        os.environ.pop('FLATPAK_SYSTEM_DIR', None)

    def setUp(self):
        self.fake = FakeFlatpak(installed=[{'id': 'com.example.Chat', 'name': 'Chatter',
                                            'installation': 'user', 'size': '300 MB'}],
                                delay=0.3, names={'org.example.Paint': 'Paint Pro'})
        from sparkstore.app import Store
        self.store = Store()
        self.pump(lambda: not self.store.catalog_busy and self.store.installed_loaded)

    def tearDown(self):
        if not self.store.closed:
            self.store.queue.wait(20)
            self.store.close()

    def pump(self, until, timeout=20.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.store.root.update()
            if until():
                return True
            time.sleep(0.01)
        self.fail("timed out waiting for the window")

    def texts(self, widget=None):
        """Every label's text on the page, to look for words."""
        widget = widget or self.store.root
        out = []
        try:
            out.append(str(widget.cget('text')))
        except Exception:     # noqa: BLE001 - not every widget has text
            pass
        if hasattr(widget, 'text') and isinstance(widget.text, str):
            out.append(widget.text)
        for child in widget.winfo_children():
            out.extend(self.texts(child))
        return out

    def test_home(self):
        s = self.store
        self.assertEqual(len(s.catalog.apps), 5)
        texts = self.texts(s.pages['home'].inner)
        self.assertIn(T('home.spark'), texts)
        self.assertIn('Spark Alpha', texts)
        self.assertIn(T('row.games'), texts)
        self.assertIn('Falling Blocks', texts)
        self.assertIn(T('chip.proprietary'), texts)
        self.assertIn(T('chip.installed'), texts)       # Chatter
        self.assertIn(text_mod.t('status.ready', n=5), s.status.cget('text'))

    def test_browse_a_category(self):
        s = self.store
        self.assertIn(T('home.browse'), self.texts(s.pages['home'].inner))
        s.go('category', 'games')
        texts = self.texts(s.pages['category'].inner)
        self.assertIn('Falling Blocks', texts)
        self.assertIn(text_mod.t('search.count', n=1), texts)
        s.go_back()
        self.assertEqual(s.page, 'home')

    def test_search_as_you_type_and_enter(self):
        s = self.store
        s.search.entry.insert(0, 'draw')
        self.pump(lambda: s.page == 'search')
        self.assertEqual(s.pages['search'].first().id, 'org.example.Paint')
        s._search_enter()
        self.assertEqual(s.page, 'app')
        self.assertEqual(s.pages['app'].subject.id, 'org.example.Paint')
        s.go_back()
        self.assertEqual(s.page, 'search')
        s.search.set('')
        self.pump(lambda: s.page == 'home')

    def test_app_page_and_install(self):
        s = self.store
        s.open_app(s.catalog.apps['org.example.Paint'])
        page = s.pages['app']
        self.pump(lambda: 'org.example.Paint' in page.facts)
        texts = self.texts(page.inner)
        self.assertIn('Paint Pro', texts)
        self.assertIn(T('chip.verified'), texts)
        self.assertIn(T('btn.install'), texts)
        self.assertIn(text_mod.t('size.remote', size=local_units('103.3 MB'),
                                 download=local_units('39.6 MB')),
                      texts)
        self.assertIn('·  ' + text_mod.t('perm.f.downloads'), texts)
        self.assertIn('GPL-3.0-or-later', texts)
        s.install(page.subject)
        self.pump(lambda: s.queue.current() is not None)
        self.assertTrue(s.qbar_shown)
        self.pump(lambda: 'org.example.Paint' in s.installed, timeout=30)
        self.pump(lambda: T('btn.open') in self.texts(page.actions))
        self.assertIn(T('btn.remove'), self.texts(page.actions))
        page.ask_remove()
        self.assertIn(T('btn.remove_data'), self.texts(page.confirm))
        s.remove(page.subject, 'user', delete_data=False)
        self.pump(lambda: 'org.example.Paint' not in s.installed, timeout=30)
        self.pump(lambda: not s.qbar_shown)

    def test_addons_on_the_app_page(self):
        s = self.store
        s.open_app('org.example.Paint')
        page = s.pages['app']
        self.assertIn(T('addons.title'), self.texts(page.inner))
        self.assertIn(text_mod.t('addons.need_app', name='Paint Pro'), self.texts(page.inner))
        self.fake.update(installed=[{'id': 'org.example.Paint', 'name': 'Paint Pro',
                                     'installation': 'user'}])
        s.refresh_installed()
        self.pump(lambda: 'org.example.Paint' in s.installed)
        self.pump(lambda: 'Extra brushes' in self.texts(page.addon_frame) and
                  T('btn.install') in self.texts(page.addon_frame))
        addon = s.catalog.addons['org.example.Paint'][0]
        s.install_addon(addon)
        self.pump(lambda: s.runtimes.get(addon.id) == 'user', timeout=30)
        self.pump(lambda: T('addons.installed') in self.texts(page.addon_frame))
        self.assertIn(['--user', 'install', '-y', 'flathub',
                       'runtime/org.example.Paint.Plugin.Extra//stable'], self.fake.calls())
        s.remove_addon(addon)
        self.pump(lambda: addon.id not in s.runtimes, timeout=30)
        self.pump(lambda: T('addons.installed') not in self.texts(page.addon_frame))

    def test_proprietary_and_failure(self):
        s = self.store
        self.fake.update(fail=['com.example.Chat'], installed=[])
        s.refresh_installed()
        self.pump(lambda: 'com.example.Chat' not in s.installed)
        s.open_app('com.example.Chat')
        texts = self.texts(s.pages['app'].inner)
        self.assertIn(T('chip.proprietary'), texts)
        self.assertTrue(said('prop.text', texts, name='Chatter'))
        s.install(s.pages['app'].subject)
        self.pump(lambda: s.queue.jobs and s.queue.jobs[-1].state == FAILED, timeout=30)
        self.pump(lambda: T('btn.retry') in self.texts(s.pages['app'].actions))
        self.assertTrue(any('Not enough disk space' in x for x in
                            self.texts(s.pages['app'].actions)))
        self.assertTrue(said('failed.install', s.status.cget('text'), name='Chatter'))
        s.go('queue')
        self.assertIn(T('btn.retry'), self.texts(s.pages['queue'].inner))
        self.fake.update(fail=[])
        s.retry(s.queue.jobs[-1])
        self.pump(lambda: 'com.example.Chat' in s.installed, timeout=30)

    def test_links_open_the_right_page(self):
        s = self.store
        s.handle_target('appstream://net.example.Blocks')
        self.assertEqual(s.pages['app'].subject.id, 'net.example.Blocks')
        self.assertIn(T('unverified.title'), self.texts(s.pages['app'].inner))
        ref = os.path.join(self.base, 'tunes.flatpakref')
        with open(ref, 'w', encoding='utf-8') as f:
            f.write("[Flatpak Ref]\nName=org.example.Tunes\nUrl=https://dl.flathub.org/repo/\n")
        s.handle_target(ref)
        self.assertEqual(s.pages['app'].subject.kind, 'flathub')
        self.assertEqual(s.pages['app'].subject.id, 'org.example.Tunes')
        other = os.path.join(self.base, 'vendor.flatpakref')
        with open(other, 'w', encoding='utf-8') as f:
            f.write("[Flatpak Ref]\nName=com.vendor.App\nTitle=Vendor App\n"
                    "Url=https://repo.vendor.example/\n")
        s.handle_target(other)
        page = s.pages['app']
        self.assertEqual((page.subject.kind, page.subject.name), ('ref', 'Vendor App'))
        texts = self.texts(page.inner)
        self.assertIn(T('ref.title'), texts)
        self.assertIn(T('btn.install_from', host='repo.vendor.example'), texts)
        s.install(page.subject)
        self.pump(lambda: 'com.vendor.App' in s.installed, timeout=30)
        self.assertIn(['--user', 'install', '-y', '--from', other],
                      self.fake.calls())
        s.handle_target('appstream://org.example.Missing')
        self.assertEqual(s.page, 'search')
        s.handle_target('not a link')
        self.assertTrue(said('link.bad', s.status.cget('text')))

    def test_flatpakrepo_page(self):
        s = self.store
        path = os.path.join(self.base, 'games.flatpakrepo')
        with open(path, 'w', encoding='utf-8') as f:
            f.write("[Flatpak Repo]\nTitle=Some Games\nUrl=https://repo.games.example/\n"
                    "Comment=Games, packaged by us\n")
        s.handle_target(path)
        page = s.pages['app']
        self.assertEqual(page.subject.kind, 'repo')
        self.pump(lambda: T('repo.add') in self.texts(page.actions))
        texts = self.texts(page.inner)
        self.assertIn(T('repo.title'), texts)
        self.assertIn('https://repo.games.example/', texts)
        s.add_remote(page.subject)
        self.pump(lambda: said('repo.added', self.texts(page.actions)), timeout=30)
        self.assertIn(['--user', 'remote-add', '--if-not-exists', '--from', 'games', path],
                      self.fake.calls())
        s.handle_target(os.path.join(self.base, 'missing.flatpakrepo'))
        self.assertIn(T('link.bad_repo'), s.status.cget('text').upper())

    def test_text_fits(self):
        """Every page at the smallest window size, in the language the suite runs in."""
        from langcheck import clipped
        s = self.store
        s.root.geometry('%dx%d' % s.root.minsize())
        s.root.update()
        pages = [('home', None), ('installed', None), ('updates', None), ('queue', None),
                 ('app', 'org.example.Paint'), ('app', 'com.example.Chat'),
                 ('app', 'net.example.Blocks'), ('app', s.spark_by_id['dev.wolklaw.SparkAlpha'])]
        for page, arg in pages:
            if page == 'app':
                s.open_app(arg)
            else:
                s.go(page)
            for _ in range(10):
                s.root.update()
                time.sleep(0.02)
            with self.subTest(page=page, app=getattr(arg, 'id', arg)):
                self.assertEqual(clipped(s.root), [])

    def test_spark_app_page(self):
        s = self.store
        s.open_app(s.spark_by_id['dev.wolklaw.SparkAlpha'])
        texts = self.texts(s.pages['app'].inner)
        self.assertIn(T('chip.spark'), texts)
        self.assertTrue(said('spark.no_source', texts))            # nothing to install from
        self.assertTrue(said('perm.spark', texts))
        self.assertIn(local_units('420.0 KB'), texts)

    def test_installed_updates_and_queue_pages(self):
        s = self.store
        self.fake.update(updates=[{'id': 'com.example.Chat', 'version': '9', 'scope': 'user'}])
        s.go('installed')
        texts = self.texts(s.pages['installed'].inner)
        self.assertIn('Chatter', texts)
        self.assertIn(text_mod.t('installed.count', n=1, size=local_units('286.1 MB')), texts)
        self.assertIn(T('unused.button'), texts)
        s.remove_unused()
        self.pump(lambda: not s.queue.busy(), timeout=30)
        self.assertIn(['--user', 'uninstall', '--unused', '-y'],
                      self.fake.calls())
        s.clear_finished()
        s.go('updates')
        s.check_updates()
        self.pump(lambda: not s.updates_busy and s.updates)
        self.assertIn(T('tab.updates') + ' 1', s.tabs.labels['updates'][0].cget('text'))
        s.update_all()
        self.pump(lambda: not s.queue.busy(), timeout=30)
        self.assertEqual([(j.kind, j.state, j.error) for j in s.queue.jobs],
                         [('update_all', DONE, '')])
        self.pump(lambda: not s.updates)
        s.go('queue')
        self.pump(lambda: T('state.done') in self.texts(s.pages['queue'].inner))
        s.clear_finished()
        self.assertIn(text_mod.t('queue.empty'),
                      self.texts(s.pages['queue'].inner))

    def test_keys_and_close_while_busy(self):
        s = self.store
        s.go('installed')

        class Key:          # a key press as Tk hands it over (synthetic ones need focus)
            def __init__(self, keysym, state=0):
                self.keysym, self.state, self.widget = keysym, state, s.root
        self.assertEqual(s._key(Key('1', 0x4)), 'break')
        self.assertEqual(s.page, 'home')
        s.search.set('paint')
        self.pump(lambda: s.page == 'search')
        s._key(Key('Escape'))
        self.pump(lambda: s.page == 'home' and not s.search.get())
        s.open_app('org.example.Paint')
        s._key(Key('Escape'))
        self.assertEqual(s.page, 'home')
        self.fake.update(delay=2)
        s.install(s.pages['app'].subject_for(s.catalog.apps['org.example.Tunes']))
        self.pump(lambda: s.queue.current() is not None)
        s.close()
        self.assertFalse(s.closed)                           # hidden until the queue is done
        self.assertTrue(s.hidden_until_idle)
        end = time.monotonic() + 30
        while not s.closed and time.monotonic() < end:
            s.root.update()
            time.sleep(0.02)
        self.assertTrue(s.closed)
        self.assertIn('org.example.Tunes', [a['id'] for a in self.fake.read()['installed']])


if __name__ == '__main__':
    unittest.main()
