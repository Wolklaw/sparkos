"""Spark Snip tests. Plain unittest:

    python -m unittest discover -s files/spark-snip/tests -v

Logic tests run anywhere. OCR tests need Tesseract (they skip without it). UI tests need a
display (on CI: xvfb-run) and open real windows for a few seconds.
"""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault('XDG_STATE_HOME', tempfile.mkdtemp(prefix='spark-snip-state-'))
os.environ.setdefault('XDG_CONFIG_HOME', tempfile.mkdtemp(prefix='spark-snip-config-'))

from PIL import Image  # noqa: E402

from sparksnip import core, recorder  # noqa: E402
from sparksnip.core import Monitor  # noqa: E402

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
        self.assertEqual(core.language_label('eng+fra'), "English + French")
        self.assertEqual(core.language_short('eng+fra'), "EN + FR")
        self.assertEqual(core.language_short('xyz'), "XYZ")

    def test_clock_and_size(self):
        self.assertEqual(core.clock(83), "01:23")
        self.assertEqual(core.clock(3723), "1:02:03")
        self.assertEqual(core.human_size(512), "512 B")
        self.assertEqual(core.human_size(5 * 1024 * 1024), "5.0 MB")

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
        self.assertTrue(line.endswith('mp4mux name=mux ! filesink location=/tmp/out.mp4'))

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
        # Plasma at 150%: the portal speaks logical pixels
        self.assertTrue(recorder.stream_matches(Monitor('DP-1', 2880, 0, 2880, 1620),
                                                {'position': (1920, 0), 'size': (1920, 1080)}))
        self.assertFalse(recorder.stream_matches(mon, {'position': (0, 0), 'size': (2560, 1440)}))

    def test_config_round_trip(self):
        core.save_config({'lang': 'fra', 'mode': 'video'})
        self.assertEqual(core.load_config()['mode'], 'video')


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
            s = ov.screens[0]
            # the fixture is centred on the screen; select a box around it
            cx, cy = s.monitor.w // 2, s.monitor.h // 2
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
        self.assertEqual(seen.get('headline'), "TEXT COPIED")
        self.assertIn("2041", seen.get('text', ''))

    def test_image_mode_reports_the_copy(self):
        seen = self._run('image')
        self.assertTrue(seen.get('overlay'))
        # copying an image needs wl-copy or xclip; either outcome is reported, never silent
        self.assertIn(seen.get('headline'), ("SCREENSHOT COPIED", "COULD NOT COPY"))


if __name__ == '__main__':
    unittest.main()
