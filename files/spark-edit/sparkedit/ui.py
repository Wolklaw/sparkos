"""Spark Edit's own pieces of interface in the house style: the file tabs, status bar items,
text fields, menus and the question dialog. The shared widgets are in widgets.py."""

from typing import Callable, Dict, List, Optional, Sequence, Tuple

import tkinter as tk
from tkinter import ttk

from .widgets import T, GlitchText, WolkButton, mix


def style_scrollbars(root: tk.Misc) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use('clam')
    except tk.TclError:
        pass
    for orient in ('Vertical', 'Horizontal'):
        name = f"Spark.{orient}.TScrollbar"
        style.configure(name, background=T["panel2"], troughcolor=T["bg"], bordercolor=T["bg"],
                        arrowcolor=T["muted"], lightcolor=T["panel2"], darkcolor=T["panel2"],
                        gripcount=0, arrowsize=12)
        style.map(name, background=[("active", T["line2"])])


def menu(root: tk.Misc, font) -> tk.Menu:
    return tk.Menu(root, tearoff=0, bg=T["panel"], fg=T["text"], activebackground=T["hover"],
                   activeforeground=T["accent"], disabledforeground=T["dim"],
                   selectcolor=T["accent"], bd=1, relief='flat', font=font,
                   activeborderwidth=0)


def entry(parent: tk.Misc, font, width: int = 30) -> tk.Entry:
    e = tk.Entry(parent, font=font, width=width, bg=T["out_bg"], fg=T["text"],
                 insertbackground=T["accent"], selectbackground=T["line2"],
                 selectforeground=T["text"], relief='flat', bd=0, highlightthickness=1,
                 highlightbackground=T["line"], highlightcolor=T["accent"])
    return e


def set_entry_error(e: tk.Entry, error: bool) -> None:
    e.configure(highlightbackground=T["pink"] if error else T["line"],
                highlightcolor=T["pink"] if error else T["accent"])


class Tab:
    def __init__(self, strip: 'TabStrip', key: object):
        self.key = key
        app_font, px = strip.font, strip.px
        self.cell = tk.Frame(strip.inner, bg=T["bg"])
        row = tk.Frame(self.cell, bg=T["bg"])
        row.pack(fill='x')
        self.row = row
        self.label = tk.Label(row, text='', font=app_font, bg=T["bg"], fg=T["muted"],
                              padx=px(10), pady=px(6), cursor='hand2')
        self.label.pack(side='left')
        self.close = tk.Label(row, text=' ', font=app_font, bg=T["bg"], fg=T["muted"],
                              padx=px(4), pady=px(6), cursor='hand2', width=2)
        self.close.pack(side='left', padx=(0, px(4)))
        self.bar = tk.Frame(self.cell, height=max(2, px(2)), bg=T["bg"])
        self.bar.pack(fill='x')
        self.name, self.dirty, self.current, self.hover = '', False, False, False
        self.tip = ''

    def paint(self) -> None:
        bg = T["panel"] if self.current else (T["hover"] if self.hover else T["bg"])
        fg = T["text"] if self.current else (T["text"] if self.hover else T["muted"])
        for w in (self.row, self.label, self.close):
            w.configure(bg=bg)
        self.label.configure(fg=fg, text=self.name)
        if self.dirty and not self.hover:
            self.close.configure(text='●', fg=T["gold"])
        elif self.current or self.hover:
            self.close.configure(text='×', fg=T["muted"])
        else:
            self.close.configure(text=' ')
        self.bar.configure(bg=T["accent"] if self.current else bg)


class TabStrip(tk.Frame):
    """One row of file tabs. Scrolls sideways (mouse wheel) when they don't fit."""

    def __init__(self, parent: tk.Misc, font, px: Callable[[float], int],
                 on_select: Callable[[object], None], on_close: Callable[[object], None],
                 on_menu: Callable[[object, tk.Event], None],
                 on_hover: Callable[[Optional[str]], None]):
        super().__init__(parent, bg=T["bg"])
        self.font, self.px = font, px
        self.on_select, self.on_close, self.on_menu, self.on_hover = \
            on_select, on_close, on_menu, on_hover
        self.canvas = tk.Canvas(self, bg=T["bg"], highlightthickness=0, bd=0, height=10)
        self.canvas.pack(fill='both', expand=True)
        self.inner = tk.Frame(self.canvas, bg=T["bg"])
        self.window = self.canvas.create_window(0, 0, anchor='nw', window=self.inner)
        self.inner.bind('<Configure>', self._fit)
        self.canvas.bind('<Configure>', self._fit)
        self.tabs: Dict[object, Tab] = {}
        self.order: List[object] = []
        for seq in ('<MouseWheel>', '<Button-4>', '<Button-5>', '<Shift-MouseWheel>'):
            self.canvas.bind(seq, self._wheel)

    def _fit(self, _e=None) -> None:
        self.canvas.configure(height=self.inner.winfo_reqheight(),
                              scrollregion=(0, 0, self.inner.winfo_reqwidth(),
                                            self.inner.winfo_reqheight()))

    def _wheel(self, event) -> str:
        if self.inner.winfo_reqwidth() <= self.canvas.winfo_width():
            return 'break'
        up = getattr(event, 'num', 0) == 4 or getattr(event, 'delta', 0) > 0
        self.canvas.xview_scroll(-3 if up else 3, 'units')
        return 'break'

    def add(self, key: object, name: str) -> None:
        tab = Tab(self, key)
        tab.name = name
        self.tabs[key] = tab
        self.order.append(key)
        tab.cell.pack(side='left', padx=(0, self.px(1)))
        for w in (tab.row, tab.label):
            w.bind('<ButtonRelease-1>', lambda _e, k=key: self.on_select(k))
            w.bind('<ButtonRelease-2>', lambda _e, k=key: self.on_close(k))
            w.bind('<ButtonRelease-3>', lambda e, k=key: self.on_menu(k, e))
        tab.close.bind('<ButtonRelease-1>', lambda _e, k=key: self.on_close(k))
        for w in (tab.row, tab.label, tab.close, tab.cell):
            w.bind('<Enter>', lambda _e, t=tab: self._hover(t, True), add='+')
            w.bind('<Leave>', lambda _e, t=tab: self._hover(t, False), add='+')
            for seq in ('<MouseWheel>', '<Button-4>', '<Button-5>', '<Shift-MouseWheel>'):
                w.bind(seq, self._wheel)
        tab.paint()

    def _hover(self, tab: Tab, on: bool) -> None:
        if on == tab.hover:
            return
        tab.hover = on
        tab.paint()
        self.on_hover(tab.tip if on else None)

    def update_tab(self, key: object, name: str, dirty: bool, tip: str = '') -> None:
        tab = self.tabs.get(key)
        if tab and (tab.name, tab.dirty, tab.tip) != (name, dirty, tip):
            tab.name, tab.dirty, tab.tip = name, dirty, tip
            tab.paint()

    def remove(self, key: object) -> None:
        tab = self.tabs.pop(key, None)
        if tab:
            self.order.remove(key)
            tab.cell.destroy()

    def select(self, key: Optional[object]) -> None:
        for k, tab in self.tabs.items():
            if tab.current != (k == key):
                tab.current = k == key
                tab.paint()
        if key in self.tabs:
            self.after_idle(lambda: self._show(key))

    def _show(self, key: object) -> None:
        tab = self.tabs.get(key)
        if not tab or not tab.cell.winfo_exists():
            return
        total = max(1, self.inner.winfo_reqwidth())
        view = self.canvas.winfo_width()
        x0 = tab.cell.winfo_x()
        x1 = x0 + tab.cell.winfo_width()
        left = self.canvas.canvasx(0)
        if x0 < left:
            self.canvas.xview_moveto(x0 / total)
        elif x1 > left + view:
            self.canvas.xview_moveto(max(0, x1 - view) / total)


class StatusItem(tk.Label):
    """A clickable piece of the status bar: uppercase mono, lit on hover."""

    def __init__(self, parent: tk.Misc, font, px, command: Optional[Callable[[tk.Event], None]],
                 tip: str = ''):
        super().__init__(parent, text='', font=font, bg=T["panel"], fg=T["muted"],
                         padx=px(8), pady=px(3), cursor='hand2' if command else '')
        self.command = command
        if command:
            self.bind('<ButtonRelease-1>', lambda e: command(e))
            self.bind('<Enter>', lambda _e: self.configure(bg=T["hover"], fg=T["text"]))
            self.bind('<Leave>', lambda _e: self.configure(bg=T["panel"], fg=self.fg))
        self.fg = T["muted"]

    def set(self, text: str, fg: Optional[str] = None) -> None:
        self.fg = fg or T["muted"]
        self.configure(text=text.upper(), fg=self.fg)


def ask(app, title: str, message: str, buttons: Sequence[Tuple[str, str, str]],
        default: Optional[str] = None, cancel: str = 'cancel') -> str:
    """A modal question in the house style. buttons: (key, label, variant), shown left to
    right; Enter picks `default` (the first button if not given), Escape picks `cancel`.
    Returns the key of the button pressed."""
    root = app.root
    px = app.px
    win = tk.Toplevel(root, bg=T["line2"], padx=1, pady=1)
    win.withdraw()
    win.title(title)
    win.transient(root)
    win.resizable(False, False)
    body = tk.Frame(win, bg=T["panel"], padx=px(20), pady=px(16))
    body.pack(fill='both', expand=True)
    head = GlitchText(body, title.upper(), app.font(11, True), bg=T["panel"])
    head.pack(anchor='w')
    tk.Label(body, text=message, font=app.font(10, False), bg=T["panel"], fg=T["text"],
             justify='left', anchor='w', wraplength=px(440)).pack(anchor='w', pady=(px(8),
                                                                               px(16)))
    row = tk.Frame(body, bg=T["panel"])
    row.pack(anchor='e')
    result = {'key': cancel}

    def pick(key: str) -> None:
        result['key'] = key
        win.destroy()

    first = None
    for key, label, variant in buttons:
        b = WolkButton(row, label, lambda k=key: pick(k), app.font(9, True), variant=variant,
                       padx=px(12), pady=px(5))
        b.pack(side='left', padx=(px(6), 0))
        if first is None or key == default:
            first = b
    win.bind('<Escape>', lambda _e: pick(cancel))
    win.bind('<Return>', lambda _e: pick(default or buttons[0][0]))
    win.protocol('WM_DELETE_WINDOW', lambda: pick(cancel))
    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    x = root.winfo_rootx() + max(0, (root.winfo_width() - w) // 2)
    y = root.winfo_rooty() + max(0, (root.winfo_height() - h) // 3)
    win.geometry(f'+{x}+{y}')
    win.deiconify()
    app.glitch.now(head, strong=True)
    try:
        win.grab_set()
    except tk.TclError:
        pass
    if first is not None:
        first.label.focus_set()
    root.wait_window(win)
    return result['key']


def separator(parent: tk.Misc, vertical: bool = False) -> tk.Frame:
    f = tk.Frame(parent, bg=T["line"], width=1 if vertical else 0, height=0 if vertical else 1)
    return f


def dim(colour: str, t: float = 0.5) -> str:
    return mix(colour, T["bg"], t)
