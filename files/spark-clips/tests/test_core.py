"""The parts that need no GStreamer and no display: the buffer rules, settings, the control
socket, the clip library, the pipeline's choices and the transport-stream counter fix."""

import json
import os
import time
import unittest

import testenv
from sparkclips import buffer, clipfile, core, ipc, library, pipeline
from sparkclips.buffer import Piece


def pieces(numbers, now=1000.0, size=1000):
    """Pieces numbered as given, one per second, the last one written at `now`."""
    return [Piece(n, f'/x/piece-{n:08d}.ts', now - (len(numbers) - 1 - i), size)
            for i, n in enumerate(numbers)]


class Buffer(unittest.TestCase):
    def test_prune_keeps_the_length_plus_a_margin_and_the_newest(self):
        held = pieces(range(100, 160))                  # 60 pieces, 59 s old at most
        old = buffer.to_prune(held, 30, 1000.0)
        self.assertTrue(old)
        self.assertTrue(all(p.mtime < 1000.0 - 30 - buffer.MARGIN for p in old))
        self.assertNotIn(held[-1], old)
        self.assertEqual(buffer.to_prune([], 30, 1000.0), [])
        lone = pieces([5], now=1.0)
        self.assertEqual(buffer.to_prune(lone, 30, 5000.0), [])     # never the open one

    def test_prune_removes_files(self):
        testenv.reset()
        folder = core.buffer_dir()
        now = time.time()
        for i in range(10):
            path = os.path.join(folder, buffer.PATTERN % i)
            with open(path, 'wb') as f:
                f.write(b'x' * 10)
            os.utime(path, (now - 100 + i, now - 100 + i))
        self.assertEqual(buffer.prune(folder, 15, now), 9)
        self.assertEqual([p.number for p in buffer.list_pieces(folder)], [9])
        buffer.clear(folder)
        self.assertEqual(buffer.list_pieces(folder), [])

    def test_cover_counts_the_newest_and_stops_at_a_gap(self):
        held = pieces(range(1, 41))
        chosen = buffer.cover(held, 30)
        self.assertEqual(len(chosen), 30)
        self.assertEqual(chosen[-1].number, 40)
        self.assertEqual(buffer.cover(held, 15)[0].number, 26)
        broken = pieces([1, 2, 3, 10, 11, 12])
        self.assertEqual([p.number for p in buffer.cover(broken, 30)], [10, 11, 12])
        self.assertEqual(buffer.seconds_held(broken), 3.0)
        self.assertEqual(buffer.cover([], 30), [])
        self.assertEqual(buffer.seconds_held([]), 0.0)

    def test_estimate_and_the_quarter_rule(self):
        small = buffer.estimate_bytes(30, 40)
        big = buffer.estimate_bytes(300, 40)
        self.assertGreater(big, small * 5)
        self.assertGreater(small, 30 * 40_000_000 // 8)          # at least the video itself
        self.assertFalse(buffer.too_big(small, 8_000_000_000))
        self.assertTrue(buffer.too_big(big, 4_000_000_000))
        self.assertFalse(buffer.too_big(big, None))
        self.assertEqual(buffer.used_bytes(pieces([1, 2, 3])), 3000)


class Settings(unittest.TestCase):
    def setUp(self):
        testenv.reset()

    def test_defaults_are_the_briefs(self):
        s = core.load_settings()
        self.assertEqual((s['seconds'], s['keep'], s['only_in_game'], s['sound'], s['mic'],
                          s['codec']), (30, True, True, True, False, 'h264'))

    def test_round_trip_and_bad_values(self):
        core.save_settings(dict(core.DEFAULTS, seconds=120, mic=True, codec='hevc'))
        s = core.load_settings()
        self.assertEqual((s['seconds'], s['mic'], s['codec']), (120, True, 'hevc'))
        with open(core.settings_path(), 'w') as f:
            json.dump({'seconds': 7, 'codec': 'av1', 'mic': 'yes', 'keep': 1, 'bitrate': 40.5}, f)
        s = core.load_settings()
        self.assertEqual((s['seconds'], s['codec'], s['mic'], s['keep']), (30, 'h264', False, True))
        with open(core.settings_path(), 'w') as f:
            f.write('not json')
        self.assertEqual(core.load_settings(), core.DEFAULTS)

    def test_the_portal_token_is_private(self):
        core.save_portal({'restore_token': 'abc'})
        self.assertEqual(core.load_portal()['restore_token'], 'abc')
        self.assertEqual(os.stat(core.portal_path()).st_mode & 0o777, 0o600)

    def test_names_are_made_safe(self):
        self.assertEqual(core.clean_name('../../etc/passwd'), 'etc passwd')
        self.assertEqual(core.clean_name('Half-Life: Alyx?'), 'Half-Life Alyx')
        self.assertEqual(core.clean_name('...'), '')
        folder = os.path.join(core.home(), 'x')
        first = core.unique_path(folder, 'Clip', '.mp4')
        open(first, 'w').close()
        self.assertTrue(core.unique_path(folder, 'Clip', '.mp4').endswith('Clip 2.mp4'))

    def test_numbers_for_people(self):
        self.assertEqual(core.duration_text(65), '1:05')
        self.assertIn('MB', core.human_size(5_000_000))


class Socket(unittest.TestCase):
    def test_a_command_gets_an_answer(self):
        testenv.reset()
        path = os.path.join(core.runtime_dir(), 'test.sock')
        seen = []

        def handler(command, args):
            seen.append((command, args))
            if command == 'boom':
                raise RuntimeError('boom')
            return {'ok': True, 'echo': args.get('x')}
        server = ipc.Server(handler, path)
        server.start()
        try:
            self.assertEqual(ipc.ask('save', path=path, x=3), {'ok': True, 'echo': 3})
            self.assertEqual(seen, [('save', {'x': 3})])
            self.assertFalse(ipc.ask('boom', path=path)['ok'])
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        finally:
            server.stop()
        self.assertIsNone(ipc.ask('save', path=path, timeout=1))         # nobody listens now


class Library(unittest.TestCase):
    def setUp(self):
        testenv.reset()

    def test_lists_games_newest_first_and_skips_the_unfinished(self):
        root = core.clips_dir()
        files = {'Hades/Hades 1.mp4': 100, 'Hades/Hades 2.mp4': 300, 'Portal/p.mkv': 200,
                 'loose.mp4': 50, 'Hades/.hidden.mp4': 400, 'Hades/half.mp4.part': 500,
                 'Hades/notes.txt': 600}
        for rel, when in files.items():
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as f:
                f.write(b'12345')
            os.utime(path, (when, when))
        clips = library.list_clips(root)
        self.assertEqual([c.name for c in clips], ['Hades 2', 'p', 'Hades 1', 'loose'])
        self.assertEqual(clips[0].game, 'Hades')
        self.assertEqual(clips[-1].game, 'Clips')
        self.assertEqual(library.list_clips(os.path.join(root, 'missing')), [])

    def test_thumbnail_keys_change_with_the_file(self):
        a = library.Clip('/x/a.mp4', 'g', 'a', 1.0, 10)
        b = library.Clip('/x/a.mp4', 'g', 'a', 2.0, 10)
        self.assertNotEqual(library.thumb_path(a), library.thumb_path(b))
        self.assertEqual(library.thumb_path(a), library.thumb_path(a))
        os.makedirs(library.thumb_dir(), exist_ok=True)
        stale = os.path.join(library.thumb_dir(), 'old.jpg')
        open(stale, 'w').close()
        self.assertEqual(library.prune_thumbs([a]), 1)
        self.assertFalse(os.path.exists(stale))

    def test_trimmed_names_and_uris(self):
        folder = core.clips_dir()
        os.makedirs(folder, exist_ok=True)
        self.assertEqual(os.path.basename(library.trimmed_name(folder, 'A b')), 'A b trimmed.mp4')
        open(os.path.join(folder, 'A b trimmed.mp4'), 'w').close()
        self.assertEqual(os.path.basename(library.trimmed_name(folder, 'A b')),
                         'A b trimmed 2.mp4')
        self.assertEqual(library.path_to_uri('/a b/c#d.mp4'), 'file:///a%20b/c%23d.mp4')


class Pipeline(unittest.TestCase):
    def test_encoder_order_and_no_av1(self):
        everything = lambda _e: True                            # noqa: E731
        enc = pipeline.pick_encoder('h264', everything)
        self.assertTrue(enc.gpu)
        self.assertIsNone(pipeline.pick_encoder('av1', everything))
        no_gpu = lambda e: e != 'vapostproc'                    # noqa: E731
        self.assertFalse(pipeline.pick_encoder('h264', no_gpu).gpu)
        nothing = lambda _e: False                              # noqa: E731
        self.assertIsNone(pipeline.pick_encoder('h264', nothing))
        self.assertIsNone(pipeline.pick_encoder('hevc', nothing))

    def test_hevc_does_not_fall_back_to_h264(self):
        h264_only = lambda e: 'h265' not in e and 'hevc' not in e   # noqa: E731
        self.assertIsNone(pipeline.pick_encoder('hevc', h264_only))

    def test_sizes_rates_and_bitrate(self):
        self.assertEqual(pipeline.scaled_size(2560, 1440, 'native'), (2560, 1440))
        self.assertEqual(pipeline.scaled_size(2560, 1440, '1080'), (1920, 1080))
        self.assertEqual(pipeline.scaled_size(1280, 720, '1080'), (1280, 720))   # never larger
        self.assertEqual(pipeline.scaled_size(1921, 1081, 'native'), (1920, 1080))
        self.assertEqual(pipeline.fps_value('60'), 60)
        self.assertIsNone(pipeline.fps_value('native'))
        low = pipeline.bitrate_kbps(40, 1280, 720, 30)
        high = pipeline.bitrate_kbps(40, 2560, 1440, 60)
        self.assertLess(low, high)
        self.assertLessEqual(high, 40_000)

    def test_audio_tracks_follow_the_settings(self):
        self.assertEqual(len(pipeline.audio_sources(True, False)), 1)
        self.assertEqual(len(pipeline.audio_sources(True, True)), 2)
        self.assertEqual(pipeline.audio_sources(False, False), [])

    def test_the_arguments_hold_a_one_second_split_and_no_shell(self):
        enc = pipeline.pick_encoder('h264', lambda e: e != 'vapostproc')
        args = pipeline.build(core.DEFAULTS, enc, pipeline.fake_source(core.DEFAULTS), 640, 360,
                              pipeline.pick_audio_encoder(lambda _e: True), '/dev/shm/x')
        joined = ' '.join(args)
        self.assertIn('splitmuxsink', joined)
        self.assertIn('max-size-time=1000000000', joined)
        self.assertIn('location=/dev/shm/x/piece-%08d.ts', joined)
        self.assertNotIn('av1', joined.lower())


def ts_packet(pid, cc, payload=True):
    head = bytes([0x47, (pid >> 8) & 0x1F, pid & 0xFF, (0x10 if payload else 0x20) | cc])
    return head + bytes(184)


class Counters(unittest.TestCase):
    def counters(self, data, pid):
        return [data[i + 3] & 0x0F for i in range(0, len(data), 188)
                if ((data[i + 1] & 0x1F) << 8 | data[i + 2]) == pid]

    def test_pieces_from_separate_muxers_are_made_continuous(self):
        first = bytearray(b''.join(ts_packet(256, c) for c in (5, 6, 7)))
        second = bytearray(b''.join(ts_packet(256, c) for c in (0, 1, 2, 3)))   # starts over
        last = {}
        clipfile._renumber(first, last)
        clipfile._renumber(second, last)
        self.assertEqual(self.counters(first, 256), [5, 6, 7])
        self.assertEqual(self.counters(second, 256), [8, 9, 10, 11])

    def test_wraps_at_sixteen_and_keeps_pids_apart(self):
        first = bytearray(b''.join(ts_packet(256, c) + ts_packet(257, c) for c in (14, 15)))
        second = bytearray(b''.join(ts_packet(256, 0) + ts_packet(257, 3) for _ in range(1)))
        last = {}
        clipfile._renumber(first, last)
        clipfile._renumber(second, last)
        self.assertEqual(self.counters(second, 256), [0])
        self.assertEqual(self.counters(second, 257), [0])

    def test_null_packets_and_junk_are_left_alone(self):
        data = bytearray(ts_packet(0x1FFF, 9) + bytes(188))
        before = bytes(data)
        clipfile._renumber(data, {})
        self.assertEqual(bytes(data), before)


if __name__ == '__main__':
    unittest.main()
