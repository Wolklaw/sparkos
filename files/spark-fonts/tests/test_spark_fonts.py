"""Spark Fonts' logic, with real fontconfig in a temporary home: parsing, grouping, filters,
the licence reader, install and remove, hostile zips, a fake Windows drive, the command line.
Needs fontconfig and one font on the system; a test skips with its reason when it can't run.
Nothing here touches your own ~/.local/share/fonts."""

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
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import fontkit  # noqa: E402,F401  (first: it points HOME at a temporary folder)
from fontkit import (HAVE_FC, SYSTEM_FACES, TMP, fresh_home, make_zip, pick_collection,  # noqa: E402
                     pick_font, rename_family)
from sparkfonts import cli, core, fcdata, fontfile, preview, store, text, winfonts  # noqa: E402

FC_LINE = ("/usr/share/fonts/x/Foo-Bold.ttf\t0\tFoo\tBold\tFoo Bold\t200\t0\t0\t100\tTrueType\t"
           "False\t65536\tFoo-Bold\ten|fr\n")


@unittest.skipUnless(HAVE_FC, "fontconfig isn't installed")
class Listing(unittest.TestCase):
    def test_system_has_fonts(self):
        self.assertTrue(SYSTEM_FACES)
        self.assertTrue(all(f.family and f.path for f in SYSTEM_FACES))

    def test_parse_a_line_and_bad_lines(self):
        raw = FC_LINE + "short line\n\n" + FC_LINE.replace("Foo", "Bar")
        faces = fcdata.parse(raw)
        self.assertEqual([f.family for f in faces], ['Foo', 'Bar'])
        self.assertEqual(faces[0].weight, 200)
        self.assertEqual(faces[0].langs, frozenset({'en', 'fr'}))
        self.assertEqual(faces[0].version_text, '1.000')

    def test_grouping_and_sorting(self):
        families = fcdata.group(SYSTEM_FACES)
        names = [f.name.lower() for f in families]
        self.assertEqual(names, sorted(names))
        # one entry per family and style: a font that is installed twice shows once
        self.assertLessEqual(sum(len(f.faces) for f in families), len(SYSTEM_FACES))
        self.assertGreater(sum(len(f.faces) for f in families), len(SYSTEM_FACES) // 2)
        self.assertTrue(all(f.system and not f.mine for f in families))

    def test_filters(self):
        families = fcdata.group(SYSTEM_FACES)
        one = families[len(families) // 2]
        got = fcdata.apply(families, fcdata.Filter(text=one.name.lower()))
        self.assertIn(one, got)
        self.assertEqual(fcdata.apply(families, fcdata.Filter(scope='mine')), [])
        self.assertEqual(len(fcdata.apply(families, fcdata.Filter(scope='system'))), len(families))
        self.assertEqual(fcdata.apply(families, fcdata.Filter(text='zzzz no such font')), [])
        mono = fcdata.apply(families, fcdata.Filter(category='mono'))
        self.assertTrue(all(fcdata.category(f) == 'mono' for f in mono))
        english = fcdata.apply(families, fcdata.Filter(lang='en'))
        self.assertTrue(all('en' in f.langs for f in english))

    def test_removal_refusal_reasons(self):
        self.assertEqual(fcdata.removal_refusal('/usr/share/fonts/a.ttf'), 'system')
        self.assertEqual(fcdata.removal_refusal('/usr/local/share/fonts/a.ttf'), 'local')
        self.assertEqual(fcdata.removal_refusal('/var/lib/flatpak/x/flatpak/fonts/a.ttf'),
                         'flatpak')
        self.assertEqual(fcdata.removal_refusal('/srv/a.ttf'), 'other')
        self.assertIsNone(fcdata.removal_refusal(os.path.join(core.fonts_dir(), 'A', 'a.ttf')))


class FontFiles(unittest.TestCase):
    def test_sniff(self):
        path = pick_font()
        if not path:
            self.skipTest("no TrueType or OpenType font on this system")
        self.assertIn(fontfile.sniff(path), ('ttf', 'otf'))
        junk = os.path.join(TMP, 'junk.ttf')
        with open(junk, 'wb') as f:
            f.write(b'this is not a font')
        self.assertIsNone(fontfile.sniff(junk))
        self.assertIsNone(fontfile.sniff(os.path.join(TMP, 'missing.ttf')))

    def test_name_table_and_licence(self):
        table = cli._name_table({1: 'Test', 2: 'Bold', 13: 'Free to use', 14: 'https://x.test'})
        names = fontfile.parse_names(table)
        self.assertEqual(names[1], 'Test')
        self.assertEqual(names[13], 'Free to use')
        self.assertEqual(fontfile.parse_names(b''), {})
        self.assertEqual(fontfile.parse_names(b'\xff' * 40), {})      # garbage doesn't raise

    def test_real_details(self):
        path = pick_font()
        if not path:
            self.skipTest("no TrueType or OpenType font on this system")
        d = fontfile.read_details(path)
        self.assertTrue(d.family)
        lic, url = fontfile.license_text(path)
        self.assertIsInstance(lic, str)
        self.assertIsInstance(url, str)

    def test_variable_axes(self):
        path = pick_font(variable=True, maximum=3_000_000)
        if not path:
            self.skipTest("no variable font on this system")
        d = fontfile.read_details(path)
        self.assertTrue(d.axes)
        self.assertTrue(all(a.tag for a in d.axes))

    def test_collection(self):
        path = pick_collection()
        if not path:
            self.skipTest("no .ttc collection on this system")
        self.assertEqual(fontfile.sniff(path), 'ttc')
        self.assertGreater(fontfile.read_details(path).faces, 1)
        kind, faces = fontfile.check_installable(path)
        self.assertEqual(kind, 'ttc')
        self.assertGreater(faces, 1)

    def test_not_a_font_and_web_fonts_are_refused(self):
        junk = os.path.join(TMP, 'fake.otf')
        with open(junk, 'wb') as f:
            f.write(b'OTTO' + b'\x00' * 8)       # right magic, no tables
        with self.assertRaises(fontfile.FontError):
            fontfile.check_installable(junk)
        woff = os.path.join(TMP, 'a.woff2')
        with open(woff, 'wb') as f:
            f.write(b'wOF2' + b'\x00' * 60)
        with self.assertRaises(fontfile.FontError) as ctx:
            fontfile.check_installable(woff)
        self.assertEqual(str(ctx.exception), 'web_font')


class Zips(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='zip-', dir=TMP)
        self.out = os.path.join(self.dir, 'out')
        os.makedirs(self.out)
        self.font = pick_font()

    def payload(self):
        if not self.font:
            self.skipTest("no TrueType or OpenType font on this system")
        with open(self.font, 'rb') as f:
            return f.read()

    def test_good_zip_keeps_only_fonts(self):
        data = self.payload()
        zpath = os.path.join(self.dir, 'ok.zip')
        make_zip(zpath, [('Fonts/a.ttf', data), ('readme.txt', b'hi'), ('__MACOSX/._a.ttf', b'x')])
        got, skipped = store.extract_zip(zpath, self.out)
        self.assertEqual([os.path.basename(p) for p in got], ['a.ttf'])
        self.assertTrue(all(os.path.realpath(p).startswith(os.path.realpath(self.out)) for p in got))
        self.assertTrue(any(n == 'readme.txt' for n, _ in skipped))

    def test_hostile_names_never_escape(self):
        data = self.payload()
        zpath = os.path.join(self.dir, 'bad.zip')
        make_zip(zpath, [('../escape.ttf', data), ('/abs.ttf', data), ('a/../../up.ttf', data),
                         ('C:\\win.ttf', data)])
        got, _skipped = store.extract_zip(zpath, self.out)
        self.assertEqual(got, [])
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'escape.ttf')))
        self.assertFalse(os.path.exists('/abs.ttf'))

    def test_symlink_entry_refused(self):
        zpath = os.path.join(self.dir, 'link.zip')
        with zipfile.ZipFile(zpath, 'w') as z:
            info = zipfile.ZipInfo('evil.ttf')
            info.create_system = 3
            info.external_attr = (0o120777 << 16)
            z.writestr(info, '/etc/passwd')
        got, skipped = store.extract_zip(zpath, self.out)
        self.assertEqual(got, [])
        self.assertEqual(len(skipped), 1)

    def test_not_font_bytes_with_font_name_refused(self):
        zpath = os.path.join(self.dir, 'fake.zip')
        make_zip(zpath, [('a.ttf', b'MZ\x90\x00 this is a program')])
        got, skipped = store.extract_zip(zpath, self.out)
        self.assertEqual(got, [])
        self.assertEqual(skipped[0][1], 'not_font')

    def test_too_many_entries_and_too_big(self):
        zpath = os.path.join(self.dir, 'many.zip')
        make_zip(zpath, [(f'f{i}.txt', b'x') for i in range(store.MAX_ENTRIES + 5)])
        with self.assertRaises(store.StoreError):
            store.extract_zip(zpath, self.out)
        big = os.path.join(self.dir, 'big.zip')
        with zipfile.ZipFile(big, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('a.ttf', b'\x00\x01\x00\x00' + b'\x00' * (store.MAX_FILE + 1000))
        got, skipped = store.extract_zip(big, self.out)
        self.assertEqual(got, [])
        self.assertTrue(skipped)

    def test_corrupt_zip(self):
        zpath = os.path.join(self.dir, 'c.zip')
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as z:
            z.writestr('a.ttf', b'x' * 100)
        with open(zpath, 'wb') as f:
            f.write(data.getvalue()[:-10])
        cands, _problems = store.plan([zpath], self.dir, installed=[])
        self.assertEqual([c.status for c in cands], [store.REFUSED])


@unittest.skipUnless(HAVE_FC, "fontconfig isn't installed")
class InstallAndRemove(unittest.TestCase):
    def setUp(self):
        fresh_home()
        self.work = tempfile.mkdtemp(prefix='work-', dir=TMP)
        src = pick_font()
        if not src:
            self.skipTest("no TrueType or OpenType font on this system")
        self.src = os.path.join(self.work, os.path.basename(src))
        # a copy under another family name, so it doesn't clash with a system font
        self.family = rename_family(src, self.src, 'Zq' + 'x' * 30)

    def faces_of(self, family):
        return [f for f in fcdata.list_faces() if f.family == family]

    def test_install_list_remove(self):
        cands, problems = store.plan([self.src], self.work)
        self.assertEqual(problems, [])
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0].status, store.NEW, cands[0])
        fam = cands[0].family
        out = store.install(cands)
        self.assertEqual(out.failed, [])
        self.assertEqual(len(out.installed), 1)
        self.assertTrue(out.installed[0].startswith(core.fonts_dir()))
        self.assertEqual(oct(os.stat(out.installed[0]).st_mode & 0o777), '0o644')
        got = self.faces_of(fam)
        self.assertTrue(got, "fc-list doesn't show the installed font")
        self.assertTrue(all(fcdata.is_user_font(f.path) for f in got))
        families = fcdata.group(fcdata.list_faces())
        mine = fcdata.apply(families, fcdata.Filter(scope='mine'))
        self.assertEqual([f.name for f in mine], [fam])
        # the same file again is "already installed"
        again = store.plan([self.src], self.work)[0]
        self.assertEqual(again[0].status, store.SAME)
        self.assertEqual(store.install(again).installed, [])
        # remove: to the trash, gone from fc-list, empty folder cleaned up
        done, failed = store.remove([f.path for f in got])
        self.assertEqual(failed, [])
        self.assertTrue(done)
        self.assertFalse(any(os.path.exists(p) for p in done))
        self.assertEqual(self.faces_of(fam), [])
        self.assertEqual(os.listdir(core.fonts_dir()), [])
        trashed = os.path.join(core.data_home(), 'Trash', 'files')
        self.assertTrue(os.path.isdir(trashed) and os.listdir(trashed))

    def test_duplicate_needs_replace(self):
        store.install(store.plan([self.src], self.work)[0])
        other = os.path.join(self.work, 'other-copy.ttf')
        with open(self.src, 'rb') as f:
            data = bytearray(f.read())
        data.extend(b'\x00' * 8)                       # same font, different bytes
        with open(other, 'wb') as f:
            f.write(data)
        cands = store.plan([other], self.work)[0]
        self.assertEqual(cands[0].status, store.DUPLICATE)
        self.assertTrue(cands[0].replaces)
        self.assertEqual(store.install(cands, replace=False).installed, [])
        out = store.install(cands, replace=True)
        self.assertEqual(len(out.installed), 1)
        self.assertEqual(out.replaced, 1)
        self.assertTrue(self.faces_of(cands[0].family))   # a variable font lists several faces from one file

    def test_system_font_is_never_installed_or_removed(self):
        system = pick_font()
        cands = store.plan([system], self.work)[0]
        self.assertEqual(cands[0].status, store.SYSTEM)
        self.assertEqual(store.install(cands, replace=True).installed, [])
        done, failed = store.remove([system])
        self.assertEqual(done, [])
        self.assertEqual(failed[0][1], 'system')
        self.assertTrue(os.path.exists(system))

    def test_not_a_font_is_refused_in_the_plan(self):
        fake = os.path.join(self.work, 'fake.ttf')
        with open(fake, 'wb') as f:
            f.write(b'just words')
        cands = store.plan([fake], self.work)[0]
        self.assertEqual(cands[0].status, store.REFUSED)
        self.assertEqual(cands[0].reason, 'not_font')
        self.assertEqual(store.install(cands).installed, [])
        self.assertEqual(os.listdir(core.fonts_dir()), [])

    def test_zip_and_folder_install(self):
        with open(self.src, 'rb') as f:
            data = f.read()
        zpath = os.path.join(self.work, 'pack.zip')
        make_zip(zpath, [('pack/a.ttf', data), ('pack/license.txt', b'x')])
        cands, _p = store.plan([zpath], self.work)
        self.assertEqual([c.status for c in cands], [store.NEW])
        folder = os.path.join(self.work, 'dir')
        os.makedirs(folder)
        shutil.copy(self.src, os.path.join(folder, 'b.ttf'))
        cands, _p = store.plan([folder], self.work)
        self.assertEqual(len(cands), 1)

    def test_collection_and_variable_install(self):
        for label, path in (('collection', pick_collection()),
                            ('variable', pick_font(variable=True, maximum=3_000_000))):
            if not path:
                continue
            with self.subTest(label):
                fresh_home()
                cands = store.plan([path], self.work)[0]
                if cands[0].status == store.SYSTEM:
                    # it's on the system already, so the plan must say so
                    self.assertEqual(store.install(cands).installed, [])
                    continue
                self.assertTrue(cands[0].installable, cands[0])

    def test_broken_files_are_found(self):
        folder = os.path.join(core.fonts_dir(), 'Junk')
        os.makedirs(folder)
        bad = os.path.join(folder, 'broken.ttf')
        with open(bad, 'wb') as f:
            f.write(b'not a font')
        store.refresh_cache()
        self.assertEqual(fcdata.find_broken(fcdata.list_faces()), [bad])
        store.remove([bad])
        self.assertEqual(fcdata.find_broken(fcdata.list_faces()), [])


class WindowsDrive(unittest.TestCase):
    def build(self, case_style):
        root = tempfile.mkdtemp(prefix='win-', dir=TMP)
        names = ('Windows', 'Fonts') if case_style == 'normal' else ('WINDOWS', 'FONTS')
        os.makedirs(os.path.join(root, names[0], names[1]))
        user = os.path.join(root, 'Users', 'Sam', 'AppData', 'Local', 'Microsoft', 'Windows',
                            'Fonts')
        os.makedirs(user)
        os.makedirs(os.path.join(root, 'Users', 'Public'))
        os.makedirs(os.path.join(root, 'Users', 'Default'))
        return root, os.path.join(root, names[0], names[1]), user

    def test_finds_system_and_user_folders(self):
        font = pick_font()
        if not font:
            self.skipTest("no TrueType or OpenType font on this system")
        for style in ('normal', 'upper'):
            with self.subTest(style):
                root, system, user = self.build(style)
                shutil.copy(font, os.path.join(system, 'ARIAL.TTF'))
                shutil.copy(font, os.path.join(user, 'mine.ttf'))
                with open(os.path.join(system, 'desktop.ini'), 'w') as f:
                    f.write('[.ShellClassInfo]')
                sources = winfonts.windows_sources(root)
                self.assertEqual(len(sources), 2)
                self.assertEqual(sources[0].where, r'C:\Windows\Fonts')
                self.assertIn('Sam', sources[1].where)
                found = winfonts.list_files(sources)
                self.assertEqual(sorted(f.name.lower() for f in found), ['arial.ttf', 'mine.ttf'])

    def test_no_windows_folder(self):
        root = tempfile.mkdtemp(prefix='nowin-', dir=TMP)
        self.assertEqual(winfonts.windows_sources(root), [])

    def test_lsblk_parsing(self):
        self.assertEqual(winfonts.parse_lsblk('{}'), [])
        self.assertEqual(winfonts.parse_lsblk('not json'), [])
        data = {'blockdevices': [{'name': 'sda', 'type': 'disk', 'children': [
            {'name': 'sda1', 'path': '/dev/sda1', 'type': 'part', 'fstype': 'ntfs',
             'label': 'Windows', 'size': 1000, 'mountpoints': [None]}]}]}
        parts = winfonts.parse_lsblk(json.dumps(data))
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0].path, '/dev/sda1')


@unittest.skipUnless(preview.available(), "Pillow isn't installed")
class Previews(unittest.TestCase):
    def test_draws_text_and_grid(self):
        path = pick_font()
        if not path:
            self.skipTest("no TrueType or OpenType font on this system")
        face = fcdata.query_file(path)[0]
        png, height = preview.draw_text(face, "Hello", 24, 300, '#ffffff', '#000000')
        self.assertEqual(png[:4], b'\x89PNG')
        self.assertGreater(height, 10)
        chars = preview.charset(face.path)
        self.assertTrue(chars)
        png, w, h = preview.grid_image(face, list(chars)[:40], 30, 8, '#fff', '#000', '#333')
        self.assertEqual(png[:4], b'\x89PNG')
        self.assertGreater(w, 100)

    def test_char_query(self):
        self.assertEqual(preview.parse_char_query('U+0041'), 0x41)
        self.assertEqual(preview.parse_char_query('0x41'), 0x41)
        self.assertEqual(preview.parse_char_query('A'), 0x41)
        self.assertIsNone(preview.parse_char_query(''))


class Cli(unittest.TestCase):
    def run_cli(self, *args, env=None):
        full = dict(os.environ)
        full.update(env or {})
        return subprocess.run([sys.executable, os.path.join(os.path.dirname(HERE), 'spark_fonts.py'),
                               *args], capture_output=True, text=True, env=full, timeout=120)

    def test_version(self):
        r = self.run_cli('--version')
        self.assertEqual(r.returncode, 0)
        self.assertIn('Spark Fonts 0.1.0', r.stdout)

    @unittest.skipUnless(HAVE_FC, "fontconfig isn't installed")
    def test_self_test_passes(self):
        r = self.run_cli('--self-test')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('self-test passed', r.stdout)

    def test_install_needs_a_file(self):
        self.assertEqual(self.run_cli('--install').returncode, 2)

    @unittest.skipUnless(HAVE_FC, "fontconfig isn't installed")
    def test_install_refuses_junk_and_installs_a_font(self):
        fresh_home()
        work = tempfile.mkdtemp(prefix='cli-', dir=TMP)
        junk = os.path.join(work, 'junk.ttf')
        with open(junk, 'wb') as f:
            f.write(b'nope')
        r = self.run_cli('--install', junk)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(os.listdir(core.fonts_dir()), [])
        src = pick_font()
        if not src:
            self.skipTest("no TrueType or OpenType font on this system")
        mine = os.path.join(work, 'font.ttf')
        rename_family(src, mine, 'Zy' + 'q' * 30)
        r = self.run_cli('--install', mine)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(os.listdir(core.fonts_dir())), 1)
        r = self.run_cli('--install', mine)       # already there: nothing to do
        self.assertEqual(r.returncode, 1)

    def test_french_cli_messages(self):
        r = self.run_cli('--install', os.path.join(TMP, 'missing.ttf'), env={'SPARK_LANG': 'fr'})
        self.assertEqual(r.returncode, 1)
        self.assertNotIn('Nothing was installed', r.stderr)


class Speed(unittest.TestCase):
    def test_grouping_and_filtering_many_faces_is_quick(self):
        faces = []
        for i in range(1200):
            faces.append(fcdata.Face(path=f'/usr/share/fonts/f{i % 300}/F{i}.ttf',
                                     family=f'Family {i % 300}', style=f'Style {i}',
                                     langs=frozenset({'en'})))
        t0 = time.monotonic()
        families = fcdata.group(faces)
        for word in ('fam', 'family 1', 'style 99', 'zzz'):
            fcdata.apply(families, fcdata.Filter(text=word, category='sans'))
        self.assertLess(time.monotonic() - t0, 1.5)
        self.assertEqual(len(families), 300)


class Strings(unittest.TestCase):
    def test_every_key_used_in_code_exists(self):
        import re
        base = os.path.join(os.path.dirname(HERE), 'sparkfonts')
        used = set()
        for name in os.listdir(base):
            if name.endswith('.py') and name != 'text.py':
                with open(os.path.join(base, name), encoding='utf-8') as f:
                    used |= set(re.findall(r"""\bt\(\s*['"]([a-z_]+\.[a-z_.0-9]*[a-z_0-9])['"]""", f.read()))
        self.assertEqual(sorted(k for k in used if k not in text.EN), [])


if __name__ == '__main__':
    unittest.main()
