"""The keys: one canvas each (fast to build), in the house style: flat, 1px edge, sharp
corners, and on hover the edges slip into the magenta and cyan channels."""

from typing import Callable, Dict, List, Optional, Tuple

import tkinter as tk

from .text import DECIMAL
from .widgets import T

# (label, action, kind). Actions: "ins:x" types x; "pre:sin(" wraps the operand in a call
# (or starts one); "wrap:before|after"; "post:²" goes after the operand; "neg", "ce",
# "clear", "back", "eq". Kinds set the look: digit, op, fn, eq, clear. The decimal key types
# the PC's decimal mark: "," in French.
Layout = List[List[Tuple[str, str, str]]]

STANDARD: Layout = [
    [('%', 'post:%', 'fn'), ('CE', 'ce', 'clear'), ('C', 'clear', 'clear'), ('', 'back', 'clear')],
    [('1/x', 'wrap:(1/|)', 'fn'), ('x²', 'post:²', 'fn'), ('√x', 'pre:√', 'fn'),
     ('÷', 'ins:÷', 'op')],
    [('7', 'ins:7', 'digit'), ('8', 'ins:8', 'digit'), ('9', 'ins:9', 'digit'),
     ('×', 'ins:×', 'op')],
    [('4', 'ins:4', 'digit'), ('5', 'ins:5', 'digit'), ('6', 'ins:6', 'digit'),
     ('−', 'ins:−', 'op')],
    [('1', 'ins:1', 'digit'), ('2', 'ins:2', 'digit'), ('3', 'ins:3', 'digit'),
     ('+', 'ins:+', 'op')],
    [('±', 'neg', 'fn'), ('0', 'ins:0', 'digit'), (DECIMAL, 'ins:' + DECIMAL, 'digit'),
     ('=', 'eq', 'eq')],
]

SCIENTIFIC: Layout = [
    [('π', 'ins:π', 'fn'), ('e', 'ins:e', 'fn'), ('n!', 'post:!', 'fn'),
     ('mod', 'ins: mod ', 'fn'), ('ʸ√x', 'pre:root(|', 'fn'), ('1/x', 'wrap:(1/|)', 'fn')],
    [('sin', 'pre:sin(', 'fn'), ('asin', 'pre:asin(', 'fn'), ('(', 'ins:(', 'fn'),
     (')', 'ins:)', 'fn'), ('C', 'clear', 'clear'), ('', 'back', 'clear')],
    [('cos', 'pre:cos(', 'fn'), ('acos', 'pre:acos(', 'fn'), ('x²', 'post:²', 'fn'),
     ('xʸ', 'ins:^', 'fn'), ('√x', 'pre:√', 'fn'), ('÷', 'ins:÷', 'op')],
    [('tan', 'pre:tan(', 'fn'), ('atan', 'pre:atan(', 'fn'), ('7', 'ins:7', 'digit'),
     ('8', 'ins:8', 'digit'), ('9', 'ins:9', 'digit'), ('×', 'ins:×', 'op')],
    [('sinh', 'pre:sinh(', 'fn'), ('ln', 'pre:ln(', 'fn'), ('4', 'ins:4', 'digit'),
     ('5', 'ins:5', 'digit'), ('6', 'ins:6', 'digit'), ('−', 'ins:−', 'op')],
    [('cosh', 'pre:cosh(', 'fn'), ('log', 'pre:log(', 'fn'), ('1', 'ins:1', 'digit'),
     ('2', 'ins:2', 'digit'), ('3', 'ins:3', 'digit'), ('+', 'ins:+', 'op')],
    [('tanh', 'pre:tanh(', 'fn'), ('eˣ', 'pre:exp(', 'fn'), ('±', 'neg', 'fn'),
     ('0', 'ins:0', 'digit'), (DECIMAL, 'ins:' + DECIMAL, 'digit'), ('=', 'eq', 'eq')],
]

PROGRAMMER: Layout = [
    [('A', 'ins:A', 'digit'), ('AND', 'ins: and ', 'fn'), ('<<', 'ins: << ', 'fn'),
     ('>>', 'ins: >> ', 'fn'), ('C', 'clear', 'clear'), ('', 'back', 'clear')],
    [('B', 'ins:B', 'digit'), ('OR', 'ins: or ', 'fn'), ('ROL', 'ins: rol ', 'fn'),
     ('ROR', 'ins: ror ', 'fn'), ('mod', 'ins: mod ', 'fn'), ('÷', 'ins:÷', 'op')],
    [('C', 'ins:C', 'digit'), ('XOR', 'ins: xor ', 'fn'), ('7', 'ins:7', 'digit'),
     ('8', 'ins:8', 'digit'), ('9', 'ins:9', 'digit'), ('×', 'ins:×', 'op')],
    [('D', 'ins:D', 'digit'), ('NOT', 'pre:~', 'fn'), ('4', 'ins:4', 'digit'),
     ('5', 'ins:5', 'digit'), ('6', 'ins:6', 'digit'), ('−', 'ins:−', 'op')],
    [('E', 'ins:E', 'digit'), ('NAND', 'ins: nand ', 'fn'), ('1', 'ins:1', 'digit'),
     ('2', 'ins:2', 'digit'), ('3', 'ins:3', 'digit'), ('+', 'ins:+', 'op')],
    [('F', 'ins:F', 'digit'), ('NOR', 'ins: nor ', 'fn'), ('(', 'ins:(', 'fn'),
     ('0', 'ins:0', 'digit'), (')', 'ins:)', 'fn'), ('=', 'eq', 'eq')],
]

LAYOUTS: Dict[str, Layout] = {'standard': STANDARD, 'scientific': SCIENTIFIC,
                              'programmer': PROGRAMMER}

STYLES = {   # face, text, edge
    'digit': (T["panel2"], T["text"], T["line"]),
    'op': (T["panel"], T["accent"], T["line"]),
    'fn': (T["panel"], T["text"], T["line"]),
    'eq': (T["accent"], T["on_accent"], T["accent"]),
    'clear': ("#140b12", T["pink"], "#3a1a2b"),
    'mem': (T["bg"], T["muted"], T["bg"]),
}


class Key(tk.Canvas):
    """One calculator key. Sizes itself to its grid cell."""

    def __init__(self, parent: tk.Misc, label: str, action: str, kind: str,
                 command: Callable[[str], None], font, small_font=None):
        pbg = parent.cget("bg")
        super().__init__(parent, width=8, height=8, bg=pbg, highlightthickness=0, bd=0,
                         takefocus=0, cursor="hand2")
        self.label, self.action, self.kind = label, action, kind
        self.command = command
        self.font = small_font if (small_font and len(label) > 2) else font
        self.enabled, self.hover, self.pressed = True, False, False
        self.bind("<Configure>", lambda _e: self.draw())
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)

    def set_enabled(self, on: bool):
        if on != self.enabled:
            self.enabled = on
            self.hover = self.hover and on
            self.configure(cursor="hand2" if on else "arrow")
            self.draw()

    def _enter(self, _e=None):
        self.hover = self.enabled
        self.draw()

    def _leave(self, _e=None):
        self.hover = self.pressed = False
        self.draw()

    def _press(self, _e=None):
        if self.enabled:
            self.pressed = True
            self.draw()

    def _release(self, event):
        was = self.pressed
        self.pressed = False
        self.draw()
        if was and self.enabled and self.winfo_containing(event.x_root,
                                                          event.y_root) is self:
            self.command(self.action)

    def flash(self):
        """Show a press for a moment (keyboard input)."""
        self.pressed = True
        self.draw()
        self.after(90, self._unflash)

    def _unflash(self):
        self.pressed = False
        if self.winfo_exists():
            self.draw()

    def draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4:
            return
        face, ink, edge = STYLES[self.kind]
        if not self.enabled:
            face, ink, edge = T["panel"], T["dim"], T["line"]
        elif self.pressed:
            face = T["accent_hov"] if self.kind == 'eq' else T["line"]
        elif self.hover:
            face = T["accent_hov"] if self.kind == 'eq' else T["hover"]
            edge = T["pink"] if self.kind == 'clear' else T["accent"]
        gap = 2
        x0, y0, x1, y1 = gap, gap, w - gap - 1, h - gap - 1
        if self.hover and not self.pressed:
            self.create_rectangle(x0 - 2, y0, x1 - 2, y1, outline=T["ch_a"], width=1)
            self.create_rectangle(x0 + 2, y0, x1 + 2, y1, outline=T["ch_b"], width=1)
        self.create_rectangle(x0, y0, x1, y1, fill=face, outline=edge, width=1)
        cx, cy = w / 2, h / 2
        if self.action == 'back':
            self._backspace(cx, cy, min(w, h), ink)
        else:
            self.create_text(cx, cy, text=self.label, fill=ink, font=self.font)

    def _backspace(self, cx: float, cy: float, size: float, ink: str):
        k = max(0.6, size / 48)
        pts = [cx - 13 * k, cy, cx - 6 * k, cy - 7 * k, cx + 12 * k, cy - 7 * k,
               cx + 12 * k, cy + 7 * k, cx - 6 * k, cy + 7 * k]
        self.create_polygon(*pts, outline=ink, fill="", width=max(1.5, 1.6 * k),
                            joinstyle="miter")
        for dx in (-1, 1):
            self.create_line(cx - 1 * k - 4 * k * dx, cy - 4 * k, cx - 1 * k + 4 * k * dx,
                             cy + 4 * k, fill=ink, width=max(1.5, 1.6 * k))


class Keypad(tk.Frame):
    """A grid of Keys for one mode."""

    def __init__(self, parent: tk.Misc, layout: Layout, command: Callable[[str], None],
                 font, small_font, pad: int):
        super().__init__(parent, bg=parent.cget("bg"))
        self.keys: List[Key] = []
        self.by_label: Dict[str, Key] = {}
        cols = max(len(row) for row in layout)
        for c in range(cols):
            self.columnconfigure(c, weight=1, uniform="k")
        for r, row in enumerate(layout):
            self.rowconfigure(r, weight=1, uniform="k")
            for c, (label, action, kind) in enumerate(row):
                key = Key(self, label, action, kind, command, font, small_font)
                key.grid(row=r, column=c, sticky="nsew", padx=pad, pady=pad)
                self.keys.append(key)
                self.by_label.setdefault(action, key)

    def key_for(self, action: str) -> Optional[Key]:
        return self.by_label.get(action)
