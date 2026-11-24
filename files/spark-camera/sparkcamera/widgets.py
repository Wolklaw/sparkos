"""The Wolklaw look for Tk: BotWatch's app palette, mono type, sharp corners, and one
recurring fault, the magenta and cyan channels slipping out of register.

Copied from Spark Space and Spark Media, the family's shared widgets; keep the common parts in
step. Spark Camera's own: Mark (its icon), the record, stop, camera, mic and rename IconButton
icons, and Choice (a drop-down in the house style)."""

import random
from typing import Any, Callable, List, Optional, Tuple

import tkinter as tk
import tkinter.font as tkfont

T = {
    "bg": "#04090b", "panel": "#0a1517", "panel2": "#0e1f22", "hover": "#12292c",
    "line": "#143a3d", "line2": "#1f6a66", "text": "#d4f1ec", "muted": "#6f9f98",
    "dim": "#3b6460", "accent": "#3de8c8", "accent_hov": "#8cf5e2", "on_accent": "#02130f",
    "pink": "#ff4d8d", "gold": "#f4c95d", "ch_a": "#ff2e88", "ch_b": "#22d8ff",
    "out_bg": "#020807", "tile": "#0b1a1c",
}
MONO_FAMILIES = ("Cascadia Mono", "Cascadia Code", "JetBrains Mono", "Hack", "Noto Sans Mono",
                 "DejaVu Sans Mono", "Liberation Mono", "Consolas", "Courier New")


def pick_mono(root: tk.Misc) -> str:
    families = {name.lower(): name for name in tkfont.families(root)}
    for wanted in MONO_FAMILIES:
        if wanted.lower() in families:
            return families[wanted.lower()]
    return "TkFixedFont"


def mix(c1: str, c2: str, t: float) -> str:
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


class Glitch:
    """The house fault: a tear 450 ms after a window opens, again every 7-12 s, and on
    every event. Off when the desktop asks for no animation; the static split stays."""

    def __init__(self, root: tk.Misc, enabled: bool):
        self.root, self.enabled = root, enabled
        self.targets: List[Any] = []
        self._loop: Optional[str] = None

    def add(self, *targets) -> None:
        self.targets.extend(targets)
        if self.enabled and self._loop is None:
            self._loop = self.root.after(450, self._tick)

    def _tick(self) -> None:
        self.now()
        self._loop = self.root.after(random.randint(7000, 12000), self._tick)

    def now(self, *targets, strong: bool = False) -> None:
        if not self.enabled:
            return
        for target in (targets or tuple(self.targets)):
            try:
                if target.winfo_exists():
                    target.burst(strong)
                    continue
            except tk.TclError:
                pass
            if target in self.targets:
                self.targets.remove(target)


class Mark(tk.Canvas):
    """Spark Camera's mark: a camera body with a lens, split into channels. Same 32-unit
    geometry as make_icons.py."""

    BODY = (5.5, 10.5, 26.5, 25.5)
    TOP = (11.5, 7, 17.5, 10.5)
    LENS = (16, 18, 4.6)

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
        self.create_rectangle(0, 0, s - 1, s - 1, fill=T["tile"], outline=T["line2"])
        width = max(1, round(1.6 * k))

        def shape(offset, colour, fill_lens=False):
            ox, oy = offset[0] * k, offset[1] * k
            x0, y0, x1, y1 = self.BODY
            self.create_rectangle(x0 * k + ox, y0 * k + oy, x1 * k + ox, y1 * k + oy,
                                  outline=colour, width=width)
            x0, y0, x1, y1 = self.TOP
            self.create_rectangle(x0 * k + ox, y0 * k + oy, x1 * k + ox, y1 * k + oy,
                                  outline=colour, width=width)
            cx, cy, r = self.LENS
            self.create_oval((cx - r) * k + ox, (cy - r) * k + oy, (cx + r) * k + ox,
                             (cy + r) * k + oy, outline=colour, width=width,
                             fill=colour if fill_lens else "")

        shape(a, T["ch_a"])
        shape(b, T["ch_b"])
        shape(c, T["accent"], fill_lens=True)
        for y0, h, colour in bars:
            self.create_rectangle(1, y0, s - 1, y0 + h, fill=colour, stipple="gray50", width=0)

    def micro(self):
        if not self.running:
            self.draw(a=(-2.6, 0.4), b=(2.6, -0.4))
            self._root().after(130, lambda: None if self.running else self.draw())

    def burst(self, strong: bool = False):
        if self.running:
            return
        self.running = True
        frames = [((random.uniform(-5, -2), random.uniform(-1, 1)),
                   (random.uniform(2, 5), random.uniform(-1, 1)),
                   (random.uniform(-1.2, 1.2), 0.0),
                   [(random.randint(2, self.size - 4), random.randint(1, 3),
                     random.choice([T["ch_a"], T["ch_b"]])) for _ in range(random.randint(1, 3))])
                  for _ in range(8 if strong else 6)]

        def step(i=0):
            if not self.winfo_exists():
                return
            if i < len(frames):
                self.draw(*frames[i])
                self._root().after(48, lambda: step(i + 1))
            else:
                self.draw()
                self.running = False

        step()


class GlitchText(tk.Canvas):
    """Text with the magenta/cyan ghosts always slightly out of register; tears on burst."""

    def __init__(self, parent: tk.Misc, text: str, font: tkfont.Font, bg: str,
                 fg: str = T["text"], split: int = 2):
        self.font, self.text, self.fg, self.split = font, text, fg, split
        self.pad = 4 + split
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0)
        self.running = False
        self.set_text(text, fg)

    def set_text(self, text: str, fg: Optional[str] = None):
        self.text = text
        if fg:
            self.fg = fg
        self.w = self.font.measure(text) + 2 * self.pad + 6
        self.h = self.font.metrics("linespace") + 6
        self.configure(width=self.w, height=self.h)
        self.draw()

    def draw(self, jitter: float = 0.0, bars=(), dy: int = 0):
        self.delete("all")
        d = self.split + abs(jitter)
        for colour, sign in ((T["ch_a"], -1), (T["ch_b"], 1)):
            self.create_text(self.pad + sign * d, self.h / 2 + dy, text=self.text, anchor="w",
                             font=self.font, fill=colour)
        self.create_text(self.pad + jitter, self.h / 2 + dy, text=self.text, anchor="w",
                         font=self.font, fill=self.fg)
        for y0, hh, colour, x0, x1 in bars:
            self.create_rectangle(x0, y0, x1, y0 + hh, fill=colour, stipple="gray25", width=0)

    def burst(self, strong: bool = False):
        if self.running or not self.winfo_exists():
            return
        self.running = True
        count = 9 if strong else 6

        def step(i=0):
            if not self.winfo_exists():
                return
            if i < count:
                bars = [(random.randint(2, max(3, self.h - 6)), random.randint(2, 5),
                         random.choice([T["ch_a"], T["ch_b"]]),
                         random.randint(0, self.w // 2), random.randint(self.w // 2, self.w))
                        for _ in range(random.randint(1, 3))]
                self.draw(jitter=random.uniform(-5, 5), bars=bars, dy=random.choice([0, 0, -1, 1]))
                self._root().after(45, lambda: step(i + 1))
            else:
                self.draw()
                self.running = False

        step()


class WolkButton(tk.Frame):
    """Sharp button; on hover and focus its edges split into the magenta/cyan channels."""

    STYLES = {   # idle bg, fg, border, hover bg
        "primary": (T["accent"], T["on_accent"], T["accent"], T["accent_hov"]),
        "ghost": (T["panel2"], T["text"], T["line2"], T["hover"]),
        "danger": ("#1a0a12", T["pink"], "#4b1c34", "#2a0f1c"),
    }

    def __init__(self, parent: tk.Misc, text: str, command: Callable[[], None], font,
                 variant: str = "ghost", padx: int = 14, pady: int = 6):
        self.pbg = parent.cget("bg")
        super().__init__(parent, bg=self.pbg)
        self.command, self.enabled, self.variant = command, True, variant
        self.bg_idle, self.fg_idle, self.border_idle, self.bg_hover = self.STYLES[variant]
        self.lbar = tk.Frame(self, bg=self.pbg, width=3)
        self.rbar = tk.Frame(self, bg=self.pbg, width=3)
        self.lbar.pack(side="left", fill="y")
        self.rbar.pack(side="right", fill="y")
        self.box = tk.Frame(self, bg=self.border_idle, padx=1, pady=1)
        self.box.pack(side="left", fill="both", expand=True)
        self.label = tk.Label(self.box, text=text.upper(), bg=self.bg_idle, fg=self.fg_idle,
                              font=font, padx=padx, pady=pady, cursor="hand2", takefocus=1,
                              highlightthickness=0)
        self.label.pack(fill="both", expand=True)
        for widget in (self.label, self.box, self.lbar, self.rbar):
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)
            widget.bind("<ButtonRelease-1>", self._click)
        self.label.bind("<FocusIn>", self._enter)
        self.label.bind("<FocusOut>", self._leave)
        self.label.bind("<Return>", self._click)
        self.label.bind("<space>", self._click)

    def _enter(self, _e=None):
        if not self.enabled:
            return
        self.lbar.config(bg=T["ch_a"])
        self.rbar.config(bg=T["ch_b"])
        self.box.config(bg=T["pink"] if self.variant == "danger" else T["accent"])
        self.label.config(bg=self.bg_hover)

    def _leave(self, _e=None):
        self.lbar.config(bg=self.pbg)
        self.rbar.config(bg=self.pbg)
        self.box.config(bg=self.border_idle if self.enabled else T["line"])
        self.label.config(bg=self.bg_idle if self.enabled else T["panel"])

    def _click(self, event=None):
        if event is not None and str(event.type) == 'ButtonRelease':
            # the release goes to the pressed widget even if the pointer has left it
            under = self.winfo_containing(event.x_root, event.y_root)
            if under not in (self.label, self.box, self.lbar, self.rbar):
                return
        if self.enabled and self.command:
            self.command()

    def set_text(self, text: str):
        self.label.config(text=text.upper())

    def set_enabled(self, on: bool):
        self.enabled = on
        self.label.config(bg=self.bg_idle if on else T["panel"],
                          fg=self.fg_idle if on else T["dim"],
                          cursor="hand2" if on else "arrow", takefocus=1 if on else 0)
        self.box.config(bg=self.border_idle if on else T["line"])
        if not on:
            self.lbar.config(bg=self.pbg)
            self.rbar.config(bg=self.pbg)


class Segmented(tk.Frame):
    """Row of mutually exclusive mono pills (EN + FR | EN | FR)."""

    def __init__(self, parent: tk.Misc, options: List[Tuple[str, str]], value: str,
                 command: Callable[[str], None], font):
        super().__init__(parent, bg=T["line2"], padx=1, pady=1)
        self.value, self.command, self.labels = value, command, {}
        for i, (text, val) in enumerate(options):
            label = tk.Label(self, text=text, font=font, padx=10, pady=4, cursor="hand2")
            label.grid(row=0, column=i, padx=(0 if i == 0 else 1, 0))
            label.bind("<ButtonRelease-1>", lambda _e, v=val: self.set(v, fire=True))
            label.bind("<Enter>", lambda _e, v=val: self._hover(v, True))
            label.bind("<Leave>", lambda _e, v=val: self._hover(v, False))
            self.labels[val] = label
        self._paint()

    def _hover(self, val: str, on: bool):
        if val != self.value:
            self.labels[val].config(bg=T["hover"] if on else T["panel"])

    def _paint(self):
        for val, label in self.labels.items():
            on = val == self.value
            label.config(bg=T["accent"] if on else T["panel"],
                         fg=T["on_accent"] if on else T["muted"])

    def set(self, val: str, fire: bool = False):
        self.value = val
        self._paint()
        if fire:
            self.command(val)


class Strip(tk.Canvas):
    """A 2px mint-to-pink line: the header rule, and the popup's countdown."""

    def __init__(self, parent: tk.Misc, height: int = 2):
        super().__init__(parent, height=height, bg=T["bg"], highlightthickness=0, bd=0)
        self.fraction, self.shift = 1.0, 0
        self.bind("<Configure>", lambda _e: self.draw())

    def draw(self, fraction: Optional[float] = None, shift: Optional[int] = None):
        if fraction is not None:
            self.fraction = fraction
        if shift is not None:
            self.shift = shift
        self.delete("all")
        width = max(1, self.winfo_width())
        end = int(width * max(0.0, min(1.0, self.fraction)))
        height = int(self.cget("height"))
        for x in range(0, end, 4):
            colour = mix(T["accent"], T["pink"], ((x + self.shift) % width) / width)
            self.create_rectangle(x, 0, min(end, x + 4), height, fill=colour, width=0)

    def burst(self, strong: bool = False):
        self.draw(shift=random.randint(0, 400))
        self._root().after(160, lambda: self.draw(shift=0) if self.winfo_exists() else None)


class GlitchPanel(tk.Frame):
    """A flat panel with a 1px edge that tears into the two channels on events."""

    def __init__(self, parent: tk.Misc, bg: str):
        self.pbg = parent.cget("bg")
        super().__init__(parent, bg=self.pbg)
        self.lbar = tk.Frame(self, bg=self.pbg, width=2)
        self.rbar = tk.Frame(self, bg=self.pbg, width=2)
        self.lbar.pack(side="left", fill="y")
        self.rbar.pack(side="right", fill="y")
        self.edge = tk.Frame(self, bg=T["line"], padx=1, pady=1)
        self.edge.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.edge, bg=bg)
        self.inner.pack(fill="both", expand=True)
        self.running = False

    def burst(self, strong: bool = False):
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
                self._root().after(45, lambda: step(i + 1))
            else:
                self.lbar.config(bg=self.pbg)
                self.rbar.config(bg=self.pbg)
                self.edge.config(bg=T["line"])
                self.running = False

        step()



class Toggle(tk.Label):
    """An on/off chip: [■ MIC] lit in the accent when on."""

    def __init__(self, parent: tk.Misc, text: str, value: bool,
                 command: Callable[[bool], None], font):
        super().__init__(parent, font=font, padx=8, pady=3, cursor="hand2",
                         highlightthickness=1, takefocus=1)
        self.text, self.value, self.command = text, value, command
        self.bind("<ButtonRelease-1>", lambda _e: self.set(not self.value, fire=True))
        self.bind("<Return>", lambda _e: self.set(not self.value, fire=True))
        self.bind("<space>", lambda _e: self.set(not self.value, fire=True))
        self.bind("<Enter>", lambda _e: self._paint(hover=True))
        self.bind("<Leave>", lambda _e: self._paint())
        self._paint()

    def _paint(self, hover: bool = False):
        on = self.value
        self.config(text=("■ " if on else "□ ") + self.text.upper(),
                    bg=T["hover"] if hover else T["panel"],
                    fg=T["accent"] if on else T["muted"],
                    highlightbackground=T["line2"] if on else T["line"])

    def set(self, value: bool, fire: bool = False):
        self.value = value
        self._paint()
        if fire:
            self.command(value)


class IconButton(tk.Canvas):
    """A square button with a drawn icon (fonts can't be trusted to have the glyphs). On hover
    and focus the icon splits into the two channels, like the house buttons' edges."""

    def __init__(self, parent: tk.Misc, icon: str, command: Callable[[], None], size: int,
                 tip: str = "", accent: bool = False):
        self.pbg = parent.cget("bg")
        super().__init__(parent, width=size, height=size, bg=self.pbg, highlightthickness=0,
                         bd=0, cursor="hand2", takefocus=1)
        self.icon, self.command, self.size, self.accent = icon, command, size, accent
        self.tip, self.enabled, self.hover = tip, True, False
        for seq, fn in (("<Enter>", self._enter), ("<Leave>", self._leave),
                        ("<FocusIn>", self._enter), ("<FocusOut>", self._leave),
                        ("<ButtonRelease-1>", self._click), ("<Return>", self._click),
                        ("<space>", self._click)):
            self.bind(seq, fn)
        self.draw()

    def set_icon(self, icon: str):
        if icon != self.icon:
            self.icon = icon
            self.draw()

    def set_enabled(self, on: bool):
        self.enabled = on
        self.configure(cursor="hand2" if on else "arrow", takefocus=1 if on else 0)
        self.draw()

    def _enter(self, _e=None):
        self.hover = self.enabled
        self.draw()

    def _leave(self, _e=None):
        self.hover = False
        self.draw()

    def _click(self, event=None):
        if event is not None and str(event.type) == 'ButtonRelease':
            if self.winfo_containing(event.x_root, event.y_root) is not self:
                return
        if self.enabled and self.command:
            self.command()
        return "break"

    def draw(self):
        self.delete("all")
        s = self.size
        if self.accent and self.enabled:
            self.create_rectangle(0, 0, s - 1, s - 1, fill=T["accent_hov"] if self.hover
                                  else T["accent"], outline="")
            main = T["on_accent"]
        else:
            self.create_rectangle(0, 0, s - 1, s - 1, fill=T["hover"] if self.hover else self.pbg,
                                  outline=T["line2"] if self.hover else "")
            main = T["text"] if self.enabled else T["dim"]
        if self.hover:
            self._shape(-2, T["ch_a"])
            self._shape(2, T["ch_b"])
        self._shape(0, main)

    def _shape(self, dx: float, colour: str):
        k = self.size / 24.0
        w = max(1.5, 1.8 * k)

        def P(*pts):
            return [v * k + (dx if i % 2 == 0 else 0) for i, v in enumerate(pts)]

        def line(*pts):
            self.create_line(*P(*pts), fill=colour, width=w, capstyle="projecting",
                             joinstyle="miter")

        def poly(*pts):
            self.create_polygon(*P(*pts), fill=colour, outline="")

        def rect(x0, y0, x1, y1, fill=True):
            if fill:
                self.create_rectangle(*P(x0, y0, x1, y1), fill=colour, outline="")
            else:
                self.create_rectangle(*P(x0, y0, x1, y1), outline=colour, width=w)

        icon = self.icon
        if icon == "play":
            poly(8, 5, 8, 19, 19, 12)
        elif icon == "pause":
            rect(7, 5, 10.5, 19)
            rect(13.5, 5, 17, 19)
        elif icon == "prev":
            rect(5, 6, 7.5, 18)
            poly(19, 6, 19, 18, 9, 12)
        elif icon == "next":
            rect(16.5, 6, 19, 18)
            poly(5, 6, 5, 18, 15, 12)
        elif icon in ("volume", "mute"):
            poly(4, 9, 8, 9, 13, 5, 13, 19, 8, 15, 4, 15)
            if icon == "volume":
                line(16, 9, 17, 12, 16, 15)
                line(19, 6.5, 21, 12, 19, 17.5)
            else:
                line(16, 9, 21, 15)
                line(21, 9, 16, 15)
        elif icon == "fullscreen":
            for x, y, ax, ay in ((5, 5, 1, 1), (19, 5, -1, 1), (5, 19, 1, -1), (19, 19, -1, -1)):
                line(x, y + 5 * ay, x, y, x + 5 * ax, y)
        elif icon == "windowed":
            for x, y, ax, ay in ((9, 9, -1, -1), (15, 9, 1, -1), (9, 15, -1, 1), (15, 15, 1, 1)):
                line(x, y + 5 * ay, x, y, x + 5 * ax, y)
        elif icon == "up":
            line(12, 19, 12, 6)
            line(7, 11, 12, 6, 17, 11)
        elif icon == "refresh":
            line(18, 12, 18, 18, 6, 18, 6, 6, 15, 6)
            poly(14, 3, 18.5, 6, 14, 9)
        elif icon == "open":
            line(13, 5, 19, 5, 19, 11)
            line(19, 5, 11, 13)
            line(16, 14, 16, 19, 5, 19, 5, 8, 10, 8)
        elif icon == "back":
            line(19, 12, 6, 12)
            line(11, 7, 6, 12, 11, 17)
        elif icon == "rotate":
            line(18, 9, 18, 18, 6, 18, 6, 6, 14, 6)
            poly(13, 3, 17.5, 6, 13, 9)
        elif icon == "rotate_ccw":
            line(6, 9, 6, 18, 18, 18, 18, 6, 10, 6)
            poly(11, 3, 6.5, 6, 11, 9)
        elif icon == "edit":
            # a crop mark: the two corner brackets every editor uses
            line(7, 3, 7, 17, 21, 17)
            line(3, 7, 17, 7, 17, 21)
        elif icon == "zoom_in":
            line(5, 12, 19, 12)
            line(12, 5, 12, 19)
        elif icon == "zoom_out":
            line(5, 12, 19, 12)
        elif icon == "fit":
            rect(5, 7, 19, 17, fill=False)
            line(8, 12, 16, 12)
        elif icon == "slideshow":
            rect(4, 6, 20, 18, fill=False)
            poly(10, 9, 10, 15, 15, 12)
        elif icon == "record":
            self.create_oval(*P(6, 6, 18, 18), fill=colour, outline="")
        elif icon == "stop":
            rect(6.5, 6.5, 17.5, 17.5)
        elif icon == "camera":
            rect(3.5, 8, 20.5, 19, fill=False)
            rect(8.5, 5, 14, 8)
            self.create_oval(*P(8.5, 10, 15.5, 17), outline=colour, width=w)
        elif icon == "mic":
            rect(9, 3.5, 15, 13.5, fill=False)
            line(6, 11, 6, 13, 9, 17, 15, 17, 18, 13, 18, 11)
            line(12, 17, 12, 21)
            line(8.5, 21, 15.5, 21)
        elif icon == "rename":
            line(5, 19, 5.8, 15, 16, 4.8, 19.2, 8, 9, 18.2, 5, 19)
            line(14, 7, 17, 10)
        elif icon == "trash":
            line(5, 7, 19, 7)
            line(10, 7, 10, 4.5, 14, 4.5, 14, 7)
            line(7, 7, 8, 19.5, 16, 19.5, 17, 7)
        elif icon == "folder":
            line(4, 18, 4, 6, 10, 6, 12, 8.5, 20, 8.5, 20, 18, 4, 18)
        elif icon == "subtitles":
            rect(4, 6, 20, 18, fill=False)
            line(7, 13.5, 11, 13.5)
            line(13, 13.5, 17, 13.5)
        elif icon == "audio":
            line(9, 17, 9, 6, 18, 4.5, 18, 15)
            rect(5.5, 15, 9, 18.5)
            rect(14.5, 13, 18, 16.5)
        elif icon == "repeat":
            line(6, 13, 6, 8, 17, 8)
            poly(16, 5, 20, 8, 16, 11)
            line(18, 11, 18, 16, 7, 16)
            poly(8, 13, 4, 16, 8, 19)
        elif icon == "shuffle":
            line(4, 7, 9, 7, 15, 17, 19, 17)
            line(4, 17, 9, 17, 15, 7, 19, 7)
            poly(18, 4, 21.5, 7, 18, 10)
            poly(18, 14, 21.5, 17, 18, 20)


# ─── Tables (copied from Spark Monitor, files/spark-monitor/sparkmonitor/ui.py) ───

def style_tables(root: tk.Misc, font, heading_font, row_height: int) -> None:
    from tkinter import ttk
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


def make_table(parent: tk.Misc, columns, show: str = "tree headings"):
    """A styled Treeview in a frame, with a scrollbar. Returns (frame, tree)."""
    from tkinter import ttk
    frame = tk.Frame(parent, bg=T["line"], padx=1, pady=1)
    tree = ttk.Treeview(frame, columns=columns, style="Spark.Treeview", show=show,
                        selectmode="browse")
    bar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview,
                        style="Spark.Vertical.TScrollbar")
    tree.configure(yscrollcommand=bar.set)
    bar.pack(side="right", fill="y")
    tree.pack(side="left", fill="both", expand=True)
    tree.tag_configure("muted", foreground=T["muted"])
    tree.tag_configure("warn", foreground=T["gold"])
    tree.tag_configure("hint", foreground=T["gold"])
    tree.tag_configure("off", foreground=T["dim"])
    return frame, tree


class Choice(tk.Frame):
    """A drop-down: the current choice on a flat button, a menu of the others under it."""

    def __init__(self, parent: tk.Misc, font, command: Callable[[str], None], width: int = 24):
        super().__init__(parent, bg=T["line2"], padx=1, pady=1)
        self.command, self.font, self.enabled = command, font, True
        self.items: List[Tuple[str, str]] = []
        self.value = ''
        self.label = tk.Label(self, text="", bg=T["panel"], fg=T["text"], font=font, anchor="w",
                              padx=8, pady=4, cursor="hand2", takefocus=1, width=width)
        self.label.pack(fill="x")
        for seq, fn in (("<Enter>", lambda _e: self._paint(True)),
                        ("<Leave>", lambda _e: self._paint(False)),
                        ("<FocusIn>", lambda _e: self._paint(True)),
                        ("<FocusOut>", lambda _e: self._paint(False)),
                        ("<ButtonRelease-1>", self._open), ("<Return>", self._open),
                        ("<space>", self._open), ("<Down>", self._open)):
            self.label.bind(seq, fn)

    def _paint(self, hover: bool):
        if not self.enabled:
            return
        self.label.config(bg=T["hover"] if hover else T["panel"])
        self.config(bg=T["accent"] if hover else T["line2"])

    def set_items(self, items: List[Tuple[str, str]], value: str = '') -> None:
        """items: (text, value). The first one is picked when value isn't among them."""
        self.items = list(items)
        self.set(value if any(v == value for _t, v in items) else (items[0][1] if items else ''))

    def set(self, value: str, fire: bool = False) -> None:
        self.value = value
        text = next((t for t, v in self.items if v == value), "")
        if len(text) > 30:
            text = text[:29] + "…"
        self.label.config(text=(text + "  ▾") if text else "")
        if fire:
            self.command(value)

    def set_enabled(self, on: bool) -> None:
        self.enabled = on
        self.label.config(fg=T["text"] if on else T["dim"], bg=T["panel"],
                          cursor="hand2" if on else "arrow", takefocus=1 if on else 0)
        self.config(bg=T["line2"] if on else T["line"])

    def _open(self, event=None):
        if not self.enabled or not self.items:
            return "break"
        if event is not None and str(event.type) == 'ButtonRelease':
            if self.winfo_containing(event.x_root, event.y_root) is not self.label:
                return "break"
        menu = tk.Menu(self, tearoff=0, bg=T["panel"], fg=T["text"], font=self.font,
                       activebackground=T["hover"], activeforeground=T["accent"], bd=1,
                       relief="flat", activeborderwidth=0)
        for text, value in self.items:
            menu.add_command(label=("■ " if value == self.value else "   ") + text,
                             command=lambda v=value: self.set(v, fire=True))
        self.menu = menu
        try:
            menu.tk_popup(self.winfo_rootx(), self.winfo_rooty() + self.winfo_height())
        finally:
            menu.grab_release()
        return "break"
