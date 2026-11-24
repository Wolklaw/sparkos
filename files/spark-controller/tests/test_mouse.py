"""The Mouse tab's backend and window, against a fake ratbagd. Nothing here writes to a real
mouse. The warning for a mouse stuck on a disabled 100 DPI slot is the one that happened."""

import os
import shutil
import tempfile
import time
import unittest

import support
from sparkcontroller import mouse
from sparkcontroller.mouse import MouseError, RatbagBackend
from fakeratbag import G502, STUCK_LOW, FakeRatbag

DISPLAY = False
try:
    import tkinter as tk
    tk.Tk().destroy()
    DISPLAY = bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))
except Exception:  # noqa: BLE001
    pass


def backend(fake):
    return RatbagBackend(fake, settle_s=0)


class Reading(unittest.TestCase):
    def test_a_g502_is_read_whole(self):
        mice = backend(FakeRatbag()).list_mice()
        self.assertEqual(len(mice), 1)
        m = mice[0]
        self.assertEqual(m.name, 'Logitech G502 HERO Gaming Mouse')
        self.assertEqual([p.index for p in m.profiles], [0, 1, 2])
        self.assertEqual(m.active_profile.index, 2)
        first = m.profiles[0]
        self.assertEqual([(s.value, s.enabled) for s in first.slots],
                         [(1200, True), (2400, True), (3200, True), (6400, True), (100, False)])
        self.assertEqual((first.active_slot.index, first.default_slot.index), (1, 1))
        self.assertEqual((first.rate, first.rates), (1000, [125, 250, 500, 1000]))
        self.assertTrue(first.slots[0].can_disable)

    def test_reading_writes_nothing(self):
        fake = FakeRatbag()
        backend(fake).list_mice()
        self.assertEqual(fake.writes, [])

    def test_x_and_y_apart_use_x(self):
        self.assertEqual(mouse.dpi_of((1600, 800)), 1600)
        self.assertEqual(mouse.dpi_of(1600), 1600)
        self.assertEqual(mouse.dpi_of(None), 0)

    def test_two_mice(self):
        self.assertEqual(len(backend(FakeRatbag(devices=2)).list_mice()), 2)

    def test_no_mouse_is_an_empty_list(self):
        fake = FakeRatbag()
        fake.objects[mouse.MANAGER_PATH][mouse.I_MANAGER]['Devices'] = []
        self.assertEqual(backend(fake).list_mice(), [])

    def test_a_daemon_that_is_not_there(self):
        with self.assertRaises(MouseError) as ctx:
            backend(FakeRatbag(down=True)).list_mice()
        self.assertEqual(ctx.exception.kind, mouse.NO_DAEMON)


class Helpers(unittest.TestCase):
    ALLOWED = [100, 400, 800, 1600, 2400, 3200]

    def test_nearest_and_step(self):
        self.assertEqual(mouse.nearest(self.ALLOWED, 2300), 2400)
        self.assertEqual(mouse.nearest(self.ALLOWED, 5000), 3200)
        self.assertEqual(mouse.nearest([], 2300), 2300)
        self.assertEqual(mouse.step(self.ALLOWED, 800, 1), 1600)
        self.assertEqual(mouse.step(self.ALLOWED, 800, -1), 400)
        self.assertEqual(mouse.step(self.ALLOWED, 3200, 1), 3200)
        self.assertEqual(mouse.step(self.ALLOWED, 100, -1), 100)
        self.assertEqual(mouse.step(self.ALLOWED, 1000, 1), 1600)    # a value off the list

    def test_validation(self):
        m = backend(FakeRatbag()).list_mice()[0]
        self.assertEqual(mouse.validate(m, m), [])
        bad = m.clone()
        bad.profiles[0].slots[0].value = 1234
        bad.profiles[0].rate = 333
        keys = [k for k, _ in mouse.validate(bad, m)]
        self.assertEqual(sorted(keys), ['mouse.bad_dpi', 'mouse.bad_rate'])

    def test_off_list_value_already_on_the_mouse_is_fine(self):
        m = backend(FakeRatbag()).list_mice()[0]
        self.assertEqual(m.profiles[0].slots[3].value, 6400)       # the list has 6500
        self.assertEqual(mouse.validate(m, m), [])
        self.assertEqual(mouse.step(m.profiles[0].slots[3].allowed, 6400, 1), 6500)

    def test_a_slot_cannot_be_active_while_off(self):
        m = backend(FakeRatbag()).list_mice()[0]
        m.profiles[0].slots[1].enabled = False        # the active and default one
        self.assertEqual(sorted(k for k, _ in mouse.validate(m, m)),
                         ['mouse.active_off', 'mouse.default_off'])

    def test_one_slot_must_stay_on(self):
        m = backend(FakeRatbag()).list_mice()[0]
        for s in m.profiles[2].slots:
            s.enabled = False
        self.assertIn('mouse.no_slot_on', [k for k, _ in mouse.validate(m, m)])

    def test_the_active_profile_must_be_on(self):
        m = backend(FakeRatbag()).list_mice()[0]
        mouse.set_active_profile(m, 1)
        self.assertEqual(mouse.validate(m, m), [])
        m.profiles[1].enabled = False
        self.assertEqual([k for k, _ in mouse.validate(m, m)], ['mouse.bad_profile'])


class LowDpiWarning(unittest.TestCase):
    def read(self, layout):
        return backend(FakeRatbag(layout)).list_mice()[0]

    def test_a_healthy_mouse_has_no_warning(self):
        for p in self.read(G502).profiles:
            self.assertIsNone(mouse.low_dpi_problem(p))

    def test_sitting_on_a_disabled_slot_is_the_bug(self):
        m = self.read(STUCK_LOW)
        self.assertEqual(mouse.low_dpi_problem(m.profiles[0]), ('off', 100))
        self.assertEqual(mouse.suggestion(m.profiles[0]), 2400)

    def test_a_slow_enabled_slot_is_warned_about(self):
        m = self.read(G502)
        slot = m.profiles[0].active_slot
        slot.value = 300
        self.assertEqual(mouse.low_dpi_problem(m.profiles[0]), ('low', 300))
        slot.value = 400
        self.assertIsNone(mouse.low_dpi_problem(m.profiles[0]))

    def test_the_fix_turns_the_slot_on_at_2400_and_nothing_is_written_yet(self):
        fake = FakeRatbag(STUCK_LOW)
        m = backend(fake).list_mice()[0]
        edited = m.clone()
        mouse.apply_low_dpi_fix(edited.profiles[0])
        self.assertIsNone(mouse.low_dpi_problem(edited.profiles[0]))
        self.assertEqual(mouse.validate(edited, m), [])
        self.assertEqual(mouse.diff_ops(m, edited),
                         [('value', 0, 4, 2400), ('enable', 0, 4, True)])
        self.assertEqual(fake.writes, [])

    def test_the_suggestion_is_a_value_the_mouse_allows(self):
        m = self.read(STUCK_LOW)
        for s in m.profiles[0].slots:
            s.allowed = [100, 1000, 2000, 3000]
        self.assertEqual(mouse.suggestion(m.profiles[0]), 2000)


class Writing(unittest.TestCase):
    def setUp(self):
        self.fake = FakeRatbag()
        self.be = backend(self.fake)
        self.mouse = self.be.list_mice()[0]

    def test_no_change_no_write_and_no_commit(self):
        self.assertEqual(self.be.apply(self.mouse, self.mouse.clone()), 0)
        self.assertEqual((self.fake.writes, self.fake.commits), ([], 0))

    def test_changes_are_written_then_committed_last(self):
        edited = self.mouse.clone()
        p = edited.profiles[2]
        p.rate = 1000
        p.slots[0].value = 1600
        p.slots[1].value = 800
        p.slots[1].enabled = True
        mouse.set_active_slot(p, 1)
        mouse.set_default_slot(p, 1)
        self.assertEqual(self.be.apply(self.mouse, edited), 6)
        kinds = [(w[0], w[2]) for w in self.fake.writes]
        self.assertEqual(self.fake.commits, 1)
        # values, then the slot on, then the choices, the rate, and the commit last
        self.assertEqual(kinds, [('set', 'Resolution'), ('set', 'Resolution'),
                                 ('set', 'IsDisabled'), ('call', 'SetActive'),
                                 ('call', 'SetDefault'), ('set', 'ReportRate'),
                                 ('call', 'Commit')])
        state = self.fake.state()[2]
        self.assertEqual(state[2], 1000)
        self.assertEqual(state[3][0][0], 1600)
        self.assertEqual(state[3][1], (800, False, True, True))

    def test_a_slot_goes_off_after_it_stops_being_active(self):
        edited = self.mouse.clone()
        p = edited.profiles[0]
        mouse.set_active_slot(p, 0)
        mouse.set_default_slot(p, 0)
        p.slots[1].enabled = False
        names = [op[0] for op in mouse.diff_ops(self.mouse, edited)]
        self.assertEqual(names, ['slot_active', 'slot_default', 'enable'])
        self.be.apply(self.mouse, edited)
        self.assertEqual(self.fake.state()[0][3][1][1], True)

    def test_switching_profile(self):
        edited = self.mouse.clone()
        mouse.set_active_profile(edited, 0)
        self.be.apply(self.mouse, edited)
        self.assertEqual([s[1] for s in self.fake.state()], [True, False, False])

    def test_the_fix_for_the_stuck_mouse_reaches_the_mouse(self):
        fake = FakeRatbag(STUCK_LOW)
        be = backend(fake)
        m = be.list_mice()[0]
        edited = m.clone()
        mouse.apply_low_dpi_fix(edited.profiles[0])
        be.apply(m, edited)
        after = be.list_mice()[0].profiles[0]
        self.assertIsNone(mouse.low_dpi_problem(after))
        self.assertEqual((after.active_slot.value, after.active_slot.enabled), (2400, True))

    def test_an_invalid_value_is_refused_before_anything_is_sent(self):
        edited = self.mouse.clone()
        edited.profiles[0].slots[0].value = 1234
        with self.assertRaises(MouseError):
            self.be.apply(self.mouse, edited)
        self.assertEqual(self.fake.writes, [])

    def test_busy_is_reported_as_busy(self):
        fake = FakeRatbag(refuse_commit=mouse.BUSY)
        be = backend(fake)
        m = be.list_mice()[0]
        edited = m.clone()
        edited.profiles[2].rate = 250
        with self.assertRaises(MouseError) as ctx:
            be.apply(m, edited)
        self.assertEqual(ctx.exception.kind, mouse.BUSY)

    def test_a_commit_that_did_not_stick_is_seen(self):
        fake = FakeRatbag(forget_commit=True)
        be = backend(fake)
        m = be.list_mice()[0]
        edited = m.clone()
        edited.profiles[2].rate = 250
        be.apply(m, edited)
        self.assertNotEqual(mouse.differences(edited, be.reread(m)), [])

    def test_error_codes(self):
        RatbagBackend._check(0)
        with self.assertRaises(MouseError) as ctx:
            RatbagBackend._check((1 << 32) - 16)      # -EBUSY as an unsigned number
        self.assertEqual(ctx.exception.kind, mouse.BUSY)
        with self.assertRaises(MouseError) as ctx:
            RatbagBackend._check((1 << 32) - 5)
        self.assertEqual(ctx.exception.kind, mouse.FAILED)


@unittest.skipUnless(DISPLAY, "needs a display")
class Window(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-controller-mouse-')
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        os.environ['XDG_CONFIG_HOME'] = os.path.join(self.dir, 'config')
        self.tree = os.path.join(self.dir, 'hwmon')
        support.fake_tree(self.tree)

    def pump(self, app, seconds):
        end = time.time() + seconds
        while time.time() < end:
            app.root.update()
            time.sleep(0.02)

    def open(self, fake):
        from sparkcontroller.app import App
        from sparkcontroller.hwmon import Hwmon
        app = App(Hwmon(self.tree), tab='mouse', use_usb=False, mouse_backend=backend(fake))
        self.addCleanup(app.close)
        self.pump(app, 1.0)
        return app, app.views['mouse']

    def test_it_shows_the_mouse_and_writes_nothing(self):
        fake = FakeRatbag()
        app, view = self.open(fake)
        self.assertEqual(view.current.name, 'Logitech G502 HERO Gaming Mouse')
        self.assertEqual(view.profile.index, 2)             # the active profile is shown first
        self.assertEqual(fake.writes, [])
        self.assertEqual(view.warning.cget('text'), '')

    def test_editing_writes_nothing_until_apply(self):
        fake = FakeRatbag()
        app, view = self.open(fake)
        view.step_slot(0, 1)
        view.make_active(0)
        view.set_rate(250)
        self.pump(app, 0.2)
        self.assertEqual(fake.writes, [])
        self.assertTrue(view.apply_button.enabled)
        view.apply()
        self.pump(app, 1.0)
        self.assertEqual(fake.commits, 1)
        self.assertEqual(fake.state()[2][2], 250)
        self.assertFalse(view.apply_button.enabled)

    def test_the_warning_and_its_fix(self):
        fake = FakeRatbag(STUCK_LOW)
        app, view = self.open(fake)
        self.assertIn('2400', view.warning.cget('text'))
        view.fix_dpi()
        self.pump(app, 0.2)
        self.assertEqual(fake.writes, [])                    # staged, not sent
        self.assertEqual(view.warning.cget('text'), '')
        view.apply()
        self.pump(app, 1.0)
        self.assertEqual(fake.state()[0][3][4][:2], (2400, 0))

    def test_no_daemon_and_no_mouse_say_so(self):
        from sparkcontroller.text import t
        app, view = self.open(FakeRatbag(down=True))
        self.assertEqual(view.message.cget('text'), t('mouse.no_daemon'))
        fake = FakeRatbag()
        fake.objects[mouse.MANAGER_PATH][mouse.I_MANAGER]['Devices'] = []
        app2, view2 = self.open(fake)
        self.assertEqual(view2.message.cget('text'), t('mouse.none'))

    def test_busy_is_shown(self):
        from sparkcontroller.text import t
        fake = FakeRatbag(refuse_commit=mouse.BUSY)
        app, view = self.open(fake)
        view.set_rate(250)
        view.apply()
        self.pump(app, 1.0)
        self.assertEqual(view.result.cget('text'), t('mouse.busy'))
        self.assertTrue(view.apply_button.enabled)


if __name__ == '__main__':
    unittest.main()
