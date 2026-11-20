"""The screens: the library (covers or a list), a game's page, adding a game, and settings."""

import os
import queue
import threading
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import messagebox

from PIL import Image, ImageTk

from . import SOURCES, anticheat, covers, launch, owngames
from .core import (Game, cache_dir, config_dir, data_dir, flatpak_installed, home, is_windows_program,
                   matches, open_uri, pick_program, sort_recent, sort_title, which)
from .strings import last_played, playtime, tr
from .widgets import (T, GlitchPanel, GlitchText, IconButton, ScrollBar, Segmented, Toggle,
                      WolkButton)

MAX_PHOTOS = 600               # covers kept as Tk images; the rest are dropped, oldest first
BOTTLES_PAGE = 'https://flathub.org/apps/com.usebottles.bottles'


def source_word(game: Game) -> str:
    return tr(f'src_{game.source}')


def launcher_line(game: Game) -> str:
    name = tr(f'launcher_{game.launcher}')
    if game.launcher == 'heroic':
        name = f"{name} ({tr(f'store_{game.source}')})"
    return f"{name}, {tr('flatpak')}" if game.flatpak else name


def entry(parent: tk.Misc, app, width: int = 28) -> Tuple[tk.Frame, tk.Entry, tk.StringVar]:
    """A flat text box with a 1px line around it."""
    var = tk.StringVar()
    box = tk.Frame(parent, bg=T["line2"], padx=1, pady=1)
    field = tk.Entry(box, textvariable=var, bg=T["panel"], fg=T["text"], relief="flat",
                     insertbackground=T["accent"], selectbackground=T["line2"],
                     selectforeground=T["text"], font=app.font(9, False), width=width,
                     highlightthickness=0, bd=app.px(5))
    field.pack(fill="both", expand=True)
    return box, field, var


def section(parent: tk.Misc, app, text: str) -> tk.Label:
    label = tk.Label(parent, text=text, bg=parent.cget("bg"), fg=T["muted"], font=app.font(7),
                     anchor="w")
    label.pack(fill="x", pady=(app.px(14), app.px(4)))
    return label


# ─── The library ──────────────────────────────────────────────

class LibraryView(tk.Frame):
    """Every game, as covers or as a list. Only the rows on screen are drawn, so 500 games
    scroll as fast as 5; covers are cut to size in a worker thread and cached on disk."""

    def __init__(self, app):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        px, font = app.px, app.font
        self.mode = app.settings.get('view') if app.settings.get('view') in ('grid', 'list') \
            else 'grid'
        self.sort = app.settings.get('sort') if app.settings.get('sort') in ('recent', 'title') \
            else 'recent'
        self.source = 'all'
        self.games: List[Game] = []
        self.shown: List[Game] = []
        self.selected = 0
        self.hover: Optional[int] = None
        self.scanning = True
        self.photos: "OrderedDict[Tuple[str, str], ImageTk.PhotoImage]" = OrderedDict()
        self.requested: set = set()
        self.jobs: "queue.Queue[Tuple[str, str, str, int, int]]" = queue.Queue()
        self.results: "queue.Queue[Tuple[str, str, Optional[Image.Image]]]" = queue.Queue()
        self.pending = 0
        self._poll_id: Optional[str] = None
        self._render_id: Optional[str] = None
        self._titles: Dict[Tuple[str, int], str] = {}
        threading.Thread(target=self._worker, daemon=True).start()

        bar = tk.Frame(self, bg=T["bg"])
        bar.pack(fill="x", padx=px(16), pady=(px(12), px(8)))
        box, self.search, self.query = entry(bar, app, width=26)
        box.pack(side="left")
        self.hint = tk.Label(self.search, text=tr('search_hint'), bg=T["panel"], fg=T["dim"],
                             font=font(9, False), cursor="xterm")
        self.hint.place(x=px(5), rely=0.5, anchor="w")
        self.hint.bind("<Button-1>", lambda _e: self.search.focus_set())
        self.query.trace_add("write", lambda *_a: self._query_changed())
        self.filters = tk.Frame(bar, bg=T["bg"])
        self.filters.pack(side="left", padx=(px(12), 0))
        self._filter_sources: Tuple[str, ...] = ()

        WolkButton(bar, tr('add_game'), app.show_add, font(8), padx=px(10),
                   pady=px(3)).pack(side="right")
        self.list_btn = IconButton(bar, "list", lambda: self.set_mode('list'), px(26),
                                   tip=tr('tip_list'))
        self.list_btn.pack(side="right", padx=(0, px(10)))
        self.grid_btn = IconButton(bar, "grid", lambda: self.set_mode('grid'), px(26),
                                   tip=tr('tip_grid'))
        self.grid_btn.pack(side="right", padx=(0, px(2)))
        self.sorter = Segmented(bar, [(tr('sort_recent'), 'recent'), (tr('sort_title'), 'title')],
                                self.sort, self.set_sort, font(8))
        self.sorter.pack(side="right", padx=(0, px(10)))
        self._paint_mode_buttons()

        tk.Frame(self, bg=T["line"], height=1).pack(fill="x", padx=px(16))
        self.holder = tk.Frame(self, bg=T["bg"])
        self.holder.pack(fill="both", expand=True, padx=(px(16), px(4)), pady=(px(10), px(8)))
        self.canvas = tk.Canvas(self.holder, bg=T["bg"], highlightthickness=0, bd=0, takefocus=1)
        self.scroll = ScrollBar(self.holder, self.canvas, px(6))
        self.scroll.pack(side="right", fill="y", padx=(px(6), 0))
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.configure(yscrollcommand=self._yscroll)
        self.canvas.bind("<Configure>", lambda _e: self.layout())
        self.canvas.bind("<Motion>", self._motion)
        self.canvas.bind("<Leave>", lambda _e: self._set_hover(None))
        self.canvas.bind("<ButtonRelease-1>", self._click)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.bind(seq, self._wheel)
        self.empty: Optional[tk.Frame] = None

    def destroy(self):
        for after_id in (self._render_id, self._poll_id):
            if after_id:
                try:
                    self.after_cancel(after_id)
                except tk.TclError:
                    pass
        self._render_id = self._poll_id = None
        super().destroy()

    # ── data ──
    def set_games(self, games: List[Game], scanning: bool):
        keep = self.shown[self.selected].key if self.shown and self.selected < len(self.shown) \
            else None
        self.games = games
        self.scanning = scanning
        self._titles.clear()
        # covers may have changed (a new download): forget images whose source changed
        self._rebuild_filters()
        self.refilter(keep)

    def refilter(self, keep: Optional[str] = None):
        query = self.query.get().strip()
        games = [g for g in self.games if (self.source == 'all' or g.source == self.source)
                 and matches(g, query)]
        self.shown = sort_recent(games) if self.sort == 'recent' else sort_title(games)
        self.selected = 0
        if keep:
            for i, g in enumerate(self.shown):
                if g.key == keep:
                    self.selected = i
                    break
        self.hover = None
        self._show_empty(not self.games and not self.scanning)
        self.layout()
        if keep is None:
            self.canvas.yview_moveto(0)

    def _rebuild_filters(self):
        present = tuple(s for s in SOURCES if any(g.source == s for g in self.games))
        if present == self._filter_sources:
            return
        self._filter_sources = present
        for child in self.filters.winfo_children():
            child.destroy()
        if self.source not in present:
            self.source = 'all'
        if len(present) > 1:
            Segmented(self.filters, [(tr('src_all'), 'all')] + [(tr(f'src_{s}'), s)
                                                                for s in present],
                      self.source, self.set_source, self.app.font(8)).pack(side="left")

    def set_source(self, source: str):
        self.source = source
        self.refilter()
        self.app.glitch.now(self.app.title)

    def set_sort(self, sort: str):
        self.sort = sort
        self.app.settings['sort'] = sort
        self.refilter(self.current().key if self.current() else None)

    def set_mode(self, mode: str):
        if mode == self.mode:
            return
        self.mode = mode
        self.app.settings['view'] = mode
        self._paint_mode_buttons()
        self.layout()
        self.ensure_visible(self.selected)

    def _paint_mode_buttons(self):
        self.grid_btn.accent = self.mode == 'grid'
        self.list_btn.accent = self.mode == 'list'
        self.grid_btn.draw()
        self.list_btn.draw()

    def _query_changed(self):
        if self.query.get():
            self.hint.place_forget()
        else:
            self.hint.place(x=self.app.px(5), rely=0.5, anchor="w")
        self.refilter()

    def current(self) -> Optional[Game]:
        return self.shown[self.selected] if 0 <= self.selected < len(self.shown) else None

    # ── empty state ──
    def _show_empty(self, empty: bool):
        if empty and self.empty is None:
            self.holder.pack_forget()
            self.empty = EmptyState(self, self.app)
            self.empty.pack(fill="both", expand=True, padx=self.app.px(16), pady=self.app.px(16))
        elif not empty and self.empty is not None:
            self.empty.destroy()
            self.empty = None
            self.holder.pack(fill="both", expand=True, padx=(self.app.px(16), self.app.px(4)),
                             pady=(self.app.px(10), self.app.px(8)))

    # ── geometry ──
    def metrics(self) -> Dict[str, int]:
        px = self.app.px
        width = max(1, self.canvas.winfo_width())
        if self.mode == 'grid':
            tile_w = px(148)
            cover_h = tile_w * 3 // 2
            gap = px(16)
            cols = max(1, (width - px(16) + gap) // (tile_w + gap))
            row_h = cover_h + px(46) + gap
            if cols > 1:     # spread the spare width over the gaps, so the grid fills the row
                gap = min(gap * 2, (width - px(16) - cols * tile_w) // (cols - 1))
            return {'cols': cols, 'row_h': row_h, 'tile_w': tile_w, 'cover_h': cover_h,
                    'gap': gap, 'width': width}
        return {'cols': 1, 'row_h': px(60), 'tile_w': px(34), 'cover_h': px(51), 'gap': 0,
                'width': width}

    def layout(self):
        m = self.metrics()
        rows = (len(self.shown) + m['cols'] - 1) // m['cols']
        height = max(rows * m['row_h'] + self.app.px(16), 1)
        self.canvas.configure(scrollregion=(0, 0, m['width'], height))
        self.render()

    def box(self, i: int, m: Optional[Dict[str, int]] = None) -> Tuple[int, int, int, int]:
        m = m or self.metrics()
        row, col = divmod(i, m['cols'])
        if self.mode == 'grid':
            x = self.app.px(8) + col * (m['tile_w'] + m['gap'])
            y = self.app.px(8) + row * m['row_h']
            return x, y, x + m['tile_w'], y + m['row_h'] - self.app.px(16)
        y = row * m['row_h']
        return 0, y, m['width'] - self.app.px(2), y + m['row_h'] - self.app.px(4)

    def hit(self, x: float, y: float) -> Optional[int]:
        m = self.metrics()
        if self.mode == 'grid':
            x, y = x - self.app.px(8), y - self.app.px(8)
            row = int(y // m['row_h'])
            col = int(x // (m['tile_w'] + m['gap']))
            if x < 0 or col >= m['cols']:
                return None
            i = row * m['cols'] + col
            x, y = x + self.app.px(8), y + self.app.px(8)
        else:
            i = int(y // m['row_h'])
        if 0 <= i < len(self.shown):
            x0, y0, x1, y1 = self.box(i, m)
            if x0 <= x <= x1 and y0 <= y <= y1:
                return i
        return None

    # ── drawing ──
    def _yscroll(self, first, last):
        self.scroll.set(first, last)
        self.render()

    def render(self):
        """Coalesce redraws: many scroll events in a row draw once."""
        if self._render_id is None:
            self._render_id = self.after_idle(self._render)

    def _render(self):
        self._render_id = None
        if not self.winfo_exists():
            return
        c = self.canvas
        c.delete("all")
        if not self.shown:
            if self.games or self.scanning:
                text = tr('scanning_first') if not self.games else (
                    tr('no_match', query=self.query.get().strip()) if self.query.get().strip()
                    else tr('none_in_filter'))
                c.create_text(self.app.px(4), self.app.px(10), text=text, anchor="nw",
                              fill=T["muted"], font=self.app.font(9, False))
            return
        m = self.metrics()
        top = c.canvasy(0)
        bottom = top + c.winfo_height()
        first = max(0, int(top // m['row_h']) - 1) * m['cols']
        last = min(len(self.shown), (int(bottom // m['row_h']) + 2) * m['cols'])
        for i in range(first, last):
            if self.mode == 'grid':
                self._tile(i, self.shown[i], m)
            else:
                self._row(i, self.shown[i], m)

    def _photo(self, game: Game, w: int, h: int) -> Optional[ImageTk.PhotoImage]:
        key = (game.key, f'{w}x{h}')
        photo = self.photos.get(key)
        if photo is not None:
            self.photos.move_to_end(key)
            return photo
        if game.cover and key not in self.requested:
            self.requested.add(key)
            self.jobs.put((game.key, key[1], game.cover, w, h))
            self.pending += 1
            if self._poll_id is None:
                self._poll_id = self.after(40, self._poll)
        return None

    def _split_frame(self, x0, y0, x1, y1, strong: bool):
        """A frame just outside the cover, its magenta and cyan copies slipping sideways."""
        c, px = self.canvas, self.app.px
        o, d, w = px(3), px(2) if strong else px(1), px(2)
        x0, y0, x1, y1 = x0 - o, y0 - o, x1 + o, y1 + o
        c.create_rectangle(x0 - d, y0, x1 - d, y1, outline=T["ch_a"], width=w)
        c.create_rectangle(x0 + d, y0, x1 + d, y1, outline=T["ch_b"], width=w)
        c.create_rectangle(x0, y0, x1, y1, outline=T["accent"] if strong else T["line2"], width=w)

    def _fit(self, text: str, width: int, size: int = 9, bold: bool = True) -> str:
        key = (text, width * 100 + size * 2 + bold)
        if key in self._titles:
            return self._titles[key]
        f = self.app.tkfont(size, bold)
        out = text
        if f.measure(text) > width:
            lo, hi = 0, len(text)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if f.measure(text[:mid].rstrip() + '…') <= width:
                    lo = mid
                else:
                    hi = mid - 1
            out = text[:lo].rstrip() + '…'
        self._titles[key] = out
        return out

    def _placeholder(self, game: Game, x0, y0, x1, y1):
        c, px = self.canvas, self.app.px
        c.create_rectangle(x0, y0, x1, y1, fill=T["tile"], outline=T["line"])
        if y1 - y0 > px(80):
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=game.title, width=x1 - x0 - px(18),
                          justify="center", fill=T["muted"], font=self.app.font(10))
            c.create_text((x0 + x1) / 2, y1 - px(12), text=source_word(game), fill=T["dim"],
                          font=self.app.font(7))
        else:
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=game.title[:1].upper(),
                          fill=T["muted"], font=self.app.font(11))

    def _tile(self, i: int, game: Game, m: Dict[str, int]):
        c, px = self.canvas, self.app.px
        x0, y0, x1, _y1 = self.box(i, m)
        cy1 = y0 + m['cover_h']
        photo = self._photo(game, m['tile_w'], m['cover_h'])
        if photo is not None:
            c.create_image(x0, y0, image=photo, anchor="nw")
        else:
            self._placeholder(game, x0, y0, x1, cy1)
        if game.anticheat:
            c.create_rectangle(x0, y0, x0 + px(84), y0 + px(16), fill=T["pink"], outline="")
            c.create_text(x0 + px(5), y0 + px(8), text="ANTI-CHEAT", anchor="w",
                          fill=T["on_accent"], font=self.app.font(7))
        sel, hov = i == self.selected, i == self.hover
        if sel or hov:
            self._split_frame(x0, y0, x1, cy1, strong=sel)
        c.create_text(x0, cy1 + px(7), text=self._fit(game.title, m['tile_w']), anchor="nw",
                      fill=T["text"] if sel or hov else T["muted"],
                      font=self.app.font(9))
        c.create_text(x0, cy1 + px(26), text=source_word(game), anchor="nw", fill=T["dim"],
                      font=self.app.font(7))
        c.create_text(x1, cy1 + px(26), text=playtime(game.playtime), anchor="ne",
                      fill=T["dim"], font=self.app.font(7, False))

    def _row(self, i: int, game: Game, m: Dict[str, int]):
        c, px = self.canvas, self.app.px
        x0, y0, x1, y1 = self.box(i, m)
        sel, hov = i == self.selected, i == self.hover
        c.create_rectangle(x0, y0, x1, y1, fill=T["panel2"] if sel else T["hover"] if hov
                           else T["panel"], outline=T["line"])
        if sel:
            c.create_rectangle(x0, y0, x0 + px(2), y1, fill=T["ch_a"], outline="")
            c.create_rectangle(x0 + px(2), y0, x0 + px(4), y1, fill=T["ch_b"], outline="")
        tx, ty = x0 + px(10), y0 + (y1 - y0 - m['cover_h']) // 2
        photo = self._photo(game, m['tile_w'], m['cover_h'])
        if photo is not None:
            c.create_image(tx, ty, image=photo, anchor="nw")
        else:
            self._placeholder(game, tx, ty, tx + m['tile_w'], ty + m['cover_h'])
        left = tx + m['tile_w'] + px(14)
        col_play, col_last = x1 - px(260), x1 - px(130)
        title_w = max(px(60), col_play - left - px(16))
        mid = (y0 + y1) / 2
        c.create_text(left, mid - px(8), text=self._fit(game.title, title_w, 10), anchor="w",
                      fill=T["text"], font=self.app.font(10))
        sub = source_word(game) + ("   ANTI-CHEAT" if game.anticheat else "")
        c.create_text(left, mid + px(10), text=sub, anchor="w",
                      fill=T["pink"] if game.anticheat else T["dim"], font=self.app.font(7))
        c.create_text(col_play, mid, text=playtime(game.playtime), anchor="w", fill=T["muted"],
                      font=self.app.font(8, False))
        c.create_text(col_last, mid, text=last_played(game.last_played), anchor="w",
                      fill=T["muted"], font=self.app.font(8, False))

    # ── covers, cut in a worker thread ──
    def _worker(self):
        while True:
            game_key, size, src, w, h = self.jobs.get()
            try:
                image = covers.thumbnail(src, w, h)
            except Exception:              # noqa: BLE001 - a bad image must not kill the worker
                image = None
            self.results.put((game_key, size, image))

    def _poll(self):
        self._poll_id = None
        if not self.winfo_exists():
            return
        changed = False
        while True:
            try:
                game_key, size, image = self.results.get_nowait()
            except queue.Empty:
                break
            self.pending -= 1
            if image is not None:
                self.photos[(game_key, size)] = ImageTk.PhotoImage(image, master=self)
                changed = True
                while len(self.photos) > MAX_PHOTOS:
                    old, _photo = self.photos.popitem(last=False)
                    self.requested.discard(old)
        if changed:
            self.render()
        if self.pending > 0:                # nothing scheduled when idle: zero CPU
            self._poll_id = self.after(40, self._poll)

    # ── mouse and keys ──
    def _set_hover(self, i: Optional[int]):
        if i != self.hover:
            self.hover = i
            self.render()

    def _motion(self, event):
        self._set_hover(self.hit(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)))

    def _click(self, event):
        self.canvas.focus_set()
        i = self.hit(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        if i is not None:
            self.selected = i
            self.render()
            self.app.show_game(self.shown[i])

    def _wheel(self, event):
        if getattr(event, 'num', 0) == 4 or getattr(event, 'delta', 0) > 0:
            self.canvas.yview_scroll(-1, "units")
        else:
            self.canvas.yview_scroll(1, "units")
        return "break"

    def ensure_visible(self, i: int):
        if not self.shown:
            return
        m = self.metrics()
        _x0, y0, _x1, y1 = self.box(i, m)
        total = max(1, ((len(self.shown) + m['cols'] - 1) // m['cols']) * m['row_h'])
        top = self.canvas.canvasy(0)
        height = self.canvas.winfo_height()
        if y0 < top:
            self.canvas.yview_moveto(max(0, y0 - self.app.px(8)) / total)
        elif y1 > top + height:
            self.canvas.yview_moveto(max(0, y1 + self.app.px(8) - height) / total)

    def move(self, delta: int):
        if not self.shown:
            return
        self.selected = max(0, min(len(self.shown) - 1, self.selected + delta))
        self.ensure_visible(self.selected)
        self.render()

    def key(self, event) -> bool:
        k = event.keysym
        in_search = self.focus_get() is self.search
        cols = self.metrics()['cols']
        if in_search:
            if k == 'Escape':
                if self.query.get():
                    self.query.set('')
                else:
                    self.canvas.focus_set()
                return True
            if k in ('Down', 'Tab'):
                self.canvas.focus_set()
                return True
            if k in ('Return', 'KP_Enter'):
                self.play_selected()
                return True
            return False
        if k == 'slash':
            self.search.focus_set()
            return True
        if k == 'Escape' and self.query.get():
            self.query.set('')
            return True
        moves = {'Left': -1, 'Right': 1, 'Up': -cols, 'Down': cols}
        if self.mode == 'list':
            moves = {'Up': -1, 'Down': 1}
        if k in moves:
            self.move(moves[k])
            return True
        rows = max(1, self.canvas.winfo_height() // self.metrics()['row_h'])
        if k in ('Prior', 'Next'):
            self.move((-1 if k == 'Prior' else 1) * rows * cols)
            return True
        if k in ('Home', 'End'):
            self.move(-len(self.shown) if k == 'Home' else len(self.shown))
            return True
        if k in ('Return', 'KP_Enter'):
            self.play_selected()
            return True
        if k in ('space', 'i') and self.current():
            self.app.show_game(self.current())
            return True
        char = event.char
        if char and len(char) == 1 and char.isprintable() and not char.isspace() \
                and not event.state & 0x4:
            self.search.focus_set()
            self.search.insert("end", char)
            return True
        return False

    def play_selected(self):
        game = self.current()
        if game:
            self.app.play(game)

    def focus_default(self):
        self.canvas.focus_set()


class EmptyState(GlitchPanel):
    """No launcher, or no installed games: say so, and where to get one."""

    def __init__(self, parent: tk.Misc, app):
        super().__init__(parent, bg=T["panel"])
        px, font = app.px, app.font
        inner = tk.Frame(self.inner, bg=T["panel"])
        inner.pack(fill="both", expand=True, padx=px(28), pady=px(28))
        self.heading = GlitchText(inner, tr('empty_title'), app.tkfont(16), T["panel"])
        self.heading.pack(anchor="w")
        for key in ('empty_body', 'empty_store'):
            tk.Label(inner, text=tr(key), bg=T["panel"], fg=T["muted"], font=font(9, False),
                     justify="left", anchor="w", wraplength=px(620)).pack(anchor="w",
                                                                          pady=(px(10), 0))
        row = tk.Frame(inner, bg=T["panel"])
        row.pack(anchor="w", pady=(px(18), 0))
        if which('spark-welcome'):
            WolkButton(row, tr('open_welcome'), app.open_welcome, font(8), variant="primary",
                       padx=px(10), pady=px(4)).pack(side="left", padx=(0, px(8)))
        WolkButton(row, tr('open_store'), app.open_store, font(8),
                   variant="ghost" if which('spark-welcome') else "primary",
                   padx=px(10), pady=px(4)).pack(side="left", padx=(0, px(8)))
        WolkButton(row, tr('add_game'), app.show_add, font(8), padx=px(10),
                   pady=px(4)).pack(side="left")
        app.glitch.now(self.heading, self, strong=True)


# ─── A game's page ────────────────────────────────────────────

class GamePage(tk.Frame):
    def __init__(self, app, game: Game):
        super().__init__(app.body, bg=T["bg"])
        self.app, self.game = app, game
        px, font = app.px, app.font
        options = app.game_options(game.key)

        wrap = tk.Frame(self, bg=T["bg"])
        wrap.pack(fill="both", expand=True, padx=px(24), pady=px(20))
        cw, ch = px(240), px(360)
        cover = tk.Canvas(wrap, width=cw, height=ch, bg=T["bg"], highlightthickness=0, bd=0)
        cover.pack(side="left", anchor="n")
        image = covers.thumbnail(game.cover, cw, ch) if game.cover else None
        if image is not None:
            self._photo = ImageTk.PhotoImage(image, master=self)
            cover.create_image(0, 0, image=self._photo, anchor="nw")
            cover.create_rectangle(0, 0, cw - 1, ch - 1, outline=T["line2"])
        else:
            cover.create_rectangle(0, 0, cw - 1, ch - 1, fill=T["tile"], outline=T["line2"])
            cover.create_text(cw / 2, ch / 2, text=game.title, width=cw - px(30), justify="center",
                              fill=T["muted"], font=font(12))

        col = tk.Frame(wrap, bg=T["bg"])
        col.pack(side="left", fill="both", expand=True, padx=(px(24), 0))
        size = 18
        while size > 11 and app.tkfont(size).measure(game.title) > px(560):
            size -= 2
        title = game.title if app.tkfont(size).measure(game.title) <= px(620) else \
            game.title[:48].rstrip() + '…'
        self.heading = GlitchText(col, title, app.tkfont(size), T["bg"])
        self.heading.pack(anchor="w")
        tk.Label(col, text=launcher_line(game).upper(), bg=T["bg"], fg=T["accent"],
                 font=font(8)).pack(anchor="w", padx=(px(6), 0))

        actions = tk.Frame(col, bg=T["bg"])
        actions.pack(anchor="w", pady=(px(16), px(4)))
        self.play_btn = WolkButton(actions, tr('play'), lambda: app.play(game), font(11),
                                   variant="primary", padx=px(26), pady=px(8))
        self.play_btn.pack(side="left")
        if game.install_dir and os.path.isdir(game.install_dir):
            WolkButton(actions, tr('open_folder'), lambda: open_uri(game.install_dir), font(8),
                       padx=px(10), pady=px(4)).pack(side="left", padx=(px(10), 0))

        if game.anticheat:
            panel = GlitchPanel(col, bg="#1a0a12")
            panel.pack(fill="x", pady=(px(12), 0))
            tk.Label(panel.inner, text=tr(f'ac_{game.anticheat}'), bg="#1a0a12", fg=T["pink"],
                     font=font(9, False), justify="left", anchor="w",
                     wraplength=px(560)).pack(anchor="w", padx=px(12), pady=(px(10), px(2)))
            tk.Label(panel.inner, text=tr('ac_source', site=anticheat.SITE,
                                          when=app.anticheat_checked()),
                     bg="#1a0a12", fg=T["muted"], font=font(7, False), anchor="w").pack(
                         anchor="w", padx=px(12), pady=(0, px(10)))
            app.glitch.now(panel, strong=True)

        facts = tk.Frame(col, bg=T["bg"])
        facts.pack(anchor="w", fill="x", pady=(px(14), 0))
        mine = app.session_totals.get(game.key, {}).get('minutes', 0)
        rows = [('fact_playtime', playtime(game.playtime)),
                ('fact_last', last_played(game.last_played)),
                ('fact_folder', game.install_dir or tr('no_folder'))]
        if mine and game.launcher != 'own':
            rows.insert(1, ('fact_spark', playtime(mine)))
        for r, (key, value) in enumerate(rows):
            tk.Label(facts, text=tr(key), bg=T["bg"], fg=T["dim"], font=font(7),
                     anchor="w").grid(row=r, column=0, sticky="w", pady=px(3))
            tk.Label(facts, text=value, bg=T["bg"], fg=T["text"], font=font(9, False),
                     anchor="w", justify="left", wraplength=px(520)).grid(
                         row=r, column=1, sticky="w", padx=(px(14), 0), pady=px(3))

        section(col, app, tr('perf_title'))
        perf = tk.Frame(col, bg=T["bg"])
        perf.pack(anchor="w", fill="x")
        toggles = tk.Frame(perf, bg=T["bg"])
        self.mangohud = Toggle(toggles, tr('perf_mangohud'), bool(options.get('mangohud')),
                               lambda v: self._option('mangohud', v), font(8))
        self.gamemode = Toggle(toggles, tr('perf_gamemode'), bool(options.get('gamemode')),
                               lambda v: self._option('gamemode', v), font(8))
        if game.source == 'own' or game.source == 'steam':
            toggles.pack(anchor="w")
            self.mangohud.pack(side="left")
            self.gamemode.pack(side="left", padx=(px(8), 0))
        note = {'own': 'perf_own', 'steam': 'perf_steam', 'heroic': 'perf_heroic',
                'lutris': 'perf_lutris'}[game.launcher]
        tk.Label(perf, text=tr(note), bg=T["bg"], fg=T["muted"], font=font(8, False),
                 justify="left", anchor="w", wraplength=px(560)).pack(anchor="w",
                                                                      pady=(px(8), 0))
        if game.source == 'steam':
            line = tk.Frame(perf, bg=T["bg"])
            line.pack(anchor="w", pady=(px(6), 0))
            box, self.paste, self.paste_var = entry(line, app, width=40)
            box.pack(side="left")
            self.paste.configure(state="readonly", readonlybackground=T["panel"],
                                 fg=T["accent"])
            WolkButton(line, tr('copy'), self._copy, font(8), padx=px(10),
                       pady=px(3)).pack(side="left", padx=(px(8), 0))
            self._refresh_paste()
        if (options.get('gamemode') or game.source == 'own') and not which('gamemoderun') \
                and game.source == 'own':
            tk.Label(perf, text=tr('no_gamemode'), bg=T["bg"], fg=T["dim"], font=font(7, False),
                     anchor="w").pack(anchor="w", pady=(px(4), 0))

        if game.source == 'own':
            WolkButton(col, tr('remove'), self._remove, font(8), variant="danger", padx=px(10),
                       pady=px(3)).pack(anchor="w", pady=(px(22), 0))
        app.glitch.now(self.heading, strong=True)

    def _option(self, name: str, value: bool):
        self.app.set_game_option(self.game.key, name, value)
        if self.game.source == 'steam':
            self._refresh_paste()

    def _refresh_paste(self):
        options = self.app.game_options(self.game.key)
        self.paste_var.set(launch.steam_paste_line(bool(options.get('mangohud')),
                                                   bool(options.get('gamemode'))))

    def _copy(self):
        self.clipboard_clear()
        self.clipboard_append(self.paste_var.get())
        self.app.set_status(tr('copied'))

    def _remove(self):
        if messagebox.askyesno(tr('remove'), tr('remove_confirm', title=self.game.title),
                               parent=self):
            owngames.remove(str(self.game.launch.get('id')))
            self.app.go_back()
            self.app.rescan()

    def key(self, event) -> bool:
        if event.keysym in ('Return', 'KP_Enter'):
            self.app.play(self.game)
            return True
        return False

    def focus_default(self):
        self.play_btn.label.focus_set()


# ─── Adding a game ────────────────────────────────────────────

class AddGameView(tk.Frame):
    def __init__(self, app):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        px, font = app.px, app.font
        self.program: Optional[str] = None
        col = tk.Frame(self, bg=T["bg"])
        col.pack(fill="both", expand=True, padx=px(28), pady=px(22))
        self.heading = GlitchText(col, tr('add_title'), app.tkfont(16), T["bg"])
        self.heading.pack(anchor="w")
        tk.Label(col, text=tr('add_body'), bg=T["bg"], fg=T["muted"], font=font(9, False),
                 justify="left", wraplength=px(620)).pack(anchor="w", pady=(px(8), 0))

        section(col, app, tr('add_program'))
        row = tk.Frame(col, bg=T["bg"])
        row.pack(anchor="w", fill="x")
        WolkButton(row, tr('add_choose'), self._choose, font(8), padx=px(10),
                   pady=px(3)).pack(side="left")
        self.path_label = tk.Label(row, text=tr('add_none'), bg=T["bg"], fg=T["dim"],
                                   font=font(8, False), anchor="w")
        self.path_label.pack(side="left", padx=(px(10), 0))

        section(col, app, tr('add_name'))
        box, self.name, self.name_var = entry(col, app, width=40)
        box.pack(anchor="w")
        self.windows = Toggle(col, tr('add_windows'), False, lambda _v: self._update(), font(8))
        self.windows.pack(anchor="w", pady=(px(12), 0))
        self.note = tk.Frame(col, bg=T["bg"])
        self.note.pack(anchor="w", fill="x")

        actions = tk.Frame(col, bg=T["bg"])
        actions.pack(anchor="w", pady=(px(20), 0))
        self.save = WolkButton(actions, tr('add_save'), self._save, font(9), variant="primary",
                               padx=px(16), pady=px(5))
        self.save.pack(side="left")
        WolkButton(actions, tr('cancel'), app.go_back, font(9), padx=px(12),
                   pady=px(5)).pack(side="left", padx=(px(8), 0))
        self._update()

    def _choose(self):
        path = pick_program(home())
        if not path:
            return
        self.program = path
        self.path_label.config(text=path, fg=T["text"])
        if not self.name_var.get().strip():
            self.name_var.set(os.path.splitext(os.path.basename(path))[0])
        self.windows.set(is_windows_program(path))
        self._update()

    def _update(self):
        for child in self.note.winfo_children():
            child.destroy()
        px, font = self.app.px, self.app.font
        if self.windows.value and not which('umu-run'):
            tk.Label(self.note, text=tr('no_umu'), bg=T["bg"], fg=T["gold"], font=font(8, False),
                     justify="left", wraplength=px(600)).pack(anchor="w", pady=(px(8), 0))
            if not flatpak_installed('com.usebottles.bottles'):
                WolkButton(self.note, tr('get_bottles'), lambda: open_uri(BOTTLES_PAGE), font(8),
                           padx=px(10), pady=px(3)).pack(anchor="w", pady=(px(6), 0))
        self.save.set_enabled(bool(self.program))

    def _save(self):
        if not self.program:
            return
        owngames.add(self.name_var.get(), self.program, windows=self.windows.value)
        self.app.go_back()
        self.app.rescan()

    def key(self, _event) -> bool:
        return False

    def focus_default(self):
        self.name.focus_set()


# ─── Settings ─────────────────────────────────────────────────

class SettingsView(tk.Frame):
    def __init__(self, app):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        px, font = app.px, app.font
        col = tk.Frame(self, bg=T["bg"])
        col.pack(fill="both", expand=True, padx=px(28), pady=px(22))
        self.heading = GlitchText(col, tr('settings_title'), app.tkfont(16), T["bg"])
        self.heading.pack(anchor="w")

        section(col, app, tr('set_after_launch'))
        Segmented(col, [(tr('after_stay'), 'stay'), (tr('after_minimize'), 'minimize'),
                        (tr('after_close'), 'close')],
                  app.settings.get('after_launch', 'stay'),
                  lambda v: app.settings.__setitem__('after_launch', v), font(8)).pack(anchor="w")

        section(col, app, tr('set_online'))
        Toggle(col, tr('set_anticheat'), app.anticheat_on(), app.set_anticheat,
               font(8)).pack(anchor="w")
        tk.Label(col, text=tr('set_anticheat_note', site=anticheat.SITE), bg=T["bg"],
                 fg=T["muted"], font=font(8, False), justify="left",
                 wraplength=px(620)).pack(anchor="w", pady=(px(6), 0))

        section(col, app, tr('set_found'))
        found = app.launchers_found()
        if not found:
            tk.Label(col, text=tr('set_none'), bg=T["bg"], fg=T["muted"],
                     font=font(8, False)).pack(anchor="w")
        for name, path in found:
            row = tk.Frame(col, bg=T["bg"])
            row.pack(anchor="w", fill="x")
            tk.Label(row, text=f"● {name}", bg=T["bg"], fg=T["accent"], font=font(8),
                     width=18, anchor="w").pack(side="left")
            tk.Label(row, text=path, bg=T["bg"], fg=T["muted"], font=font(8, False),
                     anchor="w").pack(side="left")
        tk.Label(col, text=tr('set_files', config=config_dir(), data=data_dir(),
                              cache=cache_dir()),
                 bg=T["bg"], fg=T["dim"], font=font(7, False), justify="left",
                 wraplength=px(700)).pack(anchor="w", pady=(px(18), 0))

    def key(self, _event) -> bool:
        return False

    def focus_default(self):
        self.focus_set()
