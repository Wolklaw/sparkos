"""Spark Monitor's own widgets, in the house style: the live graph, the tab bar, the table
look and the app icons. The shared ones are in widgets.py."""

import os
import zlib
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from .widgets import T, mix

PALETTE = {"cpu": T["accent"], "mem": "#b9a6ff", "gpu": T["pink"], "disk": T["gold"],
           "net": T["ch_b"]}


def nice_ceiling(value: float, base: float = 1000.0) -> float:
    """The next 1-2-5 step at or above value (bytes use base 1024 between the steps)."""
    if value <= 0:
        return 1.0
    step = 1.0
    while step * 10 <= value:
        step *= 10
    for m in (1, 2, 5, 10):
        if m * step >= value:
            return m * step
    return 10 * step


class Graph(tk.Canvas):
    """A line graph of the last N samples. The items are made once; each update only moves
    their coordinates. Hidden graphs skip the work and catch up when shown."""

    def __init__(self, parent: tk.Misc, colour: str, height: int, width: int = 120,
                 maximum: Optional[float] = 100.0, colour2: Optional[str] = None,
                 grid: bool = True, fill: bool = True, points: int = 60,
                 label: Optional[Callable[[float], str]] = None, font=None,
                 floor: float = 1.0):
        super().__init__(parent, height=height, width=width, bg=T["out_bg"],
                         highlightthickness=1, highlightbackground=mix(colour, T["bg"], 0.6),
                         bd=0)
        self.colour, self.colour2, self.maximum = colour, colour2, maximum
        self.points, self.grid_on, self.label, self.floor = points, grid, label, floor
        self.series: Sequence[Sequence[Optional[float]]] = ()
        self.top = maximum or floor
        self.grid_items: List[int] = []
        self.poly = self.create_polygon(0, 0, 0, 0, 0, 0, fill=mix(colour, T["out_bg"], 0.78),
                                        outline="") if fill else None
        self.lines = [self.create_line(0, 0, 0, 0, fill=colour, width=1.6)]
        if colour2:
            self.lines.append(self.create_line(0, 0, 0, 0, fill=colour2, width=1.4,
                                               dash=(4, 2)))
        self.text = self.create_text(0, 0, anchor="ne", text="", fill=T["muted"],
                                     font=font) if label else None
        self.bind("<Configure>", lambda _e: self._layout())
        self.bind("<Map>", lambda _e: self.redraw())

    def _layout(self):
        for item in self.grid_items:
            self.delete(item)
        self.grid_items = []
        if self.grid_on:
            w, h = self.winfo_width(), self.winfo_height()
            line = mix(self.colour, T["out_bg"], 0.86)
            for i in range(1, 10):
                x = w * i / 10
                self.grid_items.append(self.create_line(x, 0, x, h, fill=line))
            for i in range(1, 4):
                y = h * i / 4
                self.grid_items.append(self.create_line(0, y, w, y, fill=line))
            for item in self.grid_items:
                self.tag_lower(item)
        self.redraw(force=True)

    def set(self, *series: Sequence[Optional[float]]):
        self.series = series
        self.redraw()

    def redraw(self, force: bool = False):
        if not force and not self.winfo_viewable():
            return
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4:
            return
        if self.maximum is None:
            peak = max((v for s in self.series for v in s if v is not None), default=0.0)
            self.top = max(self.floor, nice_ceiling(peak * 1.05))
        else:
            self.top = self.maximum
        dx = (w - 1) / (self.points - 1)
        top, inner = self.top, h - 3
        poly_pts: List[float] = []
        for index, line in enumerate(self.lines):
            values = list(self.series[index])[-self.points:] if index < len(self.series) else []
            pts: List[float] = []
            x0 = w - 1 - (len(values) - 1) * dx
            for i, v in enumerate(values):
                v = 0.0 if v is None else min(top, max(0.0, v))
                pts.extend((x0 + i * dx, h - 2 - inner * v / top))
            if len(pts) < 4:
                pts = [-10, -10, -10, -10]
            self.coords(line, *pts)
            if index == 0:
                poly_pts = pts
        if self.poly is not None:
            if len(poly_pts) >= 4 and poly_pts[0] >= 0:
                self.coords(self.poly, *poly_pts, poly_pts[-2], h, poly_pts[0], h)
            else:
                self.coords(self.poly, -10, -10, -10, -10, -10, -10)
        if self.text is not None:
            text = self.label(self.top)
            if self.itemcget(self.text, "text") != text:
                self.itemconfigure(self.text, text=text)
            self.coords(self.text, w - 4, 3)


class TabBar(tk.Frame):
    """Uppercase mono tabs; the open one is lit with an accent bar under it."""

    def __init__(self, parent: tk.Misc, tabs: Sequence[Tuple[str, str]],
                 command: Callable[[str], None], font, px: Callable[[float], int]):
        super().__init__(parent, bg=T["bg"])
        self.command, self.current = command, None
        self.labels: Dict[str, Tuple[tk.Label, tk.Frame]] = {}
        for i, (key, text) in enumerate(tabs):
            cell = tk.Frame(self, bg=T["bg"])
            cell.pack(side="left", padx=(0 if i == 0 else px(2), 0))
            label = tk.Label(cell, text=text.upper(), font=font, bg=T["bg"], fg=T["muted"],
                             padx=px(12), pady=px(6), cursor="hand2")
            label.pack()
            bar = tk.Frame(cell, height=max(2, px(2)), bg=T["bg"])
            bar.pack(fill="x")
            label.bind("<ButtonRelease-1>", lambda _e, k=key: self.command(k))
            label.bind("<Enter>", lambda _e, k=key: self._hover(k, True))
            label.bind("<Leave>", lambda _e, k=key: self._hover(k, False))
            self.labels[key] = (label, bar)

    def _hover(self, key: str, on: bool):
        if key != self.current:
            self.labels[key][0].config(bg=T["hover"] if on else T["bg"],
                                       fg=T["text"] if on else T["muted"])

    def select(self, key: str):
        self.current = key
        for k, (label, bar) in self.labels.items():
            on = k == key
            label.config(fg=T["accent"] if on else T["muted"], bg=T["bg"])
            bar.config(bg=T["accent"] if on else T["bg"])


def style_tables(root: tk.Misc, font, heading_font, row_height: int) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use('clam')
    except tk.TclError:
        pass
    style.configure("Spark.Treeview", background=T["panel"], fieldbackground=T["panel"],
                    foreground=T["text"], bordercolor=T["line"], lightcolor=T["panel"],
                    darkcolor=T["panel"], rowheight=row_height, font=font, borderwidth=0)
    style.map("Spark.Treeview", background=[("selected", T["hover"])],
              foreground=[("selected", T["accent"])])
    style.configure("Spark.Treeview.Heading", background=T["panel2"], foreground=T["muted"],
                    bordercolor=T["line"], lightcolor=T["panel2"], darkcolor=T["panel2"],
                    font=heading_font, relief="flat", padding=(6, 4))
    style.map("Spark.Treeview.Heading", background=[("active", T["hover"])],
              foreground=[("active", T["text"])])
    style.layout("Spark.Treeview", [("Spark.Treeview.treearea", {"sticky": "nswe"})])
    style.configure("Spark.Vertical.TScrollbar", background=T["panel2"], troughcolor=T["bg"],
                    bordercolor=T["bg"], arrowcolor=T["muted"], lightcolor=T["panel2"],
                    darkcolor=T["panel2"], gripcount=0)
    style.map("Spark.Vertical.TScrollbar", background=[("active", T["line2"])])


def heading_width(tree: ttk.Treeview, title: str) -> int:
    """Pixels a column needs to show `title` (and a sort arrow) in full, in any language."""
    try:
        name = ttk.Style(tree).lookup("Spark.Treeview.Heading", "font")
        font = tkfont.Font(root=tree, font=name) if name else tkfont.nametofont("TkHeadingFont")
    except tk.TclError:
        font = tkfont.nametofont("TkHeadingFont")
    return font.measure(title + " ▼") + 14          # the heading's padding, and a little air


def make_table(parent: tk.Misc, columns: Sequence[str], show: str = "tree headings"):
    """A styled Treeview in a frame, with a scrollbar. Returns (frame, tree)."""
    frame = tk.Frame(parent, bg=T["line"], padx=1, pady=1)
    tree = ttk.Treeview(frame, columns=columns, style="Spark.Treeview", show=show,
                        selectmode="browse")
    bar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview,
                        style="Spark.Vertical.TScrollbar")
    tree.configure(yscrollcommand=bar.set)
    bar.pack(side="right", fill="y")
    tree.pack(side="left", fill="both", expand=True)
    tree.tag_configure("section", foreground=T["muted"], background=T["panel2"])
    tree.tag_configure("system", foreground=T["muted"])
    tree.tag_configure("busy", foreground=T["gold"])
    tree.tag_configure("off", foreground=T["dim"])
    return frame, tree


class Icons:
    """App icons for the table, loaded after the window is up, one per idle moment.
    Apps without a PNG icon get a small tile in a colour from their name."""

    def __init__(self, root: tk.Misc, size: int, finder: Callable[[Optional[str]], Optional[str]]):
        self.root, self.size, self.finder = root, size, finder
        self.images: Dict[str, tk.PhotoImage] = {}
        self.queue: List[str] = []
        self.pending = False
        self.changed = False

    def get(self, name: Optional[str], key: str) -> tk.PhotoImage:
        token = f"icon:{name}" if name else f"tile:{key}"
        if token in self.images:
            return self.images[token]
        if name and token not in self.queue:
            self.queue.append(token)
            if not self.pending:
                self.pending = True
                self.root.after_idle(self._load_next)
        return self._tile(key if not name else name)

    def _tile(self, key: str) -> tk.PhotoImage:
        token = f"tile:{key}"
        if token not in self.images:
            colours = (T["accent"], T["pink"], T["gold"], "#b9a6ff", T["ch_b"])
            colour = colours[zlib.crc32(key.encode()) % len(colours)]
            s = self.size
            img = tk.PhotoImage(master=self.root, width=s, height=s)
            pad = max(1, s // 8)
            img.put(mix(colour, T["panel"], 0.65), to=(pad, pad, s - pad, s - pad))
            inner = max(pad + 1, s // 3)
            img.put(colour, to=(inner, inner, s - inner, s - inner))
            self.images[token] = img
        return self.images[token]

    def _load_next(self):
        self.pending = False
        if not self.queue:
            return
        token = self.queue.pop(0)
        path = self.finder(token[5:])
        img = self._load(path) if path else None
        if img is not None:
            self.images[token] = img
            self.changed = True
        else:
            self.images[token] = self._tile(token[5:])
        if self.queue:
            self.pending = True
            self.root.after(15, self._load_next)

    def _load(self, path: str) -> Optional[tk.PhotoImage]:
        s = self.size
        try:
            from PIL import Image, ImageTk
            with Image.open(path) as im:
                im = im.convert("RGBA").resize((s, s), Image.Resampling.LANCZOS)
                return ImageTk.PhotoImage(im, master=self.root)
        except Exception:     # noqa: BLE001 - Pillow missing, or a broken file
            pass
        try:
            img = tk.PhotoImage(master=self.root, file=path)
        except tk.TclError:
            return None
        factor = max(1, round(img.width() / s))
        return img.subsample(factor) if factor > 1 else img


def scrollable(parent: tk.Misc, bg: str) -> Tuple[tk.Frame, tk.Frame]:
    """A frame whose content scrolls vertically. Returns (outer, inner)."""
    outer = tk.Frame(parent, bg=bg)
    canvas = tk.Canvas(outer, bg=bg, highlightthickness=0, bd=0)
    bar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview,
                        style="Spark.Vertical.TScrollbar")
    inner = tk.Frame(canvas, bg=bg)
    window = canvas.create_window(0, 0, anchor="nw", window=inner)
    canvas.configure(yscrollcommand=bar.set)

    def fit(_e=None):
        canvas.configure(scrollregion=canvas.bbox("all"))
        need = inner.winfo_reqheight() > canvas.winfo_height()
        if need and not bar.winfo_ismapped():
            bar.pack(side="right", fill="y")
        elif not need and bar.winfo_ismapped():
            bar.pack_forget()

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
                       else None, add="+")
    canvas.pack(side="left", fill="both", expand=True)
    return outer, inner


def is_linux() -> bool:
    return os.name == 'posix'
