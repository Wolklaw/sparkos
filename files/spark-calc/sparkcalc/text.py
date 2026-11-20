"""Every sentence the interface shows, in one place, so a French translation can be added as
a second table. t('key', name=...) fills in the blanks."""

import locale
import os
from typing import Dict, List

EN: Dict[str, str] = {
    # modes and switches
    'mode.standard': "Standard",
    'mode.scientific': "Scientific",
    'mode.programmer': "Programmer",
    'angle.deg': "DEG",
    'angle.rad': "RAD",
    'base.hex': "HEX",
    'base.dec': "DEC",
    'base.oct': "OCT",
    'base.bin': "BIN",

    # status line under the title
    'status.ready': "READY",
    'status.exact': "EXACT",
    'status.rounded': "ROUNDED TO {digits} DIGITS",
    'status.error': "NO ANSWER",
    'status.wrapped': "WRAPPED TO {bits} BITS",
    'status.copied': "COPIED",
    'status.memory': "SAVED TO MEMORY",
    'status.nothing': "NOTHING TO COPY",

    # display
    'display.rounded': "Rounded to {digits} significant digits.",
    'display.wrapped': "Too big for {bits} bits: it wrapped around, like the processor would.",
    'display.memory': "M  {value}",

    # history
    'history.title': "History",
    'history.empty': "Nothing worked out yet.",
    'history.clear': "Clear",
    'history.hint': "Click a sum to edit it again, or its answer to use it.",

    # errors: why there's no answer
    'err.empty': "Type a sum first.",
    'err.incomplete': "The sum isn't finished.",
    'err.unexpected': "Didn't expect “{token}” there.",
    'err.unbalanced': "There's a “)” without a “(”.",
    'err.char': "“{char}” isn't something Spark Calc can read.",
    'err.name': "Spark Calc doesn't know “{name}”.",
    'err.args': "{name}() takes {count} number(s).",
    'err.nested': "Too deeply nested (over {limit} levels).",
    'err.too_long': "Too long (over {limit} characters).",
    'err.div_zero': "Can't divide by zero.",
    'err.too_big': "Too big: Spark Calc works below 10^10000.",
    'err.precision': "Too big to work out exactly with 60 digits.",
    'err.factorial': "Factorial (!) needs a whole number of 0 or more.",
    'err.sqrt_neg': "A negative number has no real square root.",
    'err.even_root': "A negative number has no real even root.",
    'err.root_zero': "There's no 0th root.",
    'err.neg_power': "A negative number to a fractional power has no real answer.",
    'err.log_domain': "{name}() needs a number above 0.",
    'err.log_base': "The base of a logarithm must be above 0 and not 1.",
    'err.domain_unit': "{name}() needs a number from -1 to 1.",
    'err.domain_acosh': "acosh() needs a number of 1 or more.",
    'err.domain_atanh': "atanh() needs a number between -1 and 1.",
    'err.undefined': "{name}() has no value there.",
    'err.angle_big': "{name}() can't take angles this large.",
    'err.round_places': "round(x, n): n must be a whole number up to 1000.",
    # programmer mode
    'err.whole': "Programmer mode works with whole numbers only.",
    'err.digit': "“{digit}” isn't a {base} digit.",
    'err.too_wide': "{text} doesn't fit in {bits} bits.",
    'err.shift_neg': "Can't shift by a negative amount.",
}

FR: Dict[str, str] = {}          # to be written; English is used for any key missing here


def languages() -> List[str]:
    """'fr_CA.UTF-8' -> ['fr_CA', 'fr']"""
    lang = os.environ.get('LC_MESSAGES') or os.environ.get('LANG') or ''
    if not lang:
        try:
            lang = locale.getlocale()[0] or ''
        except ValueError:
            lang = ''
    lang = lang.split('.')[0].split('@')[0]
    return [lang, lang.split('_')[0]] if '_' in lang else ([lang] if lang else [])


_T = FR if 'fr' in languages() else EN


def t(key: str, **kw) -> str:
    text = _T.get(key) or EN.get(key) or key
    return text.format(**kw) if kw else text
