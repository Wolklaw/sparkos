"""The wallpaper is decoded once, no bigger than the largest monitor needs. No display needed.

    env -u DISPLAY -u WAYLAND_DISPLAY python3 -m unittest discover -s files/spark-shell/tests -p 'test_wallpaper.py'
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import gi  # noqa: E402
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf  # noqa: E402

from sparkshell import wallpaper  # noqa: E402


class DecodeSize(unittest.TestCase):
    def test_largest_monitor_wins(self):
        screens = [(1920, 1080), (1920, 1080), (2560, 1440)]
        self.assertEqual(wallpaper.decode_size((3840, 2160), screens, 'fill'), (2560, 1440))

    def test_cover_uses_the_tighter_side(self):
        # a 1:1 image on a 16:9 screen has to be 1920 wide to cover it
        self.assertEqual(wallpaper.decode_size((4000, 4000), [(1920, 1080)], 'fill'), (1920, 1920))

    def test_never_bigger_than_the_file(self):
        self.assertEqual(wallpaper.decode_size((1920, 1080), [(3840, 2160)], 'fill'), (1920, 1080))

    def test_center_keeps_the_file_size(self):
        self.assertEqual(wallpaper.decode_size((3840, 2160), [(1920, 1080)], 'center'), (3840, 2160))


class Texture(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, 'w.png')
        GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 800, 400).savev(self.path, 'png', [], [])
        wallpaper._cache.clear()

    def test_shared_and_scaled(self):
        a = wallpaper.texture_for(self.path, [(400, 200), (200, 100)], 'fill')
        b = wallpaper.texture_for(self.path, [(400, 200), (200, 100)], 'fill')
        self.assertIs(a, b)
        self.assertEqual((a.get_width(), a.get_height()), (400, 200))
        self.assertEqual(len(wallpaper._cache), 1)

    def test_missing_file(self):
        self.assertIsNone(wallpaper.texture_for(os.path.join(self.dir, 'gone.png'), [(1, 1)], 'fill'))
        self.assertIsNone(wallpaper.texture_for('', [(1, 1)], 'fill'))

    def test_the_sparkos_wallpaper_is_small_now(self):
        path = '/usr/share/wallpapers/SparkOS/contents/images/3840x2160.png'
        if not os.path.isfile(path):
            self.skipTest('not on SparkOS')
        t = wallpaper.texture_for(path, [(1920, 1080), (1920, 1080), (2560, 1440)], 'fill')
        self.assertEqual((t.get_width(), t.get_height()), (2560, 1440))


if __name__ == '__main__':
    unittest.main()
