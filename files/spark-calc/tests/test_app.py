"""The window, driven the way a person would: keys, the keyboard, memory, history, modes.
Needs a display (on CI: xvfb-run); skipped without one."""

import json
import logging
import os
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
    os.environ[var] = tempfile.mkdtemp(prefix=f'spark-calc-{var.lower()}-')
os.environ['SPARK_CALC_REDUCED_MOTION'] = '1'

import tkinter as tk  # noqa: E402

from sparkcalc import core  # noqa: E402

core.log.addHandler(logging.NullHandler())        # the deliberate error below stays quiet
from sparkcalc.widgets import T  # noqa: E402
from sparkcalc.text import DECIMAL, t  # noqa: E402


def num(s):
    """'0.5' as the window shows it: '0,5' in French."""
    return s.replace('.', DECIMAL)

try:
    _probe = tk.Tk()
    _probe.destroy()
    DISPLAY = True
except tk.TclError:
    DISPLAY = False


@unittest.skipUnless(DISPLAY, "needs a display")
class Window(unittest.TestCase):
    def setUp(self):
        for name in ('config.json',):
            path = os.path.join(core.config_dir(), name)
            if os.path.exists(path):
                os.remove(path)
        path = os.path.join(core.state_dir(), 'history.json')
        if os.path.exists(path):
            os.remove(path)
        from sparkcalc.app import App
        self.app = App('standard')
        self.app.root.update()

    def tearDown(self):
        try:
            self.app.close()
        except tk.TclError:
            pass

    # helpers
    def keys(self, *actions):
        for a in actions:
            self.app.press(a)
        self.app.root.update_idletasks()

    def type(self, text):
        for ch in text:
            self.app.press('ins:' + ch)

    @property
    def shown(self):
        return self.app.entry.get()

    def test_opens_quickly_in_every_mode(self):
        from sparkcalc.app import App
        self.app.close()
        for mode in ('standard', 'scientific', 'programmer'):
            start = time.perf_counter()
            self.app = App(mode)
            self.app.root.update()
            took = time.perf_counter() - start
            with self.subTest(mode=mode):
                self.assertLess(took, 1.5)          # the 0.3 s target is measured by --bench
                self.assertEqual(len(self.app.pad.keys), {'standard': 24, 'scientific': 42,
                                                          'programmer': 36}[mode])
            self.app.close()
        self.app = App('standard')

    def test_keys_work_a_sum_out(self):
        self.keys('ins:1', 'ins:2', 'ins:×', 'ins:3', 'ins:+', 'ins:4', 'eq')
        self.assertEqual(self.shown, '40')
        self.assertTrue(self.app.fresh)
        self.assertEqual(self.app.line.cget('text'), '12×3+4 =')
        self.assertEqual(self.app.status.cget('text'), t('status.exact'))

    def test_point_one_plus_point_two(self):
        self.type('0.1+0.2')
        self.keys('eq')
        self.assertEqual(self.shown, num('0.3'))

    def test_live_preview(self):
        self.type('2+3')
        self.app.root.update_idletasks()
        self.assertEqual(self.app.line.cget('text'), '= 5')
        self.type('×')
        self.assertEqual(self.app.line.cget('text'), '')          # unfinished: no preview

    def test_after_equals_digits_start_over_and_operators_carry_on(self):
        self.type('6×7')
        self.keys('eq')
        self.keys('ins:+', 'ins:1', 'eq')
        self.assertEqual(self.shown, '43')
        self.keys('ins:5')
        self.assertEqual(self.shown, '5')

    def test_rounded_answers_keep_their_exact_value(self):
        self.type('1÷3')
        self.keys('eq')
        self.assertEqual(self.shown, num('0.33333333333333333333'))
        self.assertEqual(self.app.note.cget('text'), t('display.rounded', digits=20))
        self.keys('ins:×', 'ins:3', 'eq')
        self.assertEqual(self.shown, '1')

    def test_unary_keys_act_on_the_answer(self):
        self.type('9')
        self.keys('eq', 'pre:√', 'eq')
        self.assertEqual(self.shown, '3')
        self.keys('post:²', 'eq')
        self.assertEqual(self.shown, '9')
        self.keys('wrap:(1/|)', 'eq')
        self.assertEqual(self.shown, num('0.11111111111111111111'))
        self.keys('neg', 'eq')
        self.assertEqual(self.shown, num('-0.11111111111111111111'))

    def test_percent_key(self):
        self.type('200+10')
        self.keys('post:%', 'eq')
        self.assertEqual(self.shown, '220')

    def test_clear_keys(self):
        self.type('12+345')
        self.keys('ce')
        self.assertEqual(self.shown, '12+')
        self.keys('back')
        self.assertEqual(self.shown, '12')
        self.keys('clear')
        self.assertEqual(self.shown, '')

    def test_error_glitches_and_says_why(self):
        self.type('1÷0')
        self.keys('eq')
        self.assertEqual(self.app.note.cget('text'), t('err.div_zero'))
        self.assertEqual(self.app.note.cget('fg'), T["pink"])
        self.assertEqual(self.app.status.cget('text'), t('status.error'))
        self.assertEqual(self.shown, '1÷0')                 # left to fix
        self.assertEqual(self.app.entry.index('insert'), 1)
        self.assertEqual(self.app.history, [])
        self.keys('back')                                        # editing clears the message
        self.assertEqual(self.app.note.cget('text'), '')

    def test_history(self):
        self.type('2+2')
        self.keys('eq')
        self.type('×10')
        self.keys('eq')
        self.assertEqual([h['result'] for h in self.app.history], ['4', '40'])
        with open(os.path.join(core.state_dir(), 'history.json'), encoding='utf-8') as f:
            saved = json.load(f)
        self.assertEqual(saved[-1]['expr'], '4×10')
        text = self.app.htext.get('1.0', 'end')
        self.assertLess(text.index('40'), text.index('2+2'))     # newest first
        self.app._use_expr(0)
        self.assertEqual(self.shown, '2+2')
        self.assertFalse(self.app.fresh)
        self.keys('ins:+')
        self.app._use_result(1)
        self.assertEqual(self.shown, '2+2+40')
        self.app._recall(-1)
        self.assertEqual(self.shown, '4×10')
        self.app._recall(-1)
        self.assertEqual(self.shown, '2+2')
        self.app._recall(1)
        self.assertEqual(self.shown, '4×10')
        self.app.clear_history()
        self.assertEqual(self.app.history, [])
        self.assertIn(t('history.empty'), self.app.htext.get('1.0', 'end'))

    def test_history_clicks_find_the_item_under_the_pointer(self):
        from types import SimpleNamespace
        for s in ('1+1', '2+2', '3+3'):
            self.app.press('clear')
            self.type(s)
            self.keys('eq')
        self.app.root.update()
        h = self.app.htext

        def at(tag):
            x, y, w, hh = h.bbox(h.tag_ranges(tag)[0])
            return SimpleNamespace(x=x + w // 2, y=y + hh // 2)

        self.app._history_motion(at('r1'))
        self.assertEqual(h.tag_ranges('hover'), h.tag_ranges('r1'))
        self.app._history_motion(None)
        self.assertEqual(h.tag_ranges('hover'), ())
        self.keys('clear')
        self.app._history_click(at('e1'))
        self.assertEqual(self.shown, '2+2')
        self.keys('ins:×')
        self.app._history_click(at('r2'))
        self.keys('eq')
        self.assertEqual(self.shown, '14')                       # 2+2×6

    def test_history_panel_toggles(self):
        self.assertTrue(self.app.history_on)
        self.app.toggle_history()
        self.assertFalse(self.app.hist.winfo_ismapped())
        self.app.toggle_history()
        self.app.root.update()
        self.assertTrue(self.app.hist.winfo_ismapped())

    def test_memory(self):
        self.type('5')
        self.app.memory_key('store')
        self.assertEqual(self.app.mem_label.cget('text'), 'M  5')
        self.keys('clear')
        self.type('3')
        self.app.memory_key('add')
        self.assertEqual(self.app.mem_label.cget('text'), 'M  8')
        self.app.memory_key('sub')
        self.app.memory_key('sub')
        self.assertEqual(self.app.mem_label.cget('text'), 'M  2')
        self.keys('clear', 'ins:1', 'ins:0', 'ins:×')
        self.app.memory_key('recall')
        self.keys('eq')
        self.assertEqual(self.shown, '20')
        self.app.memory_key('clear')
        self.assertEqual(self.app.mem_label.cget('text'), '')

    def test_memory_refuses_a_broken_sum(self):
        self.type('2+')
        self.app.memory_key('store')
        self.assertIsNone(self.app.memory)
        self.assertEqual(self.app.note.cget('fg'), T["pink"])

    def test_copy_and_paste(self):
        self.type('6×7')
        self.app.copy()
        self.assertEqual(self.app.root.clipboard_get(), '42')       # before = too
        self.keys('eq')
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append('1 234,5' if DECIMAL == ',' else '1,234.5')
        self.app.paste()                                             # replaces the answer
        self.assertEqual(self.shown, num('1234.5'))
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append('+0.5\n')
        self.app.paste()
        self.keys('eq')
        self.assertEqual(self.shown, '1235')

    def test_scientific(self):
        self.app.set_mode('scientific')
        self.type('30')
        self.keys('pre:sin(', 'eq')
        self.assertEqual(self.shown, num('0.5'))
        self.app.set_angle('rad')
        self.keys('clear', 'ins:π')
        self.keys('pre:cos(', 'eq')
        self.assertEqual(self.shown, '-1')
        self.type('27')
        self.keys('pre:root(|', 'ins:3', 'eq')
        self.assertEqual(self.shown, '3')
        self.assertTrue(self.app.angle_seg.winfo_ismapped())

    def test_programmer(self):
        app = self.app
        app.set_mode('programmer')
        app.set_bits(8)
        app.set_base(16)
        self.keys('ins:7', 'ins:F', 'ins:+', 'ins:1', 'eq')
        self.assertEqual(self.shown, '80')
        self.assertEqual(app.note.cget('text'), t('display.wrapped', bits=8))
        self.assertEqual(app.row_parts[10][2].cget('text'), '-128')
        self.assertEqual(app.row_parts[2][2].cget('text'), '1000 0000')
        app.set_base(2)
        self.assertEqual(self.shown, '10000000')
        digit = {k.action: k for k in app.pad.keys}
        self.assertFalse(digit['ins:2'].enabled)
        self.assertFalse(digit['ins:A'].enabled)
        self.assertTrue(digit['ins:1'].enabled)
        app.set_base(10)
        self.assertEqual(self.shown, '-128')
        self.assertTrue(digit['ins:9'].enabled)
        app.set_bits(16)
        self.keys('ins: and ', 'ins:1', 'ins:5', 'eq')
        self.assertEqual(self.shown, '0')
        self.keys('clear', 'ins:1')
        self.keys('ins: << ', 'ins:4', 'eq')
        self.assertEqual(self.shown, '16')

    def test_switching_modes_carries_the_value(self):
        self.type('255')
        self.keys('eq')
        self.app.set_mode('programmer')
        self.app.set_base(16)
        self.assertEqual(self.shown, 'FF')
        self.app.set_mode('standard')
        self.assertEqual(self.shown, '255')
        self.type('/2')
        self.keys('eq')
        self.app.set_mode('programmer')
        self.app.set_base(10)
        self.assertEqual(self.shown, '127')                       # decimals dropped

    def test_keyboard(self):
        app = self.app
        app.root.focus_force()
        app.entry.focus_force()
        app.root.update()
        if app.root.focus_get() is not app.entry:
            self.skipTest("the display gives no keyboard focus")
        for keysym in ('2', 'asterisk', '3', 'equal'):
            app.entry.event_generate('<KeyPress>', keysym=keysym)
        app.root.update()
        self.assertEqual(self.shown, '6')
        app.entry.event_generate('<KeyPress>', keysym='Escape')
        app.root.update()
        self.assertEqual(self.shown, '')
        for keysym in ('9', 'minus', '4', 'Return'):
            app.entry.event_generate('<KeyPress>', keysym=keysym)
        app.root.update()
        self.assertEqual(self.shown, '5')
        app.entry.event_generate('<Control-Key-3>')
        app.root.update()
        self.assertEqual(app.mode, 'programmer')

    def test_settings_are_kept(self):
        from sparkcalc.app import App
        self.app.set_mode('programmer')
        self.app.set_bits(16)
        self.app.set_base(2)
        self.app.close()
        self.app = App()
        self.assertEqual((self.app.mode, self.app.bits, self.app.base), ('programmer', 16, 2))

    def test_callback_errors_are_logged_not_shown(self):
        self.app._on_tk_error(ValueError, ValueError("boom"), None)
        self.assertEqual(self.app.status.cget('text'), t('status.crashed'))


if __name__ == '__main__':
    unittest.main()
