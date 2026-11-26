"""Syntax colouring: one small tokeniser per language, no dependencies.

Every lexer works one line at a time: lex(line, state) -> (tokens, state at the next line).
A token is (tag, start column, end column). The state carries what continues past the end of
a line: a block comment, a triple-quoted string, a Markdown code fence. Lexers whose state
never carries over have multiline = False, and the editor colours any line on its own.

The editor only colours what is on screen (see highlight.py), so these run on a few dozen
lines at a time, never on a whole 50 MB file.
"""

import os
import re
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .text import t

Token = Tuple[str, int, int]
State = object

TAGS = ('comment', 'string', 'keyword', 'constant', 'number', 'type', 'func', 'def', 'meta',
        'key', 'heading', 'tag', 'attr', 'var', 'code', 'link', 'emph')

IDENT = r'[A-Za-z_][A-Za-z0-9_]*'
NUMBER = (r'(?<![\w.])(?:0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|'
          r'(?:\d[\d_]*\.?[\d_]*|\.\d[\d_]*)(?:[eE][+-]?\d+)?)[A-Za-z0-9_]*')


class Lexer:
    name = 'Plain text'
    multiline = False
    line_comment: Optional[str] = None      # for "Toggle comment"
    indent_after: str = ''                  # a line ending in one of these indents the next

    def lex(self, line: str, state: State = None, pos: int = 0) -> Tuple[List[Token], State]:
        return [], None


class RuleLexer(Lexer):
    """The usual shape of a programming language: comments, strings, numbers and words.

    strings: (opening regex, closing text, backslash escapes?, may span lines?)
    extra:   (tag, regex) tried before everything else, in order
    defs:    words after which the next word is a name being defined (def, class, fn)
    """

    def __init__(self, name: str, *, keywords: Iterable[str] = (), types: Iterable[str] = (),
                 constants: Iterable[str] = (), builtins: Iterable[str] = (),
                 line_comments: Sequence[str] = (),
                 block_comments: Sequence[Tuple[str, str]] = (),
                 strings: Sequence[Tuple[str, str, bool, bool]] = (),
                 extra: Sequence[Tuple[str, str]] = (), defs: Iterable[str] = (),
                 calls: bool = True, cap_types: bool = False, numbers: bool = True,
                 ident: str = IDENT, comment: Optional[str] = None, indent_after: str = ''):
        self.name = name
        self.words: Dict[str, str] = {}
        for tag, group in (('type', builtins), ('type', types), ('constant', constants),
                           ('keyword', keywords)):
            for word in group:
                self.words[word] = tag
        self.defs = frozenset(defs)
        self.calls, self.cap_types = calls, cap_types
        self.line_comment = comment if comment is not None else \
            (line_comments[0] if line_comments else None)
        self.indent_after = indent_after
        parts: List[str] = []
        self.actions: Dict[str, Tuple] = {}
        self.closers: Dict[int, Tuple[str, 're.Pattern', bool]] = {}

        def add(pattern: str, action: Tuple) -> None:
            name = f'g{len(parts)}'
            parts.append(f'(?P<{name}>{pattern})')
            self.actions[name] = action

        for tag, pattern in extra:
            add(pattern, ('tok', tag))
        for marker in line_comments:
            add(re.escape(marker), ('line', 'comment'))
        for opener, closer in block_comments:
            sid = len(self.closers) + 1
            self.closers[sid] = ('comment', re.compile(r'.*?' + re.escape(closer)), True)
            add(re.escape(opener), ('open', sid))
        for opener, closer, escapes, spans in strings:
            sid = len(self.closers) + 1
            close = re.escape(closer)
            body = rf'(?:\\.|(?!{close})[^\\])*?' if escapes else r'.*?'
            self.closers[sid] = ('string', re.compile(body + close), spans)
            add(opener, ('open', sid))
        if numbers:
            add(NUMBER, ('tok', 'number'))
        add(ident, ('word',))
        self.rx = re.compile('|'.join(parts))
        self.multiline = any(spans for _, _, spans in self.closers.values())

    def lex(self, line: str, state: State = None, pos: int = 0) -> Tuple[List[Token], State]:
        toks: List[Token] = []
        n = len(line)
        if state:
            tag, closer, _ = self.closers[state]
            m = closer.match(line, pos)
            if not m:
                if n > pos:
                    toks.append((tag, pos, n))
                return toks, state
            toks.append((tag, pos, m.end()))
            pos = m.end()
        last_word, last_end = '', -1
        search, actions, words = self.rx.search, self.actions, self.words
        while pos < n:
            m = search(line, pos)
            if not m:
                break
            start, end = m.span()
            if end == start:                       # an empty match: step over it
                pos = start + 1
                continue
            action = actions[m.lastgroup]
            kind = action[0]
            if kind == 'word':
                word = m.group()
                tag = words.get(word)
                if last_word in self.defs and line[last_end:start].strip() == '':
                    tag = 'def'
                elif tag is None:
                    if self.calls and line[end:end + 1] == '(':
                        tag = 'func'
                    elif self.cap_types and word[0].isupper() and not word.isupper():
                        tag = 'type'
                if tag:
                    toks.append((tag, start, end))
                last_word, last_end = word, end
                pos = end
                continue
            if kind == 'tok':
                toks.append((action[1], start, end))
                pos = end
            elif kind == 'line':
                toks.append(('comment', start, n))
                return toks, None
            else:                                  # 'open': a string or block comment
                tag, closer, spans = self.closers[action[1]]
                cm = closer.match(line, end)
                if cm:
                    toks.append((tag, start, cm.end()))
                    pos = cm.end()
                else:
                    toks.append((tag, start, n))
                    return toks, (action[1] if spans else None)
            last_word = ''
        return toks, None


# ─── Languages ────────────────────────────────────────────────

PY_KEYWORDS = '''and as assert async await break class continue def del elif else except
finally for from global if import in is lambda nonlocal not or pass raise return try while
with yield'''.split()
PY_BUILTINS = '''abs all any bool bytearray bytes callable chr dict dir divmod enumerate eval
exec filter float format frozenset getattr globals hasattr hash hex id input int isinstance
issubclass iter len list map max min next object oct open ord pow print property range repr
reversed round set setattr slice sorted staticmethod classmethod str sum super tuple type vars
zip Exception BaseException ValueError TypeError KeyError IndexError OSError RuntimeError
AttributeError ImportError StopIteration NotImplementedError FileNotFoundError'''.split()
PY_PREFIX = r'(?:[rRbBuUfF]{0,2})'

JS_KEYWORDS = '''break case catch class const continue debugger default delete do else export
extends finally for function if import in instanceof let new return super switch this throw
try typeof var void while with yield async await of static get set from as'''.split()
TS_KEYWORDS = '''interface type enum implements declare readonly public private protected
namespace abstract keyof infer is satisfies module'''.split()
TS_TYPES = 'string number boolean any unknown never object bigint symbol'.split()

C_KEYWORDS = '''auto break case const continue default do else enum extern for goto if inline
register restrict return sizeof static struct switch typedef union volatile while'''.split()
CPP_KEYWORDS = '''alignas alignof catch class concept constexpr consteval constinit const_cast
co_await co_return co_yield decltype delete dynamic_cast explicit export final friend mutable
namespace new noexcept operator override private protected public reinterpret_cast requires
static_assert static_cast template this throw try typeid typename using virtual'''.split()
C_TYPES = '''void char short int long float double signed unsigned bool _Bool size_t ssize_t
int8_t int16_t int32_t int64_t uint8_t uint16_t uint32_t uint64_t intptr_t uintptr_t ptrdiff_t
off_t FILE wchar_t char8_t char16_t char32_t'''.split()

RUST_KEYWORDS = '''as async await break const continue crate dyn else enum extern fn for if impl
in let loop match mod move mut pub ref return self Self static struct super trait type unsafe
use where while'''.split()
RUST_TYPES = '''i8 i16 i32 i64 i128 isize u8 u16 u32 u64 u128 usize f32 f64 bool char str
String Vec Option Result Box'''.split()

GO_KEYWORDS = '''break case chan const continue default defer else fallthrough for func go goto
if import interface map package range return select struct switch type var'''.split()
GO_TYPES = '''bool byte complex64 complex128 error float32 float64 int int8 int16 int32 int64
rune string uint uint8 uint16 uint32 uint64 uintptr any'''.split()

SH_KEYWORDS = '''if then else elif fi for while until do done case esac in function select
return local export readonly declare typeset unset shift break continue exit time'''.split()
SH_BUILTINS = '''echo printf cd test read source alias set eval exec trap wait kill true false
pwd command type getopts let mapfile umask'''.split()

C_STRINGS = ((r'"', '"', True, False), (r"'", "'", True, False))


def _python() -> Lexer:
    return RuleLexer(
        'Python', keywords=PY_KEYWORDS, builtins=PY_BUILTINS,
        constants=('True', 'False', 'None', 'self', 'cls', 'NotImplemented', 'Ellipsis'),
        line_comments=('#',),
        strings=((PY_PREFIX + '"""', '"""', True, True), (PY_PREFIX + "'''", "'''", True, True),
                 (PY_PREFIX + '"', '"', True, False), (PY_PREFIX + "'", "'", True, False)),
        extra=(('meta', r'^\s*@[A-Za-z_][\w.]*'),), defs=('def', 'class'), indent_after=':')


def _javascript(typescript: bool = False) -> Lexer:
    return RuleLexer(
        'TypeScript' if typescript else 'JavaScript',
        keywords=JS_KEYWORDS + (TS_KEYWORDS if typescript else []),
        types=TS_TYPES if typescript else (),
        constants=('true', 'false', 'null', 'undefined', 'NaN', 'Infinity'),
        line_comments=('//',), block_comments=(('/*', '*/'),),
        strings=(('"', '"', True, False), ("'", "'", True, False), ('`', '`', True, True)),
        extra=(('meta', r'@[A-Za-z_][\w.]*'),),
        defs=('function', 'class', 'interface', 'type', 'enum'), cap_types=True,
        ident=r'[A-Za-z_$][\w$]*', indent_after='{[(')


def _json() -> Lexer:
    return RuleLexer(
        'JSON', constants=('true', 'false', 'null'),
        line_comments=('//',), block_comments=(('/*', '*/'),),
        strings=(('"', '"', True, False),),
        extra=(('key', r'"(?:\\.|[^"\\])*"(?=\s*:)'), ('number', r'-(?=\d)')),
        calls=False, indent_after='{[')


def _c(cpp: bool = False) -> Lexer:
    return RuleLexer(
        'C++' if cpp else 'C', keywords=C_KEYWORDS + (CPP_KEYWORDS if cpp else []),
        types=C_TYPES, constants=('true', 'false', 'NULL', 'nullptr'),
        line_comments=('//',), block_comments=(('/*', '*/'),), strings=C_STRINGS,
        extra=(('meta', r'^\s*#\s*[A-Za-z_]+'), ('string', r'(?<=include)\s*<[^>\n]*>')),
        defs=('struct', 'class', 'enum', 'union', 'namespace'), indent_after='{[(')


def _rust() -> Lexer:
    return RuleLexer(
        'Rust', keywords=RUST_KEYWORDS, types=RUST_TYPES,
        constants=('true', 'false', 'None', 'Some', 'Ok', 'Err'),
        line_comments=('//',), block_comments=(('/*', '*/'),),
        strings=(('b?"', '"', True, True),),
        extra=(('meta', r'#!?\[[^\]\n]*\]'), ('string', r'b?r(#*)"[^"\n]*"\1'),
               ('string', r"b?'(?:\\.|[^\\'])'"), ('type', r"'[A-Za-z_]\w*\b(?!')"),
               ('func', r'\b[A-Za-z_]\w*!(?=\s*[(\[{])')),
        defs=('fn', 'struct', 'enum', 'trait', 'type', 'mod', 'union'), cap_types=True,
        indent_after='{[(')


def _go() -> Lexer:
    return RuleLexer(
        'Go', keywords=GO_KEYWORDS, types=GO_TYPES, constants=('true', 'false', 'nil', 'iota'),
        line_comments=('//',), block_comments=(('/*', '*/'),),
        strings=(('"', '"', True, False), ("'", "'", True, False), ('`', '`', False, True)),
        defs=('func', 'type'), indent_after='{[(')


def _shell() -> Lexer:
    return RuleLexer(
        'Shell', keywords=SH_KEYWORDS, builtins=SH_BUILTINS,
        strings=((r"\$'", "'", True, True), ('"', '"', True, True), ("'", "'", False, True)),
        extra=(('comment', r'(?:^|(?<=[\s;&|(]))#.*'),
               ('var', r'\$(?:\{[^}\n]*\}|[A-Za-z_]\w*|[0-9@#?$!*-])'),
               ('def', r'^\s*[A-Za-z_][\w-]*(?=\s*\(\s*\))')),
        defs=('function',), calls=False, comment='#', numbers=False,
        ident=r'(?<![\w$-])[A-Za-z_][\w-]*')


def _toml() -> Lexer:
    return RuleLexer(
        'TOML', constants=('true', 'false', 'inf', 'nan'), line_comments=('#',),
        strings=(('"""', '"""', True, True), ("'''", "'''", False, True),
                 ('"', '"', True, False), ("'", "'", False, False)),
        extra=(('heading', r'^\s*\[\[?[^\]\n]*\]\]?'),
               ('key', r'^\s*[A-Za-z0-9_."\'-]+(?=\s*=)'),
               ('number', r'\d{4}-\d\d-\d\d(?:[T ]\d\d:\d\d(?::\d\d(?:\.\d+)?)?'
                          r'(?:Z|[+-]\d\d:\d\d)?)?')),
        calls=False, indent_after='[{')


VALUE_CONSTANTS = ('true', 'false', 'True', 'False', 'TRUE', 'FALSE', 'yes', 'no', 'Yes', 'No',
                   'on', 'off', 'null', 'Null', 'NULL', '~')


class YamlLexer(Lexer):
    name = 'YAML'
    line_comment = '#'
    indent_after = ':'
    KEY = re.compile(r'(\s*(?:-\s+)*)((?:"(?:\\.|[^"\\])*"|\'[^\']*\'|[^\s#\'"\[\]{},&*!|>%@`-]'
                     r'[^#\n]*?|-[^\s#][^#\n]*?))(\s*:)(?=\s|$)')

    def __init__(self):
        self.value = RuleLexer(
            'YAML values', constants=VALUE_CONSTANTS,
            strings=(('"', '"', True, False), ("'", "'", False, False)),
            extra=(('comment', r'(?:^|(?<=\s))#.*'), ('meta', r'^(?:---|\.\.\.)(?=\s|$)'),
                   ('meta', r'!!?[\w/:.-]*'), ('var', r'[&*][^\s,\[\]{}]+')),
            calls=False, ident=r'[A-Za-z_~][\w.-]*')

    def lex(self, line, state=None, pos=0):
        toks: List[Token] = []
        if pos == 0:
            m = self.KEY.match(line)
            if m:
                toks.append(('key', m.start(2), m.end(2)))
                pos = m.end(3)
        more, _ = self.value.lex(line, None, pos)
        return toks + more, None


class IniLexer(Lexer):
    """INI and conf files: [sections], key=value, ; and # comments (desktop entries, systemd
    units, rc files)."""
    name = 'INI'
    line_comment = '#'
    SECTION = re.compile(r'\s*\[[^\]\n]*\]')
    COMMENT = re.compile(r'\s*[;#]')
    KEY = re.compile(r'\s*([^=:\s][^=:]*?)\s*(?=[=:])')

    def __init__(self):
        self.value = RuleLexer(
            'INI values', constants=VALUE_CONSTANTS,
            strings=(('"', '"', True, False),),
            extra=(('var', r'\$(?:\{[^}\n]*\}|[A-Za-z_]\w*)|%[A-Za-z%]'),),
            calls=False)

    def lex(self, line, state=None, pos=0):
        if self.COMMENT.match(line):
            return [('comment', 0, len(line))], None
        m = self.SECTION.match(line)
        if m:
            return [('heading', 0, m.end())], None
        m = self.KEY.match(line)
        if not m:
            return [], None
        toks = [('key', m.start(1), m.end(1))]
        more, _ = self.value.lex(line, None, m.end() + 1)
        return toks + more, None


class MarkdownLexer(Lexer):
    name = 'Markdown'
    multiline = True
    FENCE = re.compile(r'\s{0,3}(`{3,}|~{3,})')
    HEADING = re.compile(r'\s{0,3}#{1,6}(?:\s|$)')
    QUOTE = re.compile(r'\s{0,3}>')
    RULE = re.compile(r'\s{0,3}([-*_])(?:\s*\1){2,}\s*$')
    LIST = re.compile(r'\s*(?:[-*+]|\d{1,9}[.)])(?=\s)')
    INLINE = re.compile(r'(?P<code>(`+)[^`].*?\2)|(?P<link>!?\[[^\]\n]*\]\([^)\n]*\)|'
                        r'<(?:https?|mailto):[^>\s]+>)|(?P<emph>\*\*[^*\n]+\*\*|__[^_\n]+__|'
                        r'(?<![*\w])\*[^*\s][^*\n]*\*(?!\*)|(?<![_\w])_[^_\s][^_\n]*_(?![_\w]))')

    def lex(self, line, state=None, pos=0):
        n = len(line)
        if state:
            if line.strip().startswith(state):
                return [('code', 0, n)], None
            return ([('code', 0, n)] if n else []), state
        m = self.FENCE.match(line)
        if m:
            return [('code', 0, n)], m.group(1)
        if self.HEADING.match(line):
            return [('heading', 0, n)], None
        if self.RULE.match(line):
            return [('meta', 0, n)], None
        if self.QUOTE.match(line):
            return [('comment', 0, n)], None
        toks: List[Token] = []
        m = self.LIST.match(line)
        if m:
            toks.append(('keyword', m.start(), m.end()))
        for m in self.INLINE.finditer(line, m.end() if m else 0):
            kind = 'code' if m.group('code') else 'link' if m.group('link') else 'emph'
            toks.append((kind, m.start(), m.end()))
        return toks, None


class HtmlLexer(Lexer):
    """HTML and XML: tags, attributes, strings in tags, entities and <!-- comments -->.
    A tag or comment may run over several lines. <script> and <style> contents stay plain."""
    name = 'HTML/XML'
    multiline = True
    TEXT = re.compile(r'<!--|<!\[CDATA\[|<[!?][^>\n]*>?|</?[A-Za-z][\w:.-]*|&#?\w+;')
    IN_TAG = re.compile(r'\s+|(?P<end>/?>)|(?P<str>(?<==)[^\s>"\']+)|'
                        r'(?P<attr>[^\s=>/"\']+)|(?P<eq>=)|'
                        r'(?P<qstr>"[^"\n]*"?|\'[^\'\n]*\'?)|(?P<other>.)')

    def lex(self, line, state=None, pos=0):
        toks: List[Token] = []
        n = len(line)
        while pos < n:
            if state in ('comment', 'cdata'):
                close = '-->' if state == 'comment' else ']]>'
                end = line.find(close, pos)
                if end == -1:
                    toks.append(('comment' if state == 'comment' else 'string', pos, n))
                    return toks, state
                toks.append(('comment' if state == 'comment' else 'string', pos, end + 3))
                pos, state = end + 3, None
            elif state == 'tag':
                m = self.IN_TAG.match(line, pos)
                kind = m.lastgroup
                if kind == 'end':
                    toks.append(('tag', m.start(), m.end()))
                    state = None
                elif kind == 'attr':
                    toks.append(('attr', m.start(), m.end()))
                elif kind in ('str', 'qstr'):
                    toks.append(('string', m.start(), m.end()))
                pos = m.end()
            else:
                m = self.TEXT.search(line, pos)
                if not m:
                    break
                text = m.group()
                if text == '<!--':
                    toks.append(('comment', m.start(), m.end()))
                    state, pos = 'comment', m.end()
                elif text == '<![CDATA[':
                    toks.append(('meta', m.start(), m.end()))
                    state, pos = 'cdata', m.end()
                elif text.startswith('&'):
                    toks.append(('constant', m.start(), m.end()))
                    pos = m.end()
                elif text[1] in '!?':
                    toks.append(('meta', m.start(), m.end()))
                    pos = m.end()
                else:
                    toks.append(('tag', m.start(), m.end()))
                    state, pos = 'tag', m.end()
        return toks, state


class CssLexer(Lexer):
    """CSS (and roughly SCSS and Less). State: (inside a comment, how many { deep)."""
    name = 'CSS'
    multiline = True
    line_comment = None
    indent_after = '{'
    RX = re.compile(r'(?P<copen>/\*)|(?P<str>"(?:\\.|[^"\\\n])*"?|\'(?:\\.|[^\'\\\n])*\'?)|'
                    r'(?P<open>\{)|(?P<close>\})|(?P<at>@[\w-]+)|(?P<imp>!important)|'
                    r'(?P<hex>#[0-9a-fA-F]{3,8}\b)|'
                    r'(?P<num>-?(?:\d+\.?\d*|\.\d+)(?:%|[a-zA-Z]+)?)|'
                    r'(?P<var>--[\w-]+|\$[\w-]+)|(?P<word>[A-Za-z_-][\w-]*)|'
                    r'(?P<sel>[.#][A-Za-z_-][\w-]*|::?[A-Za-z-]+)')

    def lex(self, line, state=None, pos=0):
        in_comment, depth = state if state else (False, 0)
        toks: List[Token] = []
        n = len(line)
        while pos < n:
            if in_comment:
                end = line.find('*/', pos)
                if end == -1:
                    toks.append(('comment', pos, n))
                    return toks, (True, depth)
                toks.append(('comment', pos, end + 2))
                pos, in_comment = end + 2, False
                continue
            m = self.RX.search(line, pos)
            if not m:
                break
            kind, start, end = m.lastgroup, m.start(), m.end()
            if kind == 'copen':
                in_comment, pos = True, start
                continue
            if kind == 'open':
                depth += 1
            elif kind == 'close':
                depth = max(0, depth - 1)
            elif kind == 'str':
                toks.append(('string', start, end))
            elif kind == 'at' or kind == 'imp':
                toks.append(('keyword', start, end))
            elif kind in ('hex', 'num'):
                toks.append(('number', start, end))
            elif kind == 'var':
                toks.append(('var', start, end))
            elif kind == 'word':
                rest = line[end:end + 40].lstrip()
                if rest.startswith('('):
                    toks.append(('func', start, end))
                elif depth > 0 and rest.startswith(':') and not rest.startswith('::') \
                        and '{' not in line[end:]:
                    toks.append(('key', start, end))
                elif depth == 0:
                    toks.append(('tag', start, end))
            elif kind == 'sel' and (depth == 0 or '{' in line[end:]):
                toks.append(('def' if line[start] in '.#' else 'meta', start, end))
            pos = end
        state = (in_comment, depth)
        return toks, (state if state != (False, 0) else None)


# ─── Finding the language ─────────────────────────────────────

FACTORIES: Dict[str, Callable[[], Lexer]] = {
    'python': _python,
    'javascript': _javascript,
    'typescript': lambda: _javascript(True),
    'json': _json,
    'yaml': YamlLexer,
    'toml': _toml,
    'ini': IniLexer,
    'shell': _shell,
    'markdown': MarkdownLexer,
    'html': HtmlLexer,
    'css': CssLexer,
    'c': _c,
    'cpp': lambda: _c(True),
    'rust': _rust,
    'go': _go,
}
NAMES = {'python': 'Python', 'javascript': 'JavaScript', 'typescript': 'TypeScript',
         'json': 'JSON', 'yaml': 'YAML', 'toml': 'TOML', 'ini': 'INI / conf', 'shell': 'Shell',
         'markdown': 'Markdown', 'html': 'HTML / XML', 'css': 'CSS', 'c': 'C', 'cpp': 'C++',
         'rust': 'Rust', 'go': 'Go'}

EXTENSIONS = {
    'python': '.py .pyw .pyi',
    'javascript': '.js .mjs .cjs .jsx',
    'typescript': '.ts .tsx .mts .cts',
    'json': '.json .jsonc .json5 .geojson .webmanifest .code-workspace',
    'yaml': '.yml .yaml',
    'toml': '.toml',
    'ini': '.ini .conf .cfg .desktop .service .socket .timer .mount .automount .target .path '
           '.slice .scope .network .netdev .link .repo .properties .directory .kcfg .rules',
    'shell': '.sh .bash .zsh .ksh .bashrc .bash_profile .profile .zshrc',
    'markdown': '.md .markdown .mdown .mkd',
    'html': '.html .htm .xhtml .xml .svg .xsl .xslt .xsd .plist .ui .qrc .kml .gpx .rss '
            '.atom .metainfo.xml',
    'css': '.css .scss .less',
    'c': '.c .h',
    'cpp': '.cpp .cc .cxx .c++ .hpp .hh .hxx .h++ .ino',
    'rust': '.rs',
    'go': '.go',
}
EXT_TO_LANG = {ext: lang for lang, exts in EXTENSIONS.items() for ext in exts.split()}
FILENAMES = {
    '.bashrc': 'shell', '.bash_profile': 'shell', '.bash_logout': 'shell', '.profile': 'shell',
    '.zshrc': 'shell', '.zprofile': 'shell', 'PKGBUILD': 'shell', '.envrc': 'shell',
    '.gitconfig': 'ini', '.editorconfig': 'ini', '.gitmodules': 'ini', 'kdeglobals': 'ini',
    'Cargo.lock': 'toml', 'Pipfile': 'toml', '.clang-format': 'yaml',
}
SHEBANGS = (('python', 'python'), ('bash', 'shell'), ('/sh', 'shell'), ('zsh', 'shell'),
            ('ksh', 'shell'), ('dash', 'shell'), ('env sh', 'shell'), ('node', 'javascript'),
            ('deno', 'typescript'))


def detect(path: Optional[str], first_line: str = '') -> Optional[str]:
    """The language for a file, from its name, else its #! line. None: plain text."""
    if path:
        name = os.path.basename(path)
        if name in FILENAMES:
            return FILENAMES[name]
        low = name.lower()
        if low.endswith('.metainfo.xml') or low.endswith('.appdata.xml'):
            return 'html'
        ext = os.path.splitext(low)[1]
        if ext in EXT_TO_LANG:
            return EXT_TO_LANG[ext]
        if low.endswith('rc') and ext == '' and first_line.lstrip().startswith('['):
            return 'ini'                                  # kwinrc, dolphinrc... (rc files from other desktops)
    if first_line.startswith('#!'):
        for needle, lang in SHEBANGS:
            if needle in first_line:
                return lang
    return None


_cache: Dict[str, Lexer] = {}


def lexer_for(lang: Optional[str]) -> Optional[Lexer]:
    if not lang or lang not in FACTORIES:
        return None
    if lang not in _cache:
        _cache[lang] = FACTORIES[lang]()
    return _cache[lang]


def name_of(lang: Optional[str]) -> str:
    return NAMES.get(lang or '', t('menu.plain'))


def lex_lines(lexer: Lexer, lines: Iterable[str], state: State = None,
              limit: int = 0) -> List[Tuple[List[Token], State]]:
    """Lex consecutive lines; returns each line's tokens and the state after it.
    limit: colour only the first `limit` characters of very long lines."""
    out = []
    for line in lines:
        if limit and len(line) > limit:
            toks, _ = lexer.lex(line[:limit], state)
            state = None
        else:
            toks, state = lexer.lex(line, state)
        out.append((toks, state))
    return out
