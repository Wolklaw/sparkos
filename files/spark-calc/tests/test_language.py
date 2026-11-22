"""The French interface: every sentence translated with the same blanks, the language taken
from the PC, the decimal comma, and text that fits. Runs in both languages (SPARK_LANG)."""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-calc-{var.lower()}-'))
os.environ['SPARK_CALC_REDUCED_MOTION'] = '1'

from langcheck import clipped, table_problems  # noqa: E402
from sparkcalc import editing as E, engine, programmer, text  # noqa: E402
from sparkcalc.engine import CalcError  # noqa: E402
from sparkcalc.lang import ui_language  # noqa: E402


class Tables(unittest.TestCase):
    def test_french_is_complete(self):
        self.assertEqual(table_problems(text.EN, text.FR), [])

    def test_errors_are_sentences_in_both(self):
        for table in (text.EN, text.FR):
            for key, value in table.items():
                if key.startswith('err.'):
                    self.assertTrue(value.endswith('.'), key)


class PickTheLanguage(unittest.TestCase):
    def test_from_the_locale(self):
        cases = [({'LANG': 'fr_CA.UTF-8'}, 'fr'), ({'LANG': 'en_CA.UTF-8'}, 'en'),
                 ({'LC_MESSAGES': 'fr_FR.UTF-8', 'LANG': 'en_US.UTF-8'}, 'fr'),
                 ({'LC_ALL': 'en_US.UTF-8', 'LC_MESSAGES': 'fr_CA.UTF-8'}, 'en'),
                 ({'LC_ALL': 'fr_CA'}, 'fr'), ({'LANG': 'C.UTF-8'}, 'en'), ({}, 'en'),
                 ({'LANG': 'fr_CA.UTF-8', 'SPARK_LANG': 'en'}, 'en'),
                 ({'LANG': 'C', 'SPARK_LANG': 'fr'}, 'fr'),
                 ({'LANG': 'fr_CA.UTF-8', 'SPARK_LANG': 'de'}, 'fr')]
        for env, want in cases:
            with self.subTest(env=env):
                self.assertEqual(ui_language(env), want)

    def test_spark_lang_picks_the_table(self):
        want = os.environ.get('SPARK_LANG')
        if want in ('en', 'fr'):
            self.assertEqual(text.LANG, want)
            self.assertEqual(text.DECIMAL, ',' if want == 'fr' else '.')


class DecimalComma(unittest.TestCase):
    def ev(self, s, **kw):
        return engine.evaluate(s, comma=True, **kw)

    def test_one_comma_five_plus_two(self):
        r = self.ev('1,5 + 2')
        self.assertEqual(r.value, engine.Fraction(7, 2))
        self.assertEqual(r.text, '3,5')

    def test_semicolons_separate_and_the_point_still_works(self):
        self.assertEqual(self.ev('round(2,5; 0)').text, '3')
        self.assertEqual(self.ev('round(2.5, 0)').text, '3')       # typed or saved in English
        self.assertEqual(self.ev('round(2.55,1)').text, '2,6')
        self.assertEqual(self.ev('root(27; 3)').text, '3')
        self.assertEqual(self.ev('log(8; 2)').text, '3')
        self.assertEqual(self.ev('0.1+0,2').text, '0,3')
        self.assertEqual(self.ev('1,5e+3').text, '1500')
        self.assertEqual(self.ev('1/3').text, '0,33333333333333333333')

    def test_round_trips(self):
        third = self.ev('1/3')
        known = {third.text: third.value}
        self.assertEqual(self.ev(third.text + '×3', known=known).text, '1')
        small = self.ev('2^-70').text
        self.assertEqual(self.ev(small).text, small)

    def test_english_is_unchanged(self):
        self.assertEqual(engine.evaluate('round(2.5, 0)').text, '3')
        self.assertEqual(engine.evaluate('1.5+2').text, '3.5')
        with self.assertRaises(CalcError):
            engine.evaluate('1,5 + 2')                             # "," separates: unexpected

    def test_programmer_mode_says_whole_numbers(self):
        with self.assertRaises(CalcError) as caught:
            programmer.evaluate('1,5', 10, 64, 0, True)
        self.assertEqual(caught.exception.key, 'whole')

    def test_never_eval(self):
        for name in ('engine.py', 'programmer.py', 'editing.py', 'app.py', 'cli.py'):
            with open(os.path.join(os.path.dirname(HERE), 'sparkcalc', name),
                      encoding='utf-8') as f:
                source = f.read()
            self.assertNotIn(' eval(', source, name)
            self.assertNotIn('builtins', source, name)


class FrenchKeys(unittest.TestCase):
    def setUp(self):
        self.was, E.COMMA = E.COMMA, True

    def tearDown(self):
        E.COMMA = self.was

    def test_operand_spans_the_comma(self):
        self.assertEqual(E.operand_start('2+1,5', 5), 2)
        self.assertEqual(E.postfix('2+1,5', 5, '²'), ('2+1,5²', 6))
        self.assertEqual(E.prefix('1,5', 3, '√'), ('√1,5', 4))

    def test_root_uses_a_semicolon(self):
        text_, cur = E.open_call('27', 2, 'root(')
        self.assertEqual((text_, cur), ('root(27; ', 9))
        self.assertEqual(engine.evaluate(text_ + '3', comma=True).text, '3')

    def test_paste_drops_french_grouping(self):
        self.assertEqual(E.clean_paste('1 234 567,89'), '1234567,89')
        self.assertEqual(E.clean_paste('1 234,5'), '1234,5')
        self.assertEqual(E.clean_paste('1,23'), '1,23')

    def test_comma_starts_a_new_sum(self):
        self.assertTrue(E.starts_fresh(','))


try:
    import tkinter as tk
    _probe = tk.Tk()
    _probe.destroy()
    DISPLAY = True
except Exception:  # noqa: BLE001 - no display, or no Tk at all
    DISPLAY = False


@unittest.skipUnless(DISPLAY, "needs a display")
class Window(unittest.TestCase):
    def setUp(self):
        from sparkcalc.app import App
        self.app = App('standard')
        self.app.root.update()

    def tearDown(self):
        try:
            self.app.close()
        except tk.TclError:
            pass

    def test_decimal_key_types_the_pcs_mark(self):
        keys = {k.action for k in self.app.pad.keys}
        self.assertIn('ins:' + text.DECIMAL, keys)
        for action in ('ins:1', 'ins:' + text.DECIMAL, 'ins:5', 'ins:+', 'ins:2'):
            self.app.press(action)
        self.app.equals()
        self.assertEqual(self.app.entry.get(), '3' + text.DECIMAL + '5')

    def test_keypad_decimal_key(self):
        from types import SimpleNamespace
        other = '.' if text.DECIMAL == ',' else ','       # the layout gives the other mark
        self.app._on_key(SimpleNamespace(state=0, char=other, keysym='KP_Decimal'))
        self.assertEqual(self.app.entry.get(), text.DECIMAL)

    def test_text_fits_in_every_mode(self):
        root = self.app.root
        sizes = (('%dx%d' % root.minsize(), False), ('620x600', True))
        for size, history in sizes:          # the smallest window has no room for history
            if self.app.history_on != history:
                self.app.toggle_history()
            root.geometry(size)
            for mode in ('standard', 'scientific', 'programmer'):
                self.app.set_mode(mode)
                with self.subTest(size=size, mode=mode):
                    self.assertEqual(clipped(root), [])
        self.app.set_mode('standard')
        root.geometry(sizes[0][0])
        longest = [text.t('status.rounded', digits=engine.DISPLAY), text.t('status.error'),
                   text.t('status.wrapped', bits=64), text.t('status.memory'),
                   text.t('status.nothing'), text.t('status.crashed')]
        for message in longest:
            with self.subTest(status=message):
                self.app.set_status(message, 'white')
                self.assertEqual(clipped(root), [])
