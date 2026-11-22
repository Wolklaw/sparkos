"""What the keys do to the text being typed (no display needed)."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from sparkcalc import editing as E  # noqa: E402
from sparkcalc.engine import evaluate  # noqa: E402


def setUpModule():
    global _COMMA
    _COMMA, E.COMMA = E.COMMA, False      # these are the English keys; test_language has the French


def tearDownModule():
    E.COMMA = _COMMA


def at_end(fn, text, *args, **kw):
    return fn(text, len(text), *args, **kw)


class Operand(unittest.TestCase):
    def test_finds_the_number_before_the_cursor(self):
        cases = [('2+35', 2), ('12', 0), ('2+sin(30)', 2), ('(1+2)', 0), ('3×(1+(2))', 2),
                 ('2+pi', 2), ('1.5e+25', 0), ('2-1.5e-3', 2), ('4!', 0), ('2+5²', 2),
                 ('7 ', 0), ('ans', 0), ('2×ans', 2)]
        for text, start in cases:
            with self.subTest(text=text):
                self.assertEqual(E.operand_start(text, len(text)), start)

    def test_no_operand(self):
        for text in ('', '2+', '(', '3×', '5 mod ', '2^', '1+)'[:2]):
            with self.subTest(text=text):
                self.assertIsNone(E.operand_start(text, len(text)))
        self.assertIsNone(E.operand_start('1+2)', 4))       # no matching (

    def test_programmer_words(self):
        self.assertEqual(E.operand_start('FF and 0x1F', 11, programmer=True), 7)
        self.assertIsNone(E.operand_start('FF and ', 7, programmer=True))
        self.assertIsNone(E.operand_start('FF and', 6, programmer=True))


class Keys(unittest.TestCase):
    def test_prefix_wraps_or_starts(self):
        self.assertEqual(at_end(E.prefix, '30', 'sin('), ('sin(30)', 7))
        self.assertEqual(at_end(E.prefix, '2+30', 'sin('), ('2+sin(30)', 9))
        self.assertEqual(at_end(E.prefix, '2+', 'sin('), ('2+sin(', 6))
        self.assertEqual(at_end(E.prefix, '', '√'), ('√', 1))
        self.assertEqual(at_end(E.prefix, '9', '√'), ('√9', 2))
        self.assertEqual(at_end(E.prefix, '(2+7)', '√'), ('√(2+7)', 6))
        self.assertEqual(at_end(E.prefix, '-9', '√'), ('√(-9)', 5))
        self.assertEqual(at_end(E.prefix, '5²', '√'), ('√(5²)', 5))
        self.assertEqual(at_end(E.prefix, '5', '~', programmer=True), ('~5', 2))
        text, cur = E.prefix('9+16', 1, '√')            # cursor after the 9
        self.assertEqual((text, cur), ('√9+16', 2))

    def test_wrap(self):
        self.assertEqual(at_end(E.wrap, '9', '(1/', ')'), ('(1/9)', 5))
        self.assertEqual(at_end(E.wrap, '2÷9', '(1/', ')'), ('2÷(1/9)', 7))
        self.assertEqual(evaluate(at_end(E.wrap, '2÷9', '(1/', ')')[0]).text, '18')
        self.assertEqual(at_end(E.wrap, '', '(1/', ')'), ('(1/', 3))

    def test_postfix(self):
        self.assertEqual(at_end(E.postfix, '5', '²'), ('5²', 2))
        self.assertEqual(at_end(E.postfix, '5 ', '²'), ('5²', 2))
        self.assertEqual(at_end(E.postfix, '-5', '²'), ('(-5)²', 5))
        self.assertEqual(evaluate(at_end(E.postfix, '-5', '²')[0]).text, '25')
        self.assertEqual(at_end(E.postfix, '3-5', '²'), ('3-5²', 4))
        self.assertEqual(at_end(E.postfix, '2+', '²'), ('2+', 2))
        self.assertEqual(at_end(E.postfix, '', '!'), ('', 0))
        self.assertEqual(at_end(E.postfix, '200+10', '%'), ('200+10%', 7))

    def test_negate(self):
        self.assertEqual(at_end(E.negate, '5'), ('-5', 2))
        self.assertEqual(at_end(E.negate, '-5'), ('5', 1))
        self.assertEqual(at_end(E.negate, '3+5'), ('3-5', 3))
        self.assertEqual(at_end(E.negate, '3-5'), ('3+5', 3))
        self.assertEqual(at_end(E.negate, '3×5'), ('3×-5', 4))
        self.assertEqual(at_end(E.negate, '3×-5'), ('3×5', 3))
        self.assertEqual(at_end(E.negate, '(-5)'), ('-(-5)', 5))
        self.assertEqual(at_end(E.negate, ''), ('-', 1))
        self.assertEqual(at_end(E.negate, '2+'), ('2+-', 3))
        # ± changes the sign of the last number, like a calculator's +/- key
        self.assertEqual(at_end(E.negate, '2^3'), ('2^-3', 4))
        for text in ('7', '3×5', '(2+3)', '1.5e+25', '4!'):
            with self.subTest(text=text):
                once = E.negate(text, len(text))[0]
                self.assertEqual(evaluate(once).value, -evaluate(text).value)
                twice = at_end(E.negate, once)[0]
                self.assertEqual(evaluate(twice).value, evaluate(text).value)

    def test_open_call(self):
        self.assertEqual(at_end(E.open_call, '27', 'root('), ('root(27, ', 9))
        self.assertEqual(at_end(E.open_call, '', 'root('), ('root(', 5))
        self.assertEqual(evaluate(at_end(E.open_call, '27', 'root(')[0] + '3').text, '3')

    def test_clear_entry(self):
        self.assertEqual(at_end(E.clear_entry, '12+345'), ('12+', 3))
        self.assertEqual(at_end(E.clear_entry, '12×-3'), ('12×', 3))
        self.assertEqual(at_end(E.clear_entry, '12+'), ('12+', 3))

    def test_backspace(self):
        self.assertEqual(E.backspace('123', 3), ('12', 2))
        self.assertEqual(E.backspace('123', 0), ('123', 0))
        self.assertEqual(E.backspace('123', 2), ('13', 1))
        self.assertEqual(E.backspace('12345', 5, (1, 3)), ('145', 1))
        self.assertEqual(E.backspace('5 and ', 6), ('5', 1))
        self.assertEqual(E.backspace('5 mod ', 6), ('5', 1))
        self.assertEqual(E.backspace('hand', 4), ('han', 3))

    def test_starts_fresh(self):
        for ch in '7.(πa√':
            self.assertTrue(E.starts_fresh(ch), ch)
        for ch in '+-×÷^!%) ':
            self.assertFalse(E.starts_fresh(ch), ch)

    def test_clean_paste(self):
        self.assertEqual(E.clean_paste('1,234,567.89'), '1234567.89')
        self.assertEqual(E.clean_paste('  2 +\n3 '), '2 + 3')
        self.assertEqual(E.clean_paste('root(8, 3)'), 'root(8, 3)')
        self.assertEqual(E.clean_paste('-12,000'), '-12000')
        self.assertEqual(E.clean_paste('1,23'), '1,23')        # not thousands: left alone


if __name__ == '__main__':
    unittest.main()
