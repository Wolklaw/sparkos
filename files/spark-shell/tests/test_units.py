"""Unit tests for the parts of Spark Shell that need no display and no bus:
config, tray parsing, the notification model, the window list, the OSD parsers.

    env -u DISPLAY -u WAYLAND_DISPLAY python3 -m unittest discover -s files/spark-shell/tests -p 'test_units.py'
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from sparkshell import config, ending, notifyd, osd, tray, windows  # noqa: E402


class Config(unittest.TestCase):
    def test_defaults(self):
        c = config.clean({})
        self.assertEqual(c['wallpaper_mode'], 'fill')
        self.assertEqual(c['panel_position'], 'bottom')
        self.assertEqual(c['pinned'], list(config.DEFAULT_PINNED))

    def test_rejects_junk(self):
        c = config.clean({'wallpaper_mode': 'spin', 'panel_position': 'left', 'pinned': 'x',
                          'wallpaper': 5})
        self.assertEqual((c['wallpaper'], c['wallpaper_mode'], c['panel_position']),
                         ('', 'fill', 'bottom'))
        self.assertEqual(c['pinned'], list(config.DEFAULT_PINNED))
        self.assertEqual(config.clean('nope')['wallpaper_mode'], 'fill')

    def test_keeps_good_values(self):
        c = config.clean({'wallpaper': '~/a.png', 'wallpaper_mode': 'fit',
                          'panel_position': 'top', 'pinned': ['a.desktop', 3]})
        self.assertEqual(c['pinned'], ['a.desktop'])
        self.assertEqual((c['wallpaper_mode'], c['panel_position']), ('fit', 'top'))

    def test_load_missing_and_broken(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(config.load(os.path.join(d, 'none.json'))['panel_position'], 'bottom')
            bad = os.path.join(d, 'bad.json')
            with open(bad, 'w') as f:
                f.write('{nope')
            self.assertEqual(config.load(bad)['wallpaper_mode'], 'fill')

    def test_save_pinned_keeps_other_keys(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'sub', 'shell.json')
            os.makedirs(os.path.dirname(path))
            with open(path, 'w') as f:
                json.dump({'wallpaper': 'x.png', 'other': 1}, f)
            config.save_pinned(['a.desktop'], path)
            with open(path) as f:
                data = json.load(f)
            self.assertEqual(data, {'wallpaper': 'x.png', 'other': 1, 'pinned': ['a.desktop']})


class TrayParsing(unittest.TestCase):
    def test_split_service(self):
        self.assertEqual(tray.split_service('org.x.Item-1', ':1.5'),
                         ('org.x.Item-1', '/StatusNotifierItem'))
        self.assertEqual(tray.split_service('/Path/Here', ':1.5'), (':1.5', '/Path/Here'))
        self.assertEqual(tray.split_service(':1.9/MyItem', ':1.5'), (':1.9', '/MyItem'))

    def test_clean_label(self):
        self.assertEqual(tray.clean_label('_Quit'), 'Quit')
        self.assertEqual(tray.clean_label('Save __As'), 'Save _As')
        self.assertEqual(tray.clean_label('Plain'), 'Plain')

    def test_parse_layout(self):
        layout = (0, {'children-display': 'submenu'}, [
            (1, {'label': '_Open'}, []),
            (2, {'type': 'separator'}, []),
            (3, {'label': 'Mode', 'children-display': 'submenu'}, [
                (4, {'label': 'Fast', 'toggle-type': 'radio', 'toggle-state': 1}, [])]),
            'junk',
        ])
        root = tray.parse_layout(layout)
        self.assertEqual([k.id for k in root.children], [1, 2, 3])
        self.assertEqual(root.children[0].label, 'Open')
        self.assertTrue(root.children[1].separator)
        self.assertTrue(root.children[2].has_submenu)
        self.assertEqual(root.children[2].children[0].toggle, ('radio', True))
        self.assertTrue(root.children[0].visible and root.children[0].enabled)


class Notifications(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sent = []
        notifyd.emit = lambda *a: self.sent.append(a)
        self.srv = notifyd.NotificationServer(None, os.path.join(self.tmp.name, 'h.json'))
        self.shown, self.closed = [], []
        self.srv.on_show = self.shown.append
        self.srv.on_close = lambda i, r: self.closed.append((i, r))

    def tearDown(self):
        for ident in list(self.srv._timers):
            self.srv._cancel_timer(ident)
        self.tmp.cleanup()

    def send(self, replaces=0, summary='s', hints=None, actions=(), timeout=-1):
        return self.srv.notify('app', replaces, '', summary, 'body', list(actions), hints or {},
                               timeout)

    def signals(self):
        return [x for x in self.sent if 'NotificationClosed' in x or 'ActionInvoked' in x]

    def test_ids_and_replace(self):
        a = self.send()
        b = self.send()
        self.assertNotEqual(a, b)
        self.assertEqual(self.send(replaces=a, summary='again'), a)
        self.assertEqual(len(self.srv.history), 2)
        self.assertEqual([h.summary for h in self.srv.history if h.id == a], ['again'])

    def test_urgency_and_timeout(self):
        n = notifyd.Notification(1, 'a', '', 's', 'b', [], {'urgency': 2}, 3000)
        self.assertTrue(n.critical)
        self.assertEqual(n.effective_timeout, 0)
        n = notifyd.Notification(1, 'a', '', 's', 'b', [], {'urgency': 9}, -1)
        self.assertEqual(n.urgency, 1)
        self.assertEqual(n.effective_timeout, notifyd.DEFAULT_TIMEOUT_MS)
        self.assertEqual(notifyd.Notification(1, 'a', '', 's', 'b', [], {}, 0).effective_timeout, 0)

    def test_actions(self):
        self.assertEqual(notifyd.parse_actions(['default', 'Open', 'r', 'Reply']),
                         [('default', 'Open'), ('r', 'Reply')])
        self.assertEqual(notifyd.parse_actions(['odd']), [])

    def test_do_not_disturb(self):
        self.srv.set_dnd(True)
        self.send()
        self.assertEqual(self.shown, [])
        self.assertEqual(len(self.srv.history), 1)
        crit = self.send(hints={'urgency': 2})
        self.assertEqual([n.id for n in self.shown], [crit])

    def test_transient_skips_history(self):
        self.send(hints={'transient': True})
        self.assertEqual(self.srv.history, [])

    def test_close_by_call_removes_history(self):
        a = self.send()
        self.srv.close(a, notifyd.CLOSED_BY_CALL)
        self.assertEqual(self.srv.history, [])
        self.assertTrue(self.signals())

    def test_dismiss_keeps_history_and_invoke_emits(self):
        a = self.send(actions=['default', 'Open'])
        self.srv.invoke(a, 'default')
        self.assertTrue([x for x in self.sent if 'ActionInvoked' in x])
        self.assertNotIn(a, self.srv.active)
        self.assertEqual(len(self.srv.history), 1)

    def test_history_persists(self):
        self.send(summary='keep me')
        again = notifyd.NotificationServer(None, self.srv.history_path)
        self.assertEqual([h.summary for h in again.history], ['keep me'])
        self.assertGreater(again.next_id, 1)


class Windows(unittest.TestCase):
    def test_update_parses_and_ignores_junk(self):
        tracker = windows.WindowTracker(None, runtime_dir='/tmp')
        seen = []
        tracker.on_changed = seen.append
        tracker.update('not json')
        self.assertEqual(seen, [])
        tracker.update(json.dumps([{'id': 'a1', 'title': 'T', 'app': 'x', 'pid': '7',
                                    'active': True}, {'title': 'no id'}, 5]))
        self.assertEqual(len(tracker.windows), 1)
        self.assertEqual(tracker.windows[0]['pid'], 7)
        self.assertEqual(tracker.active_window()['id'], 'a1')

    def test_match_app(self):
        w = {'app': 'dev.wolklaw.SparkFiles', 'cls': 'spark-files'}
        self.assertTrue(windows.match_app(w, 'dev.wolklaw.SparkFiles.desktop'))
        self.assertTrue(windows.match_app(w, 'DEV.wolklaw.sparkfiles'))
        self.assertTrue(windows.match_app(w, 'other.desktop', 'spark-files'))
        self.assertFalse(windows.match_app(w, 'other.desktop'))
        self.assertFalse(windows.match_app(w, ''))


class OsdParsers(unittest.TestCase):
    def test_wpctl(self):
        self.assertEqual(osd.parse_wpctl_volume('Volume: 0.45'), (0.45, False))
        self.assertEqual(osd.parse_wpctl_volume('Volume: 1.00 [MUTED]'), (1.0, True))
        self.assertIsNone(osd.parse_wpctl_volume('nothing'))
        self.assertIsNone(osd.parse_wpctl_volume(None))

    def test_osd_service_brightness(self):
        class FakeOsd:
            def __init__(self):
                self.shown, self.hidden = [], 0

            def show_level(self, kind, fraction, muted=False):
                self.shown.append((kind, fraction))

            def hide_now(self):
                self.hidden += 1
        fake = FakeOsd()
        osd.osd_service_call(fake, 'brightnessChanged', (40,))
        osd.osd_service_call(fake, 'screenBrightnessChanged', (130, (0, 0, 2560, 1440)))
        osd.osd_service_call(fake, 'keyboardBrightnessChanged', (-5,))
        osd.osd_service_call(fake, 'hide', ())
        self.assertEqual(fake.shown, [('brightness', 0.4), ('brightness', 1.0), ('keyboard', 0.0)])
        self.assertEqual(fake.hidden, 1)


class FakeTracker:
    def __init__(self, titles, closes=True):
        self.loaded = True
        self.windows = [{'id': '{%d}' % n, 'title': t} for n, t in enumerate(titles)]
        self.closes = closes
        self.closed = []

    def act(self, action, wid):
        self.closed.append((action, wid))
        if self.closes:
            self.windows = [w for w in self.windows if w['id'] != wid]


class SessionEndTest(unittest.TestCase):
    def setUp(self):
        self.ran, self.stuck, self.ticks = [], [], []

    def make(self, tracker):
        return ending.SessionEnd(tracker, self.ran.append,
                                 lambda c, t, label: self.stuck.append((c, t, label)),
                                 wait_s=1.0, timeout_add=lambda ms, f: self.ticks.append(f))

    def pump(self):
        while self.ticks:
            f = self.ticks.pop()
            if f():
                self.ticks.append(f)

    def test_no_windows_runs_at_once(self):
        self.make(FakeTracker([])).start(['poweroff'])
        self.assertEqual(self.ran, [['poweroff']])

    def test_windows_are_closed_first_then_it_runs(self):
        t = FakeTracker(['Spark Edit', 'Firefox'])
        end = self.make(t)
        end.start(['reboot'], label='restart')
        self.assertEqual([a for a, _ in t.closed], ['close', 'close'])
        self.pump()
        self.assertEqual(self.ran, [['reboot']])
        self.assertEqual(self.stuck, [])

    def test_a_window_that_stays_stops_it_and_says_which(self):
        t = FakeTracker(['Unsaved - Spark Edit'], closes=False)
        end = self.make(t)
        end.start(['reboot'], label='restart')
        self.pump()
        self.assertEqual(self.ran, [])
        self.assertEqual(self.stuck, [(['reboot'], ['Unsaved - Spark Edit'], 'restart')])
        self.assertFalse(end.busy)
        end.start(['reboot'], force=True)
        self.assertEqual(self.ran, [['reboot']])

    def test_tracker_not_loaded_runs_at_once(self):
        t = FakeTracker(['x'], closes=False)
        t.loaded = False
        self.make(t).start(['poweroff'])
        self.assertEqual(self.ran, [['poweroff']])


class PreloadTest(unittest.TestCase):
    """Apps started from the shell must not inherit gtk4-layer-shell (GTK 3 apps abort)."""
    def test_dropped_once_loaded(self):
        import importlib
        from unittest import mock
        spark_shell = importlib.import_module('spark_shell')
        env = {'SPARK_SHELL_PRELOADED': '1',
               'LD_PRELOAD': '/usr/lib64/libgtk4-layer-shell.so.0 /opt/other.so'}
        with mock.patch.dict(os.environ, env):
            spark_shell.preload_layer_shell()
            self.assertEqual(os.environ['LD_PRELOAD'], '/opt/other.so')
        with mock.patch.dict(os.environ, dict(env, LD_PRELOAD='/usr/lib64/libgtk4-layer-shell.so.0')):
            spark_shell.preload_layer_shell()
            self.assertNotIn('LD_PRELOAD', os.environ)


if __name__ == '__main__':
    unittest.main()
