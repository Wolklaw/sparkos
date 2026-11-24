"""Spark Audio's own widgets: the mark, tabs, sliders, level meter, dropdown and a scrolling
frame. The shared look (palette, glitch, buttons) is in widgets.py."""

import random
import tkinter as tk
from typing import Any, Callable, List, Optional, Tuple

from .widgets import T


class Mark(tk.Canvas):
    """Spark Audio's mark: three level bars split into channels. Same 32-unit geometry as
    make_icons.py."""

    BARS = ((9.0, 12.0, 15.0), (14.5, 17.5, 8.0), (20.0, 23.0, 12.0))   # x0, x1, height

    def __init__(self, parent: tk.Misc, size: int, bg: str):
        super().__init__(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0)
        self.size = size
        self.running = False
        self.bind("<Enter>", lambda _e: self.micro())
        self.draw()

    def draw(self, a=(-1.0, 0.0), b=(1.0, 0.0), c=(0.0, 0.0), bars=()):
        self.delete("all")
        s = self.size
        k = s / 32

        def shape(offset, colour):
            ox, oy = offset[0] * k, offset[1] * k
            for x0, x1, h in self.BARS:
                self.create_rectangle(x0 * k + ox, (24 - h) * k + oy, x1 * k + ox, 24 * k + oy,
                                      fill=colour, outline=colour)

        self.create_rectangle(0, 0, s - 1, s - 1, fill=T["tile"], outline=T["line2"])
        shape(a, T["ch_a"])
        shape(b, T["ch_b"])
        shape(c, T["accent"])
        for y0, h, colour in bars:
            self.create_rectangle(1, y0, s - 1, y0 + h, fill=colour, stipple="gray50", width=0)

    def micro(self):
        if not self.running:
            self.draw(a=(-2.6, 0.4), b=(2.6, -0.4))
            self.after(130, lambda: None if self.running or not self.winfo_exists() else self.draw())

    def burst(self, strong: bool = False):
        if self.running:
            return
        self.running = True
        frames = [((random.uniform(-5, -2), random.uniform(-1, 1)),
                   (random.uniform(2, 5), random.uniform(-1, 1)),
                   (random.uniform(-1.2, 1.2), 0.0),
                   [(random.randint(2, max(3, self.size - 4)), random.randint(1, 3),
                     random.choice([T["ch_a"], T["ch_b"]])) for _ in range(random.randint(1, 3))])
                  for _ in range(8 if strong else 6)]

        def step(i=0):
            if not self.winfo_exists():
                return
            if i < len(frames):
                self.draw(*frames[i])
                self.after(48, lambda: step(i + 1))
            else:
                self.draw()
                self.running = False

        step()


class TabBar(tk.Frame):
    """Uppercase mono tabs; the open one is lit with an accent bar under it."""

    def __init__(self, parent: tk.Misc, tabs, command: Callable[[str], None], font,
                 px: Callable[[float], int]):
        super().__init__(parent, bg=T["bg"])
        self.command, self.current, self.font, self.px = command, None, font, px
        self.labels = {}
        self.set_tabs(tabs)

    def set_tabs(self, tabs) -> None:
        for child in self.winfo_children():
            child.destroy()
        self.labels = {}
        px = self.px
        for i, (key, text) in enumerate(tabs):
            cell = tk.Frame(self, bg=T["bg"])
            cell.pack(side="left", padx=(0 if i == 0 else px(2), 0))
            label = tk.Label(cell, text=text.upper(), font=self.font, bg=T["bg"], fg=T["muted"],
                             padx=px(12), pady=px(6), cursor="hand2", takefocus=1)
            label.pack()
            bar = tk.Frame(cell, height=max(2, px(2)), bg=T["bg"])
            bar.pack(fill="x")
            for seq in ("<ButtonRelease-1>", "<Return>", "<space>"):
                label.bind(seq, lambda _e, k=key: self.command(k))
            label.bind("<Enter>", lambda _e, k=key: self._hover(k, True))
            label.bind("<Leave>", lambda _e, k=key: self._hover(k, False))
            self.labels[key] = (label, bar)
        if self.current in self.labels:
            self.select(self.current)

    def _hover(self, key: str, on: bool):
        if key != self.current and key in self.labels:
            self.labels[key][0].config(bg=T["hover"] if on else T["bg"],
                                       fg=T["text"] if on else T["muted"])

    def select(self, key: str):
        self.current = key
        for k, (label, bar) in self.labels.items():
            on = k == key
            label.config(fg=T["accent"] if on else T["muted"], bg=T["bg"])
            bar.config(bg=T["accent"] if on else T["bg"])


class Chip(tk.Label):
    """A small outlined label: DEFAULT, EQ, MUTED."""

    def __init__(self, parent: tk.Misc, text: str, font, colour: str = T["accent"]):
        super().__init__(parent, text=text.upper(), font=font, fg=colour, bg=parent.cget("bg"),
                         padx=6, pady=1, highlightthickness=1, highlightbackground=colour)


class Slider(tk.Canvas):
    """A horizontal slider. Click or drag, arrow keys (Shift for big steps) and the wheel work.
    command(value) fires only for changes the person makes; set() never fires it."""

    def __init__(self, parent: tk.Misc, command: Callable[[float], None], height: int = 26,
                 lo: float = 0.0, hi: float = 1.0, step: float = 0.01, center: bool = False):
        super().__init__(parent, height=height, bg=parent.cget("bg"), highlightthickness=0, bd=0,
                         takefocus=1, cursor="hand2")
        self.command, self.lo, self.hi, self.step = command, lo, hi, step
        self.center, self.value, self.muted = center, lo, False
        self.dragging, self.hover, self.enabled = False, False, True
        self.bind("<Configure>", lambda _e: self.draw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)
        for seq, on in (("<Enter>", True), ("<Leave>", False), ("<FocusIn>", True), ("<FocusOut>", False)):
            self.bind(seq, lambda _e, on=on: self._hovered(on))
        for name, d in (("Left", -1), ("Down", -1), ("Right", 1), ("Up", 1)):
            self.bind(f"<{name}>", lambda _e, d=d: self._nudge(d * self.step))
            self.bind(f"<Shift-{name}>", lambda _e, d=d: self._nudge(d * self.step * 10))
        self.bind("<Home>", lambda _e: self._set_user(self.lo))
        self.bind("<End>", lambda _e: self._set_user(self.hi))
        self.bind("<MouseWheel>", lambda e: self._nudge(self.step * 2 * (1 if e.delta > 0 else -1)))
        self.bind("<Button-4>", lambda _e: self._nudge(self.step * 2))
        self.bind("<Button-5>", lambda _e: self._nudge(-self.step * 2))

    def _hovered(self, on: bool):
        self.hover = on and self.enabled
        self.draw()

    def _x(self, value: float) -> float:
        w = max(1, self.winfo_width() - 12)
        return 6 + w * (value - self.lo) / (self.hi - self.lo)

    def _value_at(self, x: float) -> float:
        w = max(1, self.winfo_width() - 12)
        v = max(self.lo, min(self.hi, self.lo + (x - 6) / w * (self.hi - self.lo)))
        return round(v / self.step) * self.step if self.step else v

    def set(self, value: float, muted: Optional[bool] = None):
        changed = False
        if muted is not None and muted != self.muted:
            self.muted, changed = muted, True
        value = max(self.lo, min(self.hi, value))
        if not self.dragging and abs(value - self.value) > 1e-9:
            self.value, changed = value, True
        if changed:
            self.draw()

    def set_enabled(self, on: bool):
        self.enabled = on
        self.configure(cursor="hand2" if on else "arrow", takefocus=1 if on else 0)
        self.draw()

    def _set_user(self, value: float):
        if not self.enabled:
            return
        value = max(self.lo, min(self.hi, value))
        if abs(value - self.value) > 1e-9:
            self.value = value
            self.draw()
            self.command(value)

    def _nudge(self, delta: float):
        self._set_user(round((self.value + delta) / self.step) * self.step)

    def _press(self, e):
        if self.enabled:
            self.focus_set()
            self.dragging = True
            self._set_user(self._value_at(e.x))

    def _drag(self, e):
        if self.dragging:
            self._set_user(self._value_at(e.x))

    def _release(self, _e):
        self.dragging = False
        self.draw()

    def draw(self):
        self.delete("all")
        w, h = self.winfo_width(), int(self.cget("height"))
        if w < 20:
            return
        mid = h // 2
        x = self._x(self.value)
        fill = T["dim"] if (self.muted or not self.enabled) else T["accent"]
        self.create_rectangle(6, mid - 2, w - 6, mid + 2, fill=T["panel2"],
                              outline=T["line2"] if self.enabled else T["line"])
        if self.center:
            zero = self._x(0)
            self.create_rectangle(min(zero, x), mid - 1, max(zero, x), mid + 2, fill=fill, width=0)
            self.create_line(zero, mid - 7, zero, mid + 7, fill=T["muted"])
        else:
            self.create_rectangle(7, mid - 1, max(7, x), mid + 2, fill=fill, width=0)
        kh = h // 2 - 1
        if self.hover or self.dragging:      # the channels slip apart under the knob
            self.create_rectangle(x - 7, mid - kh, x + 1, mid + kh, fill=T["ch_a"], width=0)
            self.create_rectangle(x - 1, mid - kh, x + 7, mid + kh, fill=T["ch_b"], width=0)
        self.create_rectangle(x - 4, mid - kh, x + 4, mid + kh,
                              fill=T["text"] if self.enabled else T["dim"],
                              outline=T["accent"] if self.hover else T["line2"])
        if self.focus_get() is self:
            self.create_rectangle(1, 1, w - 2, h - 2, outline=T["accent"], dash=(2, 3))


class VSlider(tk.Canvas):
    """A vertical slider for EQ bands; the top is the maximum. Double-click resets."""

    def __init__(self, parent: tk.Misc, command: Callable[[float], None], width: int = 40,
                 height: int = 170, lo: float = -12.0, hi: float = 12.0, step: float = 0.5,
                 center: bool = True):
        super().__init__(parent, width=width, height=height, bg=parent.cget("bg"),
                         highlightthickness=0, bd=0, takefocus=1, cursor="hand2")
        self.command, self.lo, self.hi, self.step, self.center = command, lo, hi, step, center
        self.value = 0.0 if center else lo
        self.dragging, self.hover, self.enabled = False, False, True
        self.bind("<Configure>", lambda _e: self.draw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Double-Button-1>", lambda _e: self._set_user(0.0 if center else lo))
        for name, d in (("Up", 1), ("Right", 1), ("Down", -1), ("Left", -1)):
            self.bind(f"<{name}>", lambda _e, d=d: self._set_user(self.value + d * self.step))
        self.bind("<Button-4>", lambda _e: self._set_user(self.value + self.step))
        self.bind("<Button-5>", lambda _e: self._set_user(self.value - self.step))
        self.bind("<MouseWheel>", lambda e: self._set_user(self.value + self.step * (1 if e.delta > 0 else -1)))
        for seq, on in (("<Enter>", True), ("<Leave>", False), ("<FocusIn>", True), ("<FocusOut>", False)):
            self.bind(seq, lambda _e, on=on: self._hovered(on))

    def _hovered(self, on: bool):
        self.hover = on and self.enabled
        self.draw()

    def _y(self, value: float) -> float:
        h = max(1, self.winfo_height() - 16)
        return 8 + h * (1 - (value - self.lo) / (self.hi - self.lo))

    def _value_at(self, y: float) -> float:
        h = max(1, self.winfo_height() - 16)
        return max(self.lo, min(self.hi, self.lo + (1 - (y - 8) / h) * (self.hi - self.lo)))

    def set(self, value: float):
        value = max(self.lo, min(self.hi, value))
        if not self.dragging and abs(value - self.value) > 1e-9:
            self.value = value
            self.draw()

    def set_enabled(self, on: bool):
        self.enabled = on
        self.configure(cursor="hand2" if on else "arrow", takefocus=1 if on else 0)
        self.draw()

    def _set_user(self, value: float):
        if not self.enabled:
            return
        value = round(max(self.lo, min(self.hi, value)) / self.step) * self.step
        if abs(value - self.value) > 1e-9:
            self.value = value
            self.draw()
            self.command(value)

    def _press(self, e):
        if self.enabled:
            self.focus_set()
            self.dragging = True
            self._set_user(self._value_at(e.y))

    def _drag(self, e):
        if self.dragging:
            self._set_user(self._value_at(e.y))

    def _release(self, _e):
        self.dragging = False
        self.draw()

    def draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if h < 30:
            return
        cx = w // 2
        y = self._y(self.value)
        fill = T["accent"] if self.enabled else T["dim"]
        self.create_rectangle(cx - 2, 8, cx + 2, h - 8, fill=T["panel2"], outline=T["line2"])
        if self.center:
            zero = self._y(0.0)
            self.create_rectangle(cx - 1, min(zero, y), cx + 2, max(zero, y), fill=fill, width=0)
            self.create_line(cx - 10, zero, cx + 10, zero, fill=T["muted"])
        else:
            self.create_rectangle(cx - 1, y, cx + 2, h - 8, fill=fill, width=0)
        if self.hover or self.dragging:
            self.create_rectangle(cx - 12, y - 4, cx + 6, y + 4, fill=T["ch_a"], width=0)
            self.create_rectangle(cx - 6, y - 4, cx + 12, y + 4, fill=T["ch_b"], width=0)
        self.create_rectangle(cx - 9, y - 4, cx + 9, y + 4, fill=T["text"] if self.enabled else T["dim"],
                              outline=T["accent"] if self.hover else T["line2"])
        if self.focus_get() is self:
            self.create_rectangle(1, 1, w - 2, h - 2, outline=T["accent"], dash=(2, 3))


class Meter(tk.Canvas):
    """A level bar of small segments: accent, gold near the top, pink at the end."""

    SEGMENTS = 32

    def __init__(self, parent: tk.Misc, height: int = 8):
        super().__init__(parent, height=height, bg=parent.cget("bg"), highlightthickness=0, bd=0)
        self.lit, self.active = -1, True
        self.bind("<Configure>", lambda _e: self._redraw())

    def set(self, level: float, active: bool = True):
        lit = int(round(max(0.0, min(1.0, level)) * self.SEGMENTS)) if active else 0
        if lit != self.lit or active != self.active:
            self.active, self.lit = active, lit
            self._redraw()

    def _redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), int(self.cget("height"))
        if w < 20:
            return
        n = self.SEGMENTS
        seg = w / n
        for i in range(n):
            if i >= self.lit:
                colour = T["panel2"]
            elif i >= n * 0.92:
                colour = T["pink"]
            elif i >= n * 0.75:
                colour = T["gold"]
            else:
                colour = T["accent"]
            self.create_rectangle(i * seg + 1, 0, (i + 1) * seg - 1, h, fill=colour, width=0)


class Dropdown(tk.Menubutton):
    """A menu button: the current choice, a chevron, a flat menu."""

    def __init__(self, parent: tk.Misc, font, width: int = 24):
        super().__init__(parent, font=font, bg=T["panel2"], fg=T["text"], activebackground=T["hover"],
                         activeforeground=T["accent"], relief="flat", bd=0, padx=10, pady=5,
                         highlightthickness=1, highlightbackground=T["line2"], anchor="w",
                         width=width, cursor="hand2", takefocus=1, indicatoron=False)
        self.menu = tk.Menu(self, tearoff=False, bg=T["panel2"], fg=T["text"], font=font,
                            activebackground=T["hover"], activeforeground=T["accent"], bd=1,
                            relief="flat", activeborderwidth=0)
        self.configure(menu=self.menu)
        self.min_width = width
        self.options: List[Tuple[str, Any]] = []
        self.value: Any = None
        self.command: Optional[Callable[[Any], None]] = None
        for seq, colour in (("<Enter>", "accent"), ("<Leave>", "line2"),
                            ("<FocusIn>", "accent"), ("<FocusOut>", "line2")):
            self.bind(seq, lambda _e, c=colour: self.config(highlightbackground=T[c]))

    def set_options(self, options: List[Tuple[str, Any]], value: Any,
                    command: Optional[Callable[[Any], None]] = None) -> None:
        options = list(options)
        if options != self.options:
            self.options = options
            self.menu.delete(0, "end")
            for label, val in options:
                self.menu.add_command(label=label, command=lambda v=val: self._pick(v))
            # wide enough for the longest choice, so no label is ever cut off
            longest = max((len(label) for label, _ in options), default=0) + 4
            self.config(width=max(self.min_width, min(longest, 64)))
        if command is not None:
            self.command = command
        self.show(value)

    def show(self, value: Any) -> None:
        self.value = value
        label = next((l for l, v in self.options if v == value), "")
        self.config(text=label + "  ▾")

    def _pick(self, value: Any) -> None:
        self.show(value)
        if self.command:
            self.command(value)


class ScrollFrame(tk.Frame):
    """A frame that scrolls vertically; put children in .body."""

    def __init__(self, parent: tk.Misc, bg: str = T["bg"]):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.bar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview,
                                bg=T["panel2"], troughcolor=T["bg"], activebackground=T["line2"],
                                highlightthickness=0, bd=0, relief="flat", width=10,
                                elementborderwidth=0)
        self.canvas.configure(yscrollcommand=self._scrolled)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=bg)
        self.window = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        self.bind_all("<Button-4>", lambda e: self._wheel(-1), add="+")
        self.bind_all("<Button-5>", lambda e: self._wheel(1), add="+")

    def _scrolled(self, first, last):
        self.bar.set(first, last)
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.bar.pack_forget()
        elif not self.bar.winfo_ismapped():
            self.bar.pack(side="right", fill="y", before=self.canvas)

    def _wheel(self, direction: int):
        if not self.winfo_viewable():
            return
        px, py = self.winfo_pointerxy()
        under = self.winfo_containing(px, py)
        widget = under
        while widget is not None:
            if widget is self:
                if not isinstance(under, (Slider, VSlider)):
                    self.canvas.yview_scroll(direction * 3, "units")
                return
            widget = widget.master
