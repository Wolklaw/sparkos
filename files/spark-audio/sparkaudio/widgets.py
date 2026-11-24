"""The Wolklaw look for Tk: BotWatch's app palette, mono type, sharp corners, and one
recurring fault, the magenta and cyan channels slipping out of register.

The common parts (T, Glitch, GlitchText, WolkButton, Segmented, Strip, GlitchPanel, Toggle) are
copied from Spark Monitor (files/spark-monitor/sparkmonitor/widgets.py), which shares them with
Spark Media; keep them in step. The mark, tabs, sliders, level meter and dropdown are Spark Audio's own (controls.py)."""

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


