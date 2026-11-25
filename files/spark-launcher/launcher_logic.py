"""Spark Launcher's search logic, as Python, for the Spark shell.

This is the same logic as package/contents/code/search.js (the Plasma widget): ranking apps for
the search box, and deciding when the text is a sum for Spark Calc. The widget keeps its own
JavaScript copy because QML can't call Python; tests/vectors.json holds cases both copies must
answer the same way (tests/test_logic.py runs them here, tests/check_js.mjs runs them on the
JavaScript). Change one, change the other, and add a vector.

Standard library only."""

import re
import unicodedata

CALC_NAMES = (
    'sin', 'cos', 'tan', 'sec', 'csc', 'cot', 'asin', 'acos', 'atan', 'arcsin', 'arccos',
    'arctan', 'sinh', 'cosh', 'tanh', 'asinh', 'acosh', 'atanh', 'sqrt', 'cbrt', 'root', 'exp',
    'ln', 'log', 'log2', 'log10', 'abs', 'floor', 'ceil', 'round', 'pi', 'e', 'mod',
)

_SPLIT = re.compile(r'[\s\-_.]+')
_SUM_CHARS = re.compile(r'^[0-9a-zA-Z.,\s+\-*/^%()!×÷−·√π²³]+$')
_NAME = re.compile(r'[a-zA-Z]+[0-9]*')


def fold(text) -> str:
    """Lower case, accents dropped ('parametres' finds 'Paramètres')."""
    text = unicodedata.normalize('NFD', str(text or ''))
    return ''.join(c for c in text if not unicodedata.combining(c)).lower()


def score(app: dict, q: str) -> int:
    """Score one app against the folded query; 0 means no match. Higher is better.
    name starts with the query > a word in the name starts with it > the name contains it >
    initials > the description matches > the desktop file id matches."""
    name = fold(app.get('name'))
    if not q or not name:
        return 0
    if name == q:
        return 100
    if name.startswith(q):
        return 80
    words = _SPLIT.split(name)
    if any(w.startswith(q) for w in words):
        return 60
    if q in name:
        return 40
    if len(q) >= 2 and ''.join(w[:1] for w in words).startswith(q):
        return 30
    desc = fold(app.get('description'))
    if desc and any(w.startswith(q) for w in _SPLIT.split(desc)):
        return 20
    if q in fold(app.get('id')):
        return 10
    return 0


def filter_apps(apps, query, limit=8):
    """The apps matching the query, best first, at most `limit`."""
    q = fold(query).strip()
    if not q:
        return []
    hits = []
    for i, app in enumerate(apps):
        s = score(app, q)
        if s > 0:
            hits.append((-s, fold(app.get('name')), i, app))
    hits.sort(key=lambda h: h[:3])
    return [h[3] for h in hits[:limit or 8]]


def sum_from(text, french_comma=False) -> str:
    """The sum to hand to Spark Calc, or '' if the text isn't one. Only digits, Spark Calc's
    operators and its function names pass, so the result is safe inside single quotes."""
    t = str(text or '').strip()
    if not t or len(t) > 200:
        return ''
    if t.startswith('='):
        t = t[1:].strip()
    if not _SUM_CHARS.match(t):
        return ''
    if not re.search(r'[0-9π]', t):
        return ''
    names = _NAME.findall(t)
    for n in names:
        n = n.lower()
        if n not in CALC_NAMES and re.sub(r'[0-9]+$', '', n) not in CALC_NAMES:
            return ''
    has_op = (re.search(r'[+*/^%!×÷−·√²³]', t) or re.search(r'[0-9)]\s*-', t)
              or re.search(r'-\s*[0-9(]', t[1:]))
    if not has_op and not names and 'π' not in t:
        return ''
    if french_comma:
        t = re.sub(r'([0-9]),([0-9])', r'\1.\2', t)
    return t


def sum_command(sum_text) -> str:
    """The command that evaluates a sum, or '' if anything shell-like is in it."""
    if not sum_text or re.search(r'[\'"`$\;&|<>\n]', sum_text):
        return ''
    return "timeout 2 spark-calc --eval '" + sum_text + "'"


def show_answer(answer, french_comma=False) -> str:
    """Spark Calc writes its answer with a point; French shows a comma."""
    a = str(answer or '').strip()
    return a.replace('.', ',') if french_comma else a
