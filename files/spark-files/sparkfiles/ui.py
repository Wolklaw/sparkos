"""Spark Files' own pieces of interface in the house style: menus, text fields, the dialog
frame and the question box, the tab strip, a progress bar and tooltips. The shared widgets are
in widgets.py."""

from typing import Callable, Dict, List, Optional, Sequence, Tuple

import tkinter as tk
from tkinter import ttk

from .widgets import T, GlitchText, WolkButton, mix


class Timers:
    """Cancels a widget's pending after() calls when it's destroyed. Without this, Tkinter
    deletes the callback but Tcl still fires the timer, and the command name (made from the
    callback's id) may by then belong to a newer callback, which then runs by mistake."""

    def after(self, ms, func=None, *args):
        if func is None:
            return super().after(ms)
        holder = {}
        timers = self.__dict__.setdefault('_timers', set())

        def run(*a):
            timers.discard(holder.get('id'))
            return func(*a)
        run.__name__ = 'timer'
        holder['id'] = super().after(ms, run, *args)
        timers.add(holder['id'])
        return holder['id']

    def after_cancel(self, id_) -> None:
        self.__dict__.get('_timers', set()).discard(id_)
        super().after_cancel(id_)

    def destroy(self) -> None:
        for id_ in list(self.__dict__.get('_timers', ())):
            try:
                super().after_cancel(id_)
            except tk.TclError:
                pass
        self.__dict__.get('_timers', set()).clear()
        super().destroy()


def style_ttk(root: tk.Misc) -> None:
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


def entry(parent: tk.Misc, font, width: int = 30, bg: Optional[str] = None) -> tk.Entry:
    return tk.Entry(parent, font=font, width=width, bg=bg or T["out_bg"], fg=T["text"],
                    insertbackground=T["accent"], selectbackground=T["line2"],
                    selectforeground=T["text"], relief='flat', bd=0, highlightthickness=1,
                    highlightbackground=T["line"], highlightcolor=T["accent"],
                    disabledbackground=T["panel"], disabledforeground=T["dim"],
                    readonlybackground=T["panel"])


def set_entry_error(e: tk.Entry, error: bool) -> None:
    e.configure(highlightbackground=T["pink"] if error else T["line"],
                highlightcolor=T["pink"] if error else T["accent"])


def label(parent: tk.Misc, text: str, font, fg: str = T["text"], bg: str = T["panel"],
          **kw) -> tk.Label:
    return tk.Label(parent, text=text, font=font, fg=fg, bg=bg, **kw)


def micro(parent: tk.Misc, text: str, font, bg: str = T["panel"]) -> tk.Label:
    """An UPPERCASE muted micro-label."""
    return tk.Label(parent, text=text.upper(), font=font, fg=T["muted"], bg=bg, anchor='w')


def separator(parent: tk.Misc, vertical: bool = False, colour: str = T["line"]) -> tk.Frame:
    return tk.Frame(parent, bg=colour, width=1 if vertical else 0, height=0 if vertical else 1)


def dim(colour: str, t: float = 0.5) -> str:
    return mix(colour, T["bg"], t)


class Check(tk.Label):
    """[■] label / [□] label, the house checkbox."""

    def __init__(self, parent: tk.Misc, text: str, value: bool, font,
                 command: Optional[Callable[[bool], None]] = None, bg: str = T["panel"]):
        super().__init__(parent, font=font, bg=bg, cursor='hand2', takefocus=1, anchor='w',
                         highlightthickness=0, padx=0)
        self.text, self.value, self.command, self.bgc = text, value, command, bg
        self.enabled = True
        for seq in ('<ButtonRelease-1>', '<space>'):
            self.bind(seq, lambda _e: self.toggle())
        self.bind('<Enter>', lambda _e: self.configure(fg=T["accent"]) if self.enabled else None)
        self.bind('<Leave>', lambda _e: self._paint())
        self._paint()

    def _paint(self):
        mark = '■' if self.value else '□'
        fg = (T["text"] if self.value else T["muted"]) if self.enabled else T["dim"]
        self.configure(text=f"{mark} {self.text}", fg=fg)

    def toggle(self):
        if self.enabled:
            self.set(not self.value)
            if self.command:
                self.command(self.value)

    def set(self, value: bool):
        self.value = value
        self._paint()

    def set_enabled(self, on: bool):
        self.enabled = on
        self.configure(cursor='hand2' if on else 'arrow')
        self._paint()


class Progress(tk.Canvas):
    """A 1px-framed bar, the done part in the accent (gold when paused, pink on errors)."""

    def __init__(self, parent: tk.Misc, height: int, width: int = 120, bg: str = T["panel"]):
        super().__init__(parent, height=height, width=width, bg=bg, highlightthickness=0, bd=0)
        self.fraction, self.colour = 0.0, T["accent"]
        self.bind('<Configure>', lambda _e: self.draw())

    def set(self, fraction: float, colour: Optional[str] = None):
        fraction = max(0.0, min(1.0, fraction))
        colour = colour or T["accent"]
        if (fraction, colour) != (self.fraction, self.colour):
            self.fraction, self.colour = fraction, colour
            self.draw()

    def draw(self):
        self.delete('all')
        w, h = self.winfo_width(), int(self.cget('height'))
        self.create_rectangle(0, 0, w - 1, h - 1, outline=T["line2"], fill=T["out_bg"])
        x = 1 + (w - 3) * self.fraction
        if self.fraction > 0:
            self.create_rectangle(1, 1, x, h - 2, outline='', fill=self.colour)


class Tooltip:
    """One tooltip window for the whole app; widgets call show()/hide() on hover."""

    def __init__(self, root: tk.Misc, font):
        self.root, self.font = root, font
        self.win: Optional[tk.Toplevel] = None
        self._after: Optional[str] = None

    def attach(self, widget: tk.Misc, text: Callable[[], str] or str) -> None:
        widget.bind('<Enter>', lambda e: self._schedule(widget, text), add='+')
        widget.bind('<Leave>', lambda _e: self.hide(), add='+')
        widget.bind('<ButtonPress>', lambda _e: self.hide(), add='+')

    def _schedule(self, widget, text) -> None:
        self.hide()
        self._after = self.root.after(550, lambda: self.show(widget, text() if callable(text)
                                                               else text))

    def show(self, widget: tk.Misc, text: str) -> None:
        if not text or not widget.winfo_exists():
            return
        self.hide()
        win = tk.Toplevel(self.root, bg=T["line2"], padx=1, pady=1)
        win.wm_overrideredirect(True)
        try:
            win.wm_attributes('-type', 'tooltip')
        except tk.TclError:
            pass
        tk.Label(win, text=text, font=self.font, bg=T["panel2"], fg=T["text"], padx=8,
                 pady=3, justify='left').pack()
        x = widget.winfo_rootx()
        y = widget.winfo_rooty() + widget.winfo_height() + 4
        win.geometry(f'+{x}+{y}')
        self.win = win

    def hide(self) -> None:
        if self._after:
            self.root.after_cancel(self._after)
            self._after = None
        if self.win is not None:
            try:
                self.win.destroy()
            except tk.TclError:
                pass
            self.win = None


class Dialog(Timers, tk.Toplevel):
    """A dialog frame in the house style: glitching title, body, buttons on the right."""

    def __init__(self, app, parent: tk.Misc, title: str, width: Optional[int] = None):
        super().__init__(parent, bg=T["line2"], padx=1, pady=1)
        self.withdraw()
        self.app = app
        self.parent_window = parent.winfo_toplevel()
        self.title(title)
        self.transient(self.parent_window)
        self.result = None
        px = app.px
        self.body = tk.Frame(self, bg=T["panel"], padx=px(20), pady=px(16))
        self.body.pack(fill='both', expand=True)
        self.head = GlitchText(self.body, title.upper(), app.font(11, True), bg=T["panel"])
        self.head.pack(anchor='w', pady=(0, px(10)))
        self.content = tk.Frame(self.body, bg=T["panel"])
        self.content.pack(fill='both', expand=True)
        if width:
            self.content.configure(width=width)
        self.buttons = tk.Frame(self.body, bg=T["panel"])
        self.buttons.pack(anchor='e', pady=(px(14), 0))
        self.protocol('WM_DELETE_WINDOW', self.cancel)
        self.bind('<Escape>', lambda _e: self.cancel())

    def button(self, text: str, command: Callable[[], None], variant: str = 'ghost'
               ) -> WolkButton:
        b = WolkButton(self.buttons, text, command, self.app.font(9, True), variant=variant,
                       padx=self.app.px(12), pady=self.app.px(5))
        b.pack(side='left', padx=(self.app.px(6), 0))
        return b

    def place_and_show(self) -> None:
        self.update_idletasks()
        parent = self.parent_window
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        try:
            x = parent.winfo_rootx() + max(0, (parent.winfo_width() - w) // 2)
            y = parent.winfo_rooty() + max(0, (parent.winfo_height() - h) // 3)
        except tk.TclError:
            x, y = 200, 200
        self.geometry(f'+{x}+{y}')
        self.deiconify()
        self.lift()
        self.app.glitch.now(self.head, strong=True)

    def run(self):
        """Show modally and return self.result."""
        self.place_and_show()
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.focus_first()
        self.wait_window(self)
        return self.result

    def focus_first(self) -> None:
        pass

    def done(self, result=None) -> None:
        self.result = result
        self.destroy()

    def cancel(self) -> None:
        self.done(None)


def ask(app, parent: tk.Misc, title: str, message: str,
        buttons: Sequence[Tuple[str, str, str]], default: Optional[str] = None,
        cancel: str = 'cancel') -> str:
    """A modal question. buttons: (key, label, variant), left to right; Enter picks
    `default` (the first if not given), Escape `cancel`. Returns the key pressed."""
    d = Dialog(app, parent, title)
    tk.Label(d.content, text=message, font=app.font(10, False), bg=T["panel"], fg=T["text"],
             justify='left', anchor='w', wraplength=app.px(460)).pack(anchor='w')
    first = None
    for key, text, variant in buttons:
        b = d.button(text, lambda k=key: d.done(k), variant)
        if first is None or key == default:
            first = b
    d.bind('<Return>', lambda _e: d.done(default or buttons[0][0]))
    d.focus_first = lambda: first.label.focus_set() if first else None
    result = d.run()
    return result if result is not None else cancel


def ask_text(app, parent: tk.Misc, title: str, prompt: str, initial: str = '',
             select_stem: bool = True, validate: Optional[Callable[[str], Optional[str]]] = None,
             ok_label: str = 'OK', cancel_label: str = 'Cancel') -> Optional[str]:
    """A one-line text question; validate(text) returns an error to show, or None."""
    d = Dialog(app, parent, title)
    tk.Label(d.content, text=prompt, font=app.font(10, False), bg=T["panel"], fg=T["text"],
             anchor='w').pack(anchor='w', pady=(0, app.px(6)))
    e = entry(d.content, app.font(11, False), width=44)
    e.pack(fill='x', ipady=app.px(4))
    e.insert(0, initial)
    err = tk.Label(d.content, text='', font=app.font(9, False), bg=T["panel"], fg=T["pink"],
                   anchor='w')
    err.pack(anchor='w', pady=(app.px(4), 0))

    def ok(_e=None):
        text = e.get()
        problem = validate(text) if validate else None
        if problem:
            err.configure(text=problem)
            set_entry_error(e, True)
            app.glitch.now(d.head)
            return
        d.done(text)

    d.button(cancel_label, d.cancel)
    d.button(ok_label, ok, 'primary')
    e.bind('<Return>', ok)
    e.bind('<KeyRelease>', lambda _e: (err.configure(text=''), set_entry_error(e, False)))

    def focus():
        e.focus_set()
        e.icursor('end')
        e.selection_range(0, 'end')
        if select_stem and initial:
            from .ops import split_ext
            stem, _ext = split_ext(initial)
            e.selection_range(0, len(stem))
            e.icursor(len(stem))
    d.focus_first = focus
    return d.run()


class TabStrip(tk.Frame):
    """One row of tabs with a close cross; scrolls sideways when they don't fit."""

    def __init__(self, parent: tk.Misc, font, px, on_select: Callable[[object], None],
                 on_close: Callable[[object], None], on_menu: Callable[[object, tk.Event], None]):
        super().__init__(parent, bg=T["bg"])
        self.font, self.px = font, px
        self.on_select, self.on_close, self.on_menu = on_select, on_close, on_menu
        self.cells: Dict[object, Tuple[tk.Frame, tk.Label, tk.Label, tk.Frame]] = {}
        self.order: List[object] = []
        self.current: Optional[object] = None
        self.drop_target: Optional[object] = None

    def add(self, key: object, name: str) -> None:
        px = self.px
        cell = tk.Frame(self, bg=T["bg"])
        row = tk.Frame(cell, bg=T["bg"])
        row.pack(fill='x')
        text = tk.Label(row, text=name, font=self.font, bg=T["bg"], fg=T["muted"],
                        padx=px(10), pady=px(5), cursor='hand2')
        text.pack(side='left')
        close = tk.Label(row, text='×', font=self.font, bg=T["bg"], fg=T["dim"],
                         padx=px(4), pady=px(5), cursor='hand2')
        close.pack(side='left', padx=(0, px(4)))
        bar = tk.Frame(cell, height=max(2, px(2)), bg=T["bg"])
        bar.pack(fill='x')
        for w in (row, text):
            w.bind('<ButtonRelease-1>', lambda _e, k=key: self.on_select(k))
            w.bind('<ButtonRelease-2>', lambda _e, k=key: self.on_close(k))
            w.bind('<ButtonRelease-3>', lambda e, k=key: self.on_menu(k, e))
        close.bind('<ButtonRelease-1>', lambda _e, k=key: self.on_close(k))
        close.bind('<Enter>', lambda _e, c=close: c.configure(fg=T["pink"]))
        close.bind('<Leave>', lambda _e, c=close: c.configure(fg=T["dim"]))
        self.cells[key] = (cell, text, close, bar)
        self.order.append(key)
        self._layout()

    def _layout(self) -> None:
        for key in self.order:
            self.cells[key][0].pack_forget()
        for key in self.order:
            self.cells[key][0].pack(side='left', padx=(0, self.px(1)))
        self.paint()

    def rename(self, key: object, name: str) -> None:
        if key in self.cells:
            if len(name) > 28:
                name = name[:27] + '…'
            self.cells[key][1].configure(text=name)

    def remove(self, key: object) -> None:
        cell = self.cells.pop(key, None)
        if cell:
            self.order.remove(key)
            cell[0].destroy()

    def select(self, key: object) -> None:
        self.current = key
        self.paint()

    def paint(self) -> None:
        for key, (cell, text, close, bar) in self.cells.items():
            on = key == self.current
            drop = key == self.drop_target
            bg = T["panel"] if on else (T["hover"] if drop else T["bg"])
            for w in (cell, text, close, text.master):
                w.configure(bg=bg)
            text.configure(fg=T["text"] if on else T["muted"])
            bar.configure(bg=T["accent"] if on else (T["ch_b"] if drop else bg))

    def key_at(self, x_root: int, y_root: int) -> Optional[object]:
        for key, (cell, *_r) in self.cells.items():
            x0, y0 = cell.winfo_rootx(), cell.winfo_rooty()
            if x0 <= x_root < x0 + cell.winfo_width() and y0 <= y_root < y0 + cell.winfo_height():
                return key
        return None
