"""Spark Snip tests. Plain unittest:

    python -m unittest discover -s files/spark-snip/tests -v

Logic tests run anywhere. OCR tests need Tesseract (they skip without it). UI tests need a
display (on CI: xvfb-run) and open real windows for a few seconds.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault('XDG_STATE_HOME', tempfile.mkdtemp(prefix='spark-snip-state-'))
os.environ.setdefault('XDG_CONFIG_HOME', tempfile.mkdtemp(prefix='spark-snip-config-'))

from PIL import Image  # noqa: E402

from sparksnip import capture, core, recorder  # noqa: E402
from sparksnip.core import Monitor  # noqa: E402
from sparksnip.lang import local_units  # noqa: E402
from sparksnip.text import t  # noqa: E402

XRANDR = """Monitors: 2
 0: +*DP-1 2560/597x1440/336+0+0  DP-1
 1: +HDMI-A-1 1920/527x1080/296+2560+180  HDMI-A-1
"""


class LogicTests(unittest.TestCase):
    def test_parse_tsv_groups_lines_and_averages_confidence(self):
        tsv = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
               "5\t1\t1\t1\t1\t1\t0\t0\t1\t1\t90\tHello\n"
               "5\t1\t1\t1\t1\t2\t0\t0\t1\t1\t80\tworld\n"
               "5\t1\t1\t1\t2\t1\t0\t0\t1\t1\t-1\t \n"
               "5\t1\t1\t1\t2\t2\t0\t0\t1\t1\t70\tagain\n")
        text, conf = core.parse_tsv(tsv)
        self.assertEqual(text, "Hello world\nagain")
        self.assertAlmostEqual(conf, 80.0)

    def test_parse_tsv_empty(self):
        self.assertEqual(core.parse_tsv("header\n"), ('', 0.0))

    def test_parse_monitors(self):
        self.assertEqual(core.parse_monitors(XRANDR),
                         [Monitor('DP-1', 0, 0, 2560, 1440),
                          Monitor('HDMI-A-1', 2560, 180, 1920, 1080)])

    def test_bounding_box_and_mapping(self):
        screens = core.parse_monitors(XRANDR)
        desktop = core.bounding_box(screens)
        self.assertEqual(desktop, (0, 0, 4480, 1440))
        # same size: 1:1
        self.assertEqual(core.screen_to_image((10, 20, 110, 70), desktop, (4480, 1440)),
                         (10, 20, 110, 70))
        # screenshot at twice the X server's size
        self.assertEqual(core.screen_to_image((10, 20, 110, 70), desktop, (8960, 2880)),
                         (20, 40, 220, 140))
        # clamped to the image
        self.assertEqual(core.screen_to_image((-5, -5, 9999, 9999), desktop, (4480, 1440)),
                         (0, 0, 4480, 1440))

    def test_language_labels(self):
        self.assertEqual(core.language_label('eng+fra'), f"{t('ocr.eng')} + {t('ocr.fra')}")
        self.assertEqual(core.language_label('xyz'), "xyz")
        self.assertEqual(core.language_short('eng+fra'), "EN + FR")
        self.assertEqual(core.language_short('xyz'), "XYZ")

    def test_clock_and_size(self):
        self.assertEqual(core.clock(83), "01:23")
        self.assertEqual(core.clock(3723), "1:02:03")
        self.assertEqual(core.human_size(512), local_units("512 B"))
        self.assertEqual(core.human_size(5 * 1024 * 1024), local_units("5.0 MB"))

    def test_capture_order_can_be_forced(self):
        os.environ['SPARK_SNIP_CAPTURE'] = 'grim'
        try:
            self.assertEqual(core.capture_order(), ['grim'])
        finally:
            del os.environ['SPARK_SNIP_CAPTURE']

    def test_crop_is_even_and_inside_the_monitor(self):
        mon = Monitor('HDMI-A-1', 2560, 180, 1920, 1080)
        crop = recorder.crop_for((2600, 200, 2901, 351), mon)
        self.assertEqual((crop.left, crop.top, crop.width, crop.height), (40, 20, 300, 150))
        self.assertEqual(crop.right, 1920 - 40 - 300)
        self.assertEqual(crop.bottom, 1080 - 20 - 150)
        whole = recorder.crop_for(mon.box, mon)
        self.assertEqual((whole.left, whole.top, whole.right, whole.bottom), (0, 0, 0, 0))

    def test_pipeline_with_audio(self):
        crop = recorder.Crop(1920, 1080, 40, 20, 300, 150)
        enc = recorder.ENCODERS[1]
        tokens = recorder.build_pipeline(['videotestsrc'], crop, enc,
                                         [['pulsesrc'], ['pulsesrc', 'device=x.monitor']],
                                         '/tmp/out.mp4')
        line = ' '.join(tokens)
        self.assertIn('video/x-raw,width=1920,height=1080', line)
        self.assertIn('videocrop left=40 top=20 right=1580 bottom=910', line)
        self.assertIn('x264enc', line)
        self.assertIn('h264parse ! queue ! mux.', line)
        self.assertEqual(line.count('! amix.'), 2)
        self.assertIn('opusenc bitrate=128000 ! queue ! mux.', line)
        self.assertTrue(line.endswith(
            'mp4mux name=mux fragment-duration=1000 ! filesink location=/tmp/out.mp4'))
        aac = ' '.join(recorder.build_pipeline(['videotestsrc'], crop, enc, [['pulsesrc']],
                                               '/tmp/out.mp4', ('fdkaacenc', 'bitrate=192000')))
        self.assertIn('fdkaacenc bitrate=192000 ! queue ! mux.', aac)

    def test_has_video_reads_mp4_boxes(self):
        import struct
        import tempfile

        def box(kind, body=b''):
            return struct.pack('>I4s', 8 + len(body), kind) + body
        with tempfile.TemporaryDirectory() as folder:
            def write(name, data):
                path = os.path.join(folder, name)
                with open(path, 'wb') as fh:
                    fh.write(data)
                return path
            # killed before any index: what used to be left behind, unplayable
            cut = write('cut.mp4', box(b'ftyp', b'isom') + box(b'free') + box(b'mdat', b'x' * 64))
            self.assertEqual(recorder.mp4_boxes(cut), ['ftyp', 'free', 'mdat'])
            self.assertFalse(recorder.has_video(cut))
            frag = write('frag.mp4', box(b'ftyp', b'isom') + box(b'moov') + box(b'moof')
                         + box(b'mdat', b'x' * 64))
            self.assertTrue(recorder.has_video(frag))
            plain = write('plain.mp4', box(b'ftyp', b'isom') + box(b'moov') + box(b'mdat', b'x'))
            self.assertTrue(recorder.has_video(plain))
            self.assertFalse(recorder.has_video(write('empty.mp4', b'')))
            self.assertFalse(recorder.has_video(os.path.join(folder, 'missing.mp4')))
            self.assertTrue(recorder.has_video(write('a.webm', b'\x1aE\xdf\xa3')))

    def test_pipeline_without_audio_or_parser(self):
        crop = recorder.Crop(640, 360, 0, 0, 640, 360)
        line = ' '.join(recorder.build_pipeline(['videotestsrc'], crop, recorder.ENCODERS[-1],
                                                [], 'out.webm'))
        self.assertNotIn('amix', line)
        self.assertNotIn('h264parse', line)
        self.assertIn('webmmux name=mux', line)

    def test_stream_matches(self):
        mon = Monitor('HDMI-A-1', 2560, 180, 1920, 1080)
        self.assertTrue(recorder.stream_matches(mon, {}))
        self.assertTrue(recorder.stream_matches(mon, {'position': (2560, 180),
                                                      'size': (1920, 1080)}))
        # an output scaled to 150%: the portal speaks logical pixels
        self.assertTrue(recorder.stream_matches(Monitor('DP-1', 2880, 0, 2880, 1620),
                                                {'position': (1920, 0), 'size': (1920, 1080)}))
        self.assertFalse(recorder.stream_matches(mon, {'position': (0, 0), 'size': (2560, 1440)}))

    def test_config_round_trip(self):
        core.save_config({'lang': 'fra', 'mode': 'video'})
        self.assertEqual(core.load_config()['mode'], 'video')


class RecorderPidTests(unittest.TestCase):
    """Meta+Shift+R while recording sends SIGUSR1 to the recording Spark Snip. A pid file left
    by a crash must never send it to whatever program has that PID now (SIGUSR1 ends it)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proc = os.path.join(self.tmp, 'proc')
        self.pidfile = os.path.join(self.tmp, 'rec.pid')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def process(self, pid, start, cmdline):
        folder = os.path.join(self.proc, str(pid))
        os.makedirs(folder, exist_ok=True)
        fields = ['S'] + ['0'] * 18 + [str(start)] + ['0'] * 10
        with open(os.path.join(folder, 'stat'), 'w') as f:
            f.write(f"{pid} (python3) " + ' '.join(fields) + '\n')
        with open(os.path.join(folder, 'cmdline'), 'wb') as f:
            f.write(bytes(1).join(cmdline) + bytes(1))

    def write(self, text):
        with open(self.pidfile, 'w') as f:
            f.write(text)

    def test_only_the_recording_spark_snip(self):
        self.process(4242, 9000, [b'/usr/bin/python3', b'/usr/lib/spark-snip/spark_snip.py'])
        self.write(recorder.pid_file_text(4242, self.proc))
        self.assertEqual(recorder.running_recorder(self.pidfile, self.proc), 4242)
        # the PID now belongs to a game that started later: not ours
        self.process(4242, 12345, [rb'C:\Games\game.exe'])
        self.assertIsNone(recorder.running_recorder(self.pidfile, self.proc))
        # an old file with only a PID (or another program with the same start): never
        self.write('4242')
        self.assertIsNone(recorder.running_recorder(self.pidfile, self.proc))
        self.process(4242, 9000, [b'/usr/bin/steam'])
        self.write('4242 9000')
        self.assertIsNone(recorder.running_recorder(self.pidfile, self.proc))
        os.remove(self.pidfile)
        self.assertIsNone(recorder.running_recorder(self.pidfile, self.proc))


class CaptureLogicTests(unittest.TestCase):
    """Reading the screen in the Spark session: capture order and desktop entry."""

    @unittest.skipIf(os.name == 'nt', "Windows always uses Pillow")
    def test_spark_session_reads_with_grim_then_the_portal(self):
        orders = capture.orders_by_desktop()
        self.assertEqual(orders['spark'], ['grim', 'portal'])
        self.assertEqual(orders['wlroots'], ['grim', 'portal'])
        self.assertEqual(orders['gnome'], ['gnome-screenshot', 'portal'])
        self.assertEqual(orders['x11'], ['pil', 'portal'])

    @unittest.skipIf(os.name == 'nt', "Windows always uses Pillow")
    def test_unnamed_wayland_desktop_uses_grim(self):
        env = {'XDG_SESSION_TYPE': 'wayland', 'WAYLAND_DISPLAY': 'wayland-0',
               'XDG_CURRENT_DESKTOP': ''}
        with mock.patch.dict(os.environ, env):
            os.environ.pop('SPARK_SNIP_CAPTURE', None)
            self.assertEqual(core.capture_order(), ['grim', 'portal'])

    def test_no_other_screenshot_tool_is_known(self):
        self.assertEqual(set(core.CAPTURE_TOOLS), {'grim', 'gnome-screenshot'})
        self.assertEqual(core.BUILT_IN_CAPTURE, ('portal', 'pil'))

    def test_unknown_capture_method_is_refused(self):
        with mock.patch.dict(os.environ, {'SPARK_SNIP_CAPTURE': 'nosuchtool'}):
            with self.assertRaises(core.CaptureError) as caught:
                core.grab_screen()
        self.assertIn("not a capture method", str(caught.exception))

    def test_grim_runs_and_is_returned(self):
        def fake_run(cmd, **_kw):
            Image.new('RGB', (40, 30), (9, 8, 7)).save(cmd[-1], 'PPM')
            return subprocess.CompletedProcess(cmd, 0, b'', b'')
        with mock.patch.dict(os.environ, {'SPARK_SNIP_CAPTURE': 'grim'}), \
                mock.patch.object(core.shutil, 'which', return_value='/usr/bin/grim'), \
                mock.patch.object(core.subprocess, 'run', fake_run), \
                mock.patch.object(core, 'close_spark_menu'):
            shot, tool = core.grab_screen()
        self.assertEqual(tool, 'grim')
        self.assertEqual(shot.size, (40, 30))
        self.assertEqual(shot.getpixel((0, 0)), (9, 8, 7))

    def test_grim_failure_is_reported_with_its_reason(self):
        def fake_run(cmd, **_kw):
            return subprocess.CompletedProcess(cmd, 1, b'', b'compositor doesn\'t support screencopy\n')
        with mock.patch.dict(os.environ, {'SPARK_SNIP_CAPTURE': 'grim'}), \
                mock.patch.object(core.shutil, 'which', return_value='/usr/bin/grim'), \
                mock.patch.object(core.subprocess, 'run', fake_run), \
                mock.patch.object(core, 'close_spark_menu'):
            with self.assertRaises(core.CaptureError) as caught:
                core.grab_screen()
        self.assertIn("grim: compositor doesn't support screencopy", str(caught.exception))

    def test_missing_grim_is_reported(self):
        with mock.patch.dict(os.environ, {'SPARK_SNIP_CAPTURE': 'grim'}), \
                mock.patch.object(core.shutil, 'which', return_value=None), \
                mock.patch.object(core, 'close_spark_menu'):
            with self.assertRaises(core.CaptureError) as caught:
                core.grab_screen()
        self.assertIn("grim: not installed", str(caught.exception))

    def test_desktop_entry_has_the_actions_and_no_shortcut_keys(self):
        path = os.path.join(os.path.dirname(HERE), capture.DESKTOP_FILE)
        report = capture.check_desktop_entry(path)
        self.assertTrue(report['passed'], report)
        self.assertEqual(report['actions'], capture.ACTIONS)
        self.assertFalse(report['has_shortcut_keys'])

    def test_self_check_passes(self):
        # look only at the source's desktop entry, not at a copy installed on this machine
        empty = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {'XDG_DATA_HOME': empty, 'XDG_DATA_DIRS': empty}):
            report = capture.self_check()
        self.assertTrue(report['spark_uses_grim'], report)
        self.assertTrue(report['desktop_entries'])
        self.assertTrue(report['passed'], report)

    def test_capture_test_with_grim(self):
        import json
        out = os.path.join(tempfile.mkdtemp(), 'snip.png')

        def fake_run(cmd, **_kw):
            img = Image.new('RGB', (50, 40), (0, 0, 0))
            img.putpixel((3, 3), (255, 255, 255))
            img.save(cmd[-1], 'PPM')
            return subprocess.CompletedProcess(cmd, 0, b'', b'')
        with mock.patch.object(core.shutil, 'which', return_value='/usr/bin/grim'), \
                mock.patch.object(core.subprocess, 'run', fake_run):
            report = capture.capture_test(out)
        json.dumps(report)
        self.assertTrue(report['passed'], report)
        self.assertEqual(report['size'], [50, 40])
        with Image.open(out) as image:
            self.assertEqual(image.size, (50, 40))

    def test_capture_test_fails_on_a_blank_picture_and_without_grim(self):
        out = os.path.join(tempfile.mkdtemp(), 'snip.png')

        def blank_run(cmd, **_kw):
            Image.new('RGB', (50, 40)).save(cmd[-1], 'PPM')
            return subprocess.CompletedProcess(cmd, 0, b'', b'')
        with mock.patch.object(core.shutil, 'which', return_value='/usr/bin/grim'), \
                mock.patch.object(core.subprocess, 'run', blank_run):
            report = capture.capture_test(out)
        self.assertFalse(report['passed'])
        self.assertTrue(report['single_colour'])
        with mock.patch.object(capture.shutil, 'which', return_value=None):
            report = capture.capture_test(out)
        self.assertFalse(report['passed'])
        self.assertIn("not installed", report['error'])

    def test_install_script_has_no_desktop_environment_steps(self):
        with open(os.path.join(os.path.dirname(HERE), 'install.sh'), encoding='utf-8') as f:
            text = f.read().lower()
        for word in ('kglobalaccel', 'spectacle', 'kwin'):
            self.assertNotIn(word, text)


DBUS_CONFIG = """<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <type>session</type>
  <listen>unix:tmpdir={tmp}</listen>
  <auth>EXTERNAL</auth>
  <policy context="default">
    <allow send_destination="*" eavesdrop="true"/>
    <allow eavesdrop="true"/>
    <allow own="*"/>
  </policy>
</busconfig>
"""
NEEDS_DBUS = ("needs PyGObject and dbus-daemon; CI sets SPARK_SNIP_REQUIRE_DBUS_TESTS=1 "
              "so these never skip there")
HAVE_DBUS = capture.gio_ready()[0] and bool(shutil.which('dbus-daemon'))
if os.environ.get('SPARK_SNIP_REQUIRE_DBUS_TESTS') == '1' and not HAVE_DBUS:
    raise RuntimeError(NEEDS_DBUS)


@unittest.skipUnless(HAVE_DBUS, NEEDS_DBUS)
class DBusCaptureTests(unittest.TestCase):
    """The real D-Bus client against a stand-in portal (tests/fake_desktop.py) on a private
    bus: the Screenshot call, and the fallback from grim to the portal."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='spark-snip-dbus-')
        config = os.path.join(cls.tmp, 'bus.conf')
        with open(config, 'w', encoding='utf-8') as f:
            f.write(DBUS_CONFIG.format(tmp=cls.tmp))
        cls.daemon = subprocess.Popen(['dbus-daemon', f'--config-file={config}', '--nofork',
                                       '--nopidfile', '--print-address=1'],
                                      stdout=subprocess.PIPE, text=True)
        cls.address = cls.daemon.stdout.readline().strip()
        if not cls.address:
            cls.daemon.kill()
            raise RuntimeError("dbus-daemon gave no address")
        cls.env = mock.patch.dict(os.environ, {
            'DBUS_SESSION_BUS_ADDRESS': cls.address, 'XDG_SESSION_TYPE': 'wayland',
            'WAYLAND_DISPLAY': 'wayland-test', 'XDG_CURRENT_DESKTOP': 'sparkwl:Spark'})
        cls.env.start()
        os.environ.pop('SPARK_SNIP_CAPTURE', None)

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        cls.daemon.kill()
        cls.daemon.wait(5)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.folder = tempfile.mkdtemp(dir=self.tmp)
        self.fake = None

    def tearDown(self):
        if self.fake:
            self.fake.kill()
            self.fake.wait(5)

    def start_fake(self, *flags):
        self.fake = subprocess.Popen(
            [sys.executable, os.path.join(HERE, 'fake_desktop.py'), self.folder, *flags],
            stdout=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 15
        line = ''
        while time.monotonic() < deadline and 'READY' not in line:
            line = self.fake.stdout.readline()
            if not line and self.fake.poll() is not None:
                break
        self.assertIn('READY', line, "the stand-in desktop did not start")

    def calls(self):
        with open(os.path.join(self.folder, 'calls.txt'), encoding='utf-8') as f:
            return f.read()

    def without_grim(self):
        real = shutil.which
        return mock.patch.object(core.shutil, 'which',
                                 lambda name, *a, **k: None if name == 'grim'
                                 else real(name, *a, **k))

    def test_portal_pixels(self):
        self.start_fake()
        image = capture.portal_screenshot()
        self.assertEqual(image.size, (120, 80))
        self.assertEqual(image.getpixel((0, 0)), (1, 2, 3))
        self.assertIn("portal Screenshot interactive=False", self.calls())

    def test_falls_back_to_the_portal_without_grim(self):
        self.start_fake()
        with self.without_grim(), mock.patch.object(core, 'close_spark_menu'):
            shot, tool = core.grab_screen()
        self.assertEqual(tool, 'portal')
        self.assertEqual(shot.getpixel((0, 0)), (1, 2, 3))

    def test_reports_every_failure_clearly(self):
        self.start_fake('--no-portal')
        with self.without_grim(), mock.patch.object(core, 'close_spark_menu'), \
                self.assertRaises(core.CaptureError) as caught:
            core.grab_screen()
        message = str(caught.exception)
        self.assertTrue(message.startswith(t('cap.failed', why='')), message)
        self.assertIn("grim: not installed", message)
        self.assertIn("portal:", message)

    def test_capture_check_saves_both_paths(self):
        self.start_fake()
        out = os.path.join(self.folder, 'check')

        def fake_run(cmd, **_kw):
            Image.new('RGB', (60, 40), (5, 5, 5)).save(cmd[-1], 'PPM')
            return subprocess.CompletedProcess(cmd, 0, b'', b'')
        with mock.patch.object(core.shutil, 'which', return_value='/usr/bin/grim'), \
                mock.patch.object(core.subprocess, 'run', fake_run):
            report = capture.capture_check(out)
        self.assertTrue(report['passed'], report)
        for name in ('grim', 'portal'):
            self.assertTrue(os.path.isfile(report[name]['file']), name)


@unittest.skipUnless(core.Tesseract().cmd, "Tesseract is not installed")
class OCRTests(unittest.TestCase):
    def test_reads_english(self):
        engine = core.OCREngine(core.Tesseract(), 'eng')
        result = engine.extract_text(core.sample_image("Spark Snip reads this line"))
        self.assertIn("reads this line", result.text)
        self.assertGreater(result.confidence, 60)

    def test_blank_image_reads_nothing(self):
        engine = core.OCREngine(core.Tesseract(), 'eng')
        self.assertEqual(engine.extract_text(Image.new('RGB', (300, 120), 'white')).text.strip(), '')

    def test_missing_language_falls_back(self):
        engine = core.OCREngine(core.Tesseract(), 'zzz')
        self.assertTrue(engine.supports(engine.lang))


def _display_available() -> bool:
    if os.name != 'nt' and not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
        return False
    try:
        import tkinter
        root = tkinter.Tk()
        root.destroy()
        return True
    except Exception:                                   # noqa: BLE001
        return False


@unittest.skipUnless(core.Tesseract().cmd and _display_available(), "needs Tesseract and a display")
class UITests(unittest.TestCase):
    """Runs the real overlay on a generated picture, with --from, and drives it."""

    def _run(self, mode: str):
        from sparksnip import app as appmod
        fixture = os.path.join(tempfile.mkdtemp(), 'fixture.png')
        core.sample_image("Invoice 2041 due Friday").save(fixture)
        app = appmod.App(start_mode=None, from_file=fixture)
        app.remember_mode(mode)
        root, seen = app.root, {}

        def drive():
            ov = app.overlay
            if ov is None:
                root.after(100, drive)
                return
            seen['overlay'] = True
            # --from centres the fixture on the whole desktop, which with several monitors
            # isn't the middle of the first one: drag on the monitor that shows it
            left, top, right, bottom = core.bounding_box([sc.monitor for sc in ov.screens])
            mx, my = (left + right) // 2, (top + bottom) // 2
            s = next((sc for sc in ov.screens
                      if sc.monitor.x <= mx < sc.monitor.x + sc.monitor.w
                      and sc.monitor.y <= my < sc.monitor.y + sc.monitor.h), ov.screens[0])
            cx, cy = mx - s.monitor.x, my - s.monitor.y
            ov.press(s, cx - 330, cy - 70)
            ov.drag(s, cx + 330, cy + 70)
            ov.release(s, cx + 330, cy + 70)
            root.after(200, wait)

        def wait(tries=[0]):
            tries[0] += 1
            popup = app.popup
            if (popup is None or app.busy) and tries[0] < 100:
                root.after(100, wait)
                return
            seen['headline'] = popup.headline.text if popup else None
            seen['text'] = popup.text.get('1.0', 'end-1c') if popup else ''
            root.after(100, root.destroy)

        root.after(300, app.start_capture)
        root.after(1000, drive)
        root.after(30000, root.destroy)      # never hang the test run
        app.run()
        return seen

    def test_text_mode_reads_and_copies(self):
        seen = self._run('text')
        self.assertTrue(seen.get('overlay'))
        self.assertEqual(seen.get('headline'), t('head.text_copied'))
        self.assertIn("2041", seen.get('text', ''))

    def test_image_mode_reports_the_copy(self):
        seen = self._run('image')
        self.assertTrue(seen.get('overlay'))
        # copying an image needs wl-copy or xclip; either outcome is reported, never silent
        self.assertIn(seen.get('headline'), (t('head.shot_copied'), t('head.not_copied')))


if __name__ == '__main__':
    unittest.main()


class KeepLatestTest(unittest.TestCase):
    """Spark Link's Send screenshot reads the last screenshot from Spark Snip's cache."""

    def test_writes_a_png_in_one_step(self):
        from sparksnip.core import keep_latest
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'latest.png')
            self.assertIsNone(keep_latest(Image.new('RGB', (40, 20), 'red'), path))
            self.assertIsNone(keep_latest(Image.new('RGB', (30, 10), 'blue'), path))
            with Image.open(path) as img:
                self.assertEqual((img.format, img.size), ('PNG', (30, 10)))
            self.assertEqual(os.listdir(d), ['latest.png'])

    def test_reports_failure(self):
        from sparksnip.core import keep_latest
        with tempfile.TemporaryDirectory() as d:
            error = keep_latest(Image.new('RGB', (4, 4)), os.path.join(d, 'gone', 'latest.png'))
            self.assertTrue(error)


class OneResultWindowTest(unittest.TestCase):
    """Every screenshot used to leave its own Spark Snip running with its window open."""

    def test_newer_screenshot_signals_the_previous_one(self):
        import signal as _signal
        import tempfile
        from unittest import mock
        from sparksnip import app
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'popup.pid')
            with open(path, 'w') as f:
                f.write('424242')
            with mock.patch.object(app, '_is_spark_snip', return_value=True), mock.patch.object(app.os, 'kill') as kill:
                app.replace_previous_popup(path)
            kill.assert_called_once_with(424242, _signal.SIGUSR2)
            with open(path) as f:
                self.assertEqual(f.read(), str(os.getpid()))

    def test_unrelated_or_own_process_is_left_alone(self):
        import tempfile
        from unittest import mock
        from sparksnip import app
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'popup.pid')
            for content, is_snip in ((str(os.getpid()), True), ('424242', False), ('junk', True)):
                with open(path, 'w') as f:
                    f.write(content)
                with mock.patch.object(app, '_is_spark_snip', return_value=is_snip), mock.patch.object(app.os, 'kill') as kill:
                    app.replace_previous_popup(path)
                kill.assert_not_called()
