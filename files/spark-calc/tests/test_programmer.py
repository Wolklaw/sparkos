"""Programmer mode: bases, word sizes, bitwise operators, and overflow wrapping around."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from sparkcalc import programmer as P  # noqa: E402
from sparkcalc.engine import CalcError  # noqa: E402
from sparkcalc.text import EN  # noqa: E402


def run(expr, base=10, bits=64, ans=0):
    return P.evaluate(expr, base, bits, ans)


class Case(unittest.TestCase):
    def values(self, pairs, base=10, bits=64):
        for expr, want in pairs:
            with self.subTest(expr=expr, base=base, bits=bits):
                self.assertEqual(run(expr, base, bits).value, want)

    def fails(self, expr, key, base=10, bits=64, pos=None):
        with self.assertRaises(CalcError, msg=expr) as cm:
            run(expr, base, bits)
        self.assertEqual(cm.exception.key, key, expr)
        if pos is not None:
            self.assertEqual(cm.exception.pos, pos, expr)
        self.assertIn('err.' + key, EN)
        return cm.exception


class Arithmetic(Case):
    def test_precedence_is_cs(self):
        self.values([('2+3*4', 14), ('(2+3)*4', 20), ('1+2<<3', 24), ('1|2&3', 3), ('1|2^3', 1),
                     ('6&3^1', 3), ('8>>1+1', 2), ('10-4-3', 3), ('100/10/5', 2),
                     ('2*3%4', 2), ('1 or 2 and 3', 3), ('5 xor 1 or 8', 12)])

    def test_division_rounds_toward_zero(self):
        self.values([('7/2', 3), ('-7/2', -3), ('7/-2', -3), ('-7/-2', 3), ('7%3', 1),
                     ('-7%3', -1), ('7%-3', 1), ('-7 mod 3', -1)])

    def test_unary(self):
        self.values([('-5', -5), ('--5', 5), ('~0', -1), ('~5', -6), ('not 0', -1), ('-~0', 1),
                     ('+3', 3), ('~~7', 7)])

    def test_bitwise(self):
        self.values([('12 and 10', 8), ('12 & 10', 8), ('12 or 10', 14), ('12 | 10', 14),
                     ('12 xor 10', 6), ('12 ^ 10', 6), ('12 nand 10', ~8), ('12 nor 10', ~14),
                     ('0xF0 AND 0x3C', 0x30)])

    def test_symbols_from_the_keypad(self):
        self.values([('6×7', 42), ('8÷2', 4), ('9−4', 5)])

    def test_ans(self):
        self.assertEqual(run('ans*2', ans=21).value, 42)
        self.assertEqual(run('ans+1', bits=8, ans=127).value, -128)


class Bases(Case):
    def test_reading(self):
        self.values([('FF', 255), ('ff', 255), ('0x10', 16), ('7F+1', 128), ('A0 and F', 0),
                     ('0o17', 15), ('add', 0xADD), ('b1', 0xB1), ('0b1', 0xB1)], base=16)
        self.values([('17', 15), ('0x10', 16), ('0b11', 3)], base=8)
        self.values([('1010', 10), ('1111_0000', 240), ('0x10', 16)], base=2)
        self.values([('0x1F', 31), ('0o10', 8), ('0b101', 5), ('1_000', 1000)], base=10)

    def test_bad_digits(self):
        e = self.fails('12', 'digit', base=2, pos=1)
        self.assertIn('BIN', e.message())
        self.fails('19', 'digit', base=8, pos=1)
        self.fails('1G', 'digit', base=16, pos=1)
        self.fails('12ab', 'digit', base=10, pos=2)
        self.fails('0b102', 'digit', base=10, pos=4)
        self.fails('0x', 'incomplete')

    def test_showing(self):
        self.assertEqual(P.to_base(-1, 16, 8), 'FF')
        self.assertEqual(P.to_base(-1, 16, 64), 'FFFFFFFFFFFFFFFF')
        self.assertEqual(P.to_base(-1, 10, 8), '-1')
        self.assertEqual(P.to_base(-128, 2, 8), '10000000')
        self.assertEqual(P.to_base(8, 8, 16), '10')
        self.assertEqual(P.to_base(255, 16, 16), 'FF')
        self.assertEqual(run('255', 10, 16).text, '255')
        self.assertEqual(run('FF', 16, 16).text, 'FF')
        self.assertEqual(run('-1', 2, 8).text, '11111111')

    def test_grouping(self):
        self.assertEqual(P.group('11110000', 4), '1111 0000')
        self.assertEqual(P.group('110000', 4), '11 0000')
        self.assertEqual(P.group('-1234567', 3, ','), '-1,234,567')
        self.assertEqual(P.group('', 4), '')


class Overflow(Case):
    def test_wraps_and_says_so(self):
        cases = [('127+1', 8, -128), ('-128-1', 8, 127), ('32767+1', 16, -32768),
                 ('2147483647+1', 32, -2147483648),
                 ('9223372036854775807+1', 64, -9223372036854775808),
                 ('100*3', 8, 44), ('-128/-1', 8, -128), ('-(-128)', 8, -128), ('1<<7', 8, -128),
                 ('1<<8', 8, 0), ('1<<64', 64, 0), ('16*16', 8, 0), ('200', 8, -56),
                 ('128', 8, -128), ('--128', 8, -128), ('-(128)', 8, -128)]
        for expr, bits, want in cases:
            with self.subTest(expr=expr, bits=bits):
                r = run(expr, 10, bits)
                self.assertEqual(r.value, want)
                self.assertTrue(r.wrapped)

    def test_no_wrap_flag_when_it_fits(self):
        for expr, bits in (('126+1', 8), ('-128', 8), ('-128+0', 8), ('-32768', 16), ('0xFF', 8), ('-1>>1', 8), ('~0', 8),
                           ('5 xor 3', 8), ('0x80 ror 1', 8), ('100*1', 8)):
            with self.subTest(expr=expr, bits=bits):
                self.assertFalse(run(expr, 10, bits).wrapped)

    def test_hex_bit_patterns_are_not_overflow(self):
        r = run('FF', 16, 8)
        self.assertEqual((r.value, r.text, r.wrapped), (-1, 'FF', False))
        r = run('7F+1', 16, 8)
        self.assertEqual((r.value, r.text, r.wrapped), (-128, '80', True))

    def test_too_wide_literals(self):
        self.fails('256', 'too_wide', 10, 8)
        self.fails('0x1FF', 'too_wide', 10, 8)
        self.fails('1FFFF', 'too_wide', 16, 16)
        self.fails('1' * 65, 'too_wide', 2, 64)
        self.fails('9' * 300, 'too_wide', 10, 64)
        self.assertEqual(run('0xFFFFFFFFFFFFFFFF').value, -1)

    def test_word_sizes(self):
        for bits in P.BITS:
            with self.subTest(bits=bits):
                top = 2 ** (bits - 1) - 1
                self.assertEqual(run(f'{top}+1', 10, bits).value, -top - 1)
                self.assertEqual(run('-1', 16, bits).text, 'F' * (bits // 4))

    def test_wrap_helper(self):
        self.assertEqual(P.wrap(255, 8), -1)
        self.assertEqual(P.wrap(256, 8), 0)
        self.assertEqual(P.wrap(-129, 8), 127)
        self.assertEqual(P.wrap(2 ** 63, 64), -2 ** 63)

    def test_from_decimal(self):
        from fractions import Fraction
        self.assertEqual(P.from_decimal(Fraction(7, 2), 8), (3, True))
        self.assertEqual(P.from_decimal(Fraction(-7, 2), 8), (-3, True))
        self.assertEqual(P.from_decimal(Fraction(300), 8), (44, True))
        self.assertEqual(P.from_decimal(Fraction(42), 8), (42, False))


class Shifts(Case):
    def test_shifts(self):
        self.values([('1<<4', 16), ('16>>2', 4), ('-16>>2', -4), ('-1>>1', -1), ('-1>>>1', 127),
                     ('-1>>>7', 1), ('-1>>>8', 0), ('-1>>100', -1), ('5 shl 1', 10),
                     ('5 shr 1', 2), ('1<<100', 0)], bits=8)

    def test_rotations(self):
        self.values([('0x81 rol 1', 3), ('0x81 ror 1', -64), ('1 ror 1', -128), ('1 rol 8', 1),
                     ('1 rol 9', 2), ('0x0F rol 4', -16), ('5 ror 0', 5)], bits=8)
        self.assertEqual(run('1 ror 1', 16, 64).text, '8000000000000000')

    def test_negative_shift(self):
        self.fails('1<<-1', 'shift_neg')
        self.fails('1 rol -1', 'shift_neg')


class Errors(Case):
    def test_errors(self):
        self.fails('1/0', 'div_zero', pos=1)
        self.fails('1%0', 'div_zero')
        self.fails('5 mod (3-3)', 'div_zero')
        self.fails('1.5', 'whole', pos=0)
        self.fails('.5', 'whole')
        self.fails('', 'empty')
        self.fails('1+', 'incomplete')
        self.fails('1)', 'unbalanced')
        self.fails('3 4', 'unexpected')
        self.fails('2 $ 3', 'char', pos=2)
        self.fails('sin(1)', 'digit')
        self.fails('(' * 70 + '1', 'nested')
        self.fails('-' * 70 + '1', 'nested')
        self.fails('1' * 10001, 'too_long')
        self.assertEqual(run('(1+2').value, 3)

    def test_bad_settings_are_programming_errors(self):
        with self.assertRaises(ValueError):
            P.evaluate('1', 10, 12)
        with self.assertRaises(ValueError):
            P.evaluate('1', 3, 8)


if __name__ == '__main__':
    unittest.main()
