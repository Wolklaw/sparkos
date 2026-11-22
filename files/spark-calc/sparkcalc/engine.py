"""Standard and scientific arithmetic: a small tokenizer and a recursive-descent parser that
works the answer out as it reads. Never eval.

Numbers are exact fractions (Fraction) for as long as they can be: 0.1 + 0.2 is 3/10, 1/3*3 is
1, 2^100 is every digit of it. Results that are irrational (the square root of 2, sin, ln, pi)
are worked out with Decimal to PREC significant digits and marked inexact. Inexact results
whose first TIDY digits end in a run of zeros become exact again, so asin(0.5) in degrees is 30,
not 30.000...0001, and sqrt(2)^2 is 2. Results are shown rounded to DISPLAY significant digits.

Grammar, loosest first:
    sum      = term (("+" | "-") term)*            200 + 10% is 220: a percent on the right of
                                                   + or - is a percent of the left side
    term     = unary (("*" | "/" | "mod") unary | implicit unary)*
                                                   implicit: 2pi, 2(3+4), 3 sin 30, (1+2)(3+4)
    unary    = ("-" | "+") unary | power
    power    = postfix ("^" unary)?                right-associative; -2^2 is -4, 2^-1 is 0.5
    postfix  = primary ("!" | "%" | "²" | "³")*
    primary  = number | constant | function "(" args ")" | function unary | "(" sum ")"
A missing ")" at the end is added, the way most calculators do.

With comma=True (French), 1,5 is one and a half and a function's numbers are separated with
";" (round(2,5; 1)). The point still works (1.5), and a comma that isn't part of a number still
separates, so round(2.5, 1) typed or saved in English reads the same. Answers are then shown
with a comma. Never eval either way.
"""

import math
import re
from dataclasses import dataclass
from decimal import (ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, ROUND_HALF_UP, Context,
                     Decimal, DivisionByZero, Inexact, InvalidOperation, Overflow, localcontext)
from fractions import Fraction
from typing import Callable, Dict, List, Mapping, Optional, Tuple, Union

from . import dmath

Num = Union[Fraction, Decimal]

PREC = 60            # significant digits for inexact work
TIDY = 48            # inexact results are rounded to this many digits...
SHORT = 34           # ...and become exact if no more than this many are left
DISPLAY = 20         # significant digits shown
MAX_EXP = 10000      # numbers must stay below 10^10000; below 10^-10000 they become 0
MAX_LEN = 10000      # characters in an expression
MAX_DEPTH = 64       # nested parentheses, functions and signs
MAX_ROOT = 64        # exact roots are tried up to this degree
LIMIT_BITS = int(MAX_EXP * 3.3219)   # 2^LIMIT_BITS < 10^MAX_EXP

CTX = Context(prec=PREC, rounding=ROUND_HALF_EVEN, Emax=2 * MAX_EXP, Emin=-2 * MAX_EXP,
              traps=[InvalidOperation, DivisionByZero, Overflow])

ZERO, ONE = Fraction(0), Fraction(1)


class CalcError(Exception):
    """A calculation that has no answer. key names the sentence in text.py ('err.<key>');
    pos is where in the expression the problem is, when known."""

    def __init__(self, key: str, pos: Optional[int] = None, **kw):
        super().__init__(key)
        self.key, self.pos, self.kw = key, pos, kw

    def message(self) -> str:
        from .text import t
        return t('err.' + self.key, **self.kw)

    def __str__(self) -> str:
        return self.message()


@dataclass
class Result:
    value: Num
    text: str            # the value as shown (DISPLAY digits, no grouping); parses back
    exact: bool          # text is exactly the value
    wrapped: bool = False


# ─── Tokens ───────────────────────────────────────────────────

NUMBER = re.compile(r'(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?')
# French: a comma between digits is the decimal mark (1,5); a comma anywhere else separates
NUMBER_COMMA = re.compile(r'(?:[0-9]+(?:,[0-9]+|\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?')
NAME = re.compile(r'[A-Za-z_]+')
SPACES = ' \t\r\n   '
SYMBOLS = {
    '+': '+', '-': '-', '−': '-', '*': '*', '×': '*', '·': '*', '⋅': '*',
    '∙': '*', '/': '/', '÷': '/', '∕': '/', '^': '^', '!': '!', '%': '%',
    '(': '(', ')': ')', ',': ',', ';': ',', '²': '²', '³': '³',
}
SYMBOL_NAMES = {'π': 'pi', '√': 'sqrt', '∛': 'cbrt', 'ℯ': 'e'}

Token = Tuple[str, str, int]      # kind ('num', 'name', 'op', 'end'), text, position


def tokenize(text: str, comma: bool = False) -> List[Token]:
    number = NUMBER_COMMA if comma else NUMBER
    tokens: List[Token] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in SPACES:
            i += 1
            continue
        if '0' <= c <= '9' or (c == '.' and i + 1 < n and '0' <= text[i + 1] <= '9'):
            m = number.match(text, i)
            if not m:
                raise CalcError('char', i, char=c)
            tokens.append(('num', m.group(), i))
            i = m.end()
            continue
        if c.isalpha() and c.isascii() or c == '_':
            m = NAME.match(text, i)
            name, end = m.group().lower(), m.end()
            for suffix in ('10', '2'):             # log2(8), log10(100)
                after = end + len(suffix)
                if name + suffix in FUNCTIONS and text.startswith(suffix, end) and                         not (after < n and (text[after].isdigit() or text[after] == '.')):
                    name, end = name + suffix, after
                    break
            tokens.append(('name', name, i))
            i = end
            continue
        if c in SYMBOL_NAMES:
            tokens.append(('name', SYMBOL_NAMES[c], i))
            i += 1
            continue
        if text.startswith('**', i):
            tokens.append(('op', '^', i))
            i += 2
            continue
        if c in SYMBOLS:
            tokens.append(('op', SYMBOLS[c], i))
            i += 1
            continue
        raise CalcError('char', i, char=c)
    tokens.append(('end', '', n))
    return tokens


# ─── Exactness, size limits, display ──────────────────────────

def to_dec(x: Num) -> Decimal:
    """x as a Decimal, rounded to the working precision (run inside CTX)."""
    if isinstance(x, Decimal):
        return x
    if x.denominator == 1:
        return +Decimal(x.numerator)
    return Decimal(x.numerator) / Decimal(x.denominator)


def is_int(x: Num) -> bool:
    if isinstance(x, Fraction):
        return x.denominator == 1
    return x == x.to_integral_value()


def as_int(x: Num) -> int:
    return x.numerator if isinstance(x, Fraction) else int(x)


def sign(x: Num) -> int:
    return (x > 0) - (x < 0)


def tidy(d: Decimal) -> Num:
    """An inexact result: zero if it is below what can be told apart from zero, exact again
    if its first TIDY digits end in a long run of zeros (or nines)."""
    if not d:
        return ZERO
    with localcontext() as ctx:
        ctx.prec = TIDY
        r = ctx.plus(d).normalize(ctx)
    digits = r.as_tuple().digits
    if len(digits) <= SHORT and abs(r.adjusted()) <= MAX_EXP:
        return Fraction(r)
    return d


def check(x: Num, pos: Optional[int] = None) -> Num:
    """Keep numbers inside +-10^MAX_EXP; switch very long fractions to Decimal."""
    if isinstance(x, Fraction):
        n, d = x.numerator, x.denominator
        if n.bit_length() <= LIMIT_BITS and d.bit_length() <= LIMIT_BITS:
            return x
        with localcontext(CTX):
            return check(to_dec(x), pos)
    if not x:
        return ZERO
    if x.adjusted() >= MAX_EXP:
        raise CalcError('too_big', pos)
    if x.adjusted() < -MAX_EXP:
        return ZERO
    return tidy(x)


def format_number(x: Num, digits: int = DISPLAY, comma: bool = False) -> Tuple[str, bool]:
    """(text, exact): x rounded to `digits` significant digits; plain up to 10^digits and
    down to 10^-9, scientific (1.5e+25) outside that. exact says whether no rounding was
    needed. comma=True writes 1,5 instead of 1.5."""
    text, exact = _format_number(x, digits)
    return (text.replace('.', ',') if comma else text), exact


def _format_number(x: Num, digits: int) -> Tuple[str, bool]:
    if not x:
        return '0', True
    with localcontext() as ctx:
        ctx.prec, ctx.rounding = digits, ROUND_HALF_EVEN
        ctx.Emax, ctx.Emin = 4 * MAX_EXP, -4 * MAX_EXP
        ctx.traps[InvalidOperation] = ctx.traps[Overflow] = True
        ctx.clear_flags()
        if isinstance(x, Fraction):
            d = Decimal(x.numerator) / Decimal(x.denominator)
        else:
            d = ctx.plus(x)
        exact = isinstance(x, Fraction) and not ctx.flags[Inexact]
        d = d.normalize(ctx)
    if not d:
        return '0', exact
    if -9 <= d.adjusted() < digits:
        text = format(d, 'f')
    else:
        text = format(d, 'e')
    return text, exact


# ─── Arithmetic ───────────────────────────────────────────────

def add(a: Num, b: Num, pos: int) -> Num:
    if isinstance(a, Fraction) and isinstance(b, Fraction):
        return check(a + b, pos)
    with localcontext(CTX):
        da, db = to_dec(a), to_dec(b)
        r = da + db
        if r and da and db and r.adjusted() < max(da.adjusted(), db.adjusted()) - TIDY:
            return ZERO                          # what is left is rounding error
        return check(r, pos)


def mul(a: Num, b: Num, pos: int) -> Num:
    if not a or not b:
        return ZERO
    if isinstance(a, Fraction) and isinstance(b, Fraction):
        return check(a * b, pos)
    with localcontext(CTX):
        return check(to_dec(a) * to_dec(b), pos)


def div(a: Num, b: Num, pos: int) -> Num:
    if not b:
        raise CalcError('div_zero', pos)
    if isinstance(a, Fraction) and isinstance(b, Fraction):
        return check(a / b, pos)
    with localcontext(CTX):
        return check(to_dec(a) / to_dec(b), pos)


def mod(a: Num, b: Num, pos: int) -> Num:
    """Remainder with the sign of a (-7 mod 3 is -1), like the Windows calculator."""
    if not b:
        raise CalcError('div_zero', pos)
    if isinstance(a, Fraction) and isinstance(b, Fraction):
        q = int(a / b)                            # toward zero
        return check(a - b * q, pos)
    with localcontext(CTX):
        try:
            return check(to_dec(a) % to_dec(b), pos)
        except InvalidOperation:
            raise CalcError('precision', pos) from None


def iroot(n: int, k: int) -> int:
    """The whole k-th root of n >= 0, rounded down."""
    if n < 2:
        return n
    x = 1 << -(-n.bit_length() // k)               # 2^ceil(bits/k) >= the root
    while True:
        y = ((k - 1) * x + n // x ** (k - 1)) // k
        if y >= x:
            return x
        x = y


def exact_root(x: Fraction, k: int) -> Optional[Fraction]:
    """The k-th root of x >= 0 if it is a fraction, else None."""
    if k > MAX_ROOT:
        return None
    n, d = x.numerator, x.denominator
    rn, rd = iroot(n, k), iroot(d, k)
    if rn ** k == n and rd ** k == d:
        return Fraction(rn, rd)
    return None


def log10_abs(x: Num) -> Decimal:
    with localcontext(CTX):
        if isinstance(x, Fraction):
            return Decimal(abs(x.numerator)).log10() - Decimal(x.denominator).log10()
        return abs(x).log10()


def int_power(a: Num, n: int, pos: int) -> Num:
    if not a:
        if n < 0:
            raise CalcError('div_zero', pos)
        return ONE if n == 0 else ZERO
    if n == 0:
        return ONE
    if isinstance(a, Fraction) and abs(a) == 1:
        return a if n % 2 else ONE
    size = log10_abs(a) * n                     # roughly log10 of the answer
    if size >= MAX_EXP:
        raise CalcError('too_big', pos)
    if size < -MAX_EXP - 1:
        return ZERO
    if isinstance(a, Fraction):
        bits = max(a.numerator.bit_length(), a.denominator.bit_length()) * abs(n)
        if bits <= LIMIT_BITS + 64:
            return check(a ** n, pos)
    with localcontext(CTX):
        try:
            return check(to_dec(a) ** n, pos)
        except Overflow:
            raise CalcError('too_big', pos) from None


def power(a: Num, b: Num, pos: int) -> Num:
    if is_int(b):
        return int_power(a, as_int(b), pos)
    if not a:
        if b < 0:
            raise CalcError('div_zero', pos)
        return ZERO
    negative = a < 0
    if negative:
        # a real odd root of a negative number: (-8)^(1/3) is -2
        if isinstance(b, Fraction) and b.denominator % 2:
            r = power(-a, b, pos)
            return -r if b.numerator % 2 else r
        raise CalcError('neg_power', pos)
    if isinstance(a, Fraction) and isinstance(b, Fraction):
        root = exact_root(a, b.denominator)
        if root is not None:
            return int_power(root, b.numerator, pos)
    with localcontext(CTX):
        try:
            return check(to_dec(a) ** to_dec(b), pos)
        except Overflow:
            raise CalcError('too_big', pos) from None
        except InvalidOperation:
            raise CalcError('precision', pos) from None


def factorial(x: Num, pos: int) -> Num:
    if not is_int(x) or x < 0:
        raise CalcError('factorial', pos)
    n = as_int(x)
    if n > 3300:                                 # 3249! is past 10^10000
        raise CalcError('too_big', pos)
    return check(Fraction(math.factorial(n)), pos)


def percent_of(base: Num, pct: Num, pos: int) -> Num:
    return mul(base, div(pct, Fraction(100), pos), pos)


# ─── Functions ────────────────────────────────────────────────

SIN_DEG = {0: ZERO, 30: Fraction(1, 2), 90: ONE, 150: Fraction(1, 2), 180: ZERO,
           210: Fraction(-1, 2), 270: -ONE, 330: Fraction(-1, 2)}
TAN_DEG = {0: ZERO, 45: ONE, 135: -ONE, 180: ZERO, 225: ONE, 315: -ONE}
MAX_ANGLE = 100                                    # |x| < 10^100 for trigonometry


class Functions:
    def __init__(self, angle: str):
        self.degrees = angle == 'deg'

    # angles
    def _radians(self, x: Num, name: str, pos: int) -> Decimal:
        if isinstance(x, Decimal) and x.adjusted() >= MAX_ANGLE or \
                isinstance(x, Fraction) and abs(x) >= 10 ** MAX_ANGLE:
            raise CalcError('angle_big', pos, name=name)
        if self.degrees:
            if isinstance(x, Fraction):
                return to_dec(x % 360) * dmath.pi() / 180
            with localcontext() as ctx:
                ctx.prec = PREC + max(0, x.adjusted()) + 10
                r = x.remainder_near(360)
            return +r * dmath.pi() / 180
        return to_dec(x)

    def _deg_key(self, x: Num, shift: int = 0) -> Optional[int]:
        if self.degrees and isinstance(x, Fraction):
            r = (x + shift) % 360
            if r.denominator == 1:
                return int(r)
        return None

    def _from_radians(self, r: Decimal) -> Num:
        if self.degrees:
            r = r * 180 / dmath.pi()
        return check(r)

    @staticmethod
    def _small(r: Decimal) -> Num:
        """sin, cos: the reduced angle keeps them within [-1, 1], so anything below the last
        digit is zero."""
        if not r or r.adjusted() < -TIDY:
            return ZERO
        return check(r)

    def sin(self, x, pos):
        k = self._deg_key(x)
        if k is not None and k in SIN_DEG:
            return SIN_DEG[k]
        if not x:
            return ZERO
        return self._small(dmath.sin(self._radians(x, 'sin', pos)))

    def cos(self, x, pos):
        k = self._deg_key(x, 90)
        if k is not None and k in SIN_DEG:
            return SIN_DEG[k]
        if not x:
            return ONE
        return self._small(dmath.cos(self._radians(x, 'cos', pos)))

    def tan(self, x, pos):
        k = self._deg_key(x)
        if k is not None:
            if k in TAN_DEG:
                return TAN_DEG[k]
            if k in (90, 270):
                raise CalcError('undefined', pos, name='tan')
        if not x:
            return ZERO
        r = self._radians(x, 'tan', pos)
        c = dmath.cos(r)
        if not c or c.adjusted() < -TIDY:
            raise CalcError('undefined', pos, name='tan')
        return check(dmath.sin(r) / c, pos)

    def _recip(self, fn, name, x, pos):
        v = fn(x, pos)
        if not v:
            raise CalcError('undefined', pos, name=name)
        return div(ONE, v, pos)

    def sec(self, x, pos):
        return self._recip(self.cos, 'sec', x, pos)

    def csc(self, x, pos):
        return self._recip(self.sin, 'csc', x, pos)

    def cot(self, x, pos):
        k = self._deg_key(x)
        if k in (90, 270):
            return ZERO
        return self._recip(self.tan, 'cot', x, pos)

    def asin(self, x, pos):
        if abs(x) > 1:
            raise CalcError('domain_unit', pos, name='asin')
        if not x:
            return ZERO
        return self._from_radians(dmath.asin(to_dec(x)))

    def acos(self, x, pos):
        if abs(x) > 1:
            raise CalcError('domain_unit', pos, name='acos')
        return self._from_radians(dmath.acos(to_dec(x)))

    def atan(self, x, pos):
        if not x:
            return ZERO
        return self._from_radians(dmath.atan(to_dec(x)))

    # hyperbolic
    def sinh(self, x, pos):
        return ZERO if not x else self._exp_guard(dmath.sinh, x, pos)

    def cosh(self, x, pos):
        return ONE if not x else self._exp_guard(dmath.cosh, x, pos)

    def tanh(self, x, pos):
        return ZERO if not x else check(dmath.tanh(to_dec(x)), pos)

    def asinh(self, x, pos):
        return ZERO if not x else check(dmath.asinh(to_dec(x)), pos)

    def acosh(self, x, pos):
        if x < 1:
            raise CalcError('domain_acosh', pos)
        return ZERO if x == 1 else check(dmath.acosh(to_dec(x)), pos)

    def atanh(self, x, pos):
        if abs(x) >= 1:
            raise CalcError('domain_atanh', pos)
        return ZERO if not x else check(dmath.atanh(to_dec(x)), pos)

    @staticmethod
    def _exp_guard(fn, x, pos):
        if abs(x) > 3 * MAX_EXP:
            raise CalcError('too_big', pos)
        try:
            return check(fn(to_dec(x)), pos)
        except Overflow:
            raise CalcError('too_big', pos) from None

    # powers, roots, logarithms
    def sqrt(self, x, pos):
        if x < 0:
            raise CalcError('sqrt_neg', pos)
        if isinstance(x, Fraction):
            r = exact_root(x, 2)
            if r is not None:
                return r
        return check(to_dec(x).sqrt(), pos)

    def cbrt(self, x, pos):
        return power(x, Fraction(1, 3), pos)

    def root(self, x, n, pos):
        if not n:
            raise CalcError('root_zero', pos)
        if x < 0 and is_int(n) and as_int(n) % 2 == 0:
            raise CalcError('even_root', pos)
        return power(x, div(ONE, n, pos), pos)

    def exp(self, x, pos):
        if not x:
            return ONE
        if x >= MAX_EXP * 3:
            raise CalcError('too_big', pos)
        if x <= -MAX_EXP * 3:
            return ZERO
        try:
            return check(to_dec(x).exp(), pos)
        except Overflow:
            raise CalcError('too_big', pos) from None

    def ln(self, x, pos):
        if x <= 0:
            raise CalcError('log_domain', pos, name='ln')
        if x == 1:
            return ZERO
        return check(to_dec(x).ln(), pos)

    def log(self, x, base=None, pos=0):
        if x <= 0:
            raise CalcError('log_domain', pos, name='log')
        if base is None:
            if isinstance(x, Fraction):
                return check(log10_abs(x), pos)
            return check(to_dec(x).log10(), pos)
        if base <= 0 or base == 1:
            raise CalcError('log_base', pos)
        return check(log10_abs(x) / log10_abs(base), pos)

    def log2(self, x, pos):
        return self.log(x, Fraction(2), pos)

    # rounding and the rest
    def abs(self, x, pos):
        return abs(x)

    @staticmethod
    def _to_int(x: Num, rounding: str) -> Num:
        if isinstance(x, Fraction):
            if rounding == ROUND_FLOOR:
                return Fraction(math.floor(x))
            if rounding == ROUND_CEILING:
                return Fraction(math.ceil(x))
            half = math.floor(abs(x) + Fraction(1, 2))
            return Fraction(half if x >= 0 else -half)
        return check(Fraction(int(x.to_integral_value(rounding=rounding))))

    def floor(self, x, pos):
        return self._to_int(x, ROUND_FLOOR)

    def ceil(self, x, pos):
        return self._to_int(x, ROUND_CEILING)

    def round(self, x, places=None, pos=0):
        """Halves away from zero (2.5 -> 3); round(x, 2) keeps two decimals."""
        if places is None:
            return self._to_int(x, ROUND_HALF_UP)
        if not is_int(places) or abs(places) > 1000:
            raise CalcError('round_places', pos)
        scale = Fraction(10) ** as_int(places)
        return check(self._to_int(mul(x, scale, pos), ROUND_HALF_UP) / scale, pos)


# name: (method, fewest arguments, most arguments)
FUNCTIONS: Dict[str, Tuple[str, int, int]] = {
    'sin': ('sin', 1, 1), 'cos': ('cos', 1, 1), 'tan': ('tan', 1, 1),
    'sec': ('sec', 1, 1), 'csc': ('csc', 1, 1), 'cot': ('cot', 1, 1),
    'asin': ('asin', 1, 1), 'acos': ('acos', 1, 1), 'atan': ('atan', 1, 1),
    'arcsin': ('asin', 1, 1), 'arccos': ('acos', 1, 1), 'arctan': ('atan', 1, 1),
    'sinh': ('sinh', 1, 1), 'cosh': ('cosh', 1, 1), 'tanh': ('tanh', 1, 1),
    'asinh': ('asinh', 1, 1), 'acosh': ('acosh', 1, 1), 'atanh': ('atanh', 1, 1),
    'sqrt': ('sqrt', 1, 1), 'cbrt': ('cbrt', 1, 1), 'root': ('root', 2, 2),
    'exp': ('exp', 1, 1), 'ln': ('ln', 1, 1), 'log': ('log', 1, 2), 'log2': ('log2', 1, 1),
    'log10': ('log', 1, 1),
    'abs': ('abs', 1, 1), 'floor': ('floor', 1, 1), 'ceil': ('ceil', 1, 1),
    'round': ('round', 1, 2),
}
CONSTANTS = ('pi', 'e', 'ans')
KEYWORD_OPS = ('mod',)


# ─── The parser ───────────────────────────────────────────────

class Parser:
    def __init__(self, text: str, angle: str = 'deg', ans: Optional[Num] = None,
                 known: Optional[Mapping[str, Num]] = None, comma: bool = False):
        if len(text) > MAX_LEN:
            raise CalcError('too_long', None, limit=MAX_LEN)
        self.text = text
        self.tokens = tokenize(text, comma)
        self.i = 0
        self.depth = 0
        self.fn = Functions(angle)
        self.ans = ans if ans is not None else ZERO
        self.known = known or {}

    # token helpers
    @property
    def tok(self) -> Token:
        return self.tokens[self.i]

    def is_op(self, *ops: str) -> bool:
        kind, text, _ = self.tok
        return kind == 'op' and text in ops

    def take(self) -> Token:
        tok = self.tok
        self.i += 1
        return tok

    def nest(self, pos: int):
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise CalcError('nested', pos, limit=MAX_DEPTH)

    def unexpected(self) -> CalcError:
        kind, text, pos = self.tok
        if kind == 'end':
            return CalcError('incomplete', pos)
        if kind == 'op' and text == ')':
            return CalcError('unbalanced', pos)
        return CalcError('unexpected', pos, token=self.text[pos:pos + max(1, len(text))])

    # grammar
    def parse(self) -> Num:
        if self.tok[0] == 'end':
            raise CalcError('empty', 0)
        with localcontext(CTX):
            value = self.sum()
            if self.tok[0] != 'end':
                raise self.unexpected()
        return value

    def sum(self) -> Num:
        value, _ = self.term()
        while self.is_op('+', '-'):
            _, op, pos = self.take()
            right, pct = self.term()
            if pct is not None:                    # 200 + 10% -> 200 + 20
                right = percent_of(value, pct, pos)
            value = add(value, right if op == '+' else -right, pos)
        return value

    def term(self) -> Tuple[Num, Optional[Num]]:
        """The value, and the number before the % sign when the term is a bare percent."""
        value, pct = self.unary()
        while True:
            kind, text, pos = self.tok
            if kind == 'op' and text in ('*', '/'):
                self.take()
                right, _ = self.unary()
                value = mul(value, right, pos) if text == '*' else div(value, right, pos)
            elif kind == 'name' and text in KEYWORD_OPS:
                self.take()
                right, _ = self.unary()
                value = mod(value, right, pos)
            elif kind == 'name' or (kind == 'op' and text == '('):
                right, _ = self.unary()                  # implicit: 2pi, 2(3), 3 sin 30
                value = mul(value, right, pos)
            else:
                return value, pct
            pct = None

    def unary(self) -> Tuple[Num, Optional[Num]]:
        if self.is_op('-', '+'):
            _, op, pos = self.take()
            self.nest(pos)
            value, pct = self.unary()
            self.depth -= 1
            if op == '-':
                return -value, (-pct if pct is not None else None)
            return value, pct
        return self.power()

    def power(self) -> Tuple[Num, Optional[Num]]:
        base, pct = self.postfix()
        if self.is_op('^'):
            _, _, pos = self.take()
            self.nest(pos)
            exponent, _ = self.unary()
            self.depth -= 1
            return power(base, exponent, pos), None
        return base, pct

    def postfix(self) -> Tuple[Num, Optional[Num]]:
        value = self.primary()
        pct = None
        while self.is_op('!', '%', '²', '³'):
            _, op, pos = self.take()
            if op == '!':
                value, pct = factorial(value, pos), None
            elif op == '%':
                pct = value
                value = div(value, Fraction(100), pos)
            else:
                value, pct = int_power(value, 2 if op == '²' else 3, pos), None
        return value, pct

    def primary(self) -> Num:
        kind, text, pos = self.tok
        if kind == 'num':
            self.take()
            return self.number(text, pos)
        if kind == 'op' and text == '(':
            self.take()
            self.nest(pos)
            value = self.sum()
            self.close(pos)
            self.depth -= 1
            return value
        if kind == 'name':
            self.take()
            if text in CONSTANTS:
                if text == 'pi':
                    return check(dmath.pi())
                if text == 'e':
                    return check(Decimal(1).exp())
                return self.ans
            if text in FUNCTIONS:
                return self.call(text, pos)
            if text in KEYWORD_OPS:
                raise CalcError('unexpected', pos, token=text)
            raise CalcError('name', pos, name=self.text[pos:pos + len(text)])
        raise self.unexpected()

    def close(self, opened: int):
        if self.is_op(')'):
            self.take()
        elif self.tok[0] != 'end':                  # a missing ) at the end is added
            raise self.unexpected()

    def call(self, name: str, pos: int) -> Num:
        method, least, most = FUNCTIONS[name]
        self.nest(pos)
        args: List[Num] = []
        if self.is_op('('):
            self.take()
            if self.is_op(')'):
                raise CalcError('args', pos, name=name, count=least if least == most
                                else f"{least}-{most}")
            args.append(self.sum())
            while self.is_op(','):
                self.take()
                args.append(self.sum())
            self.close(pos)
        else:
            if self.tok[0] == 'end':
                raise CalcError('incomplete', self.tok[2])
            args.append(self.unary()[0])          # sin 30, sqrt 2: like a minus sign
        self.depth -= 1
        if not least <= len(args) <= most:
            raise CalcError('args', pos, name=name, count=least if least == most
                            else f"{least}-{most}")
        try:
            fn: Callable = getattr(self.fn, method)
            if method in ('log', 'round'):
                return fn(*args, pos=pos) if len(args) == 2 else fn(args[0], None, pos)
            return fn(*args, pos)
        except Overflow:
            raise CalcError('too_big', pos) from None
        except (InvalidOperation, DivisionByZero):
            raise CalcError('precision', pos) from None

    def number(self, text: str, pos: int) -> Num:
        for form in (text, text.replace(',', '.'), text.replace('.', ',')):
            if form in self.known:                  # a rounded result: use its exact value
                return self.known[form]
        d = Decimal(text.replace(',', '.'))
        if d and d.adjusted() >= MAX_EXP:
            raise CalcError('too_big', pos)
        if d and d.adjusted() < -MAX_EXP:
            return ZERO
        return Fraction(d)


def evaluate(text: str, angle: str = 'deg', ans: Optional[Num] = None,
             known: Optional[Mapping[str, Num]] = None, comma: bool = False) -> Result:
    """Work out an expression. Raises CalcError with a position when there's no answer.
    comma=True reads and writes the French way (1,5; see the top of this file)."""
    try:
        value = Parser(text, angle, ans, known, comma).parse()
    except RecursionError:
        raise CalcError('nested', None, limit=MAX_DEPTH) from None
    shown, exact = format_number(value, comma=comma)
    return Result(value, shown, exact)
