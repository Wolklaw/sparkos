"""What the keys do to the expression being typed. Pure text in, text out, so it is tested
without a display.

Keys like √x, x², 1/x, sin and ± act on the number just before the cursor ("the operand"):
typing 9 then √x gives √9, typing 2+3 then x² gives 2+3², after = they act on the answer.
With nothing before the cursor, function keys start a call instead: sin → "sin(".
"""

import re
from typing import Optional, Tuple

Edit = Tuple[str, int]                  # new text, new cursor position

POSTFIX = '!%²³'
OPERATORS = '+-−*×/÷^,(|&~<>'
NUMBER_CHARS = '0123456789.'
WORD_OPS = ('mod', 'and', 'or', 'xor', 'not', 'nand', 'nor', 'rol', 'ror', 'shl', 'shr')
GROUPED = re.compile(r'^[-−]?\d{1,3}(,\d{3})+(\.\d+)?$')


def _is_word(ch: str, programmer: bool) -> bool:
    if programmer:
        return ch.isascii() and (ch.isalnum() or ch == '_')
    return ch.isascii() and ch.isalpha() or ch in '_π'


def operand_start(text: str, end: int, programmer: bool = False) -> Optional[int]:
    """Where the operand that ends at `end` starts, or None if there isn't one (the text
    before `end` is empty or ends with an operator)."""
    p = end
    while p > 0 and text[p - 1] == ' ':
        p -= 1
    stop = p
    while p > 0 and text[p - 1] in POSTFIX:
        p -= 1
    if p == 0:
        return None
    ch = text[p - 1]
    if ch == ')':
        depth = 0
        while p > 0:
            p -= 1
            if text[p] == ')':
                depth += 1
            elif text[p] == '(':
                depth -= 1
                if depth == 0:
                    break
        if depth:
            return None
        while p > 0 and _is_word(text[p - 1], programmer):  # a function's name: sin(30)
            p -= 1
        return p
    if ch in NUMBER_CHARS or _is_word(ch, programmer):
        while p > 0:
            c = text[p - 1]
            if c in NUMBER_CHARS or _is_word(c, programmer):
                p -= 1
            elif not programmer and c in '+-' and p >= 3 and text[p - 2] in 'eE' and \
                    text[p - 3] in NUMBER_CHARS:
                p -= 2                                     # 1.5e+25
            else:
                break
        word = text[p:stop].lower()
        if word in WORD_OPS:
            return None
        return p
    return None


def _unary_minus_at(text: str, i: int) -> bool:
    """Is text[i] a minus sign in front of a number (not a subtraction)?"""
    if i < 0 or text[i] not in '-−':
        return False
    j = i
    while j > 0 and text[j - 1] == ' ':
        j -= 1
    return j == 0 or text[j - 1] in OPERATORS


def _signed_start(text: str, start: int) -> int:
    return start - 1 if _unary_minus_at(text, start - 1) else start


def _simple(operand: str, programmer: bool) -> bool:
    """A number, a name or a call: needs no brackets to have something put around it."""
    if not operand:
        return False
    if re.fullmatch(r'[0-9.]+([eE][+-]?[0-9]+)?', operand):
        return True
    if re.fullmatch(r'[A-Za-z_π]+', operand) or (programmer and
                                                    re.fullmatch(r'[0-9A-Za-z_]+', operand)):
        return True
    if re.fullmatch(r'[A-Za-z_]*\(.*\)', operand):
        start = operand.index('(')
        return operand_start(operand, len(operand)) == 0 and start >= 0
    return False


def insert(text: str, cursor: int, s: str) -> Edit:
    return text[:cursor] + s + text[cursor:], cursor + len(s)


def prefix(text: str, cursor: int, name: str, programmer: bool = False) -> Edit:
    """sin, √, ~: wraps the operand (30 → sin(30)), or starts a call (sin(), or "~")."""
    start = operand_start(text, cursor, programmer)
    call = name.endswith('(')
    if start is None:
        return insert(text, cursor, name)
    start = _signed_start(text, start)
    operand = text[start:cursor].rstrip()
    if call:
        new = name + operand + ')'
    elif _simple(operand, programmer):
        new = name + operand
    else:
        new = name + '(' + operand + ')'
    return text[:start] + new + text[cursor:], start + len(new)


def wrap(text: str, cursor: int, before: str, after: str, programmer: bool = False) -> Edit:
    """1/x → (1/9); 10ˣ → 10^(3). With no operand, inserts `before` alone."""
    start = operand_start(text, cursor, programmer)
    if start is None:
        return insert(text, cursor, before)
    start = _signed_start(text, start)
    operand = text[start:cursor].rstrip()
    new = before + operand + after
    return text[:start] + new + text[cursor:], start + len(new)


def postfix(text: str, cursor: int, mark: str, programmer: bool = False) -> Edit:
    """x², n!, %: appended to the operand; (-5)² keeps the sign inside. Nothing to act on:
    nothing happens."""
    start = operand_start(text, cursor, programmer)
    if start is None:
        return text, cursor
    signed = _signed_start(text, start)
    if signed != start:
        operand = text[signed:cursor].rstrip()
        new = '(' + operand + ')' + mark
        return text[:signed] + new + text[cursor:], signed + len(new)
    end = cursor
    while end > start and text[end - 1] == ' ':
        end -= 1
    return text[:end] + mark + text[cursor:], end + len(mark)


def negate(text: str, cursor: int, programmer: bool = False) -> Edit:
    """±: 5 → -5 → 5; 3+5 → 3-5 → 3+5; nothing typed → "-"."""
    start = operand_start(text, cursor, programmer)
    if start is None:
        return insert(text, cursor, '-')
    i = start - 1
    while i >= 0 and text[i] == ' ':
        i -= 1
    if i >= 0 and text[i] in '-−':
        if _unary_minus_at(text, i):
            return text[:i] + text[i + 1:], cursor - 1
        return text[:i] + '+' + text[i + 1:], cursor
    if i >= 0 and text[i] == '+':
        return text[:i] + '-' + text[i + 1:], cursor
    return text[:start] + '-' + text[start:], cursor + 1


def clear_entry(text: str, cursor: int, programmer: bool = False) -> Edit:
    """CE: removes the number before the cursor (with its sign)."""
    start = operand_start(text, cursor, programmer)
    if start is None:
        return text, cursor
    start = _signed_start(text, start)
    return text[:start] + text[cursor:], start


def backspace(text: str, cursor: int, sel: Optional[Tuple[int, int]] = None) -> Edit:
    if sel and sel[0] != sel[1]:
        a, b = sorted(sel)
        return text[:a] + text[b:], a
    if cursor <= 0:
        return text, cursor
    # a word operator with its spaces goes in one press: "5 and " → "5"
    m = re.search(r' ?\b(mod|and|or|xor|not|nand|nor|rol|ror) ?$', text[:cursor])
    if m and len(m.group()) > 1:
        return text[:m.start()] + text[cursor:], m.start()
    return text[:cursor - 1] + text[cursor:], cursor - 1


def starts_fresh(ch: str) -> bool:
    """After =, typing this starts a new sum instead of carrying on from the answer."""
    return ch.isalnum() or ch in '.(π√'


def clean_paste(text: str) -> str:
    """Pasted text: one line, no thousands separators in a plain number (1,234.5)."""
    text = ' '.join(text.split())
    if GROUPED.match(text):
        text = text.replace(',', '')
    return text


def open_call(text: str, cursor: int, name: str, programmer: bool = False) -> Edit:
    """ʸ√x: 27 → "root(27, " (type the 3 next); nothing typed → "root("."""
    start = operand_start(text, cursor, programmer)
    if start is None:
        return insert(text, cursor, name)
    start = _signed_start(text, start)
    new = name + text[start:cursor].rstrip() + ', '
    return text[:start] + new + text[cursor:], start + len(new)
