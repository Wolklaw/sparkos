"""Pieces of interface in the house style, built on widgets.py: a drop-down, a slider, rows,
a text field, and the little dialog frame."""

from typing import Callable, List, Optional, Sequence, Tuple

import tkinter as tk

from .widgets import T, WolkButton


def menu(root: tk.Misc, font) -> tk.Menu:
    return tk.Menu(root, tearoff=0, bg=T["panel"], fg=T["text"], activebackground=T["hover"],
                   activeforeground=T["accent"], disabledforeground=T["dim"], bd=1,
                   relief='flat', font=font, activeborderwidth=0)


def entry(parent: tk.Misc, font, width: int = 30, show: str = '') -> tk.Entry:
    return tk.Entry(parent, font=font, width=width, show=show, bg=T["out_bg"], fg=T["text"],
                    insertbackground=T["accent"], selectbackground=T["line2"],
                    selectforeground=T["text"], relief='flat', bd=0, highlightthickness=1,
                    highlightbackground=T["line"], highlightcolor=T["accent"])


class Choice(tk.Frame):
    """A drop-down: the current choice in a sharp box; click opens the list."""

    def __init__(self, parent: tk.Misc, options: Sequence[Tuple[str, str]], value: str,
                 command: Callable[[str], None], font, width: int = 28, bg: str = T["panel"]):
        super().__init__(parent, bg=T["line2"], padx=1, pady=1)
        self.options, self.value, self.command, self.font = list(options), value, command, font
        self.label = tk.Label(self, font=font, bg=T["panel2"], fg=T["text"], anchor='w',
                              padx=8, pady=4, width=width, cursor='hand2', takefocus=1)
        self.label.pack(fill='x')
        for seq in ('<ButtonRelease-1>', '<Return>', '<space>', '<Down>'):
            self.label.bind(seq, self.open)
        self.label.bind('<Enter>', lambda _e: self.config(bg=T["accent"]))
        self.label.bind('<Leave>', lambda _e: self.config(bg=T["line2"]))
        self.paint()

    def paint(self):
        text = next((t for t, v in self.options if v == self.value), self.value or '')
        self.label.config(text=f"{text}  ▾")

    def open(self, _e=None):
        m = menu(self, self.font)
        for text, val in self.options:
            m.add_command(label=text, command=lambda v=val: self.set(v, fire=True))
        m.tk_popup(self.winfo_rootx(), self.winfo_rooty() + self.winfo_height())

    def set(self, value: str, fire: bool = False):
        self.value = value
        self.paint()
        if fire:
            self.command(value)

    def set_options(self, options: Sequence[Tuple[str, str]], value: str):
        self.options = list(options)
        self.set(value)


class Slider(tk.Scale):
    """A flat horizontal slider; the command fires when the knob is let go (and on a click)."""

    def __init__(self, parent: tk.Misc, command: Callable[[float], None], low: float = 0,
                 high: float = 100, length: int = 260, bg: str = T["panel"]):
        super().__init__(parent, from_=low, to=high, orient='horizontal', showvalue=False,
                         length=length, bg=bg, troughcolor=T["out_bg"], highlightthickness=0,
                         bd=0, sliderrelief='flat', activebackground=T["accent_hov"],
                         width=12, sliderlength=14, takefocus=1)
        self.configure(fg=T["text"])
        self._cmd = command
        self.bind('<ButtonRelease-1>', lambda _e: command(float(self.get())))
        self.bind('<KeyRelease-Left>', lambda _e: command(float(self.get())))
        self.bind('<KeyRelease-Right>', lambda _e: command(float(self.get())))
        self.config(troughcolor=T["out_bg"])

    def put(self, value: float):
        self.set(value)


def label(parent: tk.Misc, text: str, font, fg: str = T["text"], bg: str = T["panel"],
          **kw) -> tk.Label:
    return tk.Label(parent, text=text, font=font, fg=fg, bg=bg, anchor='w', justify='left', **kw)


def rule(parent: tk.Misc, colour: str = T["line"]) -> tk.Frame:
    return tk.Frame(parent, bg=colour, height=1)


class Dialog(tk.Toplevel):
    """A small window in the house look with a message, an optional field and two buttons."""

    def __init__(self, app, title: str, message: str, ok: str, cancel: str = '',
                 field: Optional[str] = None, secret: bool = False,
                 on_ok: Optional[Callable[[str], None]] = None):
        super().__init__(app.root, bg=T["line2"], padx=1, pady=1)
        self.title(title)
        self.on_ok = on_ok
        self.transient(app.root)
        body = tk.Frame(self, bg=T["panel"], padx=18, pady=14)
        body.pack()
        label(body, title.upper(), app.font(9), fg=T["muted"]).pack(anchor='w')
        label(body, message, app.font(10), wraplength=380).pack(anchor='w', pady=(6, 8))
        self.entry = None
        if field is not None:
            self.entry = entry(body, app.font(10), 36, show='•' if secret else '')
            self.entry.insert(0, field)
            self.entry.pack(fill='x', pady=(0, 10))
            self.entry.focus_set()
            self.entry.bind('<Return>', lambda _e: self.accept())
        row = tk.Frame(body, bg=T["panel"])
        row.pack(anchor='e')
        if cancel:
            WolkButton(row, cancel, self.destroy, app.font(9), 'ghost').pack(side='left', padx=4)
        WolkButton(row, ok, self.accept, app.font(9), 'primary').pack(side='left', padx=4)
        self.bind('<Escape>', lambda _e: self.destroy())
        self.update_idletasks()
        x = app.root.winfo_rootx() + (app.root.winfo_width() - self.winfo_reqwidth()) // 2
        y = app.root.winfo_rooty() + (app.root.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def accept(self):
        value = self.entry.get() if self.entry is not None else ''
        self.destroy()
        if self.on_ok:
            self.on_ok(value)
