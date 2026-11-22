"""Every sentence the interface shows, in English and in French. The PC's language picks the
table (lang.py); t('key', name=...) fills in the blanks."""

from typing import Dict

from .lang import ui_language

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
    'status.crashed': "SOMETHING WENT WRONG",

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

FR: Dict[str, str] = {
    # modes and switches
    'mode.standard': "Standard",
    'mode.scientific': "Scientifique",
    'mode.programmer': "Programmeur",
    'angle.deg': "DEG",
    'angle.rad': "RAD",
    'base.hex': "HEX",
    'base.dec': "DEC",
    'base.oct': "OCT",
    'base.bin': "BIN",

    # status line under the title
    'status.ready': "PRÊT",
    'status.exact': "EXACT",
    'status.rounded': "ARRONDI À {digits} CHIFFRES",
    'status.error': "PAS DE RÉPONSE",
    'status.wrapped': "TRONQUÉ À {bits} BITS",
    'status.copied': "COPIÉ",
    'status.memory': "MIS EN MÉMOIRE",
    'status.nothing': "RIEN À COPIER",
    'status.crashed': "UN PROBLÈME EST SURVENU",

    # display
    'display.rounded': "Arrondi à {digits} chiffres significatifs.",
    'display.wrapped': "Trop grand pour {bits} bits : il a débordé, comme le ferait le processeur.",
    'display.memory': "M  {value}",

    # history
    'history.title': "Historique",
    'history.empty': "Aucun calcul pour l'instant.",
    'history.clear': "Effacer",
    'history.hint': "Cliquez sur un calcul pour le modifier, ou sur sa réponse pour la reprendre.",

    # errors: why there's no answer
    'err.empty': "Tapez d'abord un calcul.",
    'err.incomplete': "Le calcul n'est pas terminé.",
    'err.unexpected': "« {token} » n'était pas attendu à cet endroit.",
    'err.unbalanced': "Il y a une « ) » sans « ( ».",
    'err.char': "Spark Calc ne sait pas lire « {char} ».",
    'err.name': "Spark Calc ne connaît pas « {name} ».",
    'err.args': "{name}() prend {count} nombre(s).",
    'err.nested': "Trop imbriqué (plus de {limit} niveaux).",
    'err.too_long': "Trop long (plus de {limit} caractères).",
    'err.div_zero': "Impossible de diviser par zéro.",
    'err.too_big': "Trop grand : Spark Calc travaille sous 10^10000.",
    'err.precision': "Trop grand pour un calcul exact sur 60 chiffres.",
    'err.factorial': "La factorielle (!) demande un entier de 0 ou plus.",
    'err.sqrt_neg': "Un nombre négatif n'a pas de racine carrée réelle.",
    'err.even_root': "Un nombre négatif n'a pas de racine paire réelle.",
    'err.root_zero': "Il n'y a pas de racine d'ordre 0.",
    'err.neg_power': "Un nombre négatif à une puissance fractionnaire n'a pas de réponse réelle.",
    'err.log_domain': "{name}() demande un nombre plus grand que 0.",
    'err.log_base': "La base d'un logarithme doit être plus grande que 0 et différente de 1.",
    'err.domain_unit': "{name}() demande un nombre de -1 à 1.",
    'err.domain_acosh': "acosh() demande un nombre de 1 ou plus.",
    'err.domain_atanh': "atanh() demande un nombre entre -1 et 1.",
    'err.undefined': "{name}() n'a pas de valeur à cet endroit.",
    'err.angle_big': "{name}() ne prend pas des angles aussi grands.",
    'err.round_places': "round(x; n) : n doit être un entier d'au plus 1000.",
    # programmer mode
    'err.whole': "Le mode programmeur ne prend que des nombres entiers.",
    'err.digit': "« {digit} » n'est pas un chiffre {base}.",
    'err.too_wide': "{text} ne tient pas sur {bits} bits.",
    'err.shift_neg': "Impossible de décaler d'un nombre négatif.",
}

LANG = ui_language()
_T = FR if LANG == 'fr' else EN

# French writes 1,5 and separates a function's numbers with ; (round(2,5; 1)).
DECIMAL = ',' if LANG == 'fr' else '.'
ARG_SEP = '; ' if LANG == 'fr' else ', '


def t(key: str, **kw) -> str:
    text = _T.get(key) or EN.get(key) or key
    return text.format(**kw) if kw else text
