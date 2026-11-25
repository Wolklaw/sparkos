"""The volume item's backend: Spark Audio's own FakeBackend reading a saved pw-dump, so no real
sound device or volume is touched. Skipped when Spark Audio isn't in the checkout."""

import os
import unittest

import harness
from harness import AUDIO_FIXTURES, SPARK_AUDIO

os.environ['SPARK_AUDIO_DIR'] = SPARK_AUDIO

from sparktray import audio   # noqa: E402


@unittest.skipUnless(os.path.isfile(os.path.join(SPARK_AUDIO, 'sparkaudio', 'backend.py')),
                     "Spark Audio isn't here")
class VolumeTest(unittest.TestCase):
    def setUp(self):
        self.changes = 0
        self.vol = audio.Volume(self._changed, AUDIO_FIXTURES)
        self.assertTrue(self.vol.start())
        self.addCleanup(self.vol.stop)

    def _changed(self):
        self.changes += 1

    def test_reads_the_default_output(self):
        self.assertIsNotNone(self.vol.output())
        self.assertIsNotNone(self.vol.level())

    def test_scroll_changes_the_level_in_steps(self):
        self.vol.set_level(0.5)
        self.vol.nudge(2)
        self.assertAlmostEqual(self.vol.level(), 0.6, places=2)
        self.vol.nudge(-4)
        self.assertAlmostEqual(self.vol.level(), 0.4, places=2)

    def test_level_stays_between_zero_and_full(self):
        self.vol.set_level(0.98)
        self.vol.nudge(5)
        self.assertLessEqual(self.vol.level(), 1.0)
        self.vol.set_level(0.02)
        self.vol.nudge(-5)
        self.assertGreaterEqual(self.vol.level(), 0.0)

    def test_middle_click_mutes_and_unmutes(self):
        before = self.vol.muted()
        self.vol.toggle_mute()
        self.assertNotEqual(self.vol.muted(), before)
        self.vol.toggle_mute()
        self.assertEqual(self.vol.muted(), before)

    def test_turning_up_from_muted_unmutes(self):
        if not self.vol.muted():
            self.vol.toggle_mute()
        self.vol.nudge(1)
        self.assertFalse(self.vol.muted())

    def test_icon_follows_level(self):
        self.assertEqual(audio.icon_for(0.5, True), 'audio-volume-muted')
        self.assertEqual(audio.icon_for(None, False), 'audio-volume-muted')
        self.assertNotEqual(audio.icon_for(0.1, False), audio.icon_for(0.9, False))

    def test_not_installed_means_no_volume(self):
        os.environ['SPARK_AUDIO_DIR'] = '/nonexistent'
        try:
            import sys
            saved = sys.modules.pop('sparkaudio.backend', None)
            self.assertIsNone(audio.find_spark_audio())
            self.assertIsNone(audio.load_backend_module())
            if saved:
                sys.modules['sparkaudio.backend'] = saved
        finally:
            os.environ['SPARK_AUDIO_DIR'] = SPARK_AUDIO


if __name__ == '__main__':
    unittest.main()
