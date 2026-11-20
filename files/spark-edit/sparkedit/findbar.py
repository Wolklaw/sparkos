"""The bar under the text for Find, Replace and Go to line."""

import re
from typing import TYPE_CHECKING, Optional, Tuple

import tkinter as tk

from . import search
from .search import Query
from .text import t
from .ui import entry, set_entry_error
from .widgets import T, IconButton, Toggle, WolkButton

if TYPE_CHECKING:
    from .app import App
    from .editor import Buffer

LIVE_LIMIT = 4 * 1024 * 1024     # bigger buffers search on Enter, not on every key


class FindBar(tk.Frame):
    def __init__(self, app: 'App'):
        super().__init__(app.main, bg=T["panel"])
        self.app = app
        px, label_font, font = app.px, app.font(8, True), app.font(10, False)
        self.mode = 'find'
        self.query = Query('')
        self.pattern: Optional['re.Pattern'] = None
        self.current: Optional[Tuple[int, int]] = None      # offsets of the selected match
        self.origin = '1.0'
        self._live_id: Optional[str] = None
        self._forced = False
        self._counted: Optional[tuple] = None
        tk.Frame(self, bg=T["line"], height=1).pack(fill='x', side='top')

        # find row
        self.find_row = tk.Frame(self, bg=T["panel"], padx=px(8), pady=px(5))
        self.find_label = tk.Label(self.find_row, text=t('find.find').upper(), font=label_font,
                                   bg=T["panel"], fg=T["muted"], width=9, anchor='w')
        self.find_label.pack(side='left')
        self.find_entry = entry(self.find_row, font, 32)
        self.find_entry.pack(side='left', ipady=px(3), padx=(0, px(8)))
        self.case = Toggle(self.find_row, t('find.case'), False, lambda _v: self._changed(),
                           label_font)
        self.word = Toggle(self.find_row, t('find.word'), False, lambda _v: self._changed(),
                           label_font)
        self.regex = Toggle(self.find_row, t('find.regex'), False, lambda _v: self._changed(),
                            label_font)
        for w in (self.case, self.word, self.regex):
            w.pack(side='left', padx=(0, px(4)))
        self.count = tk.Label(self.find_row, text='', font=label_font, bg=T["panel"],
                              fg=T["muted"], padx=px(8))
        self.count.pack(side='left')
        size = px(24)
        IconButton(self.find_row, 'close', self.close, size, tip='Esc').pack(side='right')
        IconButton(self.find_row, 'down', lambda: self.step(+1), size).pack(side='right')
        IconButton(self.find_row, 'up', lambda: self.step(-1), size).pack(side='right')

        # replace row
        self.replace_row = tk.Frame(self, bg=T["panel"], padx=px(8), pady=px(0))
        tk.Label(self.replace_row, text=t('find.replace').upper(), font=label_font,
                 bg=T["panel"], fg=T["muted"], width=9, anchor='w').pack(side='left')
        self.replace_entry = entry(self.replace_row, font, 32)
        self.replace_entry.pack(side='left', ipady=px(3), padx=(0, px(8)))
        WolkButton(self.replace_row, t('find.replace_one'), self.replace_one,
                   label_font, padx=px(10), pady=px(3)).pack(side='left', padx=(0, px(4)))
        WolkButton(self.replace_row, t('find.replace_all'), self.replace_all,
                   label_font, padx=px(10), pady=px(3)).pack(side='left')

        # go to line row
        self.goto_row = tk.Frame(self, bg=T["panel"], padx=px(8), pady=px(5))
        tk.Label(self.goto_row, text=t('find.goto').upper(), font=label_font, bg=T["panel"],
                 fg=T["muted"], anchor='w').pack(side='left', padx=(0, px(8)))
        self.goto_entry = entry(self.goto_row, font, 14)
        self.goto_entry.pack(side='left', ipady=px(3), padx=(0, px(8)))
        self.goto_hint = tk.Label(self.goto_row, text='', font=label_font, bg=T["panel"],
                                  fg=T["dim"])
        self.goto_hint.pack(side='left')
        IconButton(self.goto_row, 'close', self.close, size, tip='Esc').pack(side='right')

        e = self.find_entry
        e.bind('<KeyRelease>', self._typed)
        e.bind('<Return>', lambda _e: self.step(+1) or 'break')
        e.bind('<KP_Enter>', lambda _e: self.step(+1) or 'break')
        e.bind('<Shift-Return>', lambda _e: self.step(-1) or 'break')
        self.replace_entry.bind('<Return>', lambda _e: self.replace_one() or 'break')
        self.replace_entry.bind('<Control-Return>', lambda _e: self.replace_all() or 'break')
        self.goto_entry.bind('<Return>', lambda _e: self.goto() or 'break')
        self.goto_entry.bind('<KP_Enter>', lambda _e: self.goto() or 'break')
        for w in (self.find_entry, self.replace_entry, self.goto_entry):
            w.bind('<Escape>', lambda _e: self.close() or 'break')
            app.bind_shortcuts(w)

    # ─── Showing ───────────────────────────────────────────────

    @property
    def shown(self) -> bool:
        return bool(self.winfo_ismapped())

    def open(self, mode: str) -> None:
        buf = self.app.current
        self.mode = mode
        for row in (self.find_row, self.replace_row, self.goto_row):
            row.pack_forget()
        if mode == 'goto':
            self.goto_row.pack(fill='x')
            if buf:
                self.goto_hint.configure(text=t('find.goto_hint', n=buf.line_count()).upper())
                line = buf.cursor()[0]
                self.goto_entry.delete(0, 'end')
                self.goto_entry.insert(0, str(line))
            self.goto_entry.select_range(0, 'end')
            target = self.goto_entry
        else:
            self.find_row.pack(fill='x')
            if mode == 'replace':
                self.replace_row.pack(fill='x', pady=(0, self.app.px(6)))
            if buf:
                self.origin = buf.text.index('insert')
                if buf.text.tag_ranges('sel'):
                    selected = buf.text.get('sel.first', 'sel.last')
                    if selected and '\n' not in selected and len(selected) < 200:
                        self.origin = buf.text.index('sel.first')
                        self.find_entry.delete(0, 'end')
                        self.find_entry.insert(0, selected)
            self.find_entry.select_range(0, 'end')
            target = self.find_entry
        if not self.shown:
            self.pack(side='bottom', fill='x', before=self.app.body)
        target.focus_set()
        target.icursor('end')
        if mode != 'goto':
            self._changed()

    def close(self) -> None:
        if not self.shown:
            return
        self.pack_forget()
        self.pattern = None
        self.current = None
        buf = self.app.current
        if buf:
            buf.paint_matches(None, 1, 0, None)
            buf.text.focus_set()

    # ─── Finding ───────────────────────────────────────────────

    def _typed(self, event=None) -> None:
        if event is not None and event.keysym in ('Return', 'KP_Enter', 'Escape', 'Shift_L',
                                                  'Shift_R', 'Control_L', 'Control_R'):
            return
        if self.query.text == self.find_entry.get():
            return
        if self._live_id:
            self.after_cancel(self._live_id)
        self._live_id = self.after(120, self._changed)

    def _changed(self) -> None:
        """The query or a switch changed: compile it, select the first match from where the
        search started, and count."""
        self._live_id = None
        self.query = Query(self.find_entry.get(), self.case.value, self.word.value,
                           self.regex.value)
        set_entry_error(self.find_entry, False)
        try:
            self.pattern = self.query.compile()
        except (re.error, OverflowError) as exc:
            self.pattern = None
            set_entry_error(self.find_entry, True)
            self.count.configure(text=t('find.bad', why=str(exc)).upper(), fg=T["pink"])
            self.app.glitch.now(self.app.strip)
            self._paint()
            return
        buf = self.app.current
        if self.pattern is None or buf is None:
            self.current = None
            self.count.configure(text='')
            self._paint()
            return
        if buf.loading:
            self.count.configure(text=t('find.loading').upper(), fg=T["gold"])
            return
        if buf.load_total > LIVE_LIMIT and not self._forced:
            self.current = None
            self.count.configure(text=t('find.enter').upper(), fg=T["dim"])
            self._paint()
            return
        text, lines = buf.content()
        start = lines.to_offset(*map(int, self.origin.split('.')))
        self._select(search.find_next(self.pattern, text, start), buf, text, lines)

    def step(self, direction: int) -> None:
        if self.mode == 'goto':
            return
        buf = self.app.current
        if buf is None:
            return
        if self.pattern is None or self.query.text != self.find_entry.get():
            self._forced = True
            try:
                self._changed()
            finally:
                self._forced = False
            if self.pattern is None or self.current is not None:
                return
        if buf.loading:
            return
        text, lines = buf.content()
        if self.current is not None:
            pos = self.current[1] if direction > 0 else self.current[0]
        else:
            pos = lines.to_offset(*buf.cursor())
        if direction > 0:
            span = search.find_next(self.pattern, text, pos)
        else:
            span = search.find_prev(self.pattern, text, pos)
        self._select(span, buf, text, lines)

    def _select(self, span, buf: 'Buffer', text: str, lines: search.Lines) -> None:
        self.current = span
        if span is None:
            self.count.configure(text=t('find.none').upper(), fg=T["pink"])
            self.app.glitch.now(self.app.strip)
            buf.paint_matches(self.pattern, *buf.visible_lines(), None)
            return
        a, b = lines.to_index(span[0]), lines.to_index(span[1])
        tx = buf.text
        tx.tag_remove('sel', '1.0', 'end')
        tx.tag_add('sel', a, b)
        tx.mark_set('insert', b)
        tx.see(a)
        tx.see(b)
        key = (id(buf), buf.version, self.pattern)
        if self._counted is None or self._counted[0] != key:
            self._counted = (key, search.count(self.pattern, text))
        n, more = self._counted[1]
        i = search.index_of(self.pattern, text, span)
        key = 'find.count_many' if more else 'find.count'
        self.count.configure(text=t(key, i=i, n=n).upper(), fg=T["muted"])
        self._paint()

    def _paint(self) -> None:
        buf = self.app.current
        if buf is not None and not buf.loading:
            buf.refresh()

    def paint(self, buf: 'Buffer', first: int, last: int) -> None:
        """Called after each refresh of the visible lines."""
        if not self.shown or self.mode == 'goto':
            return
        current = None
        if self.current is not None and self.pattern is not None:
            _text, lines = buf.content()
            current = (lines.to_index(self.current[0]), lines.to_index(self.current[1]))
        buf.paint_matches(self.pattern, first, last, current)

    def forget(self) -> None:
        """The text changed: offsets no longer point at the same place."""
        self.current = None

    # ─── Replacing ─────────────────────────────────────────────

    def replace_one(self) -> None:
        buf = self.app.current
        if buf is None or buf.loading:
            return
        if self.pattern is None:
            self._changed()
        if self.pattern is None:
            return
        tx = buf.text
        if self.current is not None and tx.tag_ranges('sel'):
            text, lines = buf.content()
            m = self.pattern.match(text, self.current[0])
            if m and m.end() == self.current[1]:
                new = self.query.expand(m, self.replace_entry.get())
                a, b = lines.to_index(m.start()), lines.to_index(m.end())
                tx.edit_separator()
                tx.delete(a, b)
                tx.insert(a, new)
                tx.edit_separator()
                text, lines = buf.content()
                after = m.start() + len(new)
                self._select(search.find_next(self.pattern, text, after), buf, text, lines)
                return
        self.step(+1)

    def replace_all(self) -> None:
        buf = self.app.current
        if buf is None or buf.loading:
            return
        self._changed() if self.pattern is None else None
        if self.pattern is None:
            return
        text, lines = buf.content()
        todo = search.replacements(self.query, self.pattern, text, self.replace_entry.get())
        if not todo:
            self.count.configure(text=t('find.none').upper(), fg=T["pink"])
            return
        tx = buf.text
        tx.edit_separator()
        tx.configure(autoseparators=False)
        try:
            for start, end, new in reversed(todo):
                buf.call('delete', lines.to_index(start), lines.to_index(end))
                if new:
                    buf.call('insert', lines.to_index(start), new)
        finally:
            tx.configure(autoseparators=True)
            tx.edit_separator()
        buf._changed(lines.to_pos(todo[0][0])[0])
        self.current = None
        self.count.configure(text=t('find.replaced', n=len(todo)).upper(), fg=T["accent"])
        self.app.glitch.now(self.app.strip)
        buf.refresh()

    # ─── Go to line ────────────────────────────────────────────

    def goto(self) -> None:
        buf = self.app.current
        if buf is None:
            return
        m = re.fullmatch(r'\s*(\d+)\s*(?:[:,.]\s*(\d+))?\s*', self.goto_entry.get())
        if not m:
            set_entry_error(self.goto_entry, True)
            self.app.glitch.now(self.app.strip)
            return
        set_entry_error(self.goto_entry, False)
        line = min(int(m.group(1)), buf.line_count())
        col = max(0, int(m.group(2)) - 1) if m.group(2) else 0
        self.close()
        buf.goto_line(line, col)
        buf.text.focus_set()
