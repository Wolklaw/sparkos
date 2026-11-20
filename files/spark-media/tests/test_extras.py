"""Tests for the music library, playlists, the play queue, camera RAW, photo edits and French.

    python -m unittest discover -s files/spark-media/tests -v

Song files are encoded with GStreamer on the spot (skipped without it); the DNG is written by
tests/fixtures.py. Lines starting with "speed:", "scan:" and "raw:" go to the CI summary."""

import os
import re
import shutil
import string
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-media-{var.lower()}-'))
os.environ.setdefault('SPARK_MEDIA_AUDIO_SINK', 'fakesink')

from PIL import Image  # noqa: E402

import fixtures  # noqa: E402
from sparkmedia import core, edits, musiclib, playlists, playqueue, raw, strings, tags, text  # noqa: E402
from sparkmedia import player as gst  # noqa: E402

text.set_language('en')


def touch(path: str, data: bytes = b'') -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)
    return path


class Temp(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.realpath(tempfile.mkdtemp(prefix='spark-media-x-'))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)


# ─── French ───────────────────────────────────────────────────

class LanguageTests(unittest.TestCase):
    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in ('SPARK_LANG', 'LC_ALL', 'LC_MESSAGES', 'LANG')}
        for k in self.saved:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        text.set_language('en')

    def test_locale_order_and_override(self):
        self.assertEqual(text.language(), 'en')
        os.environ['LANG'] = 'fr_CA.UTF-8'
        self.assertEqual(text.language(), 'fr')
        os.environ['LC_MESSAGES'] = 'en_US.UTF-8'          # LC_MESSAGES wins over LANG
        self.assertEqual(text.language(), 'en')
        os.environ['LC_ALL'] = 'fr_FR.UTF-8'               # LC_ALL wins over both
        self.assertEqual(text.language(), 'fr')
        os.environ['SPARK_LANG'] = 'en'                    # and SPARK_LANG over everything
        self.assertEqual(text.language(), 'en')
        os.environ['SPARK_LANG'] = 'FR'
        self.assertEqual(text.language(), 'fr')
        os.environ['SPARK_LANG'] = 'de'                    # not a language we have: ignored
        os.environ['LC_ALL'] = 'C.UTF-8'
        self.assertEqual(text.language(), 'en')

    def test_every_string_has_french_with_the_same_blanks(self):
        self.assertEqual(set(strings.EN), set(strings.FR))
        fields = lambda s: sorted(f for _l, f, _s, _c in string.Formatter().parse(s) if f)  # noqa: E731
        for key, english in strings.EN.items():
            self.assertTrue(strings.FR[key].strip(), key)
            self.assertEqual(fields(english), fields(strings.FR[key]), key)

    def test_every_key_used_exists(self):
        used = set()
        folder = os.path.join(os.path.dirname(HERE), 'sparkmedia')
        for name in os.listdir(folder):
            if name.endswith('.py'):
                with open(os.path.join(folder, name), encoding='utf-8') as f:
                    source = f.read()
                used |= set(re.findall(r"tr\('([a-z_.0-9]+)'", source))
                used |= set(re.findall(r"'((?:count|status)\.[a-z_]+)'", source))
        self.assertEqual(sorted(k for k in used if k not in strings.EN), [])

    def test_french_plural_and_vous(self):
        text.set_language('fr')
        self.assertEqual(text.plural(0, 'count.song', 'count.songs'), "0 chanson")
        self.assertEqual(text.plural(2, 'count.song', 'count.songs'), "2 chansons")
        self.assertEqual(text.tr('tab.songs'), "CHANSONS")
        # "vous", never "tu"
        for key, value in strings.FR.items():
            self.assertIsNone(re.search(r"\b(tu|ton|ta|tes)\b", value, re.I), key)


# ─── Playlists ────────────────────────────────────────────────

class PlaylistTests(Temp):
    def test_write_relative_and_read_back(self):
        a = touch(os.path.join(self.dir, 'Music', 'Band', 'Album', '01 Été.flac'))
        b = touch(os.path.join(self.dir, 'Other', 'b.mp3'))
        pl = os.path.join(self.dir, 'Music', 'Playlists', 'Mix.m3u8')
        playlists.write(pl, [a, b], [(201.4, 'Band - Été'), (None, None)])
        with open(pl, encoding='utf-8') as f:
            body = f.read()
        self.assertIn('#EXTM3U', body)
        self.assertIn('#EXTINF:201,Band - Été', body)
        self.assertIn('../Band/Album/01 Été.flac', body)      # relative, forward slashes
        self.assertIn('../../Other/b.mp3', body)
        self.assertNotIn(self.dir, body)
        back = playlists.read(pl)
        self.assertEqual(back.items, [a, b])
        self.assertEqual(back.titles, ['Band - Été', None])
        self.assertEqual(back.durations, [201.0, None])
        self.assertEqual(back.name, 'Mix')

    def test_read_others_playlists(self):
        song = touch(os.path.join(self.dir, 'x', 'song.ogg'))
        uri = core.file_uri(song)
        pl = os.path.join(self.dir, 'old.m3u')
        with open(pl, 'wb') as f:
            f.write('\ufeff#EXTM3U\r\n#EXTINF:-1,Café\r\nx/song.ogg\r\n'
                    'http://radio.example/stream\r\n\r\n# a comment\r\n'.encode('utf-8') +
                    uri.encode() + b'\r\n')
        got = playlists.read(pl)
        self.assertEqual(got.items, [song, song])
        self.assertEqual(got.titles[0], 'Café')
        self.assertIsNone(got.durations[0])
        self.assertEqual(got.skipped, ['http://radio.example/stream'])
        latin = os.path.join(self.dir, 'latin.m3u')
        with open(latin, 'wb') as f:
            f.write('#EXTINF:10,Noël\nx/song.ogg\n'.encode('cp1252'))
        self.assertEqual(playlists.read(latin).titles, ['Noël'])

    @unittest.skipIf(os.name == 'nt', "Windows paths are already backslashed")
    def test_windows_written_paths(self):
        song = touch(os.path.join(self.dir, 'A', 'b.mp3'))
        pl = os.path.join(self.dir, 'win.m3u')
        with open(pl, 'w', encoding='utf-8') as f:
            f.write('A\\b.mp3\nC:\\Music\\gone.mp3\n')
        got = playlists.read(pl)
        self.assertEqual(got.items, [song])
        self.assertEqual(got.skipped, ['C:\\Music\\gone.mp3'])

    def test_names(self):
        self.assertEqual(playlists.safe_name('  a/b:c?  '), 'a b c')
        self.assertEqual(playlists.safe_name('...'), '')
        music = os.path.join(self.dir, 'Music')
        path = playlists.new_path(music, 'Road trip')
        self.assertEqual(path, os.path.join(music, 'Playlists', 'Road trip.m3u8'))
        playlists.write(path, [])
        self.assertIsNone(playlists.new_path(music, 'Road trip'))
        self.assertIsNone(playlists.new_path(music, '///'))
        self.assertTrue(playlists.is_playlist('x.M3U8'))


# ─── Play queue ───────────────────────────────────────────────

class QueueTests(unittest.TestCase):
    def test_order_next_prev_repeat(self):
        q = playqueue.PlayQueue()
        self.assertIsNone(q.current)
        self.assertIsNone(q.next())
        q.set(['a', 'b', 'c'], 1)
        self.assertEqual(q.current, 'b')
        self.assertEqual(q.next(), 'c')
        self.assertIsNone(q.next())                  # end, no repeat
        self.assertEqual(q.current, 'c')
        self.assertEqual(q.next(wrap=True), 'a')     # the Next button wraps
        q.repeat = True
        q.jump(2)
        self.assertEqual(q.next(), 'a')
        self.assertEqual(q.prev(), 'c')

    def test_add_play_next_remove_move(self):
        q = playqueue.PlayQueue()
        q.add(['a'])
        self.assertEqual(q.current, 'a')
        q.add(['b', 'c'])
        q.play_next(['x', 'y'])
        self.assertEqual([q.items[i] for i in q.order], ['a', 'x', 'y', 'b', 'c'])
        q.remove(q.items.index('x'))
        self.assertEqual([q.items[i] for i in q.order], ['a', 'y', 'b', 'c'])
        self.assertEqual(q.current, 'a')
        q.move(q.items.index('c'), -2)
        self.assertEqual([q.items[i] for i in q.order], ['a', 'c', 'y', 'b'])
        q.next()
        q.remove(q.index)                            # remove the current song
        self.assertEqual(q.current, 'y')
        q.clear_upcoming()
        self.assertEqual(q.items, ['y'])

    def test_shuffle_plays_everything_once(self):
        q = playqueue.PlayQueue()
        q.shuffle = True
        items = [str(i) for i in range(50)]
        q.set(items, 7)
        self.assertEqual(q.current, '7')
        seen = [q.current]
        while q.next():
            seen.append(q.current)
        self.assertEqual(sorted(seen), sorted(items))
        q.set_shuffle(False)
        self.assertEqual(q.order, list(range(50)))
        q.repeat = True
        q.set_shuffle(True)
        last = q.current
        for _ in range(60):
            q.next()
        self.assertIn(q.current, items)
        self.assertTrue(last)


# ─── Music library ────────────────────────────────────────────

def fake_reader(table):
    def read(path, want_cover=False):
        song = tags.empty(path)
        song.update(table.get(os.path.basename(path), {}))
        return {'song': song, 'cover': None}
    return read


class LibraryTests(Temp):
    def scan(self, lib, roots, reader):
        scanner = musiclib.Scanner(lib, roots, reader=reader)
        scanner.start()
        scanner.thread.join(60)
        events = scanner.poll(limit=100000)
        self.assertEqual(events[-1][0], 'done')
        return scanner

    def test_grouping_and_incremental_scan(self):
        music = os.path.join(self.dir, 'Music')
        table = {
            '01.flac': dict(title='One', artist='Alpha', album='First', track=1, year=2001),
            '02.flac': dict(title='Two', artist='Alpha', album='First', track=2, year=2001),
            '10.mp3': dict(title='Ten', artist='The Beta', album='Second', track=1, year=1999),
            # a compilation without album artist: one album, by folder
            'c1.ogg': dict(title='C1', artist='Gamma', album='Hits', track=1),
            'c2.ogg': dict(title='C2', artist='Delta', album='Hits', track=2),
            'untagged.wav': {},
        }
        for name, where in (('01.flac', 'Alpha/First'), ('02.flac', 'Alpha/First'),
                            ('10.mp3', 'Beta'), ('c1.ogg', 'Hits'), ('c2.ogg', 'Hits'),
                            ('untagged.wav', '')):
            touch(os.path.join(music, where, name))
        touch(os.path.join(music, '.hidden', 'x.mp3'))
        touch(os.path.join(music, 'notes.txt'))
        touch(os.path.join(music, 'Playlists', 'Mine.m3u8'), b'#EXTM3U\n')
        Image.new('RGB', (40, 40), 'red').save(os.path.join(music, 'Alpha', 'First', 'cover.jpg'))
        lib = musiclib.Library()
        self.scan(lib, [music], fake_reader(table))
        self.assertEqual(len(lib.songs), 6)
        self.assertEqual([os.path.basename(p) for p in lib.playlists], ['Mine.m3u8'])
        albums = {a.title: a for a in lib.albums()}
        self.assertEqual(set(albums), {'First', 'Second', 'Hits', ''})
        self.assertEqual([s['title'] for s in albums['First'].songs], ['One', 'Two'])
        self.assertEqual(albums['Hits'].artist, '')              # various artists
        self.assertEqual(len(albums['Hits'].songs), 2)
        names = [a['name'] for a in lib.artists()]
        self.assertEqual(names[:2], ['Alpha', 'The Beta'])       # "The" ignored when sorting
        self.assertEqual(names[-1], '')                         # unknown artist last
        self.assertEqual(lib.artist('alpha')['albums'][0].title, 'First')
        self.assertEqual(musiclib.display_title(lib.song(os.path.join(music, 'untagged.wav'))),
                         'untagged')
        # the folder's cover.jpg became the album's cover
        self.assertIsNotNone(musiclib.load_cover(albums['First'].cover_id))
        self.assertTrue(musiclib.matches(musiclib.search_words('alp ONE'), 'One', 'Alpha'))
        self.assertTrue(musiclib.matches(musiclib.search_words('ete'), 'Été'))

        # the index survives a restart
        lib.save()
        again = musiclib.Library.load()
        self.assertEqual(set(again.songs), set(lib.songs))

        # incremental: one changed, one gone, one new; only those are read
        read = []
        base = fake_reader(table)

        def counting(path, want_cover=False):
            read.append(os.path.basename(path))
            return base(path, want_cover)

        changed = os.path.join(music, 'Beta', '10.mp3')
        os.utime(changed, (time.time() + 50, time.time() + 50))
        os.remove(os.path.join(music, 'Hits', 'c2.ogg'))
        table['new.opus'] = dict(title='New', artist='Alpha', album='First', track=3)
        touch(os.path.join(music, 'Alpha', 'First', 'new.opus'))
        scanner = self.scan(again, [music], counting)
        self.assertEqual(sorted(read), ['10.mp3', 'new.opus'])
        self.assertEqual(scanner.stats['removed'], 1)
        self.assertEqual(len(again.songs), 6)
        self.assertEqual(len(again.album(albums['First'].key).songs), 3)

    def test_broken_index_starts_over(self):
        path = os.path.join(self.dir, 'music.json')
        touch(path, b'{not json')
        self.assertEqual(musiclib.Library.load(path).songs, {})

    def test_speed_10000_songs(self):
        songs = fixtures.fake_songs(10000)
        lib = musiclib.Library()
        t0 = time.perf_counter()
        lib.update(songs)
        views = lib.views()
        t1 = time.perf_counter()
        words = musiclib.search_words('song 99')
        hits = [s for s in views['songs'] if musiclib.matches(words, s['title'], s['artist'],
                                                               s['album'])]
        t2 = time.perf_counter()
        path = os.path.join(self.dir, 'music.json')
        lib.save(path)
        t3 = time.perf_counter()
        loaded = musiclib.Library.load(path)
        loaded.views()
        t4 = time.perf_counter()
        print(f"speed: 10 000 songs: group and sort {t1 - t0:.3f} s, search {t2 - t1:.3f} s, "
              f"save {t3 - t2:.3f} s ({os.path.getsize(path) // 1024} KB), "
              f"load and group {t4 - t3:.3f} s")
        self.assertEqual(len(views['songs']), 10000)
        self.assertEqual(len(views['artists']), 400)
        self.assertGreater(len(hits), 10)
        self.assertLess(t1 - t0, 3.0)
        self.assertLess(t2 - t1, 1.0)
        self.assertLess(t4 - t3, 4.0)

    def test_speed_rescan_10000_files(self):
        music = os.path.join(self.dir, 'Music')
        for i in range(10000):
            touch(os.path.join(music, f'Artist {i % 200}', f'Album {i % 3}', f'{i:05d}.mp3'))
        lib = musiclib.Library()
        reader = fake_reader({})
        t0 = time.perf_counter()
        self.scan(lib, [music], reader)
        t1 = time.perf_counter()
        read = []
        self.scan(lib, [music], lambda p, w=False: read.append(p) or reader(p, w))
        t2 = time.perf_counter()
        print(f"scan: 10 000 files: first scan {t1 - t0:.2f} s (tags stubbed), "
              f"rescan with nothing changed {t2 - t1:.2f} s")
        self.assertEqual(len(lib.songs), 10000)
        self.assertEqual(read, [])
        self.assertLess(t2 - t1, 5.0)


@unittest.skipUnless(gst.available(), "GStreamer's Python bindings are not installed")
class TagTests(Temp):
    """Real files, encoded here, read by TagLib (when the system has it) and by GStreamer."""

    @classmethod
    def setUpClass(cls):
        cls.files = os.path.realpath(tempfile.mkdtemp(prefix='spark-media-songs-'))
        cls.flac = os.path.join(cls.files, 'Album', '03 tone.flac')
        os.makedirs(os.path.dirname(cls.flac))
        if not fixtures.encode(gst, cls.flac, 1.0):
            raise unittest.SkipTest("no FLAC encoder")
        fixtures.flac_tags(cls.flac, {'TITLE': 'Tone Three', 'ARTIST': 'Signal',
                                      'ALBUMARTIST': 'Signal & Co', 'ALBUM': 'Test Tones',
                                      'TRACKNUMBER': '3/9', 'DISCNUMBER': '2', 'DATE': '2009-05-01',
                                      'GENRE': 'Électro'},
                           picture=fixtures.cover_jpeg('#ff4d8d'))
        cls.ogg = os.path.join(cls.files, 'tone.ogg')
        fixtures.encode(gst, cls.ogg, 1.0, {'title': 'Ogg Tone', 'artist': 'Vorbis Band',
                                            'album': 'Ogg Album', 'track-number': 5})
        cls.mp3 = os.path.join(cls.files, 'tone.mp3')
        if not fixtures.encode(gst, cls.mp3, 1.0, {'title': 'Mp3 Tone', 'artist': 'Lame',
                                                   'album': 'Id3', 'track-number': 7}):
            cls.mp3 = None

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.files, ignore_errors=True)

    def check(self, read):
        got = read(self.flac, True)
        song = got['song']
        self.assertEqual(song['title'], 'Tone Three')
        self.assertEqual(song['artist'], 'Signal')
        self.assertEqual(song['albumartist'], 'Signal & Co')
        self.assertEqual(song['album'], 'Test Tones')
        self.assertEqual(song['track'], 3)
        self.assertEqual(song['disc'], 2)
        self.assertEqual(song['year'], 2009)
        self.assertEqual(song['genre'], 'Électro')
        self.assertAlmostEqual(song['length'], 1.0, delta=1.0)
        cover = tags.cover_from_bytes(got['cover'] or b'')
        self.assertIsNotNone(cover)
        self.assertEqual(cover.getpixel((10, 10))[0] > 200, True)
        song = read(self.ogg, False)['song']
        self.assertEqual((song['title'], song['artist'], song['album'], song['track']),
                         ('Ogg Tone', 'Vorbis Band', 'Ogg Album', 5))
        if self.mp3:
            song = read(self.mp3, False)['song']
            self.assertEqual((song['title'], song['artist'], song['album'], song['track']),
                             ('Mp3 Tone', 'Lame', 'Id3', 7))
        broken = touch(os.path.join(self.dir, 'broken.mp3'), b'nothing here')
        self.assertEqual(tags.read(broken)['song']['title'], '')

    def test_libraries_load_when_installed(self):
        """A TagLib or LibRaw that's installed but won't load is a bug, not a skip."""
        import ctypes.util
        if ctypes.util.find_library('tag_c'):
            self.assertIsNotNone(tags.taglib(), "libtag_c is installed but didn't load")
        if ctypes.util.find_library('raw_r'):
            self.assertIsNotNone(raw.libraw(), "libraw_r is installed but didn't load")
        print(f"scan: tags backend {tags.backend()}; raw decode {raw.decoder()}")

    @unittest.skipUnless(tags.taglib() is not None, "TagLib's C library (libtag_c) is not installed")
    def test_taglib(self):
        self.check(lambda p, c: tags.taglib().read(p, c))
        lib = tags.taglib()
        t0 = time.perf_counter()
        for _ in range(200):
            lib.read(self.flac, False)
            lib.read(self.ogg, False)
        each = (time.perf_counter() - t0) / 400
        print(f"scan: TagLib reads a song's tags in {each * 1000:.2f} ms "
              f"({1 / each:.0f} songs a second, FLAC and Ogg, file cache warm)")
        t0 = time.perf_counter()
        for _ in range(20):
            tags._discover(self.flac, False)
        print(f"scan: GStreamer's Discoverer takes {(time.perf_counter() - t0) / 20 * 1000:.1f} ms "
              f"a song")

    def test_gstreamer_discoverer(self):
        self.check(tags._discover)

    def test_library_from_real_files(self):
        lib = musiclib.Library()
        scanner = musiclib.Scanner(lib, [self.files])
        scanner.start()
        scanner.thread.join(60)
        scanner.poll(limit=100000)
        album = [a for a in lib.albums() if a.title == 'Test Tones'][0]
        self.assertEqual(album.artist, 'Signal & Co')
        self.assertIsNotNone(musiclib.load_cover(album.cover_id))     # embedded cover cached


# ─── Camera RAW ───────────────────────────────────────────────

class RawTests(Temp):
    def test_dng_preview_tags_and_orientation(self):
        path = fixtures.make_dng(os.path.join(self.dir, 'IMG_0001.dng'), orientation=6)
        with open(path, 'rb') as f:
            found = raw.previews(f.read())
        self.assertEqual(found[0][2], (96, 72))
        self.assertEqual(raw.sensor_size(path), (192, 144))
        facts = raw.info(path)
        self.assertEqual((facts['make'], facts['model'], facts['taken']),
                         ('Spark', 'Spark TestCam', '2024:07:14 10:30:00'))
        photo = core.Photo(path)
        self.assertTrue(photo.raw)
        self.assertEqual(photo.size, (72, 96))              # turned upright
        self.assertEqual(photo.taken, '2024-07-14 10:30')
        self.assertEqual(photo.camera, 'Spark TestCam')
        self.assertEqual(photo.format, 'RAW DNG')
        self.assertEqual(photo.needs_decode, raw.libraw() is not None)
        thumb = core.photo_thumbnail(path)
        self.assertEqual(thumb.size, (72, 96))
        self.assertEqual(core.kind_of(path), 'photo')

    def test_any_format_preview(self):
        for ext in ('cr3', 'raf', 'nef', 'arw', 'orf', 'rw2', 'cr2'):
            path = fixtures.raw_like(os.path.join(self.dir, f'x.{ext}'))
            self.assertEqual(core.Photo(path).size, (300, 200), ext)

    def test_not_a_raw(self):
        path = touch(os.path.join(self.dir, 'bad.nef'), b'II*\x00' + b'\x00' * 100)
        with self.assertRaises(core.PhotoError):
            core.Photo(path)

    @unittest.skipUnless(raw.libraw() is not None, "LibRaw is not installed")
    def test_libraw_develops_the_sensor_data(self):
        path = fixtures.make_dng(os.path.join(self.dir, 'IMG_0002.dng'), orientation=6)
        t0 = time.perf_counter()
        image = raw.decode(path)
        print(f"raw: {raw.decoder()} developed a {raw.sensor_size(path)} DNG in "
              f"{time.perf_counter() - t0:.3f} s")
        self.assertIsNotNone(image)
        self.assertEqual(image.mode, 'RGB')
        self.assertEqual(sorted(image.size), [144, 192])
        self.assertEqual(image.size, (144, 192))            # LibRaw turned it upright too
        # the gradient survives: brighter on one side than the other
        left = sum(image.getpixel((5, y))[0] for y in range(10, 180, 10))
        right = sum(image.getpixel((138, y))[0] for y in range(10, 180, 10))
        top = sum(image.getpixel((x, 5))[0] for x in range(10, 140, 10))
        bottom = sum(image.getpixel((x, 185))[0] for x in range(10, 140, 10))
        self.assertGreater(max(abs(left - right), abs(top - bottom)), 200)
        photo = core.Photo(path)
        photo.use_decoded(image)
        self.assertTrue(photo.developed)
        self.assertEqual(photo.size, (144, 192))
        broken = touch(os.path.join(self.dir, 'broken.cr2'), b'garbage' * 100)
        self.assertIsNone(raw.decode(broken))


# ─── Photo edits ──────────────────────────────────────────────

class EditTests(Temp):
    def photo_with_exif(self, name='photo.jpg', size=(400, 300), orientation=1):
        path = os.path.join(self.dir, name)
        image = Image.new('RGB', size, '#406080')
        image.paste((200, 220, 240), (0, 0, size[0] // 2, size[1]))
        exif = image.getexif()
        exif[0x010F] = 'Canon'
        exif[0x0110] = 'Canon EOS R6'
        exif[0x0112] = orientation
        exif[0x0132] = '2023:12:24 18:00:00'
        exif[0x8769] = {0x9003: '2023:12:24 17:59:58', 0x829D: 2.8}
        image.save(path, exif=exif.tobytes(), quality=95)
        return path

    def test_rotate_crop_enhance_save_copy(self):
        path = self.photo_with_exif(orientation=6)          # shown 300 x 400
        photo = core.Photo(path)
        self.assertEqual(photo.size, (300, 400))
        e = edits.Edits()
        e.rotate(photo.size, clockwise=True)                 # 400 x 300
        self.assertEqual(edits.rotated_size(photo.size, e.rotation), (400, 300))
        e.crop = edits.largest_box((400, 300), edits.ratio_for('1:1', (400, 300)))
        self.assertEqual(e.crop, (50, 0, 350, 300))
        e.enhance = True
        result = edits.apply(photo.image, e)
        self.assertEqual(result.size, (300, 300))
        saved = edits.save(result, path, photo.format, photo.exif, photo.icc)
        self.assertEqual(os.path.basename(saved), 'photo (edited).jpg')
        with Image.open(saved) as out:
            self.assertEqual(out.size, (300, 300))
            exif = out.getexif()
            self.assertEqual(exif.get(0x0112), 1)                       # upright already
            self.assertEqual(exif.get(0x0110), 'Canon EOS R6')
            self.assertEqual(exif.get(0x010F), 'Canon')
            self.assertEqual(exif.get_ifd(0x8769).get(0x9003), '2023:12:24 17:59:58')
        again = edits.save(result, path, photo.format, photo.exif, photo.icc)
        self.assertEqual(os.path.basename(again), 'photo (edited 2).jpg')
        # the original is untouched
        self.assertEqual(core.Photo(path).size, (300, 400))

    def test_replace_and_formats(self):
        path = self.photo_with_exif('keep.png')
        before = os.path.getmtime(path)
        photo = core.Photo(path)
        self.assertTrue(edits.can_replace(photo.format, path))
        e = edits.Edits()
        e.rotate(photo.size)
        saved = edits.save(edits.apply(photo.image, e), path, photo.format, photo.exif,
                           replace=True)
        self.assertEqual(saved, path)
        with Image.open(path) as out:
            self.assertEqual((out.format, out.size), ('PNG', (300, 400)))
        self.assertGreaterEqual(os.path.getmtime(path), before)
        # a RAW is never written back: its edit is a JPEG copy, with the camera and date
        dng = fixtures.make_dng(os.path.join(self.dir, 'cam.dng'))
        raw_photo = core.Photo(dng)
        self.assertFalse(edits.can_replace(raw_photo.format, dng))
        with self.assertRaises(ValueError):
            edits.save(raw_photo.image, dng, raw_photo.format, raw_photo.exif, replace=True)
        out = edits.save(raw_photo.image, dng, raw_photo.format, raw_photo.exif)
        self.assertEqual(os.path.basename(out), 'cam (edited).jpg')
        with Image.open(out) as image:
            exif = image.getexif()
            self.assertEqual(exif.get(0x0110), 'Spark TestCam')
            self.assertEqual(exif.get_ifd(0x8769).get(0x9003), '2024:07:14 10:30:00')

    def test_french_file_name(self):
        text.set_language('fr')
        try:
            self.assertEqual(os.path.basename(edits.edited_path(os.path.join(self.dir, 'a.jpg'),
                                                                '.jpg')), 'a (modifié).jpg')
        finally:
            text.set_language('en')

    def test_crop_geometry(self):
        size = (1000, 600)
        self.assertAlmostEqual(edits.ratio_for('4:3', (600, 1000)), 3 / 4)   # turns with the photo
        self.assertEqual(edits.ratio_for('original', size), 1000 / 600)
        self.assertEqual(edits.ratio_for('free', size), 0)
        box = (100, 100, 500, 400)
        for handle in ('se', 'nw', 'n', 'e', 'move'):
            for dx, dy in ((80, 40), (-300, -500), (900, 900)):
                for ratio in (0, 16 / 9, 1.0):
                    got = edits.drag_box(box, handle, dx, dy, ratio, size)
                    x0, y0, x1, y1 = got
                    self.assertTrue(0 <= x0 < x1 <= 1000 and 0 <= y0 < y1 <= 600, (handle, got))
                    if ratio and handle != 'move':
                        self.assertAlmostEqual((x1 - x0) / (y1 - y0), ratio, delta=0.05,
                                               msg=(handle, dx, dy, got))
        moved = edits.drag_box(box, 'move', 5000, 5000, 0, size)
        self.assertEqual(moved, (600, 300, 1000, 600))
        # four quarter turns bring the crop back where it was
        e = edits.Edits()
        e.crop = (10, 20, 110, 70)
        for _ in range(4):
            e.rotate((400, 300))
        self.assertEqual((e.rotation, e.crop), (0, (10, 20, 110, 70)))
        e.rotate((400, 300), clockwise=False)
        e.rotate((400, 300), clockwise=True)
        self.assertEqual(e.crop, (10, 20, 110, 70))

    def test_enhance_stretches_tones(self):
        flat = Image.new('RGB', (64, 64), (100, 110, 120))
        flat.paste((140, 150, 160), (0, 0, 32, 64))
        out = edits.enhance(flat)
        lo, hi = out.convert('L').getextrema()
        self.assertLess(lo, 30)
        self.assertGreater(hi, 220)


# ─── File types ───────────────────────────────────────────────

GLOBS = '/usr/share/mime/globs2'


@unittest.skipUnless(os.path.isfile(GLOBS), "no shared-mime-info here")
class MimeTests(unittest.TestCase):
    def test_desktop_entry_claims_raw_and_playlists(self):
        """What the system calls each new extension is in the desktop entry's MimeType, so
        double-clicking opens Spark Media once it's the default."""
        best = {}
        with open(GLOBS, encoding='utf-8') as f:
            for line in f:
                if line.startswith('#'):
                    continue
                parts = line.strip().split(':')
                if len(parts) < 3 or not parts[2].startswith('*.'):
                    continue
                weight, mime, ext = int(parts[0]), parts[1], parts[2][2:].lower()
                if ext not in best or weight > best[ext][0]:
                    best[ext] = (weight, [mime])
                elif weight == best[ext][0] and mime not in best[ext][1]:
                    best[ext][1].append(mime)
        desktop = os.path.join(os.path.dirname(HERE), 'dev.wolklaw.SparkMedia.desktop')
        with open(desktop, encoding='utf-8') as f:
            claimed = set(re.search(r'^MimeType=(.*)$', f.read(), re.M).group(1).split(';'))
        missing = []
        for ext in sorted(raw.RAW_EXT | {'m3u', 'm3u8'}):
            if ext not in best:
                continue
            print(f"mime: *.{ext} -> {', '.join(best[ext][1])}")
            missing += [f'{ext}: {m}' for m in best[ext][1] if m not in claimed]
        self.assertEqual(missing, [])


# ─── Windows ──────────────────────────────────────────────────

def have_display() -> bool:
    return os.name == 'nt' or bool(os.environ.get('DISPLAY'))


@unittest.skipUnless(have_display(), "needs a display")
class UITests(Temp):
    def setUp(self):
        super().setUp()
        self.home = os.path.join(self.dir, 'home')
        self.music = os.path.join(self.home, 'Music')
        os.makedirs(self.music)
        self.saved_env = {k: os.environ.get(k) for k in ('HOME', 'USERPROFILE', 'XDG_CACHE_HOME',
                                                         'XDG_CONFIG_HOME')}
        os.environ['HOME'] = os.environ['USERPROFILE'] = self.home
        os.environ['XDG_CACHE_HOME'] = os.path.join(self.dir, 'cache')
        os.environ['XDG_CONFIG_HOME'] = os.path.join(self.dir, 'config')
        self.app = None

    def tearDown(self):
        if self.app is not None:
            try:
                self.app._on_close()
            except Exception:      # noqa: BLE001
                pass
        for k, v in self.saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        text.set_language('en')
        super().tearDown()

    def pump(self, seconds=0.4, until=None):
        end = time.time() + seconds
        while time.time() < end:
            self.app.root.update()
            if until is not None and until():
                return True
            time.sleep(0.02)
        return until() if until else True

    def songs(self, names=(('Alpha', 'First', 'One'), ('Alpha', 'First', 'Two'),
                           ('Beta', 'Second', 'Three'))):
        made = []
        for n, (artist, album, title) in enumerate(names):
            path = os.path.join(self.music, artist, album, f'{n + 1:02d} {title}.flac')
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if not gst.available() or not fixtures.encode(gst, path, 3.0):
                raise unittest.SkipTest("needs GStreamer with a FLAC encoder")
            fixtures.flac_tags(path, {'TITLE': title, 'ARTIST': artist, 'ALBUM': album,
                                      'TRACKNUMBER': str(n + 1)})
            made.append(path)
        return made

    def test_music_library_play_queue_playlist(self):
        from sparkmedia.app import App
        from sparkmedia.musicview import MusicView
        from sparkmedia.playview import MusicPlayerView
        songs = self.songs()
        self.app = App([], 'music')
        app = self.app
        self.assertIsInstance(app.view, MusicView)
        self.assertTrue(self.pump(20, until=lambda: not app.scanning()))
        self.pump(0.3)
        view = app.view
        self.assertEqual(len(app.library().songs), 3)
        view._tab('albums')
        self.assertEqual(view.list.count, 2)
        view._tab('artists')
        self.assertEqual([a['name'] for a in view.items], ['Alpha', 'Beta'])
        view.list.on_activate(0)                          # Alpha
        self.assertEqual(view.page, ('artist', 'Alpha'))
        view.list.on_activate(0)                          # First
        self.assertEqual(view.page[0], 'album')
        self.assertEqual(view.list.rows[0][1], 'One')
        view._play([s['path'] for s in view.items])
        self.pump(1.0)
        session = app.music
        self.assertEqual(session.current, songs[0])
        self.assertTrue(view.now_bar.winfo_ismapped())
        self.assertEqual(view.list.marks[0], 'current')
        view._queue([songs[2]])
        self.assertEqual([session.queue.items[i] for i in session.queue.order],
                         [songs[0], songs[1], songs[2]])
        self.assertTrue(view.back())
        self.assertTrue(view.back())
        self.assertFalse(view.back())
        # filter
        view._tab('songs')
        view.filter_var.set('thr')
        view._apply_filter()
        self.assertEqual([s['title'] for s in view.items], ['Three'])
        # save the queue as a playlist, see it in Playlists, open it
        path = app.save_as_playlist(session.queue.items, name='Road trip')
        self.assertEqual(path, os.path.join(self.music, 'Playlists', 'Road trip.m3u8'))
        with open(path, encoding='utf-8') as f:
            self.assertIn('../Alpha/First/01 One.flac', f.read())
        view._tab('playlists')
        self.assertEqual(view.items, [path])
        view.list.on_activate(0)
        self.assertEqual(len(view.items), 3)
        view._remove_from_playlist(1)
        self.assertEqual(len(view.items), 2)
        # music keeps playing in the full player, and after going back
        app.show_now_playing()
        self.assertIsInstance(app.view, MusicPlayerView)
        self.pump(0.5)
        self.assertEqual(app.view.queue_list.size(), 3)
        app.go_back()
        self.assertIsInstance(app.view, MusicView)
        self.assertIs(app.music, session)
        self.assertEqual(session.current, songs[0])

    def test_open_playlist_file(self):
        from sparkmedia.app import App
        from sparkmedia.playview import MusicPlayerView
        songs = self.songs()
        pl = os.path.join(self.dir, 'list.m3u')
        playlists.write(pl, [songs[2], songs[0]])
        self.app = App([pl])
        self.pump(0.8)
        self.assertIsInstance(self.app.view, MusicPlayerView)
        self.assertEqual(self.app.music.queue.items, [songs[2], songs[0]])

    def test_photo_edit_and_raw(self):
        from sparkmedia.app import App
        from sparkmedia.viewer import PhotoView
        pics = os.path.join(self.home, 'Pictures')
        os.makedirs(pics)
        photo = os.path.join(pics, 'a.jpg')
        Image.new('RGB', (800, 600), '#3de8c8').save(photo)
        dng = fixtures.make_dng(os.path.join(pics, 'b.dng'), orientation=6)
        self.app = App([photo])
        self.pump(0.6)
        view = self.app.view
        self.assertIsInstance(view, PhotoView)
        view.start_edit()
        self.pump(0.3)
        self.assertTrue(view.editing)
        self.assertFalse(view.save_button.enabled)
        view.set_ratio('1:1')
        self.assertEqual(view.edits.crop, (100, 0, 700, 600))
        view.edit_rotate(True)
        view.set_enhance(True)
        self.pump(0.3)
        # drag the crop's corner on screen
        x0, y0 = view._to_view(view.edits.crop[0], view.edits.crop[1])
        view._crop_press(type('E', (), {'x': x0, 'y': y0})())
        view._crop_move(type('E', (), {'x': x0 + 40, 'y': y0 + 40})())
        view._end_drag()
        x0, y0, x1, y1 = view.edits.crop
        self.assertAlmostEqual(x1 - x0, y1 - y0, delta=1)    # still square
        self.assertLess(x1 - x0, 600)
        view.save_edit(False)
        self.pump(0.4)
        saved = os.path.join(pics, 'a (edited).jpg')
        self.assertTrue(os.path.isfile(saved))
        self.assertFalse(view.editing)
        self.assertEqual(view.files[view.index], saved)
        with Image.open(saved) as image:
            self.assertAlmostEqual(image.size[0], image.size[1], delta=1)
        # Esc leaves edit mode without saving
        view.start_edit()
        view.edit_rotate(True)
        self.app.go_back()
        self.assertFalse(view.editing)
        self.assertIsInstance(self.app.view, PhotoView)
        # the RAW opens on its preview, upright, and develops when LibRaw is there
        view.show(view.files.index(dng))
        self.assertTrue(view.photo.raw)
        self.assertEqual(view.photo.size, (72, 96))         # the preview, at once
        if raw.libraw() is not None:
            self.assertTrue(self.pump(10, until=lambda: view.photo.developed))
            self.assertEqual(view.photo.size, (144, 192))

    def test_french_window(self):
        from sparkmedia.app import App
        text.set_language('fr')
        self.app = App([], 'music')
        self.pump(0.3)
        labels = [label.cget('text') for label in self.app.view.tabs.labels.values()]
        self.assertEqual(labels, ['ARTISTES', 'ALBUMS', 'CHANSONS', 'LISTES'])
        self.assertEqual(self.app.status.cget('text'), '● PRÊT')


if __name__ == '__main__':
    unittest.main()
