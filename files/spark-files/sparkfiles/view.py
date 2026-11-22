"""The file view: a list (name, size, modified, type) or a grid of tiles with thumbnails, drawn
on one canvas. Only the rows on screen are drawn, so a folder of 10,000 or 100,000 files
scrolls as fast as a folder of ten.

Selection follows the desktop's habits: click, Ctrl+click, Shift+click, Ctrl+A, a rubber band
from empty space, arrows (with Shift), Home/End, Page Up/Down. Double-click or Enter opens."""

import math
import os
from typing import Dict, List, Optional, Set, Tuple

import tkinter as tk
from tkinter import ttk

from .core import human_date, human_size
from .listing import Entry, type_label
from .text import t
from .ui import Timers
from .widgets import T, mix

DRAG_START = 6          # pixels the pointer moves before a press becomes a drag


class FileView(Timers, tk.Frame):
    def __init__(self, parent: tk.Misc, app, pane):
        super().__init__(parent, bg=T["bg"])
        self.app, self.pane = app, pane
        px = app.px
        self.mode = 'list'
        self.entries: List[Entry] = []
        self.index: Dict[str, int] = {}
        self.selected: Set[str] = set()
        self.cursor = -1
        self.anchor = -1
        self.top = 0
        self.hover = -1
        self.drop_index = -1               # the folder a drag would drop into
        self.drop_all = False              # the whole view is the drop target
        self.cut: Set[str] = set()
        self.show_folder_column = False    # search results: where each file is
        self.search_root = ''
        self.where_fn = None               # the Trash: where each item came from
        self.empty_text = ''
        self.font = app.font(10, False)
        self.font_small = app.font(9, False)
        self.font_head = app.font(8, True)
        self.row_h = px(26)
        self.head_h = px(24)
        self.cols = [('name', 0), ('size', px(92)), ('modified', px(150)), ('type', px(150))]
        self._fit: Dict[Tuple[str, int, int], str] = {}
        self._fit2: Dict[Tuple[str, int], Tuple[str, str]] = {}
        self._press: Optional[Tuple[int, int, int, int]] = None    # x, y, index, state
        self._band: Optional[Tuple[int, int, Set[str]]] = None     # x0, y0(content), base
        self._band_pos: Optional[Tuple[int, int]] = None
        self._autoscroll: Optional[str] = None
        self._rename_entry: Optional[tk.Entry] = None
        self._rename_path = ''
        self._redraw_id: Optional[str] = None

        self.header = tk.Canvas(self, height=self.head_h, bg=T["panel"], highlightthickness=0,
                                bd=0)
        self.canvas = tk.Canvas(self, bg=T["bg"], highlightthickness=1,
                                highlightbackground=T["bg"], highlightcolor=T["line2"], bd=0,
                                takefocus=1, cursor='arrow')
        self.scroll = ttk.Scrollbar(self, orient='vertical', style='Spark.Vertical.TScrollbar',
                                    command=self._scrollbar)
        self.header.grid(row=0, column=0, columnspan=2, sticky='ew')
        self.canvas.grid(row=1, column=0, sticky='nsew')
        self.scroll.grid(row=1, column=1, sticky='ns')
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        c = self.canvas
        c.bind('<Configure>', lambda _e: self.redraw())
        c.bind('<ButtonPress-1>', self._on_press)
        c.bind('<B1-Motion>', self._on_motion)
        c.bind('<ButtonRelease-1>', self._on_release)
        c.bind('<Double-Button-1>', self._on_double)
        c.bind('<ButtonRelease-2>', self._on_middle)
        c.bind('<ButtonPress-3>', self._on_right)
        c.bind('<Motion>', self._on_hover)
        c.bind('<Leave>', self._on_leave)
        for seq in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            c.bind(seq, self._on_wheel)
        for seq in ('<Control-MouseWheel>', '<Control-Button-4>', '<Control-Button-5>'):
            c.bind(seq, self._on_zoom)
        c.bind('<FocusIn>', lambda _e: (self.pane.focused(), self.redraw()))
        c.bind('<FocusOut>', lambda _e: self.redraw())
        c.bind('<Key>', self._on_key)
        self.header.bind('<ButtonRelease-1>', self._on_header)
        self.header.bind('<Configure>', lambda _e: self.draw_header())

    # ─── content ─────────────────────────────────────────────

    def set_entries(self, entries: List[Entry], reset: bool = False,
                    select: Optional[List[str]] = None) -> None:
        current = self.entries[self.cursor].path if 0 <= self.cursor < len(self.entries) else None
        self.entries = entries
        self.index = {e.path: i for i, e in enumerate(entries)}
        if reset:
            self.top = 0
            self.selected = set()
            current = None
            self.anchor = -1
        if select:
            self.selected = {p for p in select if p in self.index}
            current = next((p for p in select if p in self.index), current)
        else:
            self.selected &= set(self.index)
        self.cursor = self.index.get(current, -1) if current else -1
        if self.cursor < 0 and self.selected:
            self.cursor = min(self.index[p] for p in self.selected)
        if self._rename_path and self._rename_path not in self.index:
            self.cancel_rename()
        self._clamp()
        if select and self.cursor >= 0:
            self.see(self.cursor)
        self.redraw()
        self.pane.selection_changed()

    def set_mode(self, mode: str) -> None:
        if mode != self.mode:
            first = self.first_visible()
            self.mode = mode
            self.cancel_rename()
            if mode == 'grid':
                self.header.grid_remove()
            else:
                self.header.grid()
            self.top = 0
            self.redraw(now=True)
            if first >= 0:
                self.see(first, top=True)

    def selected_entries(self) -> List[Entry]:
        return [e for e in self.entries if e.path in self.selected]

    def select_paths(self, paths: List[str], focus: bool = True) -> None:
        self.selected = {p for p in paths if p in self.index}
        found = [self.index[p] for p in paths if p in self.index]
        if found:
            self.cursor = self.anchor = found[0]
            self.see(self.cursor)
        self.redraw()
        self.pane.selection_changed()
        if focus:
            self.canvas.focus_set()

    def select_all(self) -> None:
        self.selected = set(self.index)
        self.redraw()
        self.pane.selection_changed()

    def clear_selection(self) -> None:
        if self.selected:
            self.selected = set()
            self.redraw()
            self.pane.selection_changed()

    def invert_selection(self) -> None:
        self.selected = set(self.index) - self.selected
        self.redraw()
        self.pane.selection_changed()

    # ─── geometry ────────────────────────────────────────────

    def zoom(self) -> float:
        return float(self.app.settings.get('zoom', 1.0))

    def tile(self) -> Tuple[int, int, int]:
        """(tile width, tile height, icon box) in grid mode."""
        px = self.app.px
        z = self.zoom()
        box = px(round(84 * z))
        w = max(box + px(16), px(round(116 * z)))
        line = self.font.metrics('linespace')
        return w, box + 2 * line + px(14), box

    def columns(self) -> int:
        if self.mode != 'grid':
            return 1
        w, _h, _b = self.tile()
        return max(1, (self.canvas.winfo_width() - 2 * self.app.px(8)) // w)

    def content_height(self) -> int:
        if self.mode == 'grid':
            _w, h, _b = self.tile()
            return math.ceil(len(self.entries) / self.columns()) * h + 2 * self.app.px(8)
        return len(self.entries) * self.row_h + self.app.px(4)

    def item_box(self, i: int) -> Tuple[int, int, int, int]:
        """In canvas pixels (the scroll offset applied)."""
        if self.mode == 'grid':
            w, h, _b = self.tile()
            cols = self.columns()
            pad = self.app.px(8)
            spare = max(0, self.canvas.winfo_width() - 2 * pad - cols * w) // 2
            col, row = i % cols, i // cols
            x0 = pad + spare + col * w
            y0 = pad + row * h - self.top
            return x0, y0, x0 + w, y0 + h
        y0 = i * self.row_h - self.top
        return 0, y0, self.canvas.winfo_width(), y0 + self.row_h

    def index_at(self, x: int, y: int) -> int:
        if not self.entries:
            return -1
        if self.mode == 'grid':
            w, h, _b = self.tile()
            cols = self.columns()
            pad = self.app.px(8)
            spare = max(0, self.canvas.winfo_width() - 2 * pad - cols * w) // 2
            cx, cy = x - pad - spare, y + self.top - pad
            if cx < 0 or cy < 0:
                return -1
            col, row = int(cx // w), int(cy // h)
            if col >= cols:
                return -1
            i = row * cols + col
            return i if i < len(self.entries) else -1
        i = int((y + self.top) // self.row_h)
        if 0 <= i < len(self.entries):
            return i
        return -1

    def first_visible(self) -> int:
        return self.index_at(self.app.px(10), self.app.px(10))

    def shown_cols(self) -> List[Tuple[str, int]]:
        """The columns that fit: Type goes first when the pane is narrow, then the date."""
        width = self.canvas.winfo_width()
        px = self.app.px
        cols = list(self.cols)
        if width < px(620):
            cols = [c for c in cols if c[0] != 'type']
        if width < px(440):
            cols = [c for c in cols if c[0] != 'modified']
        return cols

    def _name_width(self) -> int:
        width = self.canvas.winfo_width()
        fixed = sum(w for name, w in self.shown_cols()[1:])
        return max(self.app.px(120), width - fixed)

    def _clamp(self) -> None:
        h = self.canvas.winfo_height()
        self.top = max(0, min(self.top, max(0, self.content_height() - h)))

    def see(self, i: int, top: bool = False) -> None:
        if not (0 <= i < len(self.entries)):
            return
        h = max(1, self.canvas.winfo_height())
        x0, y0, x1, y1 = self.item_box(i)
        y0 += self.top
        y1 += self.top
        if top or y0 < self.top:
            self.top = y0 - (self.app.px(8) if self.mode == 'grid' else 0)
        elif y1 > self.top + h:
            self.top = y1 - h + (self.app.px(8) if self.mode == 'grid' else 0)
        self._clamp()
        self.redraw()

    # ─── drawing ─────────────────────────────────────────────

    def redraw(self, now: bool = False) -> None:
        if now:
            if self._redraw_id:
                self.after_cancel(self._redraw_id)
                self._redraw_id = None
            self._draw()
        elif self._redraw_id is None:
            self._redraw_id = self.after_idle(self._draw)

    def _draw(self) -> None:
        self._redraw_id = None
        if not self.winfo_exists():
            return
        c = self.canvas
        c.delete('all')
        self._clamp()
        width, height = c.winfo_width(), c.winfo_height()
        total = self.content_height()
        if total > 0 and total > height:
            self.scroll.set(self.top / total, min(1.0, (self.top + height) / total))
        else:
            self.scroll.set(0, 1)
        if self.drop_all:
            c.create_rectangle(1, 1, width - 2, height - 2, outline=T["ch_b"], width=2)
        if not self.entries:
            if self.empty_text:
                c.create_text(width // 2, self.app.px(60), text=self.empty_text,
                              font=self.font, fill=T["dim"], width=max(100, width - 40),
                              justify='center')
            self._draw_band()
            if self.mode == 'list':
                self.draw_header()
            return
        if self.mode == 'grid':
            self._draw_grid(width, height)
        else:
            self._draw_list(width, height)
            self.draw_header()
        self._draw_band()
        if self._rename_entry is not None and self._rename_path in self.index:
            self._place_rename()

    def _row_colours(self, i: int, e: Entry) -> Tuple[Optional[str], str]:
        sel = e.path in self.selected
        focus = self.canvas.focus_get() is self.canvas
        if i == self.drop_index:
            return mix(T["ch_b"], T["bg"], 0.75), T["text"]
        if sel:
            return (T["line2"] if focus else mix(T["line2"], T["bg"], 0.5)), T["text"]
        if i == self.hover:
            return T["panel"], T["text"]
        return None, (T["muted"] if e.hidden or e.path in self.cut else T["text"])

    def _draw_list(self, width: int, height: int) -> None:
        c, px = self.canvas, self.app.px
        first = max(0, self.top // self.row_h)
        last = min(len(self.entries), (self.top + height) // self.row_h + 1)
        name_w = self._name_width()
        icon = px(16)
        lang_t = t
        for i in range(first, last):
            e = self.entries[i]
            x0, y0, x1, y1 = self.item_box(i)
            bg, fg = self._row_colours(i, e)
            if bg:
                c.create_rectangle(0, y0, width, y1 - 1, fill=bg, outline='')
            if i == self.cursor and self.canvas.focus_get() is self.canvas:
                c.create_rectangle(0, y0, px(2), y1 - 1, fill=T["accent"], outline='')
            image = self._icon(e, icon)
            mid = (y0 + y1) // 2
            if image is not None:
                c.create_image(px(10), mid, image=image, anchor='w')
            tx = px(10) + icon + px(8)
            c.create_text(tx, mid, text=self._fit_text(e.name, name_w - tx - px(8), self.font),
                          anchor='w', font=self.font, fill=fg)
            x = name_w
            for key, w in self.shown_cols()[1:]:
                if key == 'size':
                    value = self._size_text(e)
                    c.create_text(x + w - px(12), mid, text=value, anchor='e',
                                  font=self.font_small, fill=T["muted"])
                elif key == 'modified':
                    if self.show_folder_column:
                        where = self.where_fn(e) if self.where_fn else self._where(e)
                        value = self._fit_text(where, w - px(10), self.font_small)
                    else:
                        value = human_date(e.mtime)
                    c.create_text(x + px(4), mid, text=value, anchor='w',
                                  font=self.font_small, fill=T["muted"])
                elif key == 'type':
                    value = self._fit_text(type_label(e, lang_t), w - px(10), self.font_small)
                    c.create_text(x + px(4), mid, text=value, anchor='w',
                                  font=self.font_small, fill=T["muted"])
                x += w

    def _where(self, e: Entry) -> str:
        parent = os.path.dirname(e.path)
        rel = os.path.relpath(parent, self.search_root) if self.search_root else parent
        return '.' if rel == '.' else rel

    def _size_text(self, e: Entry) -> str:
        if e.is_dir:
            return ''
        return human_size(e.size)

    def draw_header(self) -> None:
        h = self.header
        h.delete('all')
        if self.mode != 'list':
            return
        px = self.app.px
        width = h.winfo_width()
        h.create_line(0, self.head_h - 1, width, self.head_h - 1, fill=T["line"])
        x = 0
        sort, rev = self.pane.sort_key(), self.pane.sort_reverse()
        name_w = self._name_width()
        for key, w in self.shown_cols():
            w = name_w if key == 'name' else w
            title = t('col.' + ('where' if key == 'modified' and self.show_folder_column
                                else key)).upper()
            if key == sort:
                title += ' ▼' if rev else ' ▲'
            colour = T["accent"] if key == sort else T["muted"]
            if key == 'size':
                h.create_text(x + w - px(12), self.head_h // 2, text=title, anchor='e',
                              font=self.font_head, fill=colour)
            else:
                lead = px(10) + px(16) + px(8) if key == 'name' else px(4)
                h.create_text(x + lead, self.head_h // 2, text=title, anchor='w',
                              font=self.font_head, fill=colour)
            if key != 'name':
                h.create_line(x, px(5), x, self.head_h - px(5), fill=T["line"])
            x += w

    def _on_header(self, event) -> None:
        if self.mode != 'list':
            return
        x = 0
        name_w = self._name_width()
        for key, w in self.shown_cols():
            w = name_w if key == 'name' else w
            if x <= event.x < x + w:
                if key == 'modified' and self.show_folder_column:
                    return
                self.pane.set_sort(key)
                return
            x += w

    def _draw_grid(self, width: int, height: int) -> None:
        c, px = self.canvas, self.app.px
        w, h, box = self.tile()
        cols = self.columns()
        pad = px(8)
        first_row = max(0, (self.top - pad) // h)
        last_row = (self.top + height) // h + 1
        first, last = first_row * cols, min(len(self.entries), (last_row + 1) * cols)
        thumbs = self.app.settings.get('thumbnails', True)
        line = self.font.metrics('linespace')
        for i in range(first, last):
            e = self.entries[i]
            x0, y0, x1, y1 = self.item_box(i)
            bg, fg = self._row_colours(i, e)
            if bg:
                c.create_rectangle(x0 + px(3), y0 + px(3), x1 - px(3), y1 - px(3), fill=bg,
                                   outline='')
            if i == self.cursor and self.canvas.focus_get() is self.canvas:
                c.create_rectangle(x0 + px(3), y0 + px(3), x1 - px(3), y1 - px(3),
                                   outline=T["accent"], width=1)
            cx = (x0 + x1) // 2
            cy = y0 + px(7) + box // 2
            image = None
            if thumbs and not e.is_dir:
                image = self.app.thumb_for(e, box)
            if image is not None:
                c.create_image(cx, cy, image=image)
                if e.kind == 'video':
                    s = max(px(6), box // 8)
                    c.create_polygon(cx - s // 2, cy - s, cx - s // 2, cy + s, cx + s, cy,
                                     fill=T["text"], outline=T["bg"])
            else:
                icon = self._icon(e, max(px(16), int(box * 0.72)))
                if icon is not None:
                    c.create_image(cx, cy, image=icon)
            l1, l2 = self._fit_two(e.name, w - px(10))
            ty = y0 + px(9) + box
            c.create_text(cx, ty, text=l1, anchor='n', font=self.font, fill=fg)
            if l2:
                c.create_text(cx, ty + line, text=l2, anchor='n', font=self.font, fill=fg)

    def _icon(self, e: Entry, size: int):
        kind = 'broken' if e.broken else e.kind
        return self.app.icons.get(kind, size, e.is_link)

    def _fit_text(self, text: str, width: int, font) -> str:
        key = (text, width, id(font))
        out = self._fit.get(key)
        if out is not None:
            return out
        if width <= 0:
            out = ''
        elif font.measure(text) <= width:
            out = text
        else:
            lo, hi = 0, len(text)
            while lo < hi:                          # longest start that fits with the dots
                mid = (lo + hi + 1) // 2
                if font.measure(text[:mid] + '…') <= width:
                    lo = mid
                else:
                    hi = mid - 1
            out = text[:lo] + '…'
        if len(self._fit) > 20000:
            self._fit.clear()
        self._fit[key] = out
        return out

    def _fit_two(self, text: str, width: int) -> Tuple[str, str]:
        key = (text, width)
        out = self._fit2.get(key)
        if out is not None:
            return out
        font = self.font
        if font.measure(text) <= width:
            out = (text, '')
        else:
            lo, hi = 1, len(text)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if font.measure(text[:mid]) <= width:
                    lo = mid
                else:
                    hi = mid - 1
            cut = lo
            space = text.rfind(' ', 0, cut)          # break at a space when one is close
            if space > cut * 0.6:
                cut = space + 1
            out = (text[:cut].rstrip(), self._fit_text(text[cut:], width, font))
        if len(self._fit2) > 20000:
            self._fit2.clear()
        self._fit2[key] = out
        return out

    def _draw_band(self) -> None:
        if self._band is None or self._band_pos is None:
            return
        x0, y0c, _base = self._band
        x1, y1 = self._band_pos
        y0 = y0c - self.top
        self.canvas.create_rectangle(x0, y0, x1, y1, outline=T["accent"],
                                     fill=T["line2"], stipple='gray25')

    # ─── mouse ───────────────────────────────────────────────

    def _on_wheel(self, event) -> str:
        up = getattr(event, 'num', 0) == 4 or getattr(event, 'delta', 0) > 0
        step = self.row_h * 3 if self.mode == 'list' else self.tile()[1] // 2
        self.top += -step if up else step
        self._clamp()
        self.redraw(now=True)
        return 'break'

    def _on_zoom(self, event) -> str:
        up = getattr(event, 'num', 0) == 4 or getattr(event, 'delta', 0) > 0
        self.app.zoom(1 if up else -1)
        return 'break'

    def _scrollbar(self, *args) -> None:
        total = self.content_height()
        h = self.canvas.winfo_height()
        if args[0] == 'moveto':
            self.top = int(float(args[1]) * total)
        elif args[0] == 'scroll':
            n = int(args[1])
            unit = self.row_h if self.mode == 'list' else self.tile()[1]
            self.top += n * (h - unit if args[2] == 'pages' else unit)
        self._clamp()
        self.redraw(now=True)

    def _on_hover(self, event) -> None:
        if self._press is not None:
            return
        i = self.index_at(event.x, event.y)
        if i != self.hover:
            self.hover = i
            self.redraw()
            if i >= 0:
                self.pane.hovered(self.entries[i])
            else:
                self.pane.hovered(None)

    def _on_leave(self, _event) -> None:
        if self.hover != -1:
            self.hover = -1
            self.redraw()
            self.pane.hovered(None)

    def _on_press(self, event) -> None:
        self.canvas.focus_set()
        self.app.dnd.cancel()
        if self._rename_entry is not None:
            self.commit_rename()
        i = self.index_at(event.x, event.y)
        ctrl = bool(event.state & 0x4)
        shift = bool(event.state & 0x1)
        self._press = (event.x, event.y, i, event.state)
        if i < 0:
            base = set(self.selected) if (ctrl or shift) else set()
            if not (ctrl or shift):
                self.selected = set()
                self.pane.selection_changed()
            self._band = (event.x, event.y + self.top, base)
            self._band_pos = (event.x, event.y)
            self.redraw()
            return
        path = self.entries[i].path
        if shift and self.anchor >= 0:
            lo, hi = sorted((self.anchor, i))
            rng = {self.entries[k].path for k in range(lo, hi + 1)}
            self.selected = (self.selected | rng) if ctrl else rng
        elif ctrl:
            self.selected ^= {path}
            self.anchor = i
        elif path not in self.selected:
            self.selected = {path}
            self.anchor = i
        self.cursor = i
        self.redraw()
        self.pane.selection_changed()

    def _on_motion(self, event) -> None:
        if self._press is None:
            return
        x, y, i, state = self._press
        if self._band is not None:
            self._band_pos = (event.x, event.y)
            self._update_band()
            self._auto_scroll(event.y)
            return
        if i >= 0 and not self.app.dnd.active and \
                (abs(event.x - x) > DRAG_START or abs(event.y - y) > DRAG_START):
            path = self.entries[i].path
            if path not in self.selected:
                self.selected = {path}
            paths = [e.path for e in self.entries if e.path in self.selected]
            self.app.dnd.start(self, paths, event)
        if self.app.dnd.active:
            self.app.dnd.motion(event)

    def _on_release(self, event) -> None:
        press = self._press
        self._press = None
        self._stop_auto_scroll()
        if self._band is not None:
            self._band = None
            self._band_pos = None
            self.redraw()
            return
        if self.app.dnd.active:
            self.app.dnd.drop(event)
            return
        if press is None:
            return
        _x, _y, i, state = press
        if i >= 0 and not (state & 0x5):
            path = self.entries[i].path
            if self.selected != {path}:
                self.selected = {path}           # a click on one of several selected
                self.anchor = i
                self.redraw()
                self.pane.selection_changed()
            elif self.app.settings.get('single_click') and i == self.index_at(event.x, event.y):
                self.pane.open_entries([self.entries[i]])

    def _update_band(self) -> None:
        x0, y0c, base = self._band
        x1, y1 = self._band_pos
        ya, yb = sorted((y0c, y1 + self.top))
        xa, xb = sorted((x0, x1))
        hits = set()
        if self.mode == 'list':
            first = max(0, ya // self.row_h)
            last = min(len(self.entries) - 1, yb // self.row_h)
            if xa < self._name_width():
                hits = {self.entries[k].path for k in range(first, last + 1)}
        else:
            w, h, _b = self.tile()
            cols = self.columns()
            pad = self.app.px(8)
            first_row = max(0, (ya - pad) // h)
            last_row = (yb - pad) // h
            for row in range(first_row, last_row + 1):
                for col in range(cols):
                    k = row * cols + col
                    if k >= len(self.entries):
                        break
                    bx0, by0, bx1, by1 = self.item_box(k)
                    by0 += self.top
                    by1 += self.top
                    if bx0 < xb and bx1 > xa and by0 < yb and by1 > ya:
                        hits.add(self.entries[k].path)
        new = base | hits
        if new != self.selected:
            self.selected = new
            self.pane.selection_changed()
        self.redraw()

    def _auto_scroll(self, y: int) -> None:
        h = self.canvas.winfo_height()
        edge = self.app.px(24)
        speed = 0
        if y < edge:
            speed = -max(4, (edge - y))
        elif y > h - edge:
            speed = max(4, y - (h - edge))
        if speed and self._autoscroll is None:
            def tick():
                self._autoscroll = None
                if self._band is None and not self.app.dnd.active:
                    return
                self.top += speed
                self._clamp()
                if self._band is not None:
                    self._update_band()
                self.redraw(now=True)
                ptr_y = self.canvas.winfo_pointery() - self.canvas.winfo_rooty()
                self._auto_scroll(ptr_y)
            self._autoscroll = self.after(40, tick)
        elif not speed:
            self._stop_auto_scroll()

    def _stop_auto_scroll(self) -> None:
        if self._autoscroll:
            self.after_cancel(self._autoscroll)
            self._autoscroll = None

    def _on_double(self, event) -> None:
        i = self.index_at(event.x, event.y)
        if i >= 0:
            self._press = None
            self.pane.open_entries([self.entries[i]])

    def _on_middle(self, event) -> None:
        i = self.index_at(event.x, event.y)
        if i >= 0 and self.entries[i].is_dir:
            self.pane.window.new_tab(self.entries[i].path, select=False)

    def _on_right(self, event) -> None:
        self.canvas.focus_set()
        i = self.index_at(event.x, event.y)
        if i >= 0:
            path = self.entries[i].path
            if path not in self.selected:
                self.selected = {path}
                self.anchor = i
            self.cursor = i
        else:
            self.selected = set()
        self.redraw(now=True)
        self.pane.selection_changed()
        self.pane.context_menu(event, self.selected_entries())

    # ─── keyboard ────────────────────────────────────────────

    def _on_key(self, event) -> Optional[str]:
        key = event.keysym
        shift = bool(event.state & 0x1)
        ctrl = bool(event.state & 0x4)
        n = len(self.entries)
        if key in ('Up', 'Down', 'Left', 'Right', 'Home', 'End', 'Prior', 'Next') and n:
            if event.state & 0x8 or event.state & 0x80:      # Alt+arrows: the window's
                return None
            cols = self.columns()
            per_page = max(1, self.canvas.winfo_height() // (self.row_h if self.mode == 'list'
                                                              else self.tile()[1]))
            cur = self.cursor if self.cursor >= 0 else -1
            if key == 'Up':
                new = cur - cols if cur >= 0 else n - 1
            elif key == 'Down':
                new = cur + cols if cur >= 0 else 0
            elif key == 'Left':
                if self.mode != 'grid':
                    return None
                new = cur - 1
            elif key == 'Right':
                if self.mode != 'grid':
                    return None
                new = cur + 1
            elif key == 'Home':
                new = 0
            elif key == 'End':
                new = n - 1
            elif key == 'Prior':
                new = cur - per_page * cols
            else:
                new = cur + per_page * cols
            new = max(0, min(n - 1, new))
            self.move_cursor(new, shift, ctrl)
            return 'break'
        if key == 'space' and ctrl and 0 <= self.cursor < n:
            self.selected ^= {self.entries[self.cursor].path}
            self.redraw()
            self.pane.selection_changed()
            return 'break'
        if key in ('Return', 'KP_Enter'):
            chosen = self.selected_entries()
            if chosen:
                self.pane.open_entries(chosen)
            return 'break'
        if key == 'Escape':
            self.pane.escape()
            return 'break'
        if key == 'BackSpace':
            self.pane.go_up()
            return 'break'
        if key == 'Menu' or (key == 'F10' and shift):
            box = self.item_box(self.cursor) if self.cursor >= 0 else (0, 0, 20, 20)
            ev = type('E', (), {'x_root': self.canvas.winfo_rootx() + box[0] + 20,
                                'y_root': self.canvas.winfo_rooty() + box[1] + 10})()
            self.pane.context_menu(ev, self.selected_entries())
            return 'break'
        if event.char and event.char.isprintable() and not ctrl and not (event.state & 0x8):
            self.pane.type_to_filter(event.char)
            return 'break'
        return None

    def move_cursor(self, new: int, shift: bool = False, ctrl: bool = False) -> None:
        if not (0 <= new < len(self.entries)):
            return
        if shift:
            if self.anchor < 0:
                self.anchor = max(0, self.cursor)
            lo, hi = sorted((self.anchor, new))
            self.selected = {self.entries[k].path for k in range(lo, hi + 1)}
        elif not ctrl:
            self.selected = {self.entries[new].path}
            self.anchor = new
        self.cursor = new
        self.see(new)
        self.redraw()
        self.pane.selection_changed()

    # ─── rename in place ─────────────────────────────────────

    def start_rename(self, path: str) -> bool:
        i = self.index.get(path)
        if i is None:
            return False
        self.cancel_rename()
        self.see(i)
        self._rename_path = path
        e = tk.Entry(self.canvas, font=self.font, bg=T["out_bg"], fg=T["text"],
                     insertbackground=T["accent"], selectbackground=T["line2"],
                     selectforeground=T["text"], relief='flat', bd=0, highlightthickness=1,
                     highlightbackground=T["accent"], highlightcolor=T["accent"])
        name = self.entries[i].name
        e.insert(0, name)
        from .ops import split_ext
        stem = name if self.entries[i].is_dir else split_ext(name)[0]
        e.selection_range(0, len(stem))
        e.icursor(len(stem))
        e.bind('<Return>', lambda _e: (self.commit_rename(), 'break')[1])
        e.bind('<KP_Enter>', lambda _e: (self.commit_rename(), 'break')[1])
        e.bind('<Escape>', lambda _e: (self.cancel_rename(), 'break')[1])
        e.bind('<FocusOut>', lambda _e: self.after_idle(self.commit_rename))
        e.bind('<Tab>', lambda _e: (self.commit_rename(next_item=True), 'break')[1])
        self._rename_entry = e
        self._place_rename()
        e.focus_set()
        return True

    def _place_rename(self) -> None:
        i = self.index.get(self._rename_path)
        e = self._rename_entry
        if i is None or e is None:
            return
        px = self.app.px
        x0, y0, x1, y1 = self.item_box(i)
        if self.mode == 'list':
            tx = px(10) + px(16) + px(6)
            self.canvas.create_window(tx, (y0 + y1) // 2, window=e, anchor='w',
                                      width=max(px(120), self._name_width() - tx - px(8)),
                                      height=self.row_h - px(4))
        else:
            _w, _h, box = self.tile()
            self.canvas.create_window((x0 + x1) // 2, y0 + px(7) + box, window=e, anchor='n',
                                      width=max(px(140), x1 - x0 + px(30)),
                                      height=self.font.metrics('linespace') + px(6))

    def commit_rename(self, next_item: bool = False) -> None:
        e = self._rename_entry
        if e is None:
            return
        path, new = self._rename_path, e.get()
        self.cancel_rename(refocus=False)
        old = os.path.basename(path)
        if new and new != old:
            self.pane.rename_one(path, new)
        self.canvas.focus_set()
        if next_item:
            i = self.index.get(path, -1)
            if 0 <= i + 1 < len(self.entries):
                self.move_cursor(i + 1)
                self.start_rename(self.entries[i + 1].path)

    def cancel_rename(self, refocus: bool = True) -> None:
        e = self._rename_entry
        self._rename_entry = None
        self._rename_path = ''
        if e is not None:
            try:
                e.destroy()
            except tk.TclError:
                pass
            self.redraw()
            if refocus:
                self.canvas.focus_set()

    @property
    def renaming(self) -> bool:
        return self._rename_entry is not None

    # ─── drag and drop target ────────────────────────────────

    def drop_target_at(self, x_root: int, y_root: int, dragged: List[str]) -> Optional[str]:
        """The folder a drop at this point goes into: a folder under the pointer (not one
        being dragged), else the folder this view shows."""
        x = x_root - self.canvas.winfo_rootx()
        y = y_root - self.canvas.winfo_rooty()
        i = self.index_at(x, y)
        target_index = -1
        if i >= 0:
            e = self.entries[i]
            if e.is_dir and e.path not in dragged:
                target_index = i
        changed = target_index != self.drop_index or self.drop_all != (target_index < 0)
        self.drop_index = target_index
        self.drop_all = target_index < 0
        if changed:
            self.redraw()
        if target_index >= 0:
            return self.entries[target_index].path
        return self.pane.drop_folder()

    def clear_drop(self) -> None:
        if self.drop_index != -1 or self.drop_all:
            self.drop_index = -1
            self.drop_all = False
            self.redraw()
