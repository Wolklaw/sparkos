"""Spark Store's own widgets, in the house style: the tab bar, the search box, app cards and
rows, chips, the progress bar, scrolling pages and the icon loader. The shared ones (T,
Glitch, GlitchText, WolkButton...) are in widgets.py, copied from Spark Media."""

import zlib
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import tkinter as tk
from tkinter import ttk

from .widgets import T, mix


def style(root: tk.Misc) -> None:
    s = ttk.Style(root)
    try:
        s.theme_use('clam')
    except tk.TclError:
        pass
    s.configure("Spark.Vertical.TScrollbar", background=T["panel2"], troughcolor=T["bg"],
                bordercolor=T["bg"], arrowcolor=T["muted"], lightcolor=T["panel2"],
                darkcolor=T["panel2"], gripcount=0)
    s.map("Spark.Vertical.TScrollbar", background=[("active", T["line2"])])


def bind_tree(widget: tk.Misc, seq: str, fn) -> None:
    """Bind on a widget and everything inside it (Tk events don't bubble up)."""
    widget.bind(seq, fn, add="+")
    for child in widget.winfo_children():
        bind_tree(child, seq, fn)


class TabBar(tk.Frame):
    """Uppercase mono tabs; the open one is lit with an accent bar under it."""

    def __init__(self, parent: tk.Misc, tabs: Sequence[Tuple[str, str]],
                 command: Callable[[str], None], font, px: Callable[[float], int]):
        super().__init__(parent, bg=T["bg"])
        self.command, self.current = command, None
        self.texts = dict(tabs)
        self.labels: Dict[str, Tuple[tk.Label, tk.Frame]] = {}
        for i, (key, text) in enumerate(tabs):
            cell = tk.Frame(self, bg=T["bg"])
            cell.pack(side="left", padx=(0 if i == 0 else px(2), 0))
            label = tk.Label(cell, text=text.upper(), font=font, bg=T["bg"], fg=T["muted"],
                             padx=px(12), pady=px(6), cursor="hand2", takefocus=1)
            label.pack()
            bar = tk.Frame(cell, height=max(2, px(2)), bg=T["bg"])
            bar.pack(fill="x")
            label.bind("<ButtonRelease-1>", lambda _e, k=key: self.command(k))
            label.bind("<Return>", lambda _e, k=key: self.command(k))
            label.bind("<Enter>", lambda _e, k=key: self._hover(k, True))
            label.bind("<Leave>", lambda _e, k=key: self._hover(k, False))
            self.labels[key] = (label, bar)

    def _hover(self, key: str, on: bool):
        if key != self.current:
            self.labels[key][0].config(bg=T["hover"] if on else T["bg"],
                                       fg=T["text"] if on else T["muted"])

    def select(self, key: Optional[str]):
        self.current = key
        for k, (label, bar) in self.labels.items():
            on = k == key
            label.config(fg=T["accent"] if on else T["muted"], bg=T["bg"])
            bar.config(bg=T["accent"] if on else T["bg"])

    def set_count(self, key: str, count: int):
        text = self.texts[key].upper() + (f" {count}" if count else "")
        label = self.labels[key][0]
        if label.cget("text") != text:
            label.config(text=text)


class SearchBox(tk.Frame):
    """A flat search field with a placeholder; on_change fires as you type (debounced)."""

    def __init__(self, parent: tk.Misc, placeholder: str, font, px, width: int,
                 on_change: Callable[[str], None], on_enter: Callable[[], None]):
        super().__init__(parent, bg=T["line2"], padx=1, pady=1)
        self.placeholder, self.on_change, self.on_enter = placeholder, on_change, on_enter
        self.var = tk.StringVar(self)
        inner = tk.Frame(self, bg=T["panel"])
        inner.pack(fill="both", expand=True)
        self.lens = tk.Canvas(inner, width=px(18), height=px(18), bg=T["panel"],
                              highlightthickness=0)
        self.lens.pack(side="left", padx=(px(8), 0))
        k = px(18) / 18
        self.lens.create_oval(3 * k, 3 * k, 12 * k, 12 * k, outline=T["muted"],
                              width=max(1, k * 1.6))
        self.lens.create_line(11 * k, 11 * k, 16 * k, 16 * k, fill=T["muted"],
                              width=max(1, k * 1.8))
        self.entry = tk.Entry(inner, textvariable=self.var, font=font, width=width,
                              bg=T["panel"], fg=T["text"], insertbackground=T["accent"],
                              relief="flat", highlightthickness=0, bd=0,
                              selectbackground=T["line2"], selectforeground=T["text"])
        self.entry.pack(side="left", fill="x", expand=True, padx=(px(6), px(8)), pady=px(6))
        self.hint = tk.Label(inner, text=placeholder, font=font, bg=T["panel"], fg=T["dim"],
                             anchor="w", cursor="xterm")
        self.hint.place(in_=self.entry, x=0, rely=0.5, anchor="w")
        self.hint.bind("<Button-1>", lambda _e: self.entry.focus_set())
        self._job: Optional[str] = None
        self.var.trace_add("write", self._changed)
        self.entry.bind("<Return>", lambda _e: self.on_enter())
        self.entry.bind("<FocusIn>", lambda _e: self.config(bg=T["accent"]))
        self.entry.bind("<FocusOut>", lambda _e: self.config(bg=T["line2"]))

    def _changed(self, *_a):
        text = self.var.get()
        if text:
            self.hint.place_forget()
        else:
            self.hint.place(in_=self.entry, x=0, rely=0.5, anchor="w")
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(90, self._fire)

    def _fire(self):
        self._job = None
        self.on_change(self.var.get())

    def get(self) -> str:
        return self.var.get()

    def set(self, text: str, fire: bool = True):
        self.var.set(text)
        if not fire and self._job:
            self.after_cancel(self._job)
            self._job = None


def chip(parent: tk.Misc, text: str, font, colour: str = "", filled: bool = False,
         px: Callable[[float], int] = lambda v: int(v)) -> tk.Label:
    colour = colour or T["muted"]
    if filled:
        return tk.Label(parent, text=text.upper(), font=font, bg=colour, fg=T["on_accent"],
                        padx=px(5), pady=0)
    return tk.Label(parent, text=text.upper(), font=font, bg=parent.cget("bg"), fg=colour,
                    padx=px(5), pady=0, highlightthickness=1,
                    highlightbackground=mix(colour, T["bg"], 0.45))


class Progress(tk.Canvas):
    """A thin bar: the done part in the accent; with no figure, a block that slides."""

    def __init__(self, parent: tk.Misc, height: int, width: int = 120):
        super().__init__(parent, height=height, width=width, bg=T["out_bg"],
                         highlightthickness=1, highlightbackground=T["line"], bd=0)
        self.value: Optional[float] = None
        self.phase = 0
        self._job: Optional[str] = None
        self.bind("<Configure>", lambda _e: self.draw())

    def set(self, value: Optional[float]):
        self.value = value
        self.draw()
        if value is None and self._job is None and self.winfo_exists():
            self._job = self.after(60, self._spin)
        elif value is not None and self._job is not None:
            self.after_cancel(self._job)
            self._job = None

    def _spin(self):
        self._job = None
        if self.value is not None or not self.winfo_exists():
            return
        if self.winfo_viewable():
            self.phase = (self.phase + 6) % 1000
            self.draw()
        self._job = self.after(60, self._spin)

    def stop(self):
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        if self.value is None:
            block = max(8, w // 5)
            x = (self.phase * w // 400) % (w + block) - block
            self.create_rectangle(x, 0, x + block, h, fill=T["accent"], width=0)
        else:
            self.create_rectangle(0, 0, int(w * max(0.0, min(1.0, self.value))), h,
                                  fill=T["accent"], width=0)


class Card(tk.Frame):
    """A panel with a 1px edge that splits into the two channels on hover; click opens."""

    def __init__(self, parent: tk.Misc, bg: str = T["panel"],
                 command: Optional[Callable[[], None]] = None):
        self.pbg = parent.cget("bg")
        super().__init__(parent, bg=self.pbg)
        self.command = command
        self.lbar = tk.Frame(self, bg=self.pbg, width=2)
        self.rbar = tk.Frame(self, bg=self.pbg, width=2)
        self.lbar.pack(side="left", fill="y")
        self.rbar.pack(side="right", fill="y")
        self.edge = tk.Frame(self, bg=T["line"], padx=1, pady=1)
        self.edge.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.edge, bg=bg, cursor="hand2" if command else "")
        self.inner.pack(fill="both", expand=True)
        self.running = False

    def wire(self):
        """Call after filling .inner: hover and click on every part of the card."""
        bind_tree(self, "<Enter>", self._enter)
        bind_tree(self, "<Leave>", self._leave)
        if self.command:
            bind_tree(self, "<ButtonRelease-1>", self._click)

    def _enter(self, _e=None):
        self.lbar.config(bg=T["ch_a"])
        self.rbar.config(bg=T["ch_b"])
        self.edge.config(bg=T["accent"])

    def _leave(self, event=None):
        if event is not None:
            under = self.winfo_containing(event.x_root, event.y_root)
            if under is not None and str(under).startswith(str(self)):
                return
        self.lbar.config(bg=self.pbg)
        self.rbar.config(bg=self.pbg)
        self.edge.config(bg=T["line"])

    def _click(self, event):
        under = self.winfo_containing(event.x_root, event.y_root)
        if under is None or not str(under).startswith(str(self)):
            return
        if getattr(event.widget, '_own_click', False):
            return
        if self.command:
            self.command()

    def burst(self, strong: bool = False):
        import random
        if self.running or not self.winfo_exists():
            return
        self.running = True
        count = 8 if strong else 5

        def step(i=0):
            if not self.winfo_exists():
                return
            if i < count:
                self.lbar.config(bg=random.choice([T["ch_a"], self.pbg, T["ch_a"]]))
                self.rbar.config(bg=random.choice([T["ch_b"], self.pbg, T["ch_b"]]))
                self.edge.config(bg=random.choice([T["ch_a"], T["ch_b"], T["line2"]]))
                self.after(45, lambda: step(i + 1))
            else:
                self._leave()
                self.running = False

        step()


class Icons:
    """App icons, loaded after the page is up, one per idle moment, and kept. Apps without
    an icon file get a small tile in a colour from their name."""

    def __init__(self, root: tk.Misc):
        self.root = root
        self.images: Dict[Tuple[str, int], tk.PhotoImage] = {}
        self.queue: List[Tuple[str, int, Optional[str], tk.Label]] = []
        self.pending = False
        try:
            from PIL import ImageTk
            self.pil = ImageTk is not None
        except ImportError:
            self.pil = False

    def put(self, label: tk.Label, key: str, path: Optional[str], size: int) -> None:
        """Show the icon for key on label: now if loaded, else a tile until it is."""
        token = (path or f"tile:{key}", size)
        if token in self.images:
            label.config(image=self.images[token])
            return
        label.config(image=self.tile(key, size))
        if path:
            self.queue.append((path, size, key, label))
            if not self.pending:
                self.pending = True
                self.root.after_idle(self._next)

    def tile(self, key: str, size: int) -> tk.PhotoImage:
        token = (f"tile:{key}", size)
        if token not in self.images:
            colours = (T["accent"], T["pink"], T["gold"], "#b9a6ff", T["ch_b"])
            colour = colours[zlib.crc32(key.encode()) % len(colours)]
            s = size
            img = tk.PhotoImage(master=self.root, width=s, height=s)
            pad = max(1, s // 8)
            img.put(mix(colour, T["panel"], 0.75), to=(pad, pad, s - pad, s - pad))
            inner = max(pad + 1, s // 3)
            img.put(mix(colour, T["panel"], 0.25), to=(inner, inner, s - inner, s - inner))
            self.images[token] = img
        return self.images[token]

    def _next(self):
        self.pending = False
        for _ in range(4):                   # a few per idle moment
            if not self.queue:
                return
            path, size, key, label = self.queue.pop(0)
            token = (path, size)
            if token not in self.images:
                img = self.load(path, size)
                self.images[token] = img if img is not None else self.tile(key or path, size)
            try:
                if label.winfo_exists():
                    label.config(image=self.images[token])
            except tk.TclError:
                pass
        if self.queue:
            self.pending = True
            self.root.after(10, self._next)

    def load(self, path: str, size: int, fit_width: Optional[int] = None
             ) -> Optional[tk.PhotoImage]:
        """A picture as a PhotoImage: size x size, or fit_width wide keeping its shape."""
        if self.pil:
            try:
                from PIL import Image, ImageTk
                with Image.open(path) as im:
                    im = im.convert("RGBA")
                    if fit_width:
                        w = min(fit_width, im.width)
                        h = max(1, round(im.height * w / im.width))
                        im = im.resize((w, h), Image.Resampling.LANCZOS)
                    else:
                        im = im.resize((size, size), Image.Resampling.LANCZOS)
                    return ImageTk.PhotoImage(im, master=self.root)
            except Exception:     # noqa: BLE001 - a broken file, or a format Pillow lacks
                pass
        try:
            img = tk.PhotoImage(master=self.root, file=path)
        except tk.TclError:
            return None
        target = fit_width or size
        factor = max(1, -(-img.width() // max(1, target)))
        if factor > 1:
            img = img.subsample(factor)
        elif not fit_width and img.width() * 2 <= size:
            img = img.zoom(max(1, size // max(1, img.width())))
        return img


def scrollable(parent: tk.Misc, bg: str, px) -> Tuple[tk.Frame, tk.Frame, tk.Canvas]:
    """A frame whose content scrolls vertically. Returns (outer, inner, canvas)."""
    outer = tk.Frame(parent, bg=bg)
    canvas = tk.Canvas(outer, bg=bg, highlightthickness=0, bd=0, yscrollincrement=px(24))
    bar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview,
                        style="Spark.Vertical.TScrollbar")
    inner = tk.Frame(canvas, bg=bg)
    window = canvas.create_window(0, 0, anchor="nw", window=inner)
    canvas.configure(yscrollcommand=bar.set)

    def fit(_e=None):
        canvas.configure(scrollregion=(0, 0, inner.winfo_reqwidth(), inner.winfo_reqheight()))
        need = inner.winfo_reqheight() > canvas.winfo_height()
        if need and not bar.winfo_ismapped():
            bar.pack(side="right", fill="y", before=canvas)
        elif not need and bar.winfo_ismapped():
            bar.pack_forget()
            canvas.yview_moveto(0)

    inner.bind("<Configure>", fit)
    canvas.bind("<Configure>", lambda e: (canvas.itemconfigure(window, width=e.width), fit()))

    def wheel(event):
        if inner.winfo_reqheight() <= canvas.winfo_height():
            return
        if getattr(event, 'num', 0) == 4 or getattr(event, 'delta', 0) > 0:
            canvas.yview_scroll(-2, "units")
        else:
            canvas.yview_scroll(2, "units")

    for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        outer.bind_all(seq, lambda e: wheel(e) if str(e.widget).startswith(str(outer))
                       and outer.winfo_ismapped() else None, add="+")
    canvas.pack(side="left", fill="both", expand=True)
    return outer, inner, canvas
