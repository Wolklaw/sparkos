"""Programmer mode: whole numbers in 8, 16, 32 or 64-bit two's complement, the way a processor
holds them. Every step wraps around to the word size (0x7F + 1 in 8 bits is -128) and the
result says when that happened.

Numbers are read in the chosen base (HEX, DEC, OCT, BIN); 0x and 0o prefixes work in any
base, 0b in all but HEX (where 0b1 is the hex number B1). _ can group digits: 1111_0000.

Operators, loosest first (C's order):
    |  or  nor
    ^  xor                  ^ is XOR here, not a power
    &  and  nand
    <<  >>  >>>  rol  ror   >> keeps the sign, >>> fills with zeros; rol/ror rotate
    +  -
    *  /  %  mod            / and % round toward zero, like C
    -  ~  not               (in front of a number)
"""

import re
from typing import List, Optional, Tuple

from .engine import MAX_DEPTH, MAX_LEN, SPACES, CalcError, Result

BASES = {16: 'hex', 10: 'dec', 8: 'oct', 2: 'bin'}
BITS = (8, 16, 32, 64)
DIGITS = '0123456789abcdef'

WORD = re.compile(r'[0-9A-Za-z_]+')
SYMBOLS = ('>>>', '<<', '>>', '|', '^', '&', '+', '-', '−', '*', '×', '/', '÷',
           '%', '~', '(', ')')
SYMBOL_OPS = {'−': '-', '×': '*', '÷': '/'}
KEYWORDS = {'or': '|', 'nor': 'nor', 'xor': '^', 'and': '&', 'nand': 'nand', 'mod': '%',
            'not': '~', 'rol': 'rol', 'ror': 'ror', 'shl': '<<', 'shr': '>>', 'lsh': '<<',
            'rsh': '>>'}
LEVELS = (('|', 'nor'), ('^',), ('&', 'nand'), ('<<', '>>', '>>>', 'rol', 'ror'),
          ('+', '-'), ('*', '/', '%'))

Token = Tuple[str, object, int]      # kind ('num', 'op', 'ans', 'end'), value, position


def mask(bits: int) -> int:
    return (1 << bits) - 1


def wrap(v: int, bits: int) -> int:
    """The signed value of v's lowest `bits` bits."""
    v &= mask(bits)
    return v - (1 << bits) if v >> (bits - 1) else v


def to_base(v: int, base: int, bits: int) -> str:
    """DEC is signed; HEX, OCT and BIN show the bit pattern."""
    if base == 10:
        return str(v)
    u = v & mask(bits)
    if base == 16:
        return format(u, 'X')
    if base == 8:
        return format(u, 'o')
    return format(u, 'b')


def group(text: str, size: int, sep: str = ' ') -> str:
    """'11110000' -> '1111 0000' (from the right)."""
    neg = text.startswith('-')
    body = text[1:] if neg else text
    parts = []
    while body:
        parts.append(body[-size:])
        body = body[:-size]
    return ('-' if neg else '') + sep.join(reversed(parts))


def tokenize(text: str, base: int, bits: int) -> List[Token]:
    tokens: List[Token] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in SPACES:
            i += 1
            continue
        if c.isascii() and (c.isalnum() or c == '_'):
            m = WORD.match(text, i)
            word, i = m.group(), m.end()
            low = word.lower()
            if low in KEYWORDS:
                tokens.append(('op', KEYWORDS[low], m.start()))
            elif low == 'ans':
                tokens.append(('ans', None, m.start()))
            elif i < n and text[i] == '.' and i + 1 < n and text[i + 1].isdigit():
                raise CalcError('whole', m.start())
            else:
                tokens.append(('num', read_number(word, base, bits, m.start()), m.start()))
            continue
        if c == '.':
            raise CalcError('whole', i)
        for sym in SYMBOLS:
            if text.startswith(sym, i):
                tokens.append(('op', SYMBOL_OPS.get(sym, sym), i))
                i += len(sym)
                break
        else:
            raise CalcError('char', i, char=c)
    tokens.append(('end', None, n))
    return tokens


def read_number(word: str, base: int, bits: int, pos: int) -> Tuple[int, bool, int]:
    """(value, wrapped, as written): the literal's value as a signed number of `bits` bits.
    Literals up to 2^bits - 1 are taken as a bit pattern (0xFF in 8 bits is -1); in DEC that
    counts as wrapping around, except -128 in 8 bits and the like."""
    low = word.lower()
    digits_base, skip = base, 0
    if low.startswith('0x'):
        digits_base, skip = 16, 2
    elif low.startswith('0o'):
        digits_base, skip = 8, 2
    elif low.startswith('0b') and base != 16:
        digits_base, skip = 2, 2
    allowed = DIGITS[:digits_base] + '_'
    for k in range(skip, len(word)):
        if low[k] not in allowed:
            raise CalcError('digit', pos + k, digit=word[k], base=BASES[digits_base].upper())
    body = low[skip:].replace('_', '')
    if not body:
        raise CalcError('incomplete', pos + len(word))
    if len(body) > 64 * 4:
        raise CalcError('too_wide', pos, text=word, bits=bits)
    value = int(body, digits_base)
    if value > mask(bits):
        raise CalcError('too_wide', pos, text=word, bits=bits)
    signed = wrap(value, bits)
    return signed, digits_base == 10 and signed != value, value


class Parser:
    def __init__(self, text: str, base: int = 10, bits: int = 64, ans: int = 0):
        if bits not in BITS:
            raise ValueError(f"bits must be one of {BITS}")
        if base not in BASES:
            raise ValueError(f"base must be one of {tuple(BASES)}")
        if len(text) > MAX_LEN:
            raise CalcError('too_long', None, limit=MAX_LEN)
        self.text, self.base, self.bits = text, base, bits
        self.ans = wrap(ans, bits)
        self.tokens = tokenize(text, base, bits)
        self.i = 0
        self.depth = 0
        self.wrapped = False

    @property
    def tok(self) -> Token:
        return self.tokens[self.i]

    def is_op(self, ops) -> bool:
        kind, value, _ = self.tok
        return kind == 'op' and value in ops

    def take(self) -> Token:
        tok = self.tok
        self.i += 1
        return tok

    def fit(self, v: int) -> int:
        w = wrap(v, self.bits)
        if w != v:
            self.wrapped = True
        return w

    def unexpected(self) -> CalcError:
        kind, value, pos = self.tok
        if kind == 'end':
            return CalcError('incomplete', pos)
        if kind == 'op' and value == ')':
            return CalcError('unbalanced', pos)
        token = self.text[pos:pos + 3].split()[0] if self.text[pos:pos + 3].strip() else '?'
        return CalcError('unexpected', pos, token=token)

    def parse(self) -> int:
        if self.tok[0] == 'end':
            raise CalcError('empty', 0)
        value = self.level(0)
        if self.tok[0] != 'end':
            raise self.unexpected()
        return value

    def level(self, k: int) -> int:
        if k == len(LEVELS):
            return self.unary()
        value = self.level(k + 1)
        while self.is_op(LEVELS[k]):
            _, op, pos = self.take()
            right = self.level(k + 1)
            value = self.apply(op, value, right, pos)
        return value

    def apply(self, op: str, a: int, b: int, pos: int) -> int:
        bits = self.bits
        if op == '|':
            return a | b
        if op == 'nor':
            return ~(a | b)
        if op == '^':
            return a ^ b
        if op == '&':
            return a & b
        if op == 'nand':
            return ~(a & b)
        if op == '+':
            return self.fit(a + b)
        if op == '-':
            return self.fit(a - b)
        if op == '*':
            return self.fit(a * b)
        if op in ('/', '%'):
            if b == 0:
                raise CalcError('div_zero', pos)
            q = abs(a) // abs(b)
            if (a < 0) != (b < 0):
                q = -q
            return self.fit(q) if op == '/' else self.fit(a - b * q)
        # shifts and rotations
        if b < 0:
            raise CalcError('shift_neg', pos)
        if op == '<<':
            return self.fit(a << b) if b < bits else self.fit(0 if a == 0 else a << bits)
        if op == '>>':
            return a >> min(b, bits)
        if op == '>>>':
            return wrap((a & mask(bits)) >> b, bits) if b < bits else 0
        c = b % bits
        u = a & mask(bits)
        if op == 'ror':
            c = (bits - c) % bits
        return wrap(((u << c) | (u >> (bits - c))) & mask(bits), bits)

    def unary(self) -> int:
        if self.is_op(('-', '+', '~')):
            _, op, pos = self.take()
            kind, value, _ = self.tok
            if op == '-' and kind == 'num' and value[2] == 1 << (self.bits - 1):
                self.take()                         # -128 in 8 bits: the lowest number, as is
                return -value[2]
            self.depth += 1
            if self.depth > MAX_DEPTH:
                raise CalcError('nested', pos, limit=MAX_DEPTH)
            value = self.unary()
            self.depth -= 1
            if op == '-':
                return self.fit(-value)
            return ~value if op == '~' else value
        return self.primary()

    def primary(self) -> int:
        kind, value, pos = self.tok
        if kind == 'num':
            self.take()
            number, wrapped, _ = value
            self.wrapped = self.wrapped or wrapped
            return number
        if kind == 'ans':
            self.take()
            return self.ans
        if kind == 'op' and value == '(':
            self.take()
            self.depth += 1
            if self.depth > MAX_DEPTH:
                raise CalcError('nested', pos, limit=MAX_DEPTH)
            inner = self.level(0)
            if self.is_op((')',)):
                self.take()
            elif self.tok[0] != 'end':               # a missing ) at the end is added
                raise self.unexpected()
            self.depth -= 1
            return inner
        raise self.unexpected()


def evaluate(text: str, base: int = 10, bits: int = 64, ans: int = 0) -> Result:
    """Work out an expression in programmer mode. Result.text is in `base`."""
    parser = Parser(text, base, bits, ans)
    try:
        value = parser.parse()
    except RecursionError:
        raise CalcError('nested', None, limit=MAX_DEPTH) from None
    return Result(value, to_base(value, base, bits), True, parser.wrapped)


def from_decimal(value, bits: int) -> Tuple[int, bool]:
    """A standard-mode answer brought into programmer mode: decimals are dropped (toward
    zero) and it wraps to the word size. (value, changed)."""
    whole = int(value)
    w = wrap(whole, bits)
    return w, w != value
