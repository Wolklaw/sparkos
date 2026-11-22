"""One open file: its Text widget, line numbers, syntax colours, loading in chunks, and the
small editing helpers (indent, comment, Home).

Speed comes from doing work only for what is on screen. Line numbers and colours are drawn
for the visible lines plus a margin, again after each scroll or edit. Big files are put into
the Text widget a slice at a time (about 25 ms each) so the window stays live and the first
screen shows at once. Every change to the text passes through a small proxy in front of the
widget's Tcl command, which tells the buffer which line changed.
"""

import re
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Dict, Iterator, List, Optional, Tuple

import tkinter as tk
from tkinter import ttk

from . import BIG_FILE, HUGE_LINE, LONG_LINE, fileio, syntax
from .fileio import Format
from .search import Lines
from .widgets import T, mix

if TYPE_CHECKING:
    from .app import App

SLICE_S = 0.025          # time per loading slice
CHUNK = 64 * 1024        # characters per insert
FIRST_SCREEN = 96 * 1024  # inserted at once, before the window gets control back
MARGIN = 40              # lines coloured above and below the screen
CATCHUP_SYNC = 3000      # lines lexed at once to learn the state at the top of the screen

COLOURS = {
    'comment': T["muted"], 'string': T["gold"], 'keyword': T["accent"],
    'constant': "#ff9ebb", 'number': "#b9a6ff", 'type': "#ff9ebb", 'func': "#8ec9ff",
    'def': T["ch_b"], 'meta': T["pink"], 'key': "#8ec9ff", 'heading': T["accent"],
    'tag': T["accent"], 'attr': "#8ec9ff", 'var': "#b9a6ff", 'code': T["gold"],
    'link': T["ch_b"], 'emph': T["text"],
}


class Highlighter:
    """Colours the lines on screen. For languages whose state runs over lines (block
    comments, multi-line strings), it remembers the state at the start of each line from the
    top down to where it has looked, and forgets from an edited line onwards."""

    def __init__(self, buf: 'Buffer'):
        self.buf = buf
        self.lexer: Optional[syntax.Lexer] = None
        self.states: List[object] = [None]       # states[i]: state at the start of line i+1
        self.epoch = 0                           # bumped when what is known changes
        self._bg: Optional[str] = None
        self._bg_target = 0

    def set_lexer(self, lexer: Optional[syntax.Lexer]) -> None:
        self.cancel()
        self.epoch += 1
        self.lexer = lexer
        self.states = [None]
        buf = self.buf
        for tag in syntax.TAGS:
            buf.call('tag', 'remove', 'sx_' + tag, '1.0', 'end')

    def cancel(self) -> None:
        if self._bg:
            self.buf.text.after_cancel(self._bg)
            self._bg = None

    def invalidate(self, line: int) -> None:
        if len(self.states) > line:
            del self.states[line:]

    def _extend(self, target: int, budget: int) -> None:
        """Learn the states down to line `target`, lexing at most `budget` lines."""
        start = len(self.states)                 # first line whose end state is unknown
        stop = min(target - 1, start + budget - 1)
        if stop < start:
            return
        state = self.states[-1]
        for line in self.buf.get_lines(start, stop):
            if len(line) > LONG_LINE:
                self.lexer.lex(line[:LONG_LINE], state)
                state = None
            else:
                state = self.lexer.lex(line, state)[1]
            self.states.append(state)

    def _background(self) -> None:
        self._bg = None
        if not self.lexer:
            return
        self._extend(self._bg_target, CATCHUP_SYNC)
        if len(self.states) < self._bg_target:
            self._bg = self.buf.text.after(5, self._background)
        else:
            self.epoch += 1
            self.buf.schedule_refresh()

    def colour(self, first: int, last: int) -> None:
        lexer = self.lexer
        if lexer is None or last < first:
            return
        exact = True
        if lexer.multiline and len(self.states) < first:
            if first - len(self.states) <= CATCHUP_SYNC:
                self._extend(first, CATCHUP_SYNC)
            elif self._bg is None:
                # far down a big file: colour from here with a guess now, and learn the
                # real state at this line in the background
                self._bg_target = first
                self._bg = self.buf.text.after(5, self._background)
            exact = len(self.states) >= first
        state = self.states[first - 1] if exact and lexer.multiline else None
        ranges: Dict[str, List[str]] = defaultdict(list)
        record = exact and lexer.multiline
        for i, line in enumerate(self.buf.get_lines(first, last)):
            ln = first + i
            if len(line) > LONG_LINE:
                toks, _ = lexer.lex(line[:LONG_LINE], state)
                state = None
            else:
                toks, state = lexer.lex(line, state)
            if record and len(self.states) == ln:
                self.states.append(state)
            for tag, s, e in toks:
                r = ranges[tag]
                r.append(f'{ln}.{s}')
                r.append(f'{ln}.{e}')
        buf = self.buf
        for tag in syntax.TAGS:
            buf.call('tag', 'remove', 'sx_' + tag, f'{first}.0', f'{last}.end')
        for tag, r in ranges.items():
            buf.call('tag', 'add', 'sx_' + tag, *r)


class Buffer:
    def __init__(self, app: 'App', path: Optional[str] = None, title: str = ''):
        self.app = app
        self.path = path
        self.title = title
        self.fmt = Format()
        self.lang: Optional[str] = None
        self.lang_forced = False
        self.disk_mtime: Optional[float] = None
        self.disk_size = 0
        self.autosave_id: Optional[str] = None
        self.autosaved_version = -1
        self.version = 0
        self.loading = False
        self._shown_dirty = False
        self.load_total = 0
        self.load_done = 0
        self.load_started = 0.0
        self.pending_cursor: Optional[str] = None
        self.indent = ' ' * app.settings['tab_width']
        self.restored = False
        self.wrap = app.settings['wrap']
        self.huge_lines = False          # a line over HUGE_LINE characters
        self._chunks: Optional[Iterator[str]] = None
        self._refresh_id: Optional[str] = None
        self._content: Optional[Tuple[int, str, Lines]] = None
        self._gutter_digits = 0
        self._curline = 0
        self._scroll: Tuple = ()
        self._coloured: Tuple = ()
        self.refreshes = 0
        self.first_screen_at: Optional[float] = None

        px = app.px
        self.frame = tk.Frame(app.body, bg=T["bg"])
        self.gutter = tk.Canvas(self.frame, bg=T["bg"], highlightthickness=0, bd=0, width=px(40),
                                takefocus=0)
        self.text = tk.Text(
            self.frame, wrap='word' if self.wrap else 'none', undo=True, autoseparators=True,
            maxundo=-1, font=app.editor_font, bg=T["bg"], fg=T["text"],
            insertbackground=T["accent"], insertwidth=max(2, px(2)), insertofftime=500,
            insertontime=700, selectbackground=T["line2"], inactiveselectbackground=T["line"],
            relief='flat', bd=0, highlightthickness=0, padx=px(8), pady=px(4),
            exportselection=True, spacing1=0, spacing3=0, takefocus=1)
        self.vbar = ttk.Scrollbar(self.frame, orient='vertical', command=self._scrollbar,
                                  style="Spark.Vertical.TScrollbar")
        self.hbar = ttk.Scrollbar(self.frame, orient='horizontal', command=self.text.xview,
                                  style="Spark.Horizontal.TScrollbar")
        self.text.configure(yscrollcommand=self._on_yscroll, xscrollcommand=self.hbar.set)
        self.gutter.grid(row=0, column=0, sticky='ns')
        self.text.grid(row=0, column=1, sticky='nsew')
        self.vbar.grid(row=0, column=2, sticky='ns')
        self.frame.rowconfigure(0, weight=1)
        self.frame.columnconfigure(1, weight=1)
        self._place_hbar()
        self.set_tabs()

        self.text.tag_configure('curline', background=T["panel"])
        for tag in syntax.TAGS:
            self.text.tag_configure('sx_' + tag, foreground=COLOURS[tag])
        self.text.tag_configure('sx_heading', font=app.editor_bold)
        self.text.tag_configure('sx_emph', font=app.editor_bold)
        self.text.tag_configure('found', background=mix(T["gold"], T["bg"], 0.72))
        self.text.tag_configure('found_cur', background=T["gold"], foreground=T["on_accent"])
        self.text.tag_lower('curline')
        self.text.tag_raise('found')
        self.text.tag_raise('sel')
        self.text.tag_raise('found_cur')
        try:
            self.text.tag_configure('sel', foreground='')      # selected code keeps its colours
        except tk.TclError:
            pass

        self.highlighter = Highlighter(self)
        self._install_proxy()
        self._bind()

    # ─── The proxy: every change to the text comes through here ────

    def _install_proxy(self) -> None:
        widget = self.text._w
        self._orig = widget + '_spark'
        self.text.tk.call('rename', widget, self._orig)
        self.text.tk.createcommand(widget, self._dispatch)

    def call(self, *args):
        """The Text widget's own command, past the proxy (no change tracking)."""
        return self.text.tk.call(self._orig, *args)

    def _dispatch(self, cmd, *args):
        try:
            if cmd in ('insert', 'delete', 'replace'):
                if self.loading:
                    return ''
                line = int(str(self.call('index', args[0])).split('.')[0])
                result = self.call(cmd, *args)
                if cmd != 'delete' and not self.huge_lines and                         any(len(str(a)) > HUGE_LINE for a in args[1:]):
                    self.text.after_idle(self._check_huge)
                self._changed(line)
                return result
            if self.huge_lines:
                if cmd == 'see' and args and self._see_cheaply(args[0]):
                    return ''
                if cmd == 'xview' and args:
                    return ''                # sideways along a huge line: Tk hangs
            result = self.call(cmd, *args)
            if cmd == 'edit' and args and args[0] in ('undo', 'redo'):
                self._changed(1)
            elif cmd == 'mark' and len(args) > 1 and args[0] == 'set' and args[1] == 'insert':
                self._cursor_moved()
            return result
        except tk.TclError:
            # Tk's own bindings call some commands expecting an error to be caught
            # (deleting a selection that isn't there); answer them the way IDLE does
            return ''

    def _see_cheaply(self, index) -> bool:
        """Tk's own `see` lays out a line from its start, which takes seconds or minutes on
        a line of hundreds of thousands of characters, and Tk calls it after every key. In a
        buffer with such a line, `see` only scrolls up or down to bring the line on screen
        (the view never moves sideways there). True when handled here."""
        try:
            line = int(str(self.call('index', index)).split('.')[0])
        except (tk.TclError, ValueError):
            return False
        first, last = self.visible_lines()
        if line < first:
            self.call('yview', f'{line}.0')
        elif line > last:
            self.call('yview', f'{max(1, line - max(1, last - first) + 1)}.0')
        return True

    def _check_huge(self) -> None:
        if not self.huge_lines and fileio.has_huge_line(self.get_all(), HUGE_LINE):
            self.huge_lines = True
            self.call('xview', 'moveto', 0)
            self.set_wrap(False)
            self.app.on_huge(self)

    def _changed(self, line: int) -> None:
        self.version += 1
        self.highlighter.invalidate(line)
        self.schedule_refresh()
        self.app.on_change(self)

    def _cursor_moved(self) -> None:
        self.schedule_refresh()
        self.app.on_cursor(self)

    # ─── Reading the text ──────────────────────────────────────

    def get_all(self) -> str:
        return str(self.call('get', '1.0', 'end-1c'))

    def get_lines(self, first: int, last: int) -> List[str]:
        if last < first:
            return []
        return str(self.call('get', f'{first}.0', f'{last}.end')).split('\n')

    def content(self) -> Tuple[str, Lines]:
        """The whole text and its line starts, kept until the next change."""
        if self._content is None or self._content[0] != self.version:
            text = self.get_all()
            self._content = (self.version, text, Lines(text))
        return self._content[1], self._content[2]

    def line_count(self) -> int:
        return int(str(self.call('index', 'end-1c')).split('.')[0])

    def cursor(self) -> Tuple[int, int]:
        line, col = str(self.call('index', 'insert')).split('.')
        return int(line), int(col)

    def visible_lines(self) -> Tuple[int, int]:
        first = int(str(self.call('index', '@0,0')).split('.')[0])
        last = int(str(self.call('index', f'@0,{self.text.winfo_height()}')).split('.')[0])
        return first, last

    # ─── Loading ───────────────────────────────────────────────

    def load(self, text: str, fmt: Format, cursor: Optional[str] = None,
             modified: bool = False) -> None:
        """Put text in the widget: the first screen now, the rest a slice at a time."""
        self.fmt = fmt
        self.pending_cursor = cursor
        self.loading = True
        self.restored = modified
        self.load_total, self.load_done = len(text), 0
        self.load_started = time.perf_counter()
        self.detect_indent(text[:200000])
        self.huge_lines = fileio.has_huge_line(text, HUGE_LINE)
        if self.huge_lines:
            self.set_wrap(False)
        elif len(text) > BIG_FILE and self.wrap:
            self.set_wrap(False)
        self.text.configure(undo=False)
        self.call('delete', '1.0', 'end')
        self.call('mark', 'gravity', 'insert', 'left')      # stays at the top while loading
        self._chunks = fileio.chunks(text, CHUNK)
        while self.load_done < FIRST_SCREEN:
            if not self._insert_next():
                break
        self.first_screen_at = time.perf_counter()
        if self._chunks is None:
            return
        self.text.configure(state='disabled')
        self.text.after(1, self._load_step)

    def _insert_next(self) -> bool:
        chunk = next(self._chunks, None) if self._chunks else None
        if chunk is None:
            self._finish_load()
            return False
        self.call('insert', 'end-1c', chunk)
        self.load_done += len(chunk)
        return True

    def _load_step(self) -> None:
        if self._chunks is None or not self.text.winfo_exists():
            return
        self.text.configure(state='normal')
        end = time.perf_counter() + SLICE_S
        more = True
        while more and time.perf_counter() < end:
            more = self._insert_next()
        if more:
            self.text.configure(state='disabled')
            self.app.on_load_progress(self)
            self.schedule_refresh()
            self.text.after(1, self._load_step)

    def _finish_load(self) -> None:
        self._chunks = None
        self.loading = False
        self.text.configure(state='normal', undo=True)
        self.text.edit_reset()
        self.version += 1
        self.text.edit_modified(self.restored)
        self.call('mark', 'gravity', 'insert', 'right')
        if self.pending_cursor:
            self.goto_index(self.pending_cursor)
            self.pending_cursor = None
        self.schedule_refresh()
        self.app.on_loaded(self)

    def cancel_load(self) -> None:
        self._chunks = None
        self.loading = False
        self.highlighter.cancel()

    def detect_indent(self, sample: str) -> None:
        tabs = len(re.findall(r'^\t', sample, re.M))
        spaces = len(re.findall(r'^ {2,}\S', sample, re.M))
        width = self.app.settings['tab_width']
        if tabs > spaces or (tabs == spaces == 0 and self.lang == 'go'):
            self.indent = '\t'
        else:
            self.indent = ' ' * width

    # ─── Look ──────────────────────────────────────────────────

    def set_language(self, lang: Optional[str], forced: bool = False) -> None:
        self.lang = lang
        self.lang_forced = forced
        self.highlighter.set_lexer(syntax.lexer_for(lang))
        self.schedule_refresh()

    def set_wrap(self, on: bool) -> bool:
        """Word wrap on or off. Tk takes seconds per key on a wrapped line of hundreds of
        thousands of characters, so a buffer with such a line stays unwrapped (and doesn't
        scroll sideways either); False if that kept it off."""
        if self.huge_lines:
            on = False
        self.wrap = on
        self.text.configure(wrap='word' if on else 'none')
        self._place_hbar()
        self.schedule_refresh()
        return not self.huge_lines

    def _place_hbar(self) -> None:
        if self.wrap or self.huge_lines:
            self.hbar.grid_remove()
        else:
            self.hbar.grid(row=1, column=1, sticky='ew')

    def set_tabs(self) -> None:
        width = self.app.editor_font.measure(' ' * self.app.settings['tab_width'])
        self.text.configure(tabs=(width,), tabstyle='wordprocessor')
        self._gutter_digits = 0
        self.schedule_refresh()

    # ─── Drawing what's on screen ──────────────────────────────

    def _on_yscroll(self, first, last) -> None:
        # Tk calls this again whenever it re-measures lines, even when nothing moved
        if (first, last) == self._scroll:
            return
        self._scroll = (first, last)
        self.vbar.set(first, last)
        if not self.huge_lines:
            # with a huge line, Tk measures it bit by bit in the background and calls this
            # after each bit; a refresh here would make it start over, for ever. Wheel,
            # scrollbar, keys and edits refresh instead.
            self.schedule_refresh()

    def _scrollbar(self, *args) -> None:
        self.text.yview(*args)
        self.schedule_refresh()

    def schedule_refresh(self) -> None:
        if self._refresh_id is None:
            self._refresh_id = self.text.after(6, self.refresh)

    def refresh(self) -> None:
        self._refresh_id = None
        if not self.text.winfo_ismapped():
            return
        self.refreshes += 1
        first, last = self.visible_lines()
        self._draw_curline()
        self._draw_gutter(first, last)
        total = self.line_count()
        # changing tags makes Tk lay the lines out again, which calls back here: only touch
        # them when something really changed, or a long line keeps the loop going
        key = (first, last, total, self.version, self.highlighter.epoch,
               id(self.highlighter.lexer))
        if key != self._coloured:
            self._coloured = key
            self.highlighter.colour(max(1, first - MARGIN), min(total, last + MARGIN))
        self.app.on_refresh(self, first, last)

    def _draw_curline(self) -> None:
        line = self.cursor()[0]
        if line == self._curline and self.call('tag', 'nextrange', 'curline', f'{line}.0',
                                                f'{line}.0+1c'):
            return
        if self._curline:
            self.call('tag', 'remove', 'curline', f'{self._curline}.0', f'{self._curline + 1}.0')
        self._curline = line
        self.call('tag', 'add', 'curline', f'{line}.0', f'{line + 1}.0')

    def _draw_gutter(self, first: int, last: int) -> None:
        g = self.gutter
        app = self.app
        digits = max(3, len(str(self.line_count())))
        if digits != self._gutter_digits:
            self._gutter_digits = digits
            g.configure(width=app.gutter_font.measure('0' * digits) + app.px(18))
        g.delete('all')
        width = int(g.cget('width'))
        current = self._curline
        x = width - app.px(10)
        call = self.call
        for line in range(first, last + 1):
            info = call('dlineinfo', f'{line}.0')
            info = self.text.tk.splitlist(info) if info else ()
            if len(info) < 5:
                continue
            baseline = int(info[1]) + int(info[4])
            g.create_text(x, baseline, anchor='se', text=str(line), font=app.gutter_font,
                          fill=T["accent"] if line == current else T["dim"])
        g.create_line(width - 1, 0, width - 1, g.winfo_height(), fill=T["line"])

    def paint_matches(self, pattern, first: int, last: int,
                      current: Optional[Tuple[str, str]]) -> None:
        key = (pattern, first, last, current, self.version)
        if key == getattr(self, '_painted', None):
            return
        self._painted = key
        self.call('tag', 'remove', 'found', '1.0', 'end')
        self.call('tag', 'remove', 'found_cur', '1.0', 'end')
        if pattern is not None:
            ranges: List[str] = []
            text = '\n'.join(self.get_lines(first, last))
            lines = Lines(text)
            for i, m in enumerate(pattern.finditer(text)):
                if i > 5000:
                    break
                if m.end() > m.start():
                    l1, c1 = lines.to_pos(m.start())
                    l2, c2 = lines.to_pos(m.end())
                    ranges += [f'{l1 + first - 1}.{c1}', f'{l2 + first - 1}.{c2}']
            if ranges:
                self.call('tag', 'add', 'found', *ranges)
        if current:
            self.call('tag', 'add', 'found_cur', *current)

    # ─── Moving around ─────────────────────────────────────────

    def goto_index(self, index: str) -> None:
        if self.loading:
            self.pending_cursor = index
            return
        self.text.mark_set('insert', index)
        self.text.see('insert')

    def goto_line(self, line: int, col: int = 0) -> None:
        self.goto_index(f'{max(1, line)}.{max(0, col)}')

    # ─── Editing helpers ───────────────────────────────────────

    def _bind(self) -> None:
        t = self.text
        t.bind('<<Modified>>', self._on_modified)
        t.bind('<Configure>', lambda _e: self.schedule_refresh())
        for seq in ('<MouseWheel>', '<Button-4>', '<Button-5>', '<Shift-MouseWheel>'):
            t.bind(seq, lambda _e: self.schedule_refresh(), add='+')
        t.bind('<Map>', lambda _e: self.schedule_refresh())
        t.bind('<Return>', self._return)
        t.bind('<KP_Enter>', self._return)
        t.bind('<Tab>', self._tab)
        for seq in ('<Shift-Tab>', '<ISO_Left_Tab>'):
            try:
                t.bind(seq, self._untab)
            except tk.TclError:
                pass
        t.bind('<BackSpace>', self._backspace)
        t.bind('<Home>', self._home)
        t.bind('<Shift-Home>', lambda e: self._home(e, select=True))

    @property
    def dirty(self) -> bool:
        """Unsaved changes? Tk's own flag, which undo clears again at the saved text."""
        if self.loading:
            return self.restored
        try:
            return bool(self.text.tk.getboolean(self.call('edit', 'modified')))
        except (tk.TclError, ValueError, TypeError):
            return False

    def _on_modified(self, _e=None) -> None:
        dirty = self.dirty
        if dirty != self._shown_dirty:
            self._shown_dirty = dirty
            self.app.on_dirty(self)

    def _has_selection(self) -> bool:
        return bool(self.text.tag_ranges('sel'))

    def _return(self, _e=None):
        t = self.text
        if self.loading:
            return 'break'
        if self._has_selection():
            t.delete('sel.first', 'sel.last')
        line_text = t.get('insert linestart', 'insert')
        indent = re.match(r'[ \t]*', line_text).group()
        lexer = self.highlighter.lexer
        stripped = line_text.rstrip()
        if lexer and lexer.indent_after and stripped and stripped[-1] in lexer.indent_after:
            indent += self.indent
        t.insert('insert', '\n' + indent)
        t.see('insert')
        return 'break'

    def _selected_lines(self) -> Tuple[int, int]:
        first = int(self.text.index('sel.first').split('.')[0])
        last_idx = self.text.index('sel.last')
        last = int(last_idx.split('.')[0])
        if last_idx.endswith('.0') and last > first:
            last -= 1
        return first, last

    def _tab(self, _e=None):
        t = self.text
        if self._has_selection():
            first, last = self._selected_lines()
            if first != last or (t.index('sel.first') == f'{first}.0'
                                 and t.index('sel.last') in (f'{last}.end', f'{last + 1}.0')):
                self._indent_lines(first, last, +1)
                return 'break'
            t.delete('sel.first', 'sel.last')
        if self.indent == '\t':
            t.insert('insert', '\t')
        else:
            col = self.cursor()[1]
            width = len(self.indent)
            t.insert('insert', ' ' * (width - col % width))
        return 'break'

    def _untab(self, _e=None):
        if self._has_selection():
            first, last = self._selected_lines()
        else:
            first = last = self.cursor()[0]
        self._indent_lines(first, last, -1)
        return 'break'

    def _indent_lines(self, first: int, last: int, direction: int) -> None:
        t = self.text
        t.edit_separator()
        width = len(self.indent) if self.indent != '\t' else 1
        for line in range(first, last + 1):
            if direction > 0:
                if t.get(f'{line}.0', f'{line}.end').strip():
                    t.insert(f'{line}.0', self.indent)
            else:
                head = t.get(f'{line}.0', f'{line}.{max(width, 1)}')
                if head.startswith('\t'):
                    t.delete(f'{line}.0', f'{line}.1')
                else:
                    n = len(head) - len(head.lstrip(' '))
                    if n:
                        t.delete(f'{line}.0', f'{line}.{n}')
        t.edit_separator()
        t.tag_remove('sel', '1.0', 'end')
        t.tag_add('sel', f'{first}.0', f'{last + 1}.0')

    def _backspace(self, _e=None):
        """In the indentation, Backspace removes back to the previous indent stop."""
        if self._has_selection() or self.indent == '\t' or self.loading:
            return None
        before = self.text.get('insert linestart', 'insert')
        if before and not before.strip(' '):
            width = len(self.indent)
            n = (len(before) - 1) % width + 1
            self.text.delete(f'insert-{n}c', 'insert')
            return 'break'
        return None

    def _home(self, _e=None, select: bool = False):
        """Home goes to the first character of the line; pressed again, to column 0."""
        t = self.text
        line, col = self.cursor()
        text = t.get(f'{line}.0', f'{line}.end')
        first = len(text) - len(text.lstrip(' \t'))
        target = f'{line}.{0 if col == first or first == len(text) else first}'
        if select:
            anchor = t.index('sel.first') if self._has_selection() and \
                t.compare('sel.last', '==', 'insert') else t.index('insert')
            if self._has_selection() and t.compare('sel.first', '==', 'insert'):
                anchor = t.index('sel.last')
            t.tag_remove('sel', '1.0', 'end')
            a, b = sorted((anchor, target), key=lambda i: tuple(map(int, i.split('.'))))
            t.tag_add('sel', a, b)
        else:
            t.tag_remove('sel', '1.0', 'end')
        t.mark_set('insert', target)
        t.see('insert')
        return 'break'

    def toggle_comment(self) -> bool:
        lexer = self.highlighter.lexer
        marker = lexer.line_comment if lexer else None
        if not marker or self.loading:
            return False
        t = self.text
        if self._has_selection():
            first, last = self._selected_lines()
        else:
            first = last = self.cursor()[0]
        lines = [t.get(f'{n}.0', f'{n}.end') for n in range(first, last + 1)]
        body = [s for s in lines if s.strip()]
        if not body:
            return True
        commented = all(s.lstrip().startswith(marker) for s in body)
        column = min(len(s) - len(s.lstrip()) for s in body)
        t.edit_separator()
        for n, s in zip(range(first, last + 1), lines):
            if not s.strip():
                continue
            if commented:
                at = s.index(marker)
                end = at + len(marker) + (1 if s[at + len(marker):at + len(marker) + 1] == ' '
                                          else 0)
                t.delete(f'{n}.{at}', f'{n}.{end}')
            else:
                t.insert(f'{n}.{column}', marker + ' ')
        t.edit_separator()
        return True

    def destroy(self) -> None:
        self.cancel_load()
        if self._refresh_id:
            self.text.after_cancel(self._refresh_id)
        try:
            self.text.tk.deletecommand(self.text._w)
        except tk.TclError:
            pass
        try:
            self.call('configure', '-yscrollcommand', '')
        except tk.TclError:
            pass
        try:
            self.text.tk.call('rename', self._orig, self.text._w)
        except tk.TclError:
            pass
        self.frame.destroy()
