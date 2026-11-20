"""Spark Edit tests. Plain unittest:

    python -m unittest discover -s files/spark-edit/tests -v

File, syntax, search and session tests run anywhere, Windows included. Permission, symlink
and pkexec tests need Linux. Window tests need a display (on CI: xvfb-run) and are skipped
without one.
"""

import io
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
sys.path.insert(0, APP_DIR)
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_RUNTIME_DIR'):
    os.environ[var] = tempfile.mkdtemp(prefix=f'spark-edit-{var.lower()}-')
os.environ['SPARK_EDIT_REDUCED_MOTION'] = '1'
os.environ.pop('SPARK_EDIT_PKEXEC', None)

from sparkedit import VERSION, fileio, search, session, syntax  # noqa: E402
from sparkedit.cli import parse_target, self_test  # noqa: E402
from sparkedit.fileio import BinaryFile, EncodeError, Format  # noqa: E402
from sparkedit import instance  # noqa: E402

LINUX = sys.platform.startswith('linux')


def have_display() -> bool:
    try:
        import tkinter
        root = tkinter.Tk()
        root.destroy()
        return True
    except Exception:     # noqa: BLE001
        return False


DISPLAY = have_display()


class TempDir(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-edit-test-')
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def path(self, name: str) -> str:
        return os.path.join(self.dir, name)

    def write(self, name: str, data: bytes) -> str:
        with open(self.path(name), 'wb') as f:
            f.write(data)
        return self.path(name)

    def read(self, name: str) -> bytes:
        with open(self.path(name), 'rb') as f:
            return f.read()


# ─── Files ─────────────────────────────────────────────────────

class FileFormats(TempDir):
    def roundtrip(self, data: bytes, encoding: str, bom: bool, newline: str, text: str):
        path = self.write('f', data)
        got, fmt, _st = fileio.read_file(path)
        self.assertEqual(got, text)
        self.assertEqual((fmt.encoding, fmt.bom, fmt.newline), (encoding, bom, newline))
        fileio.write_file(path, fileio.encode(got, fmt))
        self.assertEqual(self.read('f'), data, "saving unchanged text changed the bytes")

    def test_utf8(self):
        self.roundtrip('héllo\nwörld\n'.encode(), 'utf-8', False, '\n', 'héllo\nwörld\n')

    def test_utf8_bom(self):
        self.roundtrip(b'\xef\xbb\xbfa\nb', 'utf-8', True, '\n', 'a\nb')

    def test_crlf_stays_crlf(self):
        self.roundtrip(b'one\r\ntwo\r\n', 'utf-8', False, '\r\n', 'one\ntwo\n')

    def test_old_mac_cr(self):
        self.roundtrip(b'one\rtwo', 'utf-8', False, '\r', 'one\ntwo')

    def test_utf16_le_bom(self):
        self.roundtrip('﻿Québec\r\n'.encode('utf-16-le'), 'utf-16-le', True, '\r\n',
                       'Québec\n')

    def test_utf16_be_bom(self):
        self.roundtrip('﻿abc\n'.encode('utf-16-be'), 'utf-16-be', True, '\n', 'abc\n')

    def test_utf16_without_bom(self):
        self.roundtrip('plain ascii text\n'.encode('utf-16-le'), 'utf-16-le', False, '\n',
                       'plain ascii text\n')

    def test_latin1(self):
        self.roundtrip('café à Québec\n'.encode('latin-1'), 'latin-1', False, '\n',
                       'café à Québec\n')

    def test_windows_1252(self):
        self.roundtrip('“quotes” — €5\n'.encode('cp1252'), 'cp1252', False, '\n',
                       '“quotes” — €5\n')

    def test_no_trailing_newline_kept(self):
        self.roundtrip(b'no newline at end', 'utf-8', False, '\n', 'no newline at end')

    def test_empty(self):
        self.roundtrip(b'', 'utf-8', False, '\n', '')

    def test_mixed_line_endings(self):
        text, fmt = fileio.decode(b'a\r\nb\r\nc\nd\r\n')
        self.assertEqual(text, 'a\nb\nc\nd\n')
        self.assertEqual(fmt.newline, '\r\n')
        self.assertTrue(fmt.mixed)

    def test_binary_refused(self):
        with self.assertRaises(BinaryFile):
            fileio.decode(b'\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x03\x00')
        with self.assertRaises(BinaryFile):
            fileio.decode(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR')
        text, fmt = fileio.decode(b'a\x00b', force=True)
        self.assertEqual(text, 'a\x00b')
        self.assertEqual(fmt.encoding, 'latin-1')

    def test_reopen_with_encoding(self):
        data = 'é'.encode('utf-8')
        text, fmt = fileio.decode(data, encoding='latin-1')
        self.assertEqual(text, 'Ã©')
        self.assertEqual(fmt.encoding, 'latin-1')

    def test_encode_error_says_where(self):
        with self.assertRaises(EncodeError) as cm:
            fileio.encode('ok\nfine 😀 here', Format('latin-1', False, '\r\n'))
        self.assertEqual((cm.exception.line, cm.exception.col, cm.exception.char), (2, 5, '😀'))

    def test_chunks_cut_after_newlines(self):
        text = ''.join(f'line {i}\n' for i in range(5000))
        parts = list(fileio.chunks(text, 1000))
        self.assertEqual(''.join(parts), text)
        self.assertTrue(all(p.endswith('\n') for p in parts))
        self.assertTrue(all(len(p) <= 1000 for p in parts))
        one_line = 'x' * 2500
        self.assertEqual(''.join(fileio.chunks(one_line, 1000)), one_line)

    def test_save_is_atomic_and_leaves_no_temp(self):
        path = self.write('a.txt', b'old')
        fileio.write_file(path, b'new')
        self.assertEqual(self.read('a.txt'), b'new')
        self.assertEqual(os.listdir(self.dir), ['a.txt'])

    def test_save_new_file(self):
        fileio.write_file(self.path('new.txt'), b'x')
        self.assertEqual(self.read('new.txt'), b'x')

    @unittest.skipUnless(LINUX, "POSIX permissions")
    def test_save_keeps_permissions(self):
        path = self.write('script.sh', b'#!/bin/sh\n')
        os.chmod(path, 0o750)
        fileio.write_file(path, b'#!/bin/sh\necho hi\n')
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o750)

    @unittest.skipUnless(LINUX, "POSIX umask")
    def test_new_file_gets_normal_permissions(self):
        old = os.umask(0o022)
        try:
            fileio.write_file(self.path('n.txt'), b'x')
        finally:
            os.umask(old)
        self.assertEqual(stat.S_IMODE(os.stat(self.path('n.txt')).st_mode), 0o644)

    @unittest.skipUnless(LINUX, "symlinks")
    def test_save_through_symlink_keeps_link(self):
        target = self.write('real.txt', b'a')
        link = self.path('link.txt')
        os.symlink(target, link)
        fileio.write_file(link, b'b')
        self.assertTrue(os.path.islink(link))
        self.assertEqual(self.read('real.txt'), b'b')

    @unittest.skipUnless(LINUX, "hard links")
    def test_save_keeps_hard_links(self):
        path = self.write('h1', b'a')
        os.link(path, self.path('h2'))
        fileio.write_file(path, b'b')
        self.assertEqual(self.read('h2'), b'b')
        self.assertEqual(os.stat(path).st_ino, os.stat(self.path('h2')).st_ino)

    @unittest.skipUnless(LINUX and os.geteuid() != 0, "needs a non-root user on Linux")
    def test_unwritable_file_raises_permission_error(self):
        path = self.write('ro.txt', b'a')
        os.chmod(path, 0o444)
        os.chmod(self.dir, 0o555)
        try:
            with self.assertRaises(OSError) as cm:
                fileio.write_file(path, b'b')
            self.assertTrue(fileio.is_permission_error(cm.exception))
            self.assertFalse(fileio.can_write(path))
        finally:
            os.chmod(self.dir, 0o755)

    @unittest.skipUnless(LINUX and os.geteuid() != 0, "needs a non-root user on Linux")
    def test_writable_file_in_unwritable_folder_is_written_in_place(self):
        path = self.write('w.txt', b'a')
        os.chmod(self.dir, 0o555)
        try:
            fileio.write_file(path, b'bb')
        finally:
            os.chmod(self.dir, 0o755)
        self.assertEqual(self.read('w.txt'), b'bb')

    def test_admin_command(self):
        cmd = fileio.admin_command('/tmp/x', '/etc/hosts')
        self.assertTrue(cmd[1].endswith('cp'))
        self.assertEqual(cmd[2:], ['--no-preserve=mode,ownership', '--', '/tmp/x', '/etc/hosts'])

    @unittest.skipUnless(LINUX, "runs a fake pkexec shell script")
    def test_admin_write_through_fake_pkexec(self):
        fake = self.write('pkexec', b'#!/bin/sh\nexec "$@"\n')
        os.chmod(fake, 0o755)
        target = self.write('owned.conf', b'old')
        os.environ['SPARK_EDIT_PKEXEC'] = fake
        try:
            self.assertIsNone(fileio.admin_write(target, b'new', self.dir))
            self.assertEqual(self.read('owned.conf'), b'new')
            cancel = self.write('pkexec-cancel', b'#!/bin/sh\nexit 126\n')
            os.chmod(cancel, 0o755)
            os.environ['SPARK_EDIT_PKEXEC'] = cancel
            self.assertEqual(fileio.admin_write(target, b'x', self.dir), 'cancelled')
            self.assertEqual(self.read('owned.conf'), b'new')
        finally:
            os.environ.pop('SPARK_EDIT_PKEXEC', None)
        leftovers = [n for n in os.listdir(self.dir) if n.startswith('admin-save-')]
        self.assertEqual(leftovers, [])


# ─── Syntax ────────────────────────────────────────────────────

def tokens(lang, source):
    lexer = syntax.lexer_for(lang)
    out, state = [], None
    for line in source.split('\n'):
        toks, state = lexer.lex(line, state)
        out.append([(tag, line[a:b]) for tag, a, b in toks])
    return out


def tagged(lang, source, tag):
    return [text for row in tokens(lang, source) for t, text in row if t == tag]


class Syntax(unittest.TestCase):
    def test_every_language_lexes(self):
        for lang in syntax.FACTORIES:
            with self.subTest(lang=lang):
                lexer = syntax.lexer_for(lang)
                self.assertIsInstance(lexer, syntax.Lexer)
                lexer.lex('x = "y" # z // w /* v */ <a> [b]', None)

    def test_python(self):
        src = '@decorator\ndef run(x=1.5):\n    """doc\n    more"""\n    return None  # done'
        self.assertEqual(tagged('python', src, 'def'), ['run'])
        self.assertEqual(tagged('python', src, 'meta'), ['@decorator'])
        self.assertIn('"""doc', tagged('python', src, 'string'))
        self.assertIn('    more"""', tagged('python', src, 'string'))
        self.assertIn('return', tagged('python', src, 'keyword'))
        self.assertEqual(tagged('python', src, 'comment'), ['# done'])
        self.assertEqual(tagged('python', src, 'number'), ['1.5'])
        self.assertEqual(tagged('python', 's = "a \\" b" + x', 'string'), ['"a \\" b"'])

    def test_block_comment_spans_lines(self):
        rows = tokens('c', 'int a; /* one\ntwo\nthree */ int b;')
        self.assertEqual(rows[1], [('comment', 'two')])
        self.assertEqual(rows[2][0], ('comment', 'three */'))
        self.assertIn(('type', 'int'), rows[2])

    def test_js_template_string_spans_lines(self):
        rows = tokens('javascript', 'const s = `a\nb` + f(1)')
        self.assertEqual(rows[1][0], ('string', 'b`'))
        self.assertIn(('func', 'f'), rows[1])

    def test_json_keys(self):
        self.assertEqual(tagged('json', '{"name": "x", "n": 1, "ok": true}', 'key'),
                         ['"name"', '"n"', '"ok"'])
        self.assertEqual(tagged('json', '{"ok": true}', 'constant'), ['true'])

    def test_yaml(self):
        src = 'jobs:\n  - name: build # c\n    run: "echo"\n---'
        self.assertEqual(tagged('yaml', src, 'key'), ['jobs', 'name', 'run'])
        self.assertEqual(tagged('yaml', src, 'comment'), ['# c'])
        self.assertEqual(tagged('yaml', src, 'meta'), ['---'])

    def test_toml(self):
        src = '[tool]\nname = "x"\ns = """\nmulti\n"""'
        self.assertEqual(tagged('toml', src, 'heading'), ['[tool]'])
        self.assertEqual(tagged('toml', src, 'key'), ['name', 's'])
        self.assertEqual(tokens('toml', src)[3], [('string', 'multi')])

    def test_ini(self):
        src = '[Desktop Entry]\nName[fr]=Spark Edit\n; comment\nTerminal=false'
        self.assertEqual(tagged('ini', src, 'heading'), ['[Desktop Entry]'])
        self.assertEqual(tagged('ini', src, 'key'), ['Name[fr]', 'Terminal'])
        self.assertEqual(tagged('ini', src, 'constant'), ['false'])
        self.assertEqual(tagged('ini', src, 'comment'), ['; comment'])

    def test_shell(self):
        src = 'f() {\n  echo "$HOME" ${x} # c\n}\nurl=a#b'
        self.assertEqual(tagged('shell', src, 'def'), ['f'])
        self.assertEqual(tagged('shell', src, 'var'), ['${x}'])
        self.assertEqual(tagged('shell', src, 'comment'), ['# c'])
        self.assertIn('echo', tagged('shell', src, 'type'))

    def test_markdown_fence(self):
        rows = tokens('markdown', '# Title\n```py\nx = 1  # not a heading\n```\n- `a` **b**')
        self.assertEqual(rows[0], [('heading', '# Title')])
        self.assertEqual(rows[2], [('code', 'x = 1  # not a heading')])
        self.assertEqual(rows[4], [('keyword', '-'), ('code', '`a`'), ('emph', '**b**')])

    def test_html(self):
        rows = tokens('html', '<a href="x"\n   id=y>Tom &amp; Jerry<!-- c\n -->')
        self.assertEqual(rows[0], [('tag', '<a'), ('attr', 'href'), ('string', '"x"')])
        self.assertEqual(rows[1][:3], [('attr', 'id'), ('string', 'y'), ('tag', '>')])
        self.assertIn(('constant', '&amp;'), rows[1])
        self.assertEqual(rows[2], [('comment', ' -->')])

    def test_css(self):
        rows = tokens('css', '.a:hover {\n  color: #fff;\n}')
        self.assertEqual(rows[0], [('def', '.a'), ('meta', ':hover')])
        self.assertEqual(rows[1], [('key', 'color'), ('number', '#fff')])

    def test_rust_and_go(self):
        self.assertEqual(tagged('rust', 'fn main() { println!("x"); }', 'func'), ['println!'])
        self.assertEqual(tagged('rust', 'fn main() {}', 'def'), ['main'])
        rows = tokens('go', 'x := `raw\nstill raw`')
        self.assertEqual(rows[1], [('string', 'still raw`')])

    def test_detect(self):
        cases = {
            'a.py': 'python', 'b.tsx': 'typescript', 'c.json': 'json', 'd.yaml': 'yaml',
            'e.toml': 'toml', 'f.conf': 'ini', 'dev.wolklaw.SparkEdit.desktop': 'ini',
            'g.service': 'ini', 'h.sh': 'shell', '.bashrc': 'shell', 'README.md': 'markdown',
            'i.html': 'html', 'j.svg': 'html', 'k.css': 'css', 'l.c': 'c', 'm.hpp': 'cpp',
            'n.rs': 'rust', 'o.go': 'go', 'notes.txt': None, 'system.log': None,
        }
        for name, lang in cases.items():
            with self.subTest(name=name):
                self.assertEqual(syntax.detect('/x/' + name), lang)
        self.assertEqual(syntax.detect('/x/run', '#!/usr/bin/env python3'), 'python')
        self.assertEqual(syntax.detect('/x/run', '#!/bin/bash'), 'shell')
        self.assertEqual(syntax.detect('/home/me/.config/kwinrc', '[Desktop]'), 'ini')

    def test_long_lines_are_cut(self):
        lexer = syntax.lexer_for('python')
        rows = syntax.lex_lines(lexer, ['"' + 'x' * 100, 'y = 1'], limit=10)
        self.assertEqual(rows[0][0], [('string', 0, 10)])
        self.assertEqual(rows[0][1], None)

    def test_speed(self):
        """The visible lines plus margins (about 150) must lex in well under a frame."""
        with open(os.path.join(APP_DIR, 'sparkedit', 'syntax.py'), encoding='utf-8') as f:
            lines = f.read().split('\n')[:150]
        lexer = syntax.lexer_for('python')
        t0 = time.perf_counter()
        for _ in range(10):
            syntax.lex_lines(lexer, lines)
        per_screen = (time.perf_counter() - t0) / 10
        self.assertLess(per_screen, 0.03, f"{per_screen * 1000:.1f} ms for 150 lines")


# ─── Search ────────────────────────────────────────────────────

class Search(unittest.TestCase):
    TEXT = 'Foo foo food\nbar FOO\n'

    def spans(self, query):
        pattern = query.compile()
        return [m.span() for m in pattern.finditer(self.TEXT)]

    def test_case(self):
        self.assertEqual(len(self.spans(search.Query('foo'))), 4)
        self.assertEqual(self.spans(search.Query('foo', case=True)), [(4, 7), (8, 11)])

    def test_whole_word(self):
        self.assertEqual(len(self.spans(search.Query('foo', word=True))), 3)

    def test_regex_and_literal(self):
        self.assertEqual(self.spans(search.Query('fo+d', regex=True)), [(8, 12)])
        self.assertEqual(self.spans(search.Query('fo+d')), [])
        self.assertEqual(self.spans(search.Query('^bar', regex=True)), [(13, 16)])
        with self.assertRaises(Exception):
            search.Query('(', regex=True).compile()

    def test_next_prev_wrap(self):
        p = search.Query('foo').compile()
        self.assertEqual(search.find_next(p, self.TEXT, 1), (4, 7))
        self.assertEqual(search.find_next(p, self.TEXT, 18), (0, 3))
        self.assertEqual(search.find_prev(p, self.TEXT, 4), (0, 3))
        self.assertEqual(search.find_prev(p, self.TEXT, 0), (17, 20))
        self.assertIsNone(search.find_next(search.Query('zzz').compile(), self.TEXT, 0))

    def test_empty_matches_move_on(self):
        p = search.Query('^', regex=True).compile()
        self.assertEqual(search.find_next(p, self.TEXT, 0), (13, 13))

    def test_count_and_index(self):
        p = search.Query('o').compile()
        n, more = search.count(p, self.TEXT)
        self.assertEqual((n, more), (8, False))
        self.assertEqual(search.count(p, self.TEXT, limit=5), (5, True))
        self.assertEqual(search.index_of(p, self.TEXT, (5, 6)), 3)

    def test_replacements(self):
        q = search.Query(r'(\w+)@(\w+)', regex=True)
        out = search.replacements(q, q.compile(), 'a@b c@d', r'\2@\1')
        self.assertEqual(out, [(0, 3, 'b@a'), (4, 7, 'd@c')])
        lit = search.Query('a.b')
        self.assertEqual(search.replacements(lit, lit.compile(), 'a.b axb', r'\1'),
                         [(0, 3, r'\1')])

    def test_lines(self):
        lines = search.Lines('ab\ncde\n\nf')
        self.assertEqual(lines.to_index(0), '1.0')
        self.assertEqual(lines.to_index(4), '2.1')
        self.assertEqual(lines.to_index(7), '3.0')
        self.assertEqual(lines.to_index(8), '4.0')
        self.assertEqual(lines.to_offset(2, 1), 4)
        self.assertEqual(lines.to_offset(99, 0), 8)


# ─── Session and autosave ──────────────────────────────────────

class Session(unittest.TestCase):
    def test_autosave_roundtrip(self):
        rec = session.Autosave(id=session.new_id(), path='/tmp/a.txt', title='a.txt',
                               fmt={'encoding': 'utf-8', 'bom': False, 'newline': '\r\n'},
                               cursor='3.4', disk_mtime=123.0)
        self.assertTrue(session.write_autosave(rec, 'unsaved\ntext'))
        back = session.read_autosave(rec.id)
        self.assertEqual(back.text, 'unsaved\ntext')
        self.assertEqual((back.path, back.cursor, back.disk_mtime, back.pid),
                         ('/tmp/a.txt', '3.4', 123.0, os.getpid()))
        self.assertEqual(Format.from_dict(back.fmt).newline, '\r\n')
        session.drop_autosave(rec.id)
        self.assertIsNone(session.read_autosave(rec.id))

    def test_orphans_only_from_dead_processes(self):
        mine = session.Autosave(id=session.new_id(), path=None, title='Untitled')
        session.write_autosave(mine, 'mine')
        dead = session.Autosave(id=session.new_id(), path=None, title='Untitled 2')
        session.write_autosave(dead, 'crashed')
        meta = os.path.join(session.autosave_dir(), dead.id + '.json')
        with open(meta, encoding='utf-8') as f:
            data = f.read()
        proc = subprocess.Popen([sys.executable, '-c', 'pass'])
        proc.wait()
        with open(meta, 'w', encoding='utf-8') as f:
            f.write(data.replace(f'"pid": {os.getpid()}', f'"pid": {proc.pid}'))
        ids = [r.id for r in session.orphans([])]
        self.assertIn(dead.id, ids)
        self.assertNotIn(mine.id, ids)
        self.assertNotIn(dead.id, [r.id for r in session.orphans([dead.id])])
        session.drop_autosave(mine.id)
        session.drop_autosave(dead.id)


# ─── Command line ──────────────────────────────────────────────

class CommandLine(TempDir):
    def test_targets(self):
        path = self.write('a.py', b'x')
        self.assertEqual(parse_target(path), (path, 0, 0))
        self.assertEqual(parse_target(path + ':12'), (path, 12, 0))
        self.assertEqual(parse_target(path + ':12:5'), (path, 12, 5))
        self.assertEqual(parse_target(path + ':12:5:'), (path, 12, 5))
        if os.name == 'posix':                     # Windows names can't hold a colon
            odd = self.write('b:7', b'x')
            self.assertEqual(parse_target(odd), (odd, 0, 0))
        self.assertEqual(parse_target(self.path('new.txt')), (self.path('new.txt'), 0, 0))

    def test_self_test(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = self_test()
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn('self-test passed', out.getvalue())

    def test_version(self):
        result = subprocess.run([sys.executable, os.path.join(APP_DIR, 'spark_edit.py'),
                                 '--version'], capture_output=True, text=True)
        self.assertEqual(result.stdout.strip(), f'Spark Edit {VERSION}')

    def test_instance_protocol(self):
        data = instance.encode([('/a b/c.txt', 3, 2), ('/d', 0, 0)])
        self.assertEqual(instance.decode(data), (True, [('/a b/c.txt', 3, 2), ('/d', 0, 0)]))


# ─── Desktop entry and MIME types ──────────────────────────────

def desktop_keys():
    keys = {}
    with open(os.path.join(APP_DIR, 'dev.wolklaw.SparkEdit.desktop'), encoding='utf-8') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                k, _, v = line.rstrip('\n').partition('=')
                keys.setdefault(k, v)
    return keys


GLOBS = '/usr/share/mime/globs2'
MUST_OPEN = ('.txt', '.log', '.md', '.py', '.sh', '.json', '.yaml', '.yml', '.toml', '.ini',
             '.conf', '.c', '.h', '.cpp', '.hpp', '.rs', '.go', '.js', '.css', '.xml')


class Desktop(unittest.TestCase):
    def test_entry(self):
        keys = desktop_keys()
        self.assertEqual(keys['Exec'], 'spark-edit %F')
        self.assertEqual(keys['Icon'], 'dev.wolklaw.SparkEdit')
        self.assertEqual(keys['StartupWMClass'], 'SparkEdit')
        self.assertTrue(keys['MimeType'].startswith('text/plain;'))

    @unittest.skipUnless(os.path.isfile(GLOBS), "needs shared-mime-info (Linux)")
    def test_mime_types_cover_the_languages(self):
        """Look up each extension Spark Edit colours in this system's MIME database and
        print the table (CI logs it); the common ones must be in MimeType."""
        listed = set(filter(None, desktop_keys()['MimeType'].split(';')))
        by_ext = {}
        with open(GLOBS, encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split(':')
                if len(parts) >= 3 and parts[2].startswith('*.') and '*' not in parts[2][2:]:
                    ext = parts[2][1:].lower()
                    weight = int(parts[0])
                    if ext not in by_ext or weight > by_ext[ext][0]:
                        by_ext[ext] = (weight, parts[1])
        missing = []
        print()
        for ext in sorted(set(syntax.EXT_TO_LANG) | set(MUST_OPEN)):
            mime = by_ext.get(ext, (0, '-'))[1]
            mark = 'listed' if mime in listed else ('-' if mime == '-' else 'NOT LISTED')
            print(f"  {ext:<16} {mime:<40} {mark}")
            if ext in MUST_OPEN and mime not in listed:
                missing.append(f"{ext} ({mime})")
        self.assertEqual(missing, [])


# ─── The window ────────────────────────────────────────────────

@unittest.skipUnless(DISPLAY, "needs a display (xvfb-run on CI)")
class Window(TempDir):
    def setUp(self):
        super().setUp()
        from sparkedit.app import App
        for name in os.listdir(session.autosave_dir()):
            os.unlink(os.path.join(session.autosave_dir(), name))
        self.App = App
        self.apps = []

    def tearDown(self):
        for app in self.apps:
            try:
                for buf in app.buffers:
                    buf.text.edit_modified(False)
                app.quit()
            except Exception:     # noqa: BLE001
                pass
        super().tearDown()

    def app(self, files=(), restore=False):
        app = self.App([(f, 0, 0) for f in files], restore=restore)
        app.root.after_cancel(app._poll_id) if app._poll_id else None
        self.apps.append(app)
        self.pump(app)
        return app

    def pump(self, app, until=None, timeout=10.0):
        end = time.monotonic() + timeout
        while True:
            app.root.update()
            app._poll()
            if until is None or until():
                if until is None:
                    return True
                return True
            if time.monotonic() > end:
                self.fail("timed out waiting")
            time.sleep(0.005)

    def type(self, buf, text):
        for ch in text:
            if ch == '\n':
                buf.text.event_generate('<Return>')
            else:
                buf.text.insert('insert', ch)
        buf.app.root.update()

    def test_new_buffer_on_start(self):
        app = self.app()
        self.assertEqual(len(app.buffers), 1)
        self.assertIsNone(app.buffers[0].path)
        self.assertEqual(app.current.title, 'Untitled')

    def test_open_edit_undo_save_keeps_crlf(self):
        path = self.write('w.txt', b'one\r\ntwo\r\n')
        app = self.app([path])
        buf = app.current
        self.assertEqual(buf.title, 'w.txt')
        self.assertEqual(len(app.buffers), 1, "the empty Untitled tab should make way")
        self.assertFalse(buf.dirty)
        self.assertEqual(app.st_newline.cget('text'), 'CRLF')
        buf.text.mark_set('insert', '1.3')
        self.type(buf, '!')
        self.assertTrue(buf.dirty)
        buf.text.edit_undo()
        app.root.update()
        self.assertFalse(buf.dirty, "undo back to the saved text should clear the dot")
        buf.text.edit_redo()
        app.root.update()
        self.assertTrue(buf.dirty)
        self.assertTrue(app.save(buf))
        self.assertEqual(self.read('w.txt'), b'one!\r\ntwo\r\n')
        self.assertFalse(buf.dirty)

    def test_auto_indent(self):
        app = self.app()
        buf = app.current
        buf.set_language('python')
        self.type(buf, 'def f():\nx\n')
        self.assertEqual(buf.get_all(), 'def f():\n    x\n    ')
        buf.text.event_generate('<BackSpace>')
        app.root.update()
        self.assertEqual(buf.get_all(), 'def f():\n    x\n')

    def test_toggle_comment(self):
        app = self.app()
        buf = app.current
        buf.set_language('python')
        buf.text.insert('1.0', 'a = 1\n    b = 2\n')
        buf.text.tag_add('sel', '1.0', '2.end')
        buf.toggle_comment()
        self.assertEqual(buf.get_all(), '# a = 1\n#     b = 2\n')
        buf.text.tag_add('sel', '1.0', '2.end')
        buf.toggle_comment()
        self.assertEqual(buf.get_all(), 'a = 1\n    b = 2\n')

    def test_syntax_tags_on_visible_lines(self):
        src = ''.join(f'def f{i}():\n    return "s{i}"  # c\n' for i in range(400))
        path = self.write('m.py', src.encode())
        app = self.app([path])
        buf = app.current
        buf.refresh()
        self.assertTrue(buf.text.tag_ranges('sx_keyword'))
        self.assertTrue(buf.text.tag_ranges('sx_string'))
        # far below the screen nothing is coloured yet
        self.assertFalse(buf.text.tag_nextrange('sx_keyword', '700.0', 'end'))
        buf.goto_line(790)
        buf.refresh()
        self.assertTrue(buf.text.tag_nextrange('sx_keyword', '780.0', '800.0'))

    def test_block_comment_far_above_the_screen(self):
        src = '/* start\n' + 'still comment\n' * 5000 + '*/\nint x;\n' * 1
        path = self.write('c.c', src.encode())
        app = self.app([path])
        buf = app.current
        buf.goto_line(4000)
        buf.refresh()
        self.pump(app, until=lambda: not buf.highlighter._bg)
        buf.refresh()
        self.assertTrue(buf.text.tag_nextrange('sx_comment', '4000.0', '4000.end'))
        buf.goto_line(5003)
        buf.refresh()
        self.assertTrue(buf.text.tag_nextrange('sx_type', '5003.0', '5003.end'))

    def test_big_file_loads_in_slices(self):
        line = 'x' * 79 + '\n'
        path = self.write('big.log', (line * 120000).encode())       # about 9.6 MB
        app = self.app()
        buf = app.open_path(path)
        self.pump(app, until=lambda: buf.first_screen_at is not None)
        self.pump(app, until=lambda: not buf.loading, timeout=60)
        self.assertEqual(buf.line_count(), 120001)
        self.assertFalse(buf.dirty)
        self.assertFalse(buf.wrap, "files over 5 MB open without word wrap")
        self.assertEqual(buf.cursor(), (1, 0))
        buf.text.insert('1.0', 'y')
        self.assertTrue(buf.dirty)

    def test_find_and_replace_all(self):
        path = self.write('f.txt', b'cat dog cat\ncatalog\n')
        app = self.app([path])
        buf = app.current
        app.find('replace')
        bar = app.findbar
        bar.find_entry.insert(0, 'cat')
        bar.word.set(True)
        bar._changed()
        self.assertEqual(bar.count.cget('text'), '1 OF 2')
        bar.step(+1)
        self.assertEqual(bar.count.cget('text'), '2 OF 2')
        bar.replace_entry.insert(0, 'bird')
        bar.replace_all()
        self.assertEqual(buf.get_all(), 'bird dog bird\ncatalog\n')
        buf.text.edit_undo()
        self.assertEqual(buf.get_all(), 'cat dog cat\ncatalog\n', "Replace all is one undo")

    def test_regex_replace_one(self):
        path = self.write('r.txt', b'a=1\nb=2\n')
        app = self.app([path])
        buf = app.current
        app.find('replace')
        bar = app.findbar
        bar.find_entry.insert(0, r'(\w)=(\d)')
        bar.regex.set(True)
        bar._changed()
        bar.replace_entry.insert(0, r'\2=\1')
        bar.replace_one()
        self.assertEqual(buf.get_all(), '1=a\nb=2\n')

    def test_goto_line(self):
        path = self.write('g.txt', ''.join(f'{i}\n' for i in range(100)).encode())
        app = self.app([path])
        buf = app.current
        app.find('goto')
        app.findbar.goto_entry.delete(0, 'end')
        app.findbar.goto_entry.insert(0, '50:2')
        app.findbar.goto()
        self.assertEqual(buf.cursor(), (50, 1))

    def test_autosave_and_restore_after_a_crash(self):
        path = self.write('a.txt', b'saved\n')
        app = self.app([path])
        buf = app.current
        buf.text.insert('end-1c', 'unsaved')
        app.autosave(buf)
        record = session.read_autosave(buf.autosave_id)
        self.assertEqual(record.text, 'saved\nunsaved')
        self.assertEqual(record.path, path)
        app.save_session()
        # a crash: the window goes without quitting; its pid is now "dead"
        meta = os.path.join(session.autosave_dir(), buf.autosave_id + '.json')
        with open(meta, encoding='utf-8') as f:
            data = f.read()
        with open(meta, 'w', encoding='utf-8') as f:
            f.write(data.replace(f'"pid": {os.getpid()}', '"pid": 999999999'))
        state = os.path.join(os.environ['XDG_STATE_HOME'], 'spark-edit', 'session.json')
        with open(state, encoding='utf-8') as f:
            data = f.read()
        with open(state, 'w', encoding='utf-8') as f:
            f.write(data.replace(f'"pid": {os.getpid()}', '"pid": 999999999'))
        crashed_id = buf.autosave_id
        buf.autosave_id = None
        buf.text.edit_modified(False)
        app2 = self.app(restore=True)
        restored = [b for b in app2.buffers if b.path == path]
        self.assertEqual(len(restored), 1)
        self.pump(app2, until=lambda: not restored[0].loading)
        self.assertEqual(restored[0].get_all(), 'saved\nunsaved')
        self.assertTrue(restored[0].dirty)
        self.assertEqual(self.read('a.txt'), b'saved\n', "the file itself is untouched")
        self.assertTrue(app2.save(restored[0]))
        self.assertEqual(self.read('a.txt'), b'saved\nunsaved')
        self.assertIsNone(session.read_autosave(crashed_id))

    def test_quit_keeps_unsaved_and_next_start_brings_it_back(self):
        app = self.app()
        buf = app.current
        buf.text.insert('1.0', 'scratch note')
        app.root.update()
        app.quit()
        self.apps.remove(app)
        app2 = self.app(restore=True)
        texts = [b.get_all() for b in app2.buffers]
        self.assertIn('scratch note', texts)
        self.assertTrue(app2.current.dirty)

    def test_close_asks_and_dont_save_discards(self):
        from sparkedit import app as appmod
        app = self.app()
        buf = app.current
        buf.text.insert('1.0', 'x')
        app.autosave(buf)
        aid = buf.autosave_id
        answers = []
        original = appmod.ask
        appmod.ask = lambda *a, **k: (answers.append(a[1]), 'discard')[1]
        try:
            app.close_buffer(buf)
        finally:
            appmod.ask = original
        self.assertEqual(answers, ['Save changes?'])
        self.assertNotIn(buf, app.buffers)
        self.assertIsNone(session.read_autosave(aid))

    def test_encoding_and_line_ending_changes(self):
        path = self.write('e.txt', 'é\n'.encode('utf-8'))
        app = self.app([path])
        buf = app.current
        app._save_with('latin-1', False)
        app._set_newline('\r\n')
        self.assertTrue(buf.dirty)
        self.assertTrue(app.save(buf))
        self.assertEqual(self.read('e.txt'), b'\xe9\r\n')
        app.reload(buf, 'utf-8')
        self.pump(app, until=lambda: not buf.loading)
        self.assertEqual(buf.get_all(), '�\n')

    def test_reload_when_changed_on_disk(self):
        path = self.write('d.txt', b'one\n')
        app = self.app([path])
        buf = app.current
        time.sleep(0.05)
        self.write('d.txt', b'two\n')
        os.utime(path, (time.time() + 5, time.time() + 5))
        app._focus_in(type('E', (), {'widget': app.root})())
        self.pump(app, until=lambda: not buf.loading)
        self.assertEqual(buf.get_all(), 'two\n')

    @unittest.skipUnless(LINUX, "Unix socket")
    def test_second_launch_hands_files_over(self):
        app = self.app()
        path = self.write('h.txt', b'handed over\n')
        script = (f"import sys; sys.path.insert(0, {APP_DIR!r}); "
                  f"from sparkedit.instance import hand_over; "
                  f"sys.exit(0 if hand_over([({path!r}, 1, 1)]) else 1)")
        proc = subprocess.Popen([sys.executable, '-c', script])
        self.pump(app, until=lambda: proc.poll() is not None)
        self.assertEqual(proc.returncode, 0)
        self.pump(app, until=lambda: any(b.path == path for b in app.buffers))


if __name__ == '__main__':
    unittest.main()
