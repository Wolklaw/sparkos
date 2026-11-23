"""The big screen: a fullscreen couch layout, made to be read from across the room and driven
with a controller (the keyboard and mouse work too).

  top      the selected game, large: title, launcher, playtime, last played
  rows     KEEP PLAYING (recently played), then one row per launcher, then ALL GAMES; big
           covers, the selected one framed by the magenta and cyan channels
  bottom   what each button does

Everything is drawn on one canvas and sized from the window's height (1080 px is the design
size), so it reads the same on a 1080p or a 4K TV. Only the covers in view are cut, in a worker
thread. Nothing runs while nobody touches it.

Three layers: the rows; a game's page (Start or Space); the search keyboard (Y or /).
"""

import queue
import threading
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

import tkinter as tk
import tkinter.font as tkfont

from PIL import Image, ImageTk

from . import SOURCES, covers
from .core import Game, matches, sort_recent, sort_title
from .strings import last_played, playtime, tr
from .widgets import T, mix

RECENT_MAX = 15
KEYS = [list("ABCDEFGHIJKLM"), list("NOPQRSTUVWXYZ"),
        list("1234567890") + ['space', 'delete', 'done']]
MAX_PHOTOS = 160


def launcher_words(game: Game) -> str:
    from .views import launcher_line
    return launcher_line(game)


class Row:
    def __init__(self, title: str, games: List[Game]):
        self.title, self.games = title, games
        self.col = 0          # selected cover in this row
        self.first = 0        # first cover in view


def build_rows(games: List[Game], query: str = '') -> List[Row]:
    """The rows for these games: a search gives one row; otherwise recent, per launcher, all."""
    if query:
        found = sort_title([g for g in games if matches(g, query)])
        return [Row(tr('big_search_for', query=query), found)] if found else []
    rows = []
    played = [g for g in sort_recent(games) if g.last_played][:RECENT_MAX]
    if played:
        rows.append(Row(tr('big_recent'), played))
    sources = [s for s in SOURCES if any(g.source == s for g in games)]
    for source in sources:
        rows.append(Row(tr(f'src_{source}'), sort_title([g for g in games if g.source == source])))
    if len(sources) > 1:
        rows.append(Row(tr('big_all'), sort_title(games)))
    return rows


class BigScreen(tk.Frame):
    def __init__(self, app):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        self.games: List[Game] = []
        self.rows: List[Row] = []
        self.row = 0
        self.query = ''
        self.layer = 'rows'              # rows, page, search
        self.page_game: Optional[Game] = None
        self.key_pos = (0, 0)            # search keyboard: (row, column)
        self.toast_text = ''
        self.toast_colour = T["accent"]
        self._toast_id: Optional[str] = None
        self._render_id: Optional[str] = None
        self._fonts: Dict[Tuple[int, bool], tkfont.Font] = {}
        self._fit_cache: Dict[Tuple[str, int, int], str] = {}
        # covers, cut in a worker thread; the poll runs only while some are being cut
        self.photos: "OrderedDict[Tuple[str, int, int], ImageTk.PhotoImage]" = OrderedDict()
        self.requested: set = set()
        self.jobs: "queue.Queue[Tuple[str, str, int, int]]" = queue.Queue()
        self.results: "queue.Queue[Tuple[str, int, int, Optional[Image.Image]]]" = queue.Queue()
        self.pending = 0
        self._poll_id: Optional[str] = None
        threading.Thread(target=self._worker, daemon=True).start()

        self.canvas = tk.Canvas(self, bg=T["bg"], highlightthickness=0, bd=0, takefocus=1)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._resized())
        self.canvas.bind("<ButtonRelease-1>", self._click)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.bind(seq, self._wheel)
        self.set_games([g for g in app.games if g.installed])

    def destroy(self):
        for after_id in (self._render_id, self._poll_id, self._toast_id):
            if after_id:
                try:
                    self.after_cancel(after_id)
                except tk.TclError:
                    pass
        self._render_id = self._poll_id = self._toast_id = None
        self.jobs.put(None)              # ends the worker
        super().destroy()

    # ── sizes: everything scales with the window's height ──
    def u(self, value: float) -> int:
        h = max(1, self.canvas.winfo_height())
        return max(1, int(round(value * max(0.45, h / 1080))))

    def font(self, size: int, bold: bool = True) -> tkfont.Font:
        px = self.u(size)
        key = (px, bold)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(self, family=self.app.mono, size=-px,
                                           weight="bold" if bold else "normal")
        return self._fonts[key]

    def metrics(self) -> Dict[str, int]:
        u = self.u
        w = max(1, self.canvas.winfo_width())
        cover_w, cover_h, gap = u(220), u(330), u(30)
        margin = u(80)
        visible = max(1, (w - 2 * margin + gap) // (cover_w + gap))
        return {'w': w, 'h': max(1, self.canvas.winfo_height()), 'cover_w': cover_w,
                'cover_h': cover_h, 'gap': gap, 'margin': margin, 'visible': visible,
                'rows_top': u(420), 'row_h': u(450)}

    # ── data ──
    def set_games(self, games: List[Game]):
        keep = self.current()
        self.games = list(games)
        self._rebuild(keep.key if keep else None)

    def _rebuild(self, keep: Optional[str] = None):
        old_row = self.rows[self.row].title if self.rows and self.row < len(self.rows) else None
        self.rows = build_rows(self.games, self.query)
        self.row = 0
        for r, row in enumerate(self.rows):        # stay on the same game when we can
            if row.title == old_row:
                self.row = r
                for c, game in enumerate(row.games):
                    if game.key == keep:
                        row.col = c
                break
        self._fit_cache.clear()
        for row in self.rows:
            self._scroll_row(row)
        if self.page_game is not None and not any(g.key == self.page_game.key
                                                  for g in self.games):
            self.page_game = None
            self.layer = 'rows'
        self.render()

    def current(self) -> Optional[Game]:
        if not self.rows or self.row >= len(self.rows):
            return None
        row = self.rows[self.row]
        return row.games[row.col] if 0 <= row.col < len(row.games) else None

    def _scroll_row(self, row: Row):
        visible = self.metrics()['visible'] if self.canvas.winfo_width() > 1 else 6
        row.col = max(0, min(row.col, len(row.games) - 1))
        if row.col < row.first:
            row.first = row.col
        elif row.col >= row.first + visible:
            row.first = row.col - visible + 1
        row.first = max(0, min(row.first, max(0, len(row.games) - visible)))

    # ── moving ──
    def move(self, dx: int, dy: int):
        if self.layer == 'search':
            r, c = self.key_pos
            r = max(0, min(len(KEYS) - 1, r + dy))
            c = max(0, min(len(KEYS[r]) - 1, c + dx))
            self.key_pos = (r, c)
            self.render()
            return
        if self.layer != 'rows' or not self.rows:
            return
        if dy:
            self.row = max(0, min(len(self.rows) - 1, self.row + dy))
        if dx:
            row = self.rows[self.row]
            row.col = max(0, min(len(row.games) - 1, row.col + dx))
        self._scroll_row(self.rows[self.row])
        self.render()

    def play(self):
        game = self.page_game if self.layer == 'page' else self.current()
        if game is not None:
            self.app.play(game)
            self.app.glitch.now(self.app.mark, strong=True)

    def open_page(self):
        game = self.current()
        if game is not None and self.layer == 'rows':
            self.page_game = game
            self.layer = 'page'
            self.render()

    def open_search(self):
        self.layer = 'search'
        self.render()

    def back(self):
        """B / Esc: close the top layer; clear a search; then leave the big screen."""
        if self.layer in ('page', 'search'):
            self.layer = 'rows'
            self.page_game = None
            self.render()
        elif self.query:
            self.set_query('')
        else:
            self.app.leave_big()

    def set_query(self, query: str):
        self.query = query[:40]
        self._rebuild()

    def press_key(self):
        r, c = self.key_pos
        key = KEYS[r][c]
        if key == 'done':
            self.layer = 'rows'
            self.render()
        elif key == 'delete':
            self.set_query(self.query[:-1])
        elif key == 'space':
            if self.query and not self.query.endswith(' '):
                self.set_query(self.query + ' ')
        else:
            self.set_query(self.query + key.lower())

    def cycle_row(self, delta: int):
        if self.layer == 'rows' and self.rows:
            self.row = (self.row + delta) % len(self.rows)
            self.render()

    # ── input ──
    def pad(self, action: str) -> None:
        moves = {'up': (0, -1), 'down': (0, 1), 'left': (-1, 0), 'right': (1, 0)}
        if action in moves:
            self.move(*moves[action])
        elif action == 'a':
            if self.layer == 'search':
                self.press_key()
            else:
                self.play()
        elif action == 'b':
            self.back()
        elif action == 'y':
            if self.layer == 'search':
                self.layer = 'rows'
                self.render()
            elif self.layer == 'rows':
                self.open_search()
        elif action == 'start':
            if self.layer == 'page':
                self.play()
            else:
                self.open_page()
        elif action in ('lb', 'rb'):
            self.cycle_row(-1 if action == 'lb' else 1)
        elif action == 'guide':
            self.app.leave_big()

    def key(self, event) -> bool:
        k = event.keysym
        if self.layer == 'search':
            if k in ('Return', 'KP_Enter', 'Escape'):
                self.layer = 'rows'
                self.render()
                return True
            if k == 'BackSpace':
                self.set_query(self.query[:-1])
                return True
            char = getattr(event, 'char', '')
            if char and len(char) == 1 and char.isprintable() and not event.state & 0x4:
                if char == ' ' and (not self.query or self.query.endswith(' ')):
                    return True
                self.set_query(self.query + char.lower())
                return True
        moves = {'Left': (-1, 0), 'Right': (1, 0), 'Up': (0, -1), 'Down': (0, 1)}
        if k in moves:
            self.move(*moves[k])
            return True
        if k in ('Return', 'KP_Enter'):
            if self.layer == 'search':
                self.press_key()
            else:
                self.play()
            return True
        if k in ('Escape', 'BackSpace'):
            self.back()
            return True
        if k in ('space', 'i'):
            self.open_page()
            return True
        if k == 'slash':
            self.open_search()
            return True
        if k in ('Prior', 'Next'):
            self.cycle_row(-1 if k == 'Prior' else 1)
            return True
        if k == 'F11':
            self.app.leave_big()
            return True
        return False

    def focus_default(self):
        self.canvas.focus_set()

    def toast(self, text: str, colour: Optional[str] = None, hold_ms: int = 2500):
        self.toast_text, self.toast_colour = text, colour or T["accent"]
        if self._toast_id:
            self.after_cancel(self._toast_id)
        self._toast_id = self.after(min(hold_ms, 8000), self._toast_off)
        self.render()

    def _toast_off(self):
        self._toast_id = None
        self.toast_text = ''
        self.render()

    # ── mouse ──
    def _hit(self, x: int, y: int) -> Optional[Tuple[int, int]]:
        m = self.metrics()
        for r in range(self.row, len(self.rows)):
            top = m['rows_top'] + (r - self.row) * m['row_h'] + self.u(44)
            if top > m['h']:
                break
            if not top <= y <= top + m['cover_h']:
                continue
            i = (x - m['margin']) // (m['cover_w'] + m['gap'])
            row = self.rows[r]
            col = row.first + i
            if x >= m['margin'] and 0 <= col < len(row.games):
                return r, col
        return None

    def _click(self, event):
        self.canvas.focus_set()
        if self.layer != 'rows':
            return
        hit = self._hit(event.x, event.y)
        if hit is None:
            return
        r, col = hit
        if (r, col) == (self.row, self.rows[r].col):
            self.open_page()
        else:
            self.row = r
            self.rows[r].col = col
            self._scroll_row(self.rows[r])
            self.render()

    def _wheel(self, event):
        down = not (getattr(event, 'num', 0) == 4 or getattr(event, 'delta', 0) > 0)
        self.move(0, 1 if down else -1)
        return "break"

    # ── drawing ──
    def _resized(self):
        self._fit_cache.clear()
        for row in self.rows:
            self._scroll_row(row)
        self.render()

    def render(self):
        if self._render_id is None:
            self._render_id = self.after_idle(self._render)

    def _render(self):
        self._render_id = None
        if not self.winfo_exists():
            return
        c = self.canvas
        c.delete("all")
        m = self.metrics()
        self._header(m)
        if self.layer == 'page' and self.page_game is not None:
            self._page(m, self.page_game)
        else:
            self._hero(m)
            self._rows(m)
            if self.layer == 'search':
                self._keyboard(m)
        self._hints(m)

    def _ghost_text(self, x, y, text, font, fill=None, anchor="nw", split=2):
        """Text with its magenta and cyan copies slightly out of register: the house mark."""
        c, d = self.canvas, self.u(split)
        c.create_text(x - d, y, text=text, font=font, fill=T["ch_a"], anchor=anchor)
        c.create_text(x + d, y, text=text, font=font, fill=T["ch_b"], anchor=anchor)
        c.create_text(x, y, text=text, font=font, fill=fill or T["text"], anchor=anchor)

    def _fit(self, text: str, width: int, size: int, bold: bool = True) -> str:
        key = (text, width, size * 2 + bold)
        if key in self._fit_cache:
            return self._fit_cache[key]
        f = self.font(size, bold)
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
        self._fit_cache[key] = out
        return out

    def _header(self, m):
        c, u = self.canvas, self.u
        self._ghost_text(m['margin'], u(36), tr('title'), self.font(30))
        n = len(self.games)
        count = tr('game_1') if n == 1 else tr('games_n', n=n)
        c.create_text(m['w'] - m['margin'], u(48), text=count, anchor="ne", fill=T["muted"],
                      font=self.font(22))
        if self.toast_text:
            c.create_text(m['w'] - m['margin'], u(84), text=self.toast_text[:70], anchor="ne",
                          fill=self.toast_colour, font=self.font(22))
        # the header rule: mint into pink, as in the window
        y = u(110)
        steps = 48
        span = m['w'] - 2 * m['margin']
        for i in range(steps):
            x0 = m['margin'] + span * i // steps
            x1 = m['margin'] + span * (i + 1) // steps
            c.create_rectangle(x0, y, x1, y + max(2, u(3)), width=0,
                               fill=mix(T["accent"], T["pink"], i / steps))

    def _hero(self, m):
        c, u = self.canvas, self.u
        x, width = m['margin'], m['w'] - 2 * m['margin']
        if self.layer == 'search':
            text = tr('big_search_for', query=self.query + '▌')
            self._ghost_text(x, u(150), self._fit(text, width, 52), self.font(52))
            return
        game = self.current()
        if game is None:
            text = tr('big_empty') if not self.games else tr('no_match', query=self.query)
            c.create_text(x, u(170), text=text, anchor="nw", fill=T["muted"],
                          font=self.font(30, False), width=width)
            return
        self._ghost_text(x, u(140), self._fit(game.title, width, 60), self.font(60))
        c.create_text(x + u(4), u(232), text=launcher_words(game).upper(), anchor="nw",
                      fill=T["accent"], font=self.font(24))
        facts = f"{playtime(game.playtime)}   ·   {last_played(game.last_played)}"
        c.create_text(x + u(4), u(278), text=facts, anchor="nw", fill=T["muted"],
                      font=self.font(26, False))
        if game.anticheat:
            c.create_text(x + u(4), u(324), text=self._fit(tr(f'ac_{game.anticheat}'), width, 22,
                                                            False),
                          anchor="nw", fill=T["pink"], font=self.font(22, False))

    def _rows(self, m):
        c, u = self.canvas, self.u
        top = m['rows_top']
        if self.layer == 'search':
            top = u(240)
            if not self.rows and self.query:
                c.create_text(m['margin'], top, text=tr('no_match', query=self.query),
                              anchor="nw", fill=T["muted"], font=self.font(28, False))
        bottom_limit = m['h'] - u(90) if self.layer != 'search' else m['h'] - u(440)
        for r in range(self.row, len(self.rows)):
            y = top + (r - self.row) * m['row_h']
            if y > bottom_limit:
                break
            row = self.rows[r]
            active = r == self.row
            label = row.title + f"   {len(row.games)}"
            c.create_text(m['margin'], y, text=label, anchor="nw",
                          fill=T["text"] if active else T["dim"], font=self.font(24))
            cy = y + u(44)
            last = min(len(row.games), row.first + m['visible'] + 1)
            for i in range(row.first, last):
                x = m['margin'] + (i - row.first) * (m['cover_w'] + m['gap'])
                if x > m['w']:
                    break
                self._cover(row.games[i], x, cy, m, selected=active and i == row.col)
            if row.first > 0:            # more covers to the left
                c.create_text(u(40), cy + m['cover_h'] // 2, text="‹", fill=T["muted"],
                              font=self.font(48))

    def _cover(self, game: Game, x: int, y: int, m, selected: bool):
        c, u = self.canvas, self.u
        w, h = m['cover_w'], m['cover_h']
        photo = self._photo(game, w, h)
        if photo is not None:
            c.create_image(x, y, image=photo, anchor="nw")
        else:
            c.create_rectangle(x, y, x + w, y + h, fill=T["tile"], outline=T["line"])
            c.create_text(x + w / 2, y + h / 2, text=game.title, width=w - u(24),
                          justify="center", fill=T["muted"], font=self.font(24))
        if game.anticheat:
            c.create_rectangle(x, y, x + u(150), y + u(32), fill=T["pink"], outline="")
            c.create_text(x + u(8), y + u(16), text=tr('anticheat_badge'), anchor="w",
                          fill=T["on_accent"], font=self.font(18))
        if selected:
            o, d, lw = u(6), u(4), max(2, u(4))
            c.create_rectangle(x - o - d, y - o, x + w + o - d, y + h + o, outline=T["ch_a"],
                               width=lw)
            c.create_rectangle(x - o + d, y - o, x + w + o + d, y + h + o, outline=T["ch_b"],
                               width=lw)
            c.create_rectangle(x - o, y - o, x + w + o, y + h + o, outline=T["accent"], width=lw)
        c.create_text(x, y + h + u(14), text=self._fit(game.title, w, 22), anchor="nw",
                      fill=T["text"] if selected else T["muted"], font=self.font(22))

    def _page(self, m, game: Game):
        c, u = self.canvas, self.u
        cw, ch = u(400), u(600)
        x, y = m['margin'], u(160)
        photo = self._photo(game, cw, ch)
        if photo is not None:
            c.create_image(x, y, image=photo, anchor="nw")
        else:
            c.create_rectangle(x, y, x + cw, y + ch, fill=T["tile"], outline=T["line2"])
            c.create_text(x + cw / 2, y + ch / 2, text=game.title, width=cw - u(40),
                          justify="center", fill=T["muted"], font=self.font(32))
        tx = x + cw + u(60)
        width = m['w'] - tx - m['margin']
        self._ghost_text(tx, y, self._fit(game.title, width, 60), self.font(60))
        c.create_text(tx + u(4), y + u(92), text=launcher_words(game).upper(), anchor="nw",
                      fill=T["accent"], font=self.font(24))
        facts = [(tr('fact_playtime'), playtime(game.playtime)),
                 (tr('fact_last'), last_played(game.last_played)),
                 (tr('fact_folder'), game.install_dir or tr('no_folder'))]
        fy = y + u(160)
        for label, value in facts:
            c.create_text(tx + u(4), fy, text=label, anchor="nw", fill=T["dim"],
                          font=self.font(20))
            c.create_text(tx + u(4), fy + u(30), text=self._fit(value, width, 28, False),
                          anchor="nw", fill=T["text"], font=self.font(28, False))
            fy += u(86)
        if game.anticheat:
            c.create_text(tx + u(4), fy, text=tr(f'ac_{game.anticheat}'), anchor="nw",
                          fill=T["pink"], font=self.font(22, False), width=width)
            fy += u(90)
        # the Play button, already selected: A or Enter starts the game
        bw, bh = u(300), u(84)
        by = max(fy + u(20), y + ch - bh)
        d = u(4)
        c.create_rectangle(tx - d, by, tx + bw - d, by + bh, fill=T["ch_a"], outline="")
        c.create_rectangle(tx + d, by, tx + bw + d, by + bh, fill=T["ch_b"], outline="")
        c.create_rectangle(tx, by, tx + bw, by + bh, fill=T["accent"], outline="")
        c.create_text(tx + bw / 2, by + bh / 2, text=tr('big_play'), fill=T["on_accent"],
                      font=self.font(34))

    def _keyboard(self, m):
        c, u = self.canvas, self.u
        cell_h, gap = u(70), u(10)
        cols = len(KEYS[0])
        cell_w = (m['w'] - 2 * m['margin'] - (cols - 1) * gap) // cols
        top = m['h'] - u(380)
        c.create_rectangle(0, top - u(30), m['w'], m['h'] - u(90), fill=T["panel"], outline="")
        c.create_line(0, top - u(30), m['w'], top - u(30), fill=T["line2"], width=max(1, u(2)))
        for r, keys in enumerate(KEYS):
            x = m['margin']
            y = top + r * (cell_h + gap)
            for col, key in enumerate(keys):
                w = cell_w
                label = {'space': tr('big_space'), 'delete': tr('big_delete'),
                         'done': tr('big_done')}.get(key, key)
                on = (r, col) == self.key_pos
                if on:
                    d = u(3)
                    c.create_rectangle(x - d, y, x + w - d, y + cell_h, outline=T["ch_a"],
                                       width=max(2, u(3)))
                    c.create_rectangle(x + d, y, x + w + d, y + cell_h, outline=T["ch_b"],
                                       width=max(2, u(3)))
                c.create_rectangle(x, y, x + w, y + cell_h,
                                   fill=T["accent"] if on else T["panel2"],
                                   outline=T["accent"] if on else T["line"])
                c.create_text(x + w / 2, y + cell_h / 2, text=self._fit(label, w - u(8), 26),
                              fill=T["on_accent"] if on else T["text"], font=self.font(26))
                x += w + gap

    def _hints(self, m):
        c, u = self.canvas, self.u
        y = m['h'] - u(52)
        # the bar covers whatever row runs under it
        c.create_rectangle(0, y - u(28), m['w'], m['h'], fill=T["bg"], outline="")
        c.create_line(m['margin'], y - u(28), m['w'] - m['margin'], y - u(28), fill=T["line"])
        if self.layer == 'search':
            hints = [('A', tr('big_type')), ('B', tr('big_done'))]
        elif self.layer == 'page':
            hints = [('A', tr('big_play')), ('B', tr('big_back'))]
        else:
            hints = [('A', tr('big_play')),
                     ('B', tr('big_back') if self.query else tr('big_exit')),
                     ('Y', tr('big_search')), ('START', tr('big_page')),
                     ('LB RB', tr('big_filter'))]
        x = m['margin']
        f_btn, f_txt = self.font(20), self.font(22)
        for button, words in hints:
            bw = f_btn.measure(button) + u(20)
            c.create_rectangle(x, y - u(18), x + bw, y + u(18), fill=T["panel2"],
                               outline=T["line2"])
            c.create_text(x + bw / 2, y, text=button, fill=T["accent"], font=f_btn)
            x += bw + u(12)
            c.create_text(x, y, text=words, anchor="w", fill=T["text"], font=f_txt)
            x += f_txt.measure(words) + u(40)
        c.create_text(m['w'] - m['margin'], y, text=tr('big_keys'), anchor="e", fill=T["dim"],
                      font=self.font(18, False))

    # ── covers ──
    def _photo(self, game: Game, w: int, h: int) -> Optional[ImageTk.PhotoImage]:
        key = (game.key, w, h)
        photo = self.photos.get(key)
        if photo is not None:
            self.photos.move_to_end(key)
            return photo
        if game.cover and key not in self.requested:
            self.requested.add(key)
            self.jobs.put((game.key, game.cover, w, h))
            self.pending += 1
            if self._poll_id is None:
                self._poll_id = self.after(40, self._poll)
        return None

    def _worker(self):
        while True:
            job = self.jobs.get()
            if job is None:
                return
            game_key, src, w, h = job
            try:
                image = covers.thumbnail(src, w, h)
            except Exception:              # noqa: BLE001 - a bad image must not kill the worker
                image = None
            self.results.put((game_key, w, h, image))

    def _poll(self):
        self._poll_id = None
        if not self.winfo_exists():
            return
        changed = False
        while True:
            try:
                game_key, w, h, image = self.results.get_nowait()
            except queue.Empty:
                break
            self.pending -= 1
            if image is not None:
                self.photos[(game_key, w, h)] = ImageTk.PhotoImage(image, master=self)
                changed = True
                while len(self.photos) > MAX_PHOTOS:
                    old, _photo = self.photos.popitem(last=False)
                    self.requested.discard(old)
        if changed:
            self.render()
        if self.pending > 0:                # nothing scheduled when idle
            self._poll_id = self.after(40, self._poll)
