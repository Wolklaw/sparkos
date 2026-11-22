"""Functions Python's decimal module doesn't have (pi, trigonometry, hyperbolic), worked out to
the precision of the current decimal context. Each one adds guard digits while it works and
rounds once at the end. Square root, exp, ln and log10 come from decimal itself."""

from decimal import Decimal, getcontext, localcontext
from typing import Dict

_PI: Dict[int, Decimal] = {}
GUARD = 10


def pi() -> Decimal:
    """Pi to the current precision (Machin's formula in whole numbers, cached)."""
    prec = getcontext().prec
    if prec not in _PI:
        digits = prec + GUARD
        unity = 10 ** digits

        def arccot(x: int) -> int:
            total = power = unity // x
            n, sign, x2 = 3, -1, x * x
            while True:
                power //= x2
                term = power // n
                if not term:
                    return total
                total += sign * term
                sign, n = -sign, n + 2

        value = 4 * (4 * arccot(5) - arccot(239))
        with localcontext() as ctx:
            ctx.prec = prec
            _PI[prec] = +Decimal(value).scaleb(-digits)
    return +_PI[prec]


def reduce_angle(x: Decimal) -> Decimal:
    """x - 2*pi*n, in [-pi, pi], with enough digits of pi for the size of x."""
    prec = getcontext().prec
    with localcontext() as ctx:
        ctx.prec = prec + max(0, x.adjusted()) + GUARD
        r = x.remainder_near(2 * pi())
    return +r


def _sin_series(x: Decimal) -> Decimal:
    x2 = x * x
    total, term, i = x, x, 1
    while True:
        term = -term * x2 / ((i + 1) * (i + 2))
        i += 2
        nxt = total + term
        if nxt == total:
            return total
        total = nxt


def _cos_series(x: Decimal) -> Decimal:
    x2 = x * x
    total, term, i = Decimal(1), Decimal(1), 0
    while True:
        term = -term * x2 / ((i + 1) * (i + 2))
        i += 2
        nxt = total + term
        if nxt == total:
            return total
        total = nxt


def sin(x: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec += GUARD
        r = _sin_series(reduce_angle(x))
    return +r


def cos(x: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec += GUARD
        r = _cos_series(reduce_angle(x))
    return +r


def atan(x: Decimal) -> Decimal:
    if not x:
        return Decimal(0)
    with localcontext() as ctx:
        ctx.prec += GUARD
        sign = -1 if x < 0 else 1
        y = abs(x)
        invert = y > 1
        if invert:
            y = 1 / y
        halvings = 0
        tenth = Decimal("0.1")
        while y > tenth:                      # atan(y) = 2 atan(y / (1 + sqrt(1 + y^2)))
            y = y / (1 + (1 + y * y).sqrt())
            halvings += 1
        y2 = y * y
        total, power, n = y, y, 1
        while True:
            power = -power * y2
            n += 2
            nxt = total + power / n
            if nxt == total:
                break
            total = nxt
        r = total * (2 ** halvings)
        if invert:
            r = pi() / 2 - r
        r = sign * r
    return +r


def asin(x: Decimal) -> Decimal:
    """For -1 <= x <= 1 (the caller checks)."""
    with localcontext() as ctx:
        ctx.prec += GUARD
        if abs(x) == 1:
            r = pi() / 2 * (1 if x > 0 else -1)
        else:
            r = atan(x / (1 - x * x).sqrt())
    return +r


def acos(x: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec += GUARD
        r = pi() / 2 - asin(x)
    return +r


def _extra(x: Decimal) -> int:
    """Guard digits for small x, where e^x - e^-x loses digits to cancellation."""
    return GUARD + (max(0, -x.adjusted()) if x else 0)


def sinh(x: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec += _extra(x)
        ex = x.exp()
        r = (ex - 1 / ex) / 2
    return +r


def cosh(x: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec += GUARD
        ex = abs(x).exp()
        r = (ex + 1 / ex) / 2
    return +r


def tanh(x: Decimal) -> Decimal:
    prec = getcontext().prec
    if abs(x) > prec * 2:                      # 1 - tanh(x) is below the last digit
        return Decimal(1 if x > 0 else -1)
    with localcontext() as ctx:
        ctx.prec += _extra(x)
        e2 = (2 * x).exp()
        r = (e2 - 1) / (e2 + 1)
    return +r


def asinh(x: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec += _extra(x)
        y = abs(x)
        r = (y + (y * y + 1).sqrt()).ln()
        r = r if x >= 0 else -r
    return +r


def acosh(x: Decimal) -> Decimal:
    """For x >= 1 (the caller checks)."""
    with localcontext() as ctx:
        ctx.prec += GUARD + max(0, -(x - 1).adjusted() if x != 1 else 0)
        r = (x + (x * x - 1).sqrt()).ln()
    return +r


def atanh(x: Decimal) -> Decimal:
    """For -1 < x < 1 (the caller checks)."""
    with localcontext() as ctx:
        ctx.prec += _extra(x) + max(0, -(1 - abs(x)).adjusted())
        r = ((1 + x) / (1 - x)).ln() / 2
    return +r
