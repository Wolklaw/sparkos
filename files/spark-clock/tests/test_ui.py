"""The window, under a display (Xvfb in CI), in a temporary home: make an alarm through the
editor, start and stop timers, run the stopwatch with laps, add a world clock, and see the ring
banner and its Stop button. Nothing outside the temporary folders is written and the service is
never started (start_service=False)."""

import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ['SPARK_CLOCK_REDUCED_MOTION'] = '1'


def have_display() -> bool:
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


@unittest.skipUnless(have_display(), "needs a display")
class Window(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='spark-clock-ui-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.saved = {k: os.environ.get(k) for k in ('XDG_CONFIG_HOME', 'XDG_STATE_HOME')}
        os.environ['XDG_CONFIG_HOME'] = os.path.join(self.tmp, 'config')
        os.environ['XDG_STATE_HOME'] = os.path.join(self.tmp, 'state')
        self.addCleanup(self._restore)
        from sparkclock.app import App
        self.clock = {'now': time.time()}
        self.app = App(ask=lambda *a, **k: True, error=lambda *a, **k: None,
                       clock=lambda: self.clock['now'], start_service=False)
        self.addCleanup(self.app.close)
        self.pump(0.3)

    def _restore(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def pump(self, seconds=0.1):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.app.root.update()
            time.sleep(0.01)

    def test_alarm_through_the_editor(self):
        from sparkclock import store
        from sparkclock.editor import AlarmEditor
        editor = AlarmEditor(self.app, None)
        editor.hour.delete(0, 'end')
        editor.hour.insert(0, '6')
        editor.minute.delete(0, 'end')
        editor.minute.insert(0, '45')
        editor.set_days([0, 1, 2, 3, 4])
        editor.label.insert(0, 'Work')
        self.assertTrue(editor.save())
        alarm = store.load_config()['alarms'][0]
        self.assertEqual((alarm['time'], alarm['days'], alarm['label']),
                         ('06:45', [0, 1, 2, 3, 4], 'Work'))
        self.assertTrue(alarm['enabled'])

    def test_a_bad_time_is_refused_with_a_reason(self):
        from sparkclock import store
        from sparkclock.editor import AlarmEditor
        editor = AlarmEditor(self.app, None)
        editor.hour.delete(0, 'end')
        editor.hour.insert(0, '99')
        self.assertFalse(editor.save())
        self.assertTrue(editor.error.cget('text'))
        self.assertEqual(store.load_config()['alarms'], [])
        editor.close()

    def test_timers(self):
        from sparkclock import store
        tab = self.app.tabs['timers']
        self.assertIsNone(tab.start(0))                      # nothing to start
        tab.start(300)
        tab.start(90)
        self.assertEqual(len(store.load_timers()), 2)         # several at once
        self.app.show('timers')
        self.pump(0.3)

    def test_stopwatch_and_laps(self):
        from sparkclock import store
        tab = self.app.tabs['stopwatch']
        tab.toggle()
        self.clock['now'] += 12.5
        tab.lap()
        self.clock['now'] += 7.5
        tab.toggle()
        sw = store.load_stopwatch()
        self.assertAlmostEqual(sw['elapsed'], 20.0, places=2)
        self.assertEqual(len(sw['laps']), 1)
        tab.reset()
        self.assertEqual(store.load_stopwatch()['laps'], [])

    def test_world_clocks_start_with_montreal(self):
        from sparkclock import cities, store
        tab = self.app.tabs['world']
        self.assertEqual(tab.zones()[0], cities.HOME_ZONE)
        tab.entry.insert(0, 'Tokyo')
        tab.filter()
        self.assertEqual(tab.add(), 'Asia/Tokyo')
        self.assertIn('Asia/Tokyo', store.load_config()['world'])

    def test_a_ring_shows_a_banner_and_stop_answers_it(self):
        from sparkclock import store
        now = self.clock['now']
        store.save_service({'pid': os.getpid(), 'beat': now, 'last_tick': now, 'snoozes': [],
                            'ringing': [{'key': 'alarm:abc', 'kind': 'alarm', 'ref': 'abc',
                                         'title': 'Alarm 06:45', 'body': 'Work', 'snooze': 9,
                                         'since': now}]})
        self.app.refresh_data(force=True)
        self.app._banners(now)
        self.assertIn('alarm:abc', self.app.banners)
        self.app.banners['alarm:abc']['stop'].invoke() if hasattr(
            self.app.banners['alarm:abc']['stop'], 'invoke') else self.app.answer(
                'alarm:abc', 'stop')
        self.assertNotIn('alarm:abc', self.app.banners)
        self.assertEqual([c['cmd'] for c in store.take_commands()], ['stop'])


if __name__ == '__main__':
    unittest.main()
