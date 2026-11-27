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

from sparkshell import (compositor, config, connectstatus, ending, ordering, notifyd, osd, password, screensaver, tray, windows, xembed)  # noqa: E402


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


class XembedPixels(unittest.TestCase):
    def test_bgra_to_argb_big_endian(self):
        # one pixel: B=1 G=2 R=3 A=4, as X11 ZPixmap hands it over
        self.assertEqual(xembed.to_argb_be(bytes([1, 2, 3, 4]), 32), bytes([4, 3, 2, 1]))

    def test_24_bit_is_opaque(self):
        self.assertEqual(xembed.to_argb_be(bytes([1, 2, 3, 0, 5, 6, 7, 0]), 24),
                         bytes([255, 3, 2, 1, 255, 7, 6, 5]))


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
        self.srv.flush()
        again = notifyd.NotificationServer(None, self.srv.history_path)
        self.assertEqual([h.summary for h in again.history], ['keep me'])
        self.assertGreater(again.next_id, 1)


class Windows(unittest.TestCase):
    def test_update_parses_and_ignores_junk(self):
        tracker = windows.WindowTracker()
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

    def test_next_brightness(self):
        self.assertEqual(osd.next_brightness(50, 100, True), 55)
        self.assertEqual(osd.next_brightness(98, 100, True), 100)
        self.assertEqual(osd.next_brightness(3, 100, False), 1)      # never fully dark
        self.assertEqual(osd.next_brightness(120000, 120000, False), 114000)
        self.assertEqual(osd.next_brightness(4, 7, True), 5)         # tiny ranges still move
        self.assertEqual(osd.next_brightness(4, 0, True), 4)

    def test_read_backlights(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, 'amdgpu_bl0'))
            for name, text in (('brightness', '40\n'), ('max_brightness', '255\n')):
                with open(os.path.join(root, 'amdgpu_bl0', name), 'w') as f:
                    f.write(text)
            os.makedirs(os.path.join(root, 'broken'))
            self.assertEqual(osd.read_backlights(root), [('amdgpu_bl0', 40, 255)])
        self.assertEqual(osd.read_backlights('/nonexistent-backlight-dir'), [])


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


class SignOutTest(unittest.TestCase):
    # 10 helper -> 11 compositor -> 12 tee; 20 session runner -> 21 shell -> 22 sign-out,
    # 21 -> 23 window list; 30 Xwayland; 40 Wine -> 41 Battle.net
    TREE = {10: 1, 11: 10, 12: 11, 20: 1, 21: 20, 22: 21, 23: 21, 30: 1, 40: 1, 41: 40}

    def test_apps_go_compositor_and_shell_stay(self):
        out = ending.leftovers(sorted(self.TREE), 22, 10, parent=lambda p: self.TREE.get(p, 0))
        self.assertEqual(out, [23, 30, 40, 41])

    def test_no_leader_known_keeps_only_the_shell(self):
        out = ending.leftovers([20, 21, 22, 40], 22, 0, parent=lambda p: self.TREE.get(p, 0))
        self.assertEqual(out, [40])

    def test_the_compositor_binary_is_found_not_its_wrapper(self):
        exes = {10: 'greetd', 11: 'spark-compositor.bin', 12: 'tee', 13: 'bash'}
        self.assertEqual(ending.compositors(sorted(exes), exe=exes.get), [11])


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


class ScreenSaverTest(unittest.TestCase):
    def test_flag_follows_first_and_last_inhibit(self):
        changes = []
        inh = screensaver.Inhibitors(changes.append)
        a = inh.add(':1.5', 'Steam', 'game')
        b = inh.add(':1.6', 'mpv', 'video')
        self.assertNotEqual(a, b)
        self.assertFalse(inh.remove(a, sender=':1.6'))     # not yours
        self.assertTrue(inh.remove(a, sender=':1.5'))
        self.assertEqual(changes, [True])
        inh.drop_sender(':1.6')                             # mpv left the bus
        self.assertEqual(changes, [True, False])
        self.assertFalse(inh.active)

    def test_write_flag(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'spark-wl', 'idle-inhibit')
            screensaver.write_flag(True, path)
            self.assertTrue(os.path.exists(path))
            screensaver.write_flag(False, path)
            self.assertFalse(os.path.exists(path))
            screensaver.write_flag(False, path)             # already gone is fine


class MediaKeysTest(unittest.TestCase):
    def test_playing_player_wins(self):
        self.assertEqual(osd.choose_player([('a', 'Paused'), ('b', 'Playing'), ('c', 'Stopped')]), 'b')
        self.assertEqual(osd.choose_player([('a', 'Stopped'), ('b', 'Paused')]), 'b')
        self.assertEqual(osd.choose_player([('a', 'Stopped')]), 'a')
        self.assertIsNone(osd.choose_player([]))


# a passwd that talks like Fedora's: current password "old", pwquality wants 8 characters
FAKE_PASSWD = r"""#!/bin/sh
printf 'Current password: '; read -r cur
if [ "$cur" != old ]; then
  echo 'passwd: Authentication token manipulation error'; echo 'passwd: password unchanged'; exit 10
fi
printf 'New password: '; read -r new
if [ ${#new} -lt 8 ]; then
  echo 'BAD PASSWORD: The password is shorter than 8 characters'; printf 'New password: '; read -r new
fi
printf 'Retype new password: '; read -r again
[ "$new" = "$again" ] || { echo 'Sorry, passwords do not match.'; echo 'passwd: Authentication token manipulation error'; exit 10; }
echo "$new" > "$OUT"
echo 'passwd: all authentication tokens updated successfully.'
"""


class PasswordTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.fake = os.path.join(self.dir.name, 'passwd')
        with open(self.fake, 'w') as f:
            f.write(FAKE_PASSWD)
        os.chmod(self.fake, 0o755)
        self.out = os.path.join(self.dir.name, 'out')
        os.environ['OUT'] = self.out

    def tearDown(self):
        os.environ.pop('OUT', None)
        self.dir.cleanup()

    def run_it(self, current, new):
        return password.change(current, new, command=(self.fake,), timeout=10)

    def test_checks(self):
        self.assertEqual(password.check('', 'a', 'a'), 'pw_need_current')
        self.assertEqual(password.check('o', '', ''), 'pw_need_new')
        self.assertEqual(password.check('o', 'a', 'b'), 'pw_mismatch')
        self.assertEqual(password.check('o', 'o', 'o'), 'pw_same')
        self.assertIsNone(password.check('o', 'longer one', 'longer one'))

    def test_changed(self):
        self.assertEqual(self.run_it('old', 'good password'), (True, ''))
        with open(self.out) as f:
            self.assertEqual(f.read().strip(), 'good password')

    def test_wrong_current(self):
        self.assertEqual(self.run_it('nope', 'good password'), (False, ''))
        self.assertFalse(os.path.exists(self.out))

    def test_too_weak(self):
        ok, message = self.run_it('old', 'short')
        self.assertFalse(ok)
        self.assertIn('shorter than 8', message)
        self.assertFalse(os.path.exists(self.out))


class ConfigNewKeys(unittest.TestCase):
    def test_defaults(self):
        c = config.clean({})
        self.assertEqual(c['tray_order'], [])
        self.assertEqual(c['connect_widget'], {'enabled': False, 'monitor': ''})

    def test_tray_order_is_cleaned(self):
        c = config.clean({'tray_order': ['a', 3, '', 'b', 'a', None]})
        self.assertEqual(c['tray_order'], ['a', 'b'])
        self.assertEqual(config.clean({'tray_order': 'a'})['tray_order'], [])

    def test_connect_widget_is_validated(self):
        ok = config.clean({'connect_widget': {'enabled': True, 'monitor': ' DP-1 '}})
        self.assertEqual(ok['connect_widget'], {'enabled': True, 'monitor': 'DP-1'})
        for junk in ('yes', 5, None, [], {'enabled': 'true', 'monitor': 7}, {'enabled': 1}):
            self.assertEqual(config.clean({'connect_widget': junk})['connect_widget'],
                             {'enabled': False, 'monitor': ''}, junk)

    def test_savers_keep_other_keys(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'shell.json')
            with open(path, 'w') as f:
                json.dump({'wallpaper': 'x.png', 'pinned': ['a.desktop'], 'other': 1}, f)
            config.save_tray_order(['b', 'a'], path)
            config.save_connect_widget(enabled=True, path=path)
            written = config.save_connect_widget(monitor='HDMI-A-1', path=path)
            self.assertEqual(written, {'enabled': True, 'monitor': 'HDMI-A-1'})
            with open(path) as f:
                data = json.load(f)
            self.assertEqual(data, {'wallpaper': 'x.png', 'pinned': ['a.desktop'], 'other': 1,
                                    'tray_order': ['b', 'a'],
                                    'connect_widget': {'enabled': True, 'monitor': 'HDMI-A-1'}})
            config.save_pinned(['c.desktop'], path)
            self.assertEqual(config.load(path)['connect_widget']['monitor'], 'HDMI-A-1')
            self.assertEqual(config.load(path)['tray_order'], ['b', 'a'])


class Ordering(unittest.TestCase):
    def test_merge_keeps_unknown_last(self):
        self.assertEqual(ordering.merge_order(['b', 'a'], ['a', 'c', 'b', 'd']),
                         ['b', 'a', 'c', 'd'])
        self.assertEqual(ordering.merge_order([], ['x', 'y']), ['x', 'y'])
        self.assertEqual(ordering.merge_order(['gone', 'a'], ['a']), ['a'])
        pairs = [('id1', 'k1'), ('id2', 'k2')]
        self.assertEqual(ordering.merge_order(['id2'], pairs, ident=lambda p: p[0]),
                         [('id2', 'k2'), ('id1', 'k1')])

    def test_move_key(self):
        keys = ['a', 'b', 'c', 'd']
        self.assertEqual(ordering.move_key(keys, 'a', 'c', False), ['b', 'a', 'c', 'd'])
        self.assertEqual(ordering.move_key(keys, 'a', 'c', True), ['b', 'c', 'a', 'd'])
        self.assertEqual(ordering.move_key(keys, 'd', 'a', False), ['d', 'a', 'b', 'c'])
        self.assertEqual(ordering.move_key(keys, 'b', None, True), ['a', 'c', 'd', 'b'])
        self.assertEqual(ordering.move_key(keys, 'b', 'b', True), keys)
        self.assertEqual(ordering.move_key(keys, 'z', 'b', False), ['a', 'z', 'b', 'c', 'd'])

    def test_pinned_reorder(self):
        keys = ['p1', 'p2', 'p3', 'u1', 'u2']
        pinned = ['p1', 'p2', 'p3']
        self.assertEqual(ordering.reorder_tasks(keys, pinned, 'p3', 'p1', False),
                         (['p3', 'p1', 'p2'], ['u1', 'u2']))
        # a pinned app dropped among the unpinned ones stays pinned, last in the group
        self.assertEqual(ordering.reorder_tasks(keys, pinned, 'p1', 'u2', True),
                         (['p2', 'p3', 'p1'], ['u1', 'u2']))

    def test_unpinned_reorder_and_pin_by_drop(self):
        keys = ['p1', 'p2', 'u1', 'u2']
        pinned = ['p1', 'p2']
        self.assertEqual(ordering.reorder_tasks(keys, pinned, 'u2', 'u1', False),
                         (['p1', 'p2'], ['u2', 'u1']))
        # between pinned ones: pinned at that spot
        self.assertEqual(ordering.reorder_tasks(keys, pinned, 'u2', 'p2', False),
                         (['p1', 'u2', 'p2'], ['u1']))
        self.assertEqual(ordering.reorder_tasks(keys, pinned, 'u1', 'p1', False),
                         (['u1', 'p1', 'p2'], ['u2']))
        # right after the last pinned app is still the unpinned group
        self.assertEqual(ordering.reorder_tasks(keys, pinned, 'u2', 'p2', True),
                         (['p1', 'p2'], ['u2', 'u1']))
        # an app with no desktop entry cannot be pinned: it lands just after the pinned ones
        self.assertEqual(ordering.reorder_tasks(keys, pinned, 'u2', 'p1', False, pinnable=False),
                         (['p1', 'p2'], ['u2', 'u1']))

    def test_uninstalled_pinned_entries_survive(self):
        self.assertEqual(ordering.reorder_tasks(['p1', 'p2'], ['p1', 'gone.desktop', 'p2'],
                                                'p2', 'p1', False),
                         (['p2', 'p1', 'gone.desktop'], []))

    def test_drop_at_the_end(self):
        self.assertEqual(ordering.reorder_tasks(['p1', 'u1', 'u2'], ['p1'], 'u1', None, True),
                         (['p1'], ['u2', 'u1']))


class CompositorProtocol(unittest.TestCase):
    def test_parse_workspace(self):
        self.assertEqual(compositor.parse_line('workspace 2 4 1,3\n'),
                         {'kind': 'workspace', 'current': 2, 'count': 4, 'occupied': [1, 3]})
        self.assertEqual(compositor.parse_line('workspace 1 1 -')['occupied'], [])
        self.assertEqual(compositor.parse_line('workspace 3 4 4,2,2,9')['occupied'], [2, 4])

    def test_parse_rejects_bad_lines(self):
        for bad in ('', 'workspace', 'workspace x 4 -', 'workspace 5 4 -', 'workspace 0 4 -',
                    'workspace 1 0 -', 'workspace 1 4 a,b', 'tiling maybe', 'focus 12 foo',
                    'whatever 1 2'):
            self.assertIsNone(compositor.parse_line(bad), bad)

    def test_parse_others(self):
        self.assertEqual(compositor.parse_line('tiling on'), {'kind': 'tiling', 'on': True})
        self.assertEqual(compositor.parse_line('tiling off')['on'], False)
        self.assertEqual(compositor.parse_line('ok'), {'kind': 'ok'})
        self.assertEqual(compositor.parse_line('error no such workspace'),
                         {'kind': 'error', 'text': 'no such workspace'})

    def test_socket_path(self):
        old = os.environ.get('XDG_RUNTIME_DIR')
        os.environ['XDG_RUNTIME_DIR'] = '/run/user/7'
        try:
            self.assertEqual(compositor.socket_path(), '/run/user/7/spark-wl/ctl')
        finally:
            if old is None:
                del os.environ['XDG_RUNTIME_DIR']
            else:
                os.environ['XDG_RUNTIME_DIR'] = old

    def test_link_against_a_fake_socket(self):
        """watch, state lines, a command on its own connection, and a reconnect-free missing socket."""
        import socket
        import threading
        from gi.repository import GLib
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'ctl')
            server = socket.socket(socket.AF_UNIX)
            server.bind(path)
            server.listen(4)
            commands = []

            def serve():
                for _ in range(2):
                    conn, _addr = server.accept()
                    line = conn.makefile().readline().strip()
                    if line == 'watch':
                        conn.sendall(b'ok\nfocus 1 x\nworkspace 2 4 1,2\ntiling on\n')
                        self.keep = conn
                    else:
                        commands.append(line)
                        conn.sendall(b'ok\n')
                        conn.close()
            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            link = compositor.CompositorLink(path)
            loop = GLib.MainLoop()
            replies = []
            state = {'sent': False}

            def changed():
                if link.tiling and not state['sent']:
                    state['sent'] = True
                    link.send('workspace next', lambda r: (replies.append(r), loop.quit()))
            link.on_change = changed
            link.start()
            GLib.timeout_add_seconds(5, loop.quit)
            loop.run()
            link.stop()
            server.close()
            self.assertEqual((link.current, link.count, link.occupied, link.tiling),
                             (1, 1, [], None))        # reset when stopped
            self.assertEqual(replies, ['ok'])
            self.assertEqual(commands, ['workspace next'])

    def test_missing_socket_is_quiet(self):
        link = compositor.CompositorLink('/nonexistent/spark-wl/ctl')
        link.start()
        self.assertFalse(link.visible())
        link.stop()
        got = []
        link.send('tile-toggle', got.append)
        self.assertEqual(got, [''])


STATUS = {
    'checked': 1767225600, 'summary': 'warn',
    'machines': [{'name': 'optiplex', 'state': 'ok', 'verdict': 'fine', 'problems': []},
                 {'name': 'wolkhost', 'state': 'warn', 'verdict': 'disk 91%',
                  'problems': ['disk 91%', 'swap in use']},
                 {'name': 'delta', 'state': 'rebooting', 'verdict': 'back soon', 'problems': []}],
    'sites': [{'name': 'wolklaw.dev', 'url': 'https://wolklaw.dev', 'state': 'ok',
               'status': 200, 'ms': 85},
              {'name': 'nova', 'url': 'https://nova.wolklaw.dev', 'state': 'down',
               'status': None, 'ms': None}]}


class ConnectStatusParsing(unittest.TestCase):
    def test_parses_a_document(self):
        s = connectstatus.parse_status(json.dumps(STATUS))
        self.assertEqual(s['summary'], 'warn')
        self.assertEqual(len(s['machines']), 3)
        self.assertEqual(s['machines'][1]['problems'], ['disk 91%', 'swap in use'])
        self.assertEqual(s['sites'][1]['status'], None)
        self.assertEqual(connectstatus.problem_count(s), 2)     # one machine, one site
        self.assertEqual(connectstatus.widget_state(s), 'warn')

    def test_rejects_and_fills_in(self):
        for bad in ('', 'nope', '[]', '5', 'null'):
            self.assertIsNone(connectstatus.parse_status(bad), bad)
        s = connectstatus.parse_status(json.dumps(
            {'summary': 'fine?', 'machines': ['x', {'name': 'a', 'state': 'odd'}],
             'sites': 3, 'checked': 'soon'}))
        self.assertEqual(s['summary'], 'empty')
        self.assertEqual(s['machines'], [{'name': 'a', 'state': 'warn', 'verdict': '',
                                          'problems': []}])
        self.assertEqual((s['sites'], s['checked']), ([], None))
        self.assertEqual(connectstatus.widget_state(s), 'unknown')
        self.assertEqual(connectstatus.widget_state(None), 'unknown')

    def test_summary_text(self):
        s = connectstatus.parse_status(json.dumps(STATUS))
        self.assertEqual(connectstatus.summary_text(s, 'en'),
                         'Spark Connect: 2 problems (wolkhost, nova)')
        self.assertIn('2 problèmes', connectstatus.summary_text(s, 'fr'))
        ok = connectstatus.parse_status(json.dumps({'summary': 'ok', 'machines': [], 'sites': []}))
        self.assertEqual(connectstatus.summary_text(ok, 'en'),
                         'Spark Connect: everything is fine.')
        self.assertEqual(connectstatus.summary_text(None, 'en'), 'Spark Connect: checking...')
        empty = connectstatus.parse_status('{"summary": "empty"}')
        self.assertIn('nothing to watch', connectstatus.summary_text(empty, 'en'))
        one = connectstatus.parse_status(json.dumps(
            {'summary': 'down', 'machines': [{'name': 'a', 'state': 'down'}]}))
        self.assertEqual(connectstatus.summary_text(one, 'en'), 'Spark Connect: 1 problem (a)')

    def test_site_text(self):
        s = connectstatus.parse_status(json.dumps(STATUS))
        self.assertEqual(connectstatus.site_text(s['sites'][0]), '200, 85 ms')
        self.assertEqual(connectstatus.site_text(s['sites'][1]), 'down')

    def test_host_connector(self):
        self.assertEqual(connectstatus.host_connector('DP-2', ['DP-1', 'DP-2'], 'DP-1'), 'DP-2')
        self.assertEqual(connectstatus.host_connector('', ['DP-1', 'DP-2'], 'DP-1'), 'DP-1')
        self.assertEqual(connectstatus.host_connector('HDMI-9', ['DP-1'], 'DP-1'), 'DP-1')

    def test_every_new_string_has_french(self):
        from sparkshell.strings import STRINGS
        self.assertEqual(sorted(set(STRINGS['en']) - set(STRINGS['fr'])), [])
        for key, text in STRINGS['en'].items():
            self.assertEqual(text.count('%s') + text.count('%d'),
                             STRINGS['fr'][key].count('%s') + STRINGS['fr'][key].count('%d'), key)
