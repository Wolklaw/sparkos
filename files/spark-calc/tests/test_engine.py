"""The standard and scientific arithmetic: the parser, exactness, errors and limits.

    python -m unittest discover -s files/spark-calc/tests -v
"""

import os
import sys
import time
import unittest
from decimal import Decimal
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from sparkcalc import engine  # noqa: E402
from sparkcalc.engine import CalcError, evaluate, format_number  # noqa: E402
from sparkcalc.text import EN, t  # noqa: E402


def ans(expr, **kw):
    return evaluate(expr, **kw).text


class Case(unittest.TestCase):
    def same(self, pairs, **kw):
        for expr, want in pairs:
            with self.subTest(expr=expr):
                self.assertEqual(ans(expr, **kw), want)

    def fails(self, expr, key, pos=None, **kw):
        with self.assertRaises(CalcError, msg=expr) as cm:
            evaluate(expr, **kw)
        self.assertEqual(cm.exception.key, key, expr)
        if pos is not None:
            self.assertEqual(cm.exception.pos, pos, expr)
        self.assertIn('err.' + key, EN)
        return cm.exception


class Exactness(Case):
    def test_decimal_sums_are_exact(self):
        self.same([('0.1+0.2', '0.3'), ('0.1*3', '0.3'), ('1-0.9', '0.1'), ('0.7+0.1', '0.8'),
                   ('1.1*1.1', '1.21'), ('0.3-0.1-0.2', '0'), ('100*1.1', '110'),
                   ('4.35*100', '435'), ('1.15*100', '115'), ('0.1+0.7', '0.8')])

    def test_fractions_stay_exact(self):
        self.same([('1/3*3', '1'), ('1/3+1/3+1/3', '1'), ('2/3*3/2', '1'), ('1/7*7', '1'),
                   ('(1/3)^2*9', '1'), ('1/49*49', '1')])
        r = evaluate('1/3')
        self.assertEqual(r.value, Fraction(1, 3))
        self.assertFalse(r.exact)                  # shown rounded
        self.assertEqual(r.text, '0.33333333333333333333')

    def test_exact_flag(self):
        self.assertTrue(evaluate('0.5').exact)
        self.assertTrue(evaluate('2^64').exact)
        self.assertFalse(evaluate('2/3').exact)
        self.assertFalse(evaluate('sqrt(2)').exact)
        self.assertTrue(evaluate('sqrt(16)').exact)

    def test_big_integers_exact(self):
        self.assertEqual(evaluate('2^64').text, '18446744073709551616')
        self.assertEqual(evaluate('2^200').value, Fraction(2 ** 200))
        self.assertEqual(evaluate('25!').value, Fraction(15511210043330985984000000))
        self.assertEqual(evaluate('2^200-2^200+1').text, '1')
        self.assertEqual(evaluate('(10^50+1)-10^50').text, '1')

    def test_rounding_display(self):
        self.same([('2/3', '0.66666666666666666667'), ('1/7', '0.14285714285714285714'),
                   ('12345678901234567890', '12345678901234567890'),
                   ('123456789012345678901', '1.234567890123456789e+20'),
                   ('0.000000001', '0.000000001'), ('0.0000000001', '1e-10'),
                   ('10^20', '1e+20'), ('-1/3', '-0.33333333333333333333'), ('-0', '0')])

    def test_irrational_results_tidy(self):
        self.same([('sqrt(2)^2', '2'), ('sqrt(2)*sqrt(2)', '2'), ('sqrt(2)^2-2', '0'),
                   ('2^0.5*2^0.5', '2'), ('ln(e)', '1'), ('exp(ln(5))', '5'),
                   ('pi/pi', '1'), ('pi-pi', '0'), ('e^2/e/e', '1'), ('log(8, 2)', '3'),
                   ('10^log(7)', '7')])

    def test_known_values_keep_exactness(self):
        third = evaluate('1/3')
        r = evaluate(third.text + '*3', known={third.text: third.value})
        self.assertEqual(r.text, '1')
        self.assertEqual(evaluate(third.text + '*3').text, '0.99999999999999999999')

    def test_ans(self):
        self.assertEqual(ans('ans*2', ans=Fraction(21)), '42')
        self.assertEqual(ans('ans+1'), '1')                # 0 when nothing yet


class Precedence(Case):
    def test_basic_order(self):
        self.same([('2+3*4', '14'), ('(2+3)*4', '20'), ('10-4-3', '3'), ('100/10/5', '2'),
                   ('2*3+4*5', '26'), ('8/2*4', '16'), ('1+2*3-4/2', '5'),
                   ('2+3×4', '14'), ('9÷3−1', '2'), ('2·3', '6')])

    def test_powers(self):
        self.same([('2^3^2', '512'), ('(2^3)^2', '64'), ('-2^2', '-4'), ('(-2)^2', '4'),
                   ('2^-1', '0.5'), ('2^-2^2', '0.0625'), ('2**10', '1024'), ('3*2^2', '12'),
                   ('2^3*2', '16'), ('-3^2+1', '-8'), ('5²', '25'), ('2³', '8'), ('-5²', '-25'),
                   ('(-5)²', '25'), ('2^0.5^2', '1.1892071150027210667')])

    def test_unary_signs(self):
        self.same([('--5', '5'), ('-+-5', '5'), ('+5', '5'), ('3--2', '5'), ('3+-2', '1'),
                   ('2*-3', '-6'), ('-(-3)', '3'), ('−4', '-4')])

    def test_factorial_and_percent(self):
        self.same([('3!', '6'), ('0!', '1'), ('-3!', '-6'), ('2^3!', '64'), ('3!^2', '36'),
                   ('3!!', '720'), ('50%', '0.5'), ('200+10%', '220'), ('200-10%', '180'),
                   ('200*10%', '20'), ('200/10%', '2000'), ('200+(10%)', '200.1'),
                   ('200+10%*2', '200.2'), ('10%+5', '5.1'), ('200+-10%', '180'),
                   ('50+50%+10', '85')])

    def test_implicit_multiplication(self):
        self.same([('2(3+4)', '14'), ('(1+2)(3+4)', '21'), ('3 sin 30', '1.5'),
                   ('2sqrt(9)', '6'), ('√9√4', '6'),
                   ('1/2(4)', '2'), ('2^2(3)', '12'), ('(2)(3)(4)', '24')])
        self.assertEqual(ans('2pi'), ans('2*pi'))
        self.assertEqual(ans('2e'), ans('2*e'))

    def test_functions_without_brackets(self):
        self.same([('√16', '4'), ('√16+9', '13'), ('√(16+9)', '5'), ('sin 30', '0.5'),
                   ('sqrt 2^2', '2'), ('-√4', '-2')])
        self.fails('√-4', 'sqrt_neg')

    def test_mod(self):
        self.same([('10 mod 3', '1'), ('-7 mod 3', '-1'), ('7 mod -3', '1'), ('7.5 mod 2', '1.5'),
                   ('2+10 mod 4*3', '8'), ('1/3 mod 1/6', '0.055555555555555555556'), ('(1/3) mod (1/6)', '0'), ('9 MOD 4', '1')])

    def test_missing_close_bracket_is_added(self):
        self.same([('(1+2', '3'), ('2*(3+(4', '14'), ('sin(30', '0.5'), ('root(27, 3', '3')])


class Numbers(Case):
    def test_literals(self):
        self.same([('1.', '1'), ('.5', '0.5'), ('007', '7'), ('1e3', '1000'), ('1E3', '1000'),
                   ('1.5e+25', '1.5e+25'), ('2.5e-3', '0.0025'), ('2e+3', '2000'),
                   (' 12 ', '12')])

    def test_e_constant_vs_exponent(self):
        self.assertEqual(ans('2e3'), '2000')
        self.assertEqual(ans('2e'), ans('2*e'))
        self.assertEqual(ans('e+1'), ans('e + 1'))
        self.assertEqual(ans('2e +3'), ans('2*e+3'))

    def test_display_round_trips(self):
        for expr in ('1/3', '2^100', '1/7*10^30', '10^-15/3', 'pi*10^40', '-2/3'):
            with self.subTest(expr=expr):
                shown = evaluate(expr).text
                self.assertEqual(evaluate(shown).text, shown)

    def test_format_number(self):
        self.assertEqual(format_number(Fraction(1, 4)), ('0.25', True))
        self.assertEqual(format_number(Fraction(1, 3), 5), ('0.33333', False))
        self.assertEqual(format_number(Fraction(10 ** 25)), ('1e+25', True))
        self.assertEqual(format_number(Decimal('-0.5')), ('-0.5', False))
        self.assertEqual(format_number(Fraction(0)), ('0', True))


class Scientific(Case):
    def test_degrees(self):
        self.same([('sin(30)', '0.5'), ('cos(60)', '0.5'), ('tan(45)', '1'), ('sin(90)', '1'),
                   ('sin(180)', '0'), ('cos(90)', '0'), ('sin(-30)', '-0.5'), ('sin(390)', '0.5'),
                   ('cos(180)', '-1'), ('tan(135)', '-1'), ('sin(720)', '0'),
                   ('asin(0.5)', '30'), ('acos(0.5)', '60'), ('atan(1)', '45'), ('acos(-1)', '180'),
                   ('asin(1)', '90'), ('sin(45)', '0.7071067811865475244'),
                   ('sin(60)^2', '0.75'), ('sec(60)', '2'), ('csc(30)', '2'), ('cot(45)', '1'),
                   ('sin(1e20)', ans('sin(1e20 mod 360)'))])

    def test_radians(self):
        self.same([('sin(pi)', '0'), ('cos(pi)', '-1'), ('sin(pi/6)', '0.5'), ('cos(0)', '1'),
                   ('tan(pi/4)', '1'), ('atan(1)*4', '3.1415926535897932385'),
                   ('asin(1)', '1.5707963267948966192'), ('sin(2pi)', '0'),
                   ('sin(1)', '0.84147098480789650665'), ('cos(1)', '0.5403023058681397174'),
                   ('sin(1e50)', '-0.78967249342931008271')], angle='rad')

    def test_hyperbolic(self):
        self.same([('sinh(0)', '0'), ('cosh(0)', '1'), ('tanh(0)', '0'),
                   ('sinh(1)', '1.1752011936438014569'), ('cosh(1)', '1.5430806348152437785'),
                   ('tanh(1)', '0.76159415595576488812'), ('tanh(100)', '1'), ('tanh(-100)', '-1'),
                   ('asinh(sinh(2))', '2'), ('acosh(cosh(3))', '3'), ('atanh(tanh(0.5))', '0.5'),
                   ('sinh(1e-30)', '1e-30')])

    def test_logs_and_roots(self):
        self.same([('log(1000)', '3'), ('log(0.001)', '-3'), ('log10(100)', '2'), ('log2(8)', '3'),
                   ('log2(1024)', '10'), ('ln(1)', '0'), ('log(8, 2)', '3'), ('exp(0)', '1'),
                   ('sqrt(16)', '4'), ('sqrt(1/4)', '0.5'), ('sqrt(0.01)', '0.1'), ('cbrt(27)', '3'),
                   ('cbrt(-27)', '-3'), ('root(16, 4)', '2'), ('root(-32, 5)', '-2'),
                   ('8^(2/3)', '4'), ('(-8)^(1/3)', '-2'), ('(-8)^(2/3)', '4'), ('4^0.5', '2'),
                   ('sqrt(2)', '1.4142135623730950488'), ('e', '2.7182818284590452354'),
                   ('pi', '3.1415926535897932385'), ('π', '3.1415926535897932385'),
                   ('exp(1)', '2.7182818284590452354'), ('ln(2)', '0.69314718055994530942')])

    def test_rounding_functions(self):
        self.same([('round(2.5)', '3'), ('round(-2.5)', '-3'), ('round(2.4)', '2'),
                   ('round(3.14159, 2)', '3.14'), ('round(1234, -2)', '1200'), ('floor(-2.5)', '-3'),
                   ('ceil(2.1)', '3'), ('ceil(-2.1)', '-2'), ('abs(-3)', '3'), ('floor(pi)', '3'),
                   ('round(1/3, 3)', '0.333')])

    def test_names_are_case_blind(self):
        self.same([('SIN(30)', '0.5'), ('Sqrt(4)', '2'), ('PI/pi', '1'), ('Log2(8)', '3')])


class Errors(Case):
    def test_division_by_zero(self):
        for expr in ('1/0', '0/0', '5 mod 0', '1/(2-2)', '0^-1', '1/(sin(180))', '1/(1/3*3-1)'):
            with self.subTest(expr=expr):
                self.fails(expr, 'div_zero')
        self.fails('1/0', 'div_zero', pos=1)
        self.fails('2+3/0', 'div_zero', pos=3)

    def test_syntax(self):
        self.fails('', 'empty')
        self.fails('   ', 'empty')
        self.fails('1+', 'incomplete', pos=2)
        self.fails('2*', 'incomplete')
        self.fails('sin', 'incomplete')
        self.fails('(', 'incomplete')
        self.fails('1+)', 'unbalanced', pos=2)
        self.fails('(1+2))', 'unbalanced', pos=5)
        self.fails('5 3', 'unexpected', pos=2)
        self.fails('1 + * 2', 'unexpected', pos=4)
        self.fails('1,2', 'unexpected', pos=1)
        self.fails('1..2', 'unexpected')
        self.fails('3 # 4', 'char', pos=2)
        self.fails('2€', 'char', pos=1)
        self.fails('x+1', 'name', pos=0)
        self.fails('sinpi', 'name')
        self.fails('mod 3', 'unexpected')
        self.fails('sin()', 'args')
        self.fails('root(8)', 'args')
        self.fails('sqrt(1, 2)', 'args')

    def test_messages_name_the_problem(self):
        self.assertEqual(self.fails('x', 'name').message(), t('err.name', name='x'))
        self.assertEqual(self.fails('#', 'char').message(), t('err.char', char='#'))
        self.assertIn('sin()', self.fails('sin()', 'args').message())
        for key, text in EN.items():
            if key.startswith('err.'):
                self.assertTrue(text.endswith('.'), key)

    def test_domains(self):
        self.fails('sqrt(-1)', 'sqrt_neg')
        self.fails('(-2)^0.5', 'neg_power')
        self.fails('(-8)^(1/2)', 'neg_power')
        self.fails('root(-16, 4)', 'even_root')
        self.fails('root(8, 0)', 'root_zero')
        self.fails('ln(0)', 'log_domain')
        self.fails('log(-5)', 'log_domain')
        self.fails('log(8, 1)', 'log_base')
        self.fails('log(8, -2)', 'log_base')
        self.fails('asin(2)', 'domain_unit')
        self.fails('acos(-1.0001)', 'domain_unit')
        self.fails('acosh(0.5)', 'domain_acosh')
        self.fails('atanh(1)', 'domain_atanh')
        self.fails('tan(90)', 'undefined')
        self.fails('tan(-270)', 'undefined')
        self.fails('csc(180)', 'undefined')
        self.fails('cot(0)', 'undefined')
        self.fails('tan(pi/2)', 'undefined', angle='rad')
        self.fails('(-1)!', 'factorial')
        self.fails('2.5!', 'factorial')
        self.fails('round(2, 0.5)', 'round_places')

    def test_nesting_and_length_limits(self):
        self.assertEqual(ans('(' * 60 + '1' + ')' * 60), '1')
        self.fails('(' * 70 + '1', 'nested')
        self.fails('-' * 70 + '1', 'nested')
        self.fails('2' + '^2' * 70, 'nested')
        self.fails('sin ' * 70 + '1', 'nested')
        self.fails('1' * (engine.MAX_LEN + 1), 'too_long')
        self.assertEqual(ans('+'.join(['1'] * 2000)), '2000')   # long, but flat


class Limits(Case):
    def test_huge_numbers(self):
        self.assertEqual(ans('1e9999'), '1e+9999')
        self.assertEqual(ans('10^9999'), '1e+9999')
        self.assertEqual(ans('9.99e9999'), '9.99e+9999')
        self.assertEqual(ans('3000!'), '4.1493596034378540856e+9130')
        self.assertEqual(ans('2^33000'), ans('2^32999*2'))
        self.assertEqual(ans('0.1^-5000'), '1e+5000')
        self.assertEqual(ans('(10^5000+1)-10^5000'), '1')
        self.assertEqual(ans('1.0001^100000'), '22015.456048552198646')

    def test_too_big(self):
        for expr in ('1e10000', '10^10000', '10^9999*10', '2^2^2^2^2', '9^9^9', '3300!',
                     '1e5000*1e5000', 'exp(30000)', 'sinh(30000)', 'cosh(-30000)', '2^1e30',
                     '10^9999/0.1', '(1e5000)^2.5', 'exp(23026)'):
            with self.subTest(expr=expr):
                start = time.perf_counter()
                self.fails(expr, 'too_big')
                self.assertLess(time.perf_counter() - start, 1.0, expr)

    def test_tiny_numbers_become_zero(self):
        self.same([('1e-10001', '0'), ('1e-20000', '0'), ('0.1^20000', '0'), ('exp(-30000)', '0'),
                   ('1e-9999', '1e-9999'), ('10^-9999', '1e-9999'), ('2^-40000', '0')])

    def test_long_literal_beyond_python_int_limit(self):
        digits = '7' * 4900                      # Python refuses str<->int past 4300 digits
        self.assertEqual(ans(digits + '-' + digits), '0')
        self.assertEqual(ans(digits + '/' + digits), '1')
        self.assertEqual(ans(digits), '7.7777777777777777778e+4899')

    def test_powers_of_one(self):
        self.same([('1^1e100', '1'), ('(-1)^(10^30)', '1'), ('(-1)^(10^30+1)', '-1'),
                   ('0^0', '1'), ('0^5', '0'), ('0^0.5', '0')])

    def test_large_angles(self):
        self.fails('sin(1e100)', 'angle_big')
        self.fails('cos(1e100)', 'angle_big', angle='rad')
        self.assertTrue(ans('sin(1e99)', angle='rad'))

    def test_every_sum_is_quick(self):
        sums = ('3249!', '2^33219', '1/3^5000', '(1/3)^20000', 'sqrt(10^9999)', 'ln(10^9999)',
                'sin(1e99)', '1e9999/7', 'root(10^9999, 64)', '2^(1/65)', 'atan(1e9999)',
                '170!')
        for expr in sums:
            with self.subTest(expr=expr):
                start = time.perf_counter()
                try:
                    evaluate(expr)
                except CalcError:
                    pass
                self.assertLess(time.perf_counter() - start, 1.0, expr)


class Tokens(unittest.TestCase):
    def test_tokenize(self):
        kinds = [(k, v) for k, v, _ in engine.tokenize('2×π+√3 mod 4²')]
        self.assertEqual(kinds, [('num', '2'), ('op', '*'), ('name', 'pi'), ('op', '+'),
                                 ('name', 'sqrt'), ('num', '3'), ('name', 'mod'), ('num', '4'),
                                 ('op', '²'), ('end', '')])

    def test_log_suffixes(self):
        names = [v for k, v, _ in engine.tokenize('log2(8) log10(1) log 2 log20') if k == 'name']
        self.assertEqual(names, ['log2', 'log10', 'log', 'log'])

    def test_positions(self):
        self.assertEqual([p for _, _, p in engine.tokenize(' 12 + ab')], [1, 4, 6, 8])


if __name__ == '__main__':
    unittest.main()
