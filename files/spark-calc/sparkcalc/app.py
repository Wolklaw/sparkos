"""The window: the display, a keypad per mode, memory keys and the history panel."""

import os
import re
import shutil
import subprocess
import time
from fractions import Fraction
from typing import Any, Dict, List, Optional, Tuple

import tkinter as tk
import tkinter.font as tkfont

from . import APP_CLASS, APP_NAME, APP_SLUG, MODES, VERSION
from . import core, editing, engine
from . import programmer as prog
from .core import log, reduced_motion
from .engine import DISPLAY, CalcError, Num, Result, format_number
from .keypad import LAYOUTS, Key, Keypad
from .text import t
from .widgets import (MONO_FAMILIES, T, Glitch, GlitchPanel, GlitchText, IconButton, Mark,
                      Segmented, Strip, WolkButton)

BASE_ORDER = (16, 10, 8, 2)
ENTRY_SIZES = (26, 21, 17, 14, 12)
KNOWN_KEEP = 300
HEX_DIGITS = '0123456789ABCDEF'


# ─── Look ─────────────────────────────────────────────────────

def detect_scale(root: tk.Tk) -> float:
    """UI scale. Tk ignores the desktop's scaling on Linux, but Plasma publishes it to X
    programs as Xft.dpi, so read that."""
    forced = os.environ.get('SPARK_CALC_SCALE')
    if forced:
        try:
            return max(0.5, min(4.0, float(forced)))
        except ValueError:
            pass
    if os.name != 'nt' and shutil.which('xrdb'):
        try:
            out = subprocess.run(['xrdb', '-query'], capture_output=True, text=True,
                                 timeout=3).stdout
            match = re.search(r'^Xft\.dpi:\s*([0-9.]+)', out, re.M)
            if match:
                return max(1.0, min(4.0, float(match.group(1)) / 96))
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    try:
        return max(1.0, min(4.0, root.winfo_fpixels('1i') / 96))
    except tk.TclError:
        return 1.0


def pick_mono_cached(root: tk.Tk) -> str:
    """The mono font, remembered between runs: listing every font family takes a moment on
    a PC with many fonts, and the window should open at once."""
    path = os.path.join(core.cache_dir(), 'font')
    try:
        with open(path, encoding='utf-8') as f:
            name = f.read().strip()
        if name and tkfont.Font(root, family=name).actual('family') == name:
            return name
    except OSError:
        pass
    families = {n.lower(): n for n in tkfont.families(root)}
    name = next((families[w.lower()] for w in MONO_FAMILIES if w.lower() in families),
                "TkFixedFont")
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(name)
    except OSError:
        pass
    return name


def load_icon(root: tk.Misc) -> Optional[tk.PhotoImage]:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in (f'{APP_SLUG}-64.png', f'{APP_SLUG}-256.png'):
        path = os.path.join(here, 'icons', name)
        if os.path.isfile(path):
            try:
                return tk.PhotoImage(master=root, file=path)
            except tk.TclError:
                pass
    return None


def group_value(text: str, base: int) -> str:
    """How the programmer rows show a value: 0000 1111 in BIN and HEX, 1,234 in DEC."""
    if base == 10:
        return prog.group(text, 3, ',')
    return prog.group(text, 4 if base in (2, 16) else 3)


class App:
    def __init__(self, mode: Optional[str] = None):
        if os.name == 'nt':                      # Windows dev runs only: no bitmap stretching
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except (AttributeError, OSError):
                pass
        self.root = tk.Tk(className=APP_CLASS)
        self.root.withdraw()
        self.root.report_callback_exception = self._on_tk_error
        self.scale = detect_scale(self.root)
        try:
            self.root.tk.call('tk', 'scaling', self.scale * 96 / 72)
        except tk.TclError:
            pass
        self.mono = pick_mono_cached(self.root)
        self._fonts: Dict[Tuple[int, bool], tkfont.Font] = {}

        s = self.settings = core.load_settings()
        self.mode = mode if mode in MODES else (s.get('mode') if s.get('mode') in MODES
                                                 else 'standard')
        self.angle = s.get('angle') if s.get('angle') in ('deg', 'rad') else 'deg'
        self.bits = s.get('bits') if s.get('bits') in prog.BITS else 64
        self.base = s.get('base') if s.get('base') in prog.BASES else 10
        self.history_on = s.get('history', True) is not False
        self.history: List[Dict[str, Any]] = core.load_history()
        self.known: Dict[str, Num] = {}          # rounded answers shown -> their exact value
        self.ans: Num = Fraction(0)
        self.ans_prog = 0
        self.memory: Optional[Num] = None
        self.fresh = False                       # the entry holds an answer
        self.last: Optional[Result] = None
        self.recall: Optional[int] = None        # history position while using Up/Down
        self._internal = False
        self._status_id: Optional[str] = None
        self._entry_size: Optional[int] = None
        self.first_paint: Optional[float] = None
        self.pads: Dict[str, Keypad] = {}
        self.pad: Optional[Keypad] = None
        self.glitch = Glitch(self.root, enabled=not reduced_motion()
                             and s.get("glitch", True) is not False)

        self._build()
        self.set_mode(self.mode, initial=True)
        self.root.deiconify()
        self.entry.focus_set()
        self.glitch.add(self.title, self.mark, self.strip)
        self.root.after_idle(self._fill_history)

    # look helpers
    def px(self, value: float) -> int:
        return int(round(value * self.scale))

    def font(self, size: int, bold: bool = True) -> Tuple[str, int, str]:
        return (self.mono, size, "bold" if bold else "normal")

    def tkfont(self, size: int, bold: bool = True) -> tkfont.Font:
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(self.root, family=self.mono, size=size,
                                           weight="bold" if bold else "normal")
        return self._fonts[key]

    def _on_tk_error(self, exc_type, exc_value, exc_tb):
        log.error("unhandled callback error", exc_info=(exc_type, exc_value, exc_tb))
        self.set_status("SOMETHING WENT WRONG", T["pink"])
        self.glitch.now(self.title, strong=True)

    # ─── Building ─────────────────────────────────────────────

    def _build(self):
        root, px, bg = self.root, self.px, T["bg"]
        root.title(APP_NAME)
        root.configure(bg=bg)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.minsize(px(320), px(480))
        icon = load_icon(root)
        if icon is not None:
            root.iconphoto(True, icon)
            self._icon = icon

        head = tk.Frame(root, bg=bg)
        head.pack(fill="x", padx=px(14), pady=(px(10), px(8)))
        self.mark = Mark(head, px(30), bg)
        self.mark.pack(side="left")
        col = tk.Frame(head, bg=bg)
        col.pack(side="left", padx=(px(10), 0))
        self.title = GlitchText(col, "SPARK CALC", self.tkfont(14), bg)
        self.title.pack(anchor="w")
        self.status = tk.Label(col, text="", bg=bg, fg=T["accent"], font=self.font(7),
                               anchor="w")
        self.status.pack(anchor="w", padx=(px(6), 0))
        tk.Label(head, text=f"V{VERSION}", bg=T["panel"], fg=T["muted"], font=self.font(7),
                 padx=px(6), pady=px(2), highlightthickness=1,
                 highlightbackground=T["line"]).pack(side="right", anchor="n", pady=(px(4), 0))
        self.hist_button = IconButton(head, "history", self.toggle_history, px(26))
        self.hist_button.pack(side="right", anchor="n", padx=(0, px(8)))
        self.strip = Strip(root, height=px(2))
        self.strip.pack(fill="x")

        bar = tk.Frame(root, bg=bg)
        bar.pack(fill="x", padx=px(12), pady=(px(8), px(4)))
        self.modes = Segmented(bar, [(t(f'mode.{m}').upper(), m) for m in MODES], self.mode,
                               self.set_mode, self.font(8))
        self.modes.pack(side="left")
        self.opts = tk.Frame(bar, bg=bg)
        self.opts.pack(side="right")
        self.angle_seg = Segmented(self.opts, [(t('angle.deg'), 'deg'), (t('angle.rad'), 'rad')],
                                   self.angle, self.set_angle, self.font(8))
        self.bits_seg = Segmented(self.opts, [(str(b), str(b)) for b in prog.BITS],
                                  str(self.bits), lambda v: self.set_bits(int(v)), self.font(8))

        main = tk.Frame(root, bg=bg)
        main.pack(fill="both", expand=True, padx=px(12), pady=(px(4), px(12)))
        self.hist = tk.Frame(main, bg=bg, width=px(240))
        self.calc = tk.Frame(main, bg=bg)
        if self.history_on:
            self.hist.pack(side="right", fill="y", padx=(px(10), 0))
        self.calc.pack(side="left", fill="both", expand=True)
        self._build_display()
        self._build_memory()
        self.pad_holder = tk.Frame(self.calc, bg=bg)
        self.pad_holder.pack(fill="both", expand=True, pady=(px(2), 0))
        self._build_history()

        root.bind('<Return>', lambda _e: self.equals())
        root.bind('<KP_Enter>', lambda _e: self.equals())
        root.bind('<Escape>', lambda _e: self.press('clear'))
        root.bind('<F9>', lambda _e: self.press('neg'))
        for key, fn in (('1', lambda: self.set_mode('standard')),
                        ('2', lambda: self.set_mode('scientific')),
                        ('3', lambda: self.set_mode('programmer')),
                        ('h', self.toggle_history), ('w', self.close),
                        ('m', lambda: self.memory_key('store')),
                        ('p', lambda: self.memory_key('add')),
                        ('q', lambda: self.memory_key('sub')),
                        ('r', lambda: self.memory_key('recall')),
                        ('l', lambda: self.memory_key('clear'))):
            for k in sorted({key, key.upper()}):
                # on the entry too: Tk's own entry bindings use some of these (Ctrl+H)
                for widget in (root, self.entry):
                    widget.bind(f'<Control-Key-{k}>', lambda _e, fn=fn: (fn(), 'break')[1])

        geometry = self.settings.get("geometry")
        if isinstance(geometry, str) and re.fullmatch(r'\d+x\d+(\+-?\d+\+-?\d+)?', geometry):
            root.geometry(geometry)
        else:
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            w = px(620) if self.history_on else px(380)
            root.geometry(f"{min(w, int(sw * 0.9))}x{min(px(600), int(sh * 0.9))}")
        root.bind('<Expose>', self._exposed, add='+')

    def _build_display(self):
        px = self.px
        self.display = GlitchPanel(self.calc, bg=T["panel"])
        self.display.pack(fill="x")
        inner = self.display.inner
        self.line = tk.Label(inner, text="", bg=T["panel"], fg=T["muted"],
                             font=self.font(9, False), anchor="e")
        self.line.pack(fill="x", padx=px(10), pady=(px(8), 0))
        self.entry_var = tk.StringVar(master=self.root)
        self.entry = tk.Entry(inner, textvariable=self.entry_var, font=self.tkfont(ENTRY_SIZES[0]),
                              bg=T["panel"], fg=T["text"], insertbackground=T["accent"],
                              insertwidth=px(2), relief="flat", bd=0, highlightthickness=0,
                              justify="right", selectbackground=T["line2"],
                              selectforeground=T["text"], exportselection=False)
        self.entry.pack(fill="x", padx=px(10))
        self.note = tk.Label(inner, text="", bg=T["panel"], fg=T["muted"],
                             font=self.font(8, False), anchor="e", justify="right")
        self.note.pack(fill="x", padx=px(10), pady=(0, px(8)))
        self.note.bind('<Configure>', lambda e: self.note.configure(wraplength=max(50, e.width)))

        self.rows = tk.Frame(inner, bg=T["panel"])
        self.row_parts: Dict[int, Tuple[tk.Frame, tk.Label, tk.Label]] = {}
        for base in BASE_ORDER:
            row = tk.Frame(self.rows, bg=T["panel"], cursor="hand2")
            row.pack(fill="x", padx=(0, px(10)), pady=px(1))
            marker = tk.Frame(row, bg=T["panel"], width=px(3))
            marker.pack(side="left", fill="y")
            name = tk.Label(row, text=t(f'base.{prog.BASES[base]}'), bg=T["panel"],
                            fg=T["muted"], font=self.font(8), width=4, anchor="w",
                            cursor="hand2")
            name.pack(side="left", padx=(px(7), px(6)), anchor="n")
            value = tk.Label(row, text="0", bg=T["panel"], fg=T["text"],
                             font=self.font(9, False), anchor="w", justify="left",
                             cursor="hand2")
            value.pack(side="left", fill="x", expand=True)
            value.bind('<Configure>', lambda e, v=value: v.configure(wraplength=max(50, e.width)))
            for w in (row, name, value, marker):
                w.bind('<ButtonRelease-1>', lambda _e, b=base: self.set_base(b))
            self.row_parts[base] = (marker, name, value)
        tk.Frame(self.rows, bg=T["panel"], height=px(6)).pack()

        e = self.entry
        e.bind('<Key>', self._on_key)
        e.bind('<Up>', lambda _e: self._recall(-1))
        e.bind('<Down>', lambda _e: self._recall(1))
        e.bind('<Configure>', lambda _e: self._fit_font())
        for k in ('c', 'C'):
            e.bind(f'<Control-{k}>', self.copy)
        for k in ('v', 'V'):
            e.bind(f'<Control-{k}>', self.paste)
        e.bind('<<Paste>>', self.paste)
        self.entry_var.trace_add('write', self._changed)

    def _build_memory(self):
        px = self.px
        row = tk.Frame(self.calc, bg=T["bg"], height=px(30))
        row.pack(fill="x", pady=(px(6), 0))
        row.grid_propagate(False)
        row.rowconfigure(0, weight=1)
        for i, (label, action) in enumerate((('MC', 'mem:clear'), ('MR', 'mem:recall'),
                                             ('M+', 'mem:add'), ('M−', 'mem:sub'),
                                             ('MS', 'mem:store'))):
            row.columnconfigure(i, weight=1, uniform="m")
            key = Key(row, label, action, 'mem', self.press, self.font(9))
            key.grid(row=0, column=i, sticky="nsew")
        row.columnconfigure(5, weight=3)
        self.mem_label = tk.Label(row, text="", bg=T["bg"], fg=T["muted"], font=self.font(8),
                                  anchor="e")
        self.mem_label.grid(row=0, column=5, sticky="nsew", padx=(px(6), px(2)))

    def _build_history(self):
        px = self.px
        top = tk.Frame(self.hist, bg=T["bg"])
        top.pack(fill="x", pady=(0, px(4)))
        tk.Label(top, text=t('history.title').upper(), bg=T["bg"], fg=T["muted"],
                 font=self.font(8)).pack(side="left")
        WolkButton(top, t('history.clear'), self.clear_history, self.font(7),
                   padx=px(6), pady=px(1)).pack(side="right")
        self.htext = tk.Text(self.hist, bg=T["panel"], fg=T["text"], bd=0, width=1,
                             highlightthickness=1, highlightbackground=T["line"],
                             highlightcolor=T["line"], wrap="char", cursor="arrow",
                             padx=px(10), pady=px(8), takefocus=0, font=self.font(9, False),
                             selectbackground=T["panel"], inactiveselectbackground=T["panel"],
                             spacing1=0, spacing3=0)
        self.htext.pack(fill="both", expand=True)
        self.htext.tag_configure('expr', foreground=T["muted"], justify="right",
                                 font=self.font(9, False))
        self.htext.tag_configure('res', foreground=T["text"], justify="right",
                                 font=self.font(11), spacing3=px(10))
        self.htext.tag_configure('hint', foreground=T["dim"], font=self.font(8, False),
                                 spacing1=px(6))
        self.htext.tag_configure('hover', background=T["hover"])
        self.htext.configure(state="disabled")
        # bound once; the item under the pointer is found from its tag (e3: sum, r3: answer)
        self._hovered: Optional[str] = None
        self.htext.bind('<Motion>', self._history_motion)
        self.htext.bind('<Leave>', lambda _e: self._history_motion(None))
        self.htext.bind('<ButtonRelease-1>', self._history_click)
        self.hist.pack_propagate(False)

    def _exposed(self, event):
        if self.first_paint is None and event.widget is self.root:
            self.first_paint = time.monotonic()

    # ─── Modes ────────────────────────────────────────────────

    @property
    def programmer(self) -> bool:
        return self.mode == 'programmer'

    def set_mode(self, mode: str, initial: bool = False):
        if mode not in MODES:
            return
        old = self.mode
        if not initial and (old == 'programmer') != (mode == 'programmer'):
            value = self._current_value()
            self.mode = mode
            if value is None:
                self._set_entry('', fresh=False)
            elif mode == 'programmer':
                v, changed = prog.from_decimal(value, self.bits)
                self._set_entry(prog.to_base(v, self.base, self.bits), fresh=True)
                self.last = Result(v, prog.to_base(v, self.base, self.bits), True, changed)
                if changed:
                    self.set_status(t('status.wrapped', bits=self.bits), T["gold"])
            else:
                text, _ = format_number(Fraction(value))
                self._set_entry(text, fresh=True)
                self.last = Result(Fraction(value), text, True)
        self.mode = mode
        self.modes.set(mode)
        self.angle_seg.pack_forget()
        self.bits_seg.pack_forget()
        if mode == 'scientific':
            self.angle_seg.pack(side="right")
        elif mode == 'programmer':
            self.bits_seg.pack(side="right")
        if mode == 'programmer':
            self.rows.pack(fill="x")
        else:
            self.rows.pack_forget()
        if self.pad is not None:
            self.pad.pack_forget()
        if mode not in self.pads:
            self.pads[mode] = Keypad(self.pad_holder, LAYOUTS[mode], self.press,
                                     self.font(13), self.font(10), pad=self.px(2))
        self.pad = self.pads[mode]
        self.pad.pack(fill="both", expand=True)
        self._paint_base()
        self._preview()
        if not initial:
            self.glitch.now(self.title, self.display)
        self.entry.focus_set()

    def set_angle(self, angle: str):
        self.angle = angle
        self.angle_seg.set(angle)
        self._preview()

    def _current_prog_value(self) -> Optional[int]:
        if self.fresh and self.last is not None and isinstance(self.last.value, int):
            return self.last.value
        text = self.entry.get().strip()
        if not text:
            return None
        try:
            return prog.evaluate(text, self.base, self.bits, self.ans_prog).value
        except CalcError:
            return None

    def set_bits(self, bits: int):
        if bits == self.bits:
            return
        value = self._current_prog_value()
        self.bits = bits
        self.bits_seg.set(str(bits))
        if value is not None:
            w = prog.wrap(value, bits)
            text = prog.to_base(w, self.base, bits)
            self._set_entry(text, fresh=True)
            self.last = Result(w, text, True, w != value)
            if w != value:
                self.set_status(t('status.wrapped', bits=bits), T["gold"])
        self.ans_prog = prog.wrap(self.ans_prog, bits)
        self._preview()

    def set_base(self, base: int):
        if base == self.base:
            return
        value = self._current_prog_value()
        self.base = base
        if value is not None:
            text = prog.to_base(value, base, self.bits)
            self._set_entry(text, fresh=True)
            self.last = Result(value, text, True)
        self._paint_base()
        self._preview()

    def _paint_base(self):
        for base, (marker, name, _value) in self.row_parts.items():
            on = base == self.base
            marker.configure(bg=T["accent"] if on else T["panel"])
            name.configure(fg=T["accent"] if on else T["muted"])
        pad = self.pads.get('programmer')
        if pad is not None:
            allowed = HEX_DIGITS[:self.base]
            for key in pad.keys:
                kind, _, arg = key.action.partition(':')
                if kind == 'ins' and len(arg) == 1 and arg in HEX_DIGITS:
                    key.set_enabled(arg in allowed)

    def _show_rows(self, value: Optional[int]):
        for base, (_m, _n, label) in self.row_parts.items():
            text = '' if value is None else group_value(prog.to_base(value, base, self.bits), base)
            label.configure(text=text or ' ')

    # ─── Typing and keys ──────────────────────────────────────

    def _set_entry(self, text: str, fresh: bool, cursor: Optional[int] = None):
        self.fresh = fresh
        self._internal = True
        try:
            self.entry_var.set(text)
        finally:
            self._internal = False
        self.entry.icursor(len(text) if cursor is None else cursor)
        self.entry.selection_clear()
        self._show_cursor()

    def _show_cursor(self):
        cur = self.entry.index('insert')
        if cur >= len(self.entry.get()):
            self.entry.xview_moveto(1.0)
        else:
            self.entry.xview(max(0, cur - 8))

    def _changed(self, *_):
        if not self._internal:
            self.fresh = False
            self.recall = None
            self.note.configure(text="", fg=T["muted"])
        self._fit_font()
        self._preview()

    def _fit_font(self):
        width = self.entry.winfo_width() - 6
        text = self.entry.get()
        size = ENTRY_SIZES[-1]
        if width > 10:
            for size in ENTRY_SIZES:
                if self.tkfont(size).measure(text) <= width:
                    break
        if size != self._entry_size:
            self._entry_size = size
            self.entry.configure(font=self.tkfont(size))

    def _selection(self) -> Optional[Tuple[int, int]]:
        if self.entry.selection_present():
            return self.entry.index('sel.first'), self.entry.index('sel.last')
        return None

    def _on_key(self, event):
        if event.state & 0x4:                         # Control: the bindings handle it
            return None
        ch = event.char
        if ch == '=':
            self.equals()
            return 'break'
        if not ch or not ch.isprintable():
            return None
        self._flash(ch)
        if self.fresh and editing.starts_fresh(ch) and not self._selection():
            self._set_entry('', fresh=False)
        if ch in '*/':
            self.press('ins:' + ('×' if ch == '*' else '÷'))
            return 'break'
        return None

    def _flash(self, ch: str):
        if self.pad is None:
            return
        symbol = {'*': '×', '/': '÷', '-': '−'}.get(ch, ch)
        key = self.pad.key_for('ins:' + (symbol.upper() if self.programmer else symbol))
        if key is not None and key.enabled:
            key.flash()

    def press(self, action: str):
        """What a key does. Actions are described in keypad.py."""
        kind, _, arg = action.partition(':')
        if kind == 'eq':
            self.equals()
            return
        if kind == 'mem':
            self.memory_key(arg)
            return
        if kind == 'clear':
            self._set_entry('', fresh=False)
            self.line.configure(text="")
            self.note.configure(text="", fg=T["muted"])
            self._show_rows(None)
            self.entry.focus_set()
            return
        text, cur = self.entry.get(), self.entry.index('insert')
        sel = self._selection()
        p = self.programmer
        if kind == 'ins':
            word = arg.strip().lower()
            if self.fresh and word not in editing.WORD_OPS and word not in ('<<', '>>') and \
                    editing.starts_fresh(word[:1] or ' '):
                text, cur, sel = '', 0, None
            if sel:
                text, cur = editing.backspace(text, cur, sel)
            text, cur = editing.insert(text, cur, arg)
        elif kind == 'pre':
            if arg == 'root(|':
                text, cur = editing.open_call(text, cur, 'root(', p)
            else:
                text, cur = editing.prefix(text, cur, arg, p)
        elif kind == 'wrap':
            before, _, after = arg.partition('|')
            text, cur = editing.wrap(text, cur, before, after, p)
        elif kind == 'post':
            text, cur = editing.postfix(text, cur, arg, p)
        elif kind == 'neg':
            text, cur = editing.negate(text, cur, p)
        elif kind == 'ce':
            text, cur = editing.clear_entry(text, cur, p)
        elif kind == 'back':
            text, cur = editing.backspace(text, cur, sel)
        self.entry_var.set(text)
        self.entry.icursor(cur)
        self.entry.selection_clear()
        self._show_cursor()
        self.entry.focus_set()

    # ─── Working it out ───────────────────────────────────────

    def calculate(self, text: str) -> Result:
        if self.programmer:
            return prog.evaluate(text, self.base, self.bits, self.ans_prog)
        return engine.evaluate(text, self.angle, self.ans, self.known)

    def _preview(self):
        text = self.entry.get()
        if self.fresh:
            if self.programmer and self.last is not None and isinstance(self.last.value, int):
                self._show_rows(self.last.value)
            return
        if not text.strip():
            self.line.configure(text="")
            if self.programmer:
                self._show_rows(None)
            return
        try:
            r = self.calculate(text)
        except CalcError:
            self.line.configure(text="")
            return
        self.line.configure(text=("= " if r.exact else "≈ ") + r.text)
        if self.programmer:
            self._show_rows(r.value)

    def equals(self):
        text = self.entry.get().strip()
        if not text or (self.fresh and self.last is not None and text == self.last.text):
            return
        try:
            r = self.calculate(text)
        except CalcError as exc:
            self._error(exc)
            return
        self.last = r
        if self.programmer:
            self.ans_prog = r.value
        else:
            self.ans = r.value
            if not r.exact:
                self.known[r.text] = r.value
                while len(self.known) > KNOWN_KEEP:
                    self.known.pop(next(iter(self.known)))
        item = {'expr': text, 'result': r.text, 'mode': self.mode}
        if self.programmer:
            item.update(base=self.base, bits=self.bits)
        self.history.append(item)
        del self.history[:-core.HISTORY_KEEP]
        core.save_history(self.history)
        self._fill_history()
        self.line.configure(text=f"{text} {'=' if r.exact else chr(0x2248)}")
        self._set_entry(r.text, fresh=True)
        if r.wrapped:
            self.note.configure(text=t('display.wrapped', bits=self.bits), fg=T["gold"])
            self.set_status(t('status.wrapped', bits=self.bits), T["gold"])
        elif not r.exact:
            self.note.configure(text=t('display.rounded', digits=DISPLAY), fg=T["muted"])
            self.set_status(t('status.rounded', digits=DISPLAY), T["muted"])
        else:
            self.note.configure(text="", fg=T["muted"])
            self.set_status(t('status.exact'), T["accent"])
        if self.programmer:
            self._show_rows(r.value)
        self.glitch.now(self.display)

    def _error(self, exc: CalcError):
        self.note.configure(text=exc.message(), fg=T["pink"])
        self.set_status(t('status.error'), T["pink"])
        if exc.pos is not None:
            self.entry.icursor(exc.pos)
            self._show_cursor()
        self.glitch.now(self.display, self.title, strong=True)

    def _current_value(self) -> Optional[Num]:
        """The answer on show, or what the entry works out to; None if it doesn't."""
        if self.fresh and self.last is not None:
            v = self.last.value
            return Fraction(v) if isinstance(v, int) else v
        text = self.entry.get().strip()
        if not text:
            return None
        try:
            v = self.calculate(text).value
        except CalcError:
            return None
        return Fraction(v) if isinstance(v, int) else v

    # ─── Memory, copy, paste ──────────────────────────────────

    def memory_key(self, what: str):
        if what == 'clear':
            self.memory = None
        elif what == 'recall':
            if self.memory is None:
                return
            if self.programmer:
                v, _ = prog.from_decimal(self.memory, self.bits)
                text = prog.to_base(v, self.base, self.bits)
            else:
                text, exact = format_number(self.memory)
                if not exact:
                    self.known[text] = self.memory
            self.insert_value(text)
            return
        else:
            text = self.entry.get().strip()
            if not text:
                return
            try:
                value = self._current_value()
                if value is None:
                    self.calculate(text)              # raises the reason
                    return
                if what == 'store' or self.memory is None:
                    self.memory = value if what != 'sub' else -value
                elif what == 'add':
                    self.memory = engine.add(self.memory, value, 0)
                else:
                    self.memory = engine.add(self.memory, -value, 0)
            except CalcError as exc:
                self._error(exc)
                return
            self.set_status(t('status.memory'), T["accent"])
        self._paint_memory()

    def _paint_memory(self):
        if self.memory is None:
            self.mem_label.configure(text="")
            return
        text, _ = format_number(self.memory)
        self.mem_label.configure(text=t('display.memory', value=text))

    def insert_value(self, text: str):
        """A number from memory or history: replaces an answer on show, else goes in at
        the cursor (after a sign or operator)."""
        if self.fresh:
            self._set_entry('', fresh=False)
        self.press('ins:' + text)

    def copy(self, _event=None):
        if self.entry.selection_present():
            return None                                # copy the selection as usual
        if self.fresh and self.last is not None:
            text = self.last.text
        else:
            try:
                text = self.calculate(self.entry.get()).text
            except CalcError:
                self.set_status(t('status.nothing'), T["muted"])
                return 'break'
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.set_status(t('status.copied'), T["accent"])
        return 'break'

    def paste(self, _event=None):
        try:
            text = editing.clean_paste(self.root.clipboard_get())
        except tk.TclError:
            return 'break'
        if not text:
            return 'break'
        current, cur = self.entry.get(), self.entry.index('insert')
        sel = self._selection()
        if self.fresh:
            current, cur, sel = '', 0, None
        if sel:
            current, cur = editing.backspace(current, cur, sel)
        new, cur = editing.insert(current, cur, text)
        self.entry_var.set(new)
        self.entry.icursor(cur)
        self.entry.selection_clear()
        self._show_cursor()
        return 'break'

    def _recall(self, step: int):
        exprs = [h['expr'] for h in self.history if (h.get('mode') == 'programmer') ==
                 self.programmer]
        if not exprs:
            return 'break'
        if self.recall is None:
            self.recall = len(exprs) if step < 0 else len(exprs) - 1
        self.recall = max(0, min(len(exprs), self.recall + step))
        text = exprs[self.recall] if self.recall < len(exprs) else ''
        keep = self.recall
        self._set_entry(text, fresh=False)
        self.recall = keep
        self._preview()
        return 'break'

    # ─── History panel ────────────────────────────────────────

    def toggle_history(self):
        self.history_on = not self.history_on
        if self.history_on:
            self.calc.pack_forget()
            self.hist.pack(side="right", fill="y", padx=(self.px(10), 0))
            self.calc.pack(side="left", fill="both", expand=True)
            if self.root.state() == 'normal':
                w, h = self.root.winfo_width(), self.root.winfo_height()
                if w < self.px(560):
                    self.root.geometry(f"{w + self.px(250)}x{h}")
            self._fill_history()
        else:
            self.hist.pack_forget()
        self.entry.focus_set()

    def clear_history(self):
        self.history = []
        core.save_history(self.history)
        self._fill_history()
        self.glitch.now(self.title)
        self.entry.focus_set()

    def _fill_history(self):
        h = self.htext
        h.configure(state="normal")
        h.delete('1.0', 'end')
        if not self.history:
            h.insert('end', t('history.empty') + '\n', 'hint')
        for i in range(len(self.history) - 1, -1, -1):
            item = self.history[i]
            h.insert('end', item['expr'] + ' =\n', ('expr', f'e{i}'))
            h.insert('end', item['result'] + '\n', ('res', f'r{i}'))
        if self.history:
            h.insert('end', t('history.hint'), 'hint')
        h.configure(state="disabled")
        self._hovered = None

    def _history_item(self, event) -> Optional[str]:
        """'e3' or 'r3' (sum or answer of history item 3) under the pointer, or None."""
        index = self.htext.index(f'@{event.x},{event.y}')
        for tag in self.htext.tag_names(index):
            if tag[:1] in 'er' and tag[1:].isdigit():
                return tag
        return None

    def _history_motion(self, event):
        tag = self._history_item(event) if event is not None else None
        if tag == self._hovered:
            return
        self._hovered = tag
        self.htext.tag_remove('hover', '1.0', 'end')
        if tag:
            ranges = self.htext.tag_ranges(tag)
            for start, end in zip(ranges[::2], ranges[1::2]):
                self.htext.tag_add('hover', start, end)
        self.htext.configure(cursor="hand2" if tag else "arrow")

    def _history_click(self, event):
        tag = self._history_item(event)
        if tag:
            (self._use_expr if tag[0] == 'e' else self._use_result)(int(tag[1:]))

    def _match_item(self, item: Dict[str, Any]):
        mode = item.get('mode', 'standard')
        if (mode == 'programmer') != self.programmer:
            self.set_mode(mode if mode in MODES else 'standard')
        if self.programmer:
            if item.get('bits') in prog.BITS and item['bits'] != self.bits:
                self.bits = item['bits']
                self.bits_seg.set(str(self.bits))
            if item.get('base') in prog.BASES and item['base'] != self.base:
                self.base = item['base']
                self._paint_base()

    def _use_expr(self, i: int):
        if 0 <= i < len(self.history):
            item = self.history[i]
            self._match_item(item)
            self._set_entry(item['expr'], fresh=False)
            self._preview()
            self.glitch.now(self.display)
        self.entry.focus_set()

    def _use_result(self, i: int):
        if 0 <= i < len(self.history):
            item = self.history[i]
            self._match_item(item)
            self.insert_value(item['result'])
        self.entry.focus_set()

    # ─── Status, closing ──────────────────────────────────────

    def set_status(self, text: str, colour: str, revert_ms: int = 2500):
        self.status.configure(text=text, fg=colour)
        if self._status_id:
            self.root.after_cancel(self._status_id)
        self._status_id = self.root.after(revert_ms, self._status_idle)

    def _status_idle(self):
        self._status_id = None
        self.status.configure(text=t('status.ready'), fg=T["accent"])

    def close(self):
        try:                              # glitch frames and other short timers still queued
            for job in self.root.tk.splitlist(self.root.tk.call('after', 'info')):
                self.root.after_cancel(job)
        except tk.TclError:
            pass
        self.glitch._loop = None
        s = self.settings
        if self.root.state() == 'normal':
            s["geometry"] = self.root.geometry()
        s.update(mode=self.mode, angle=self.angle, bits=self.bits, base=self.base,
                 history=self.history_on, version=VERSION)
        core.save_settings(s)
        log.info("--- shutting down ---")
        self.root.destroy()

    def run(self):
        self._status_idle()
        self.root.mainloop()


# ─── Measuring ────────────────────────────────────────────────

BENCH_SUMS = ('12×3+4', '0.1+0.2', 'sin(30)+cos(60)', '2^64', '1/3*3', '√2^2',
              '(1+2)(3+4)', '100!', '200+10%', 'ln(e)')


def bench(mode: str) -> int:
    """Open the window, report the time to first paint, then type and work out a few sums
    through the window and report how long each took."""
    app = App(mode)
    wait_until = time.monotonic() + 5
    while app.first_paint is None and time.monotonic() < wait_until:
        app.root.update()
    painted = time.monotonic()
    from .cli import T0, process_age
    age = process_age()
    at_paint = None if age is None else age - (time.monotonic() - (app.first_paint or painted))
    since_import = (app.first_paint or painted) - T0
    sums = BENCH_SUMS if mode != 'programmer' else ('0x7F+1', '255 and 15', '1<<10',
                                                     '-1>>>1', '12345*678')
    times = []
    for s in sums:
        start = time.perf_counter()
        app.press('clear')
        app.entry_var.set(s)
        app.equals()
        app.root.update_idletasks()
        times.append(time.perf_counter() - start)
    app.root.update()
    app.close()
    print(f"{APP_NAME} {VERSION} bench, mode: {mode}")
    if at_paint is not None:
        print(f"first paint:  {at_paint:.2f} s after the process started")
    print(f"first paint:  {since_import:.2f} s after the app's code was loaded")
    print(f"per sum:      {1000 * sum(times) / len(times):.1f} ms on average, slowest "
          f"{1000 * max(times):.1f} ms ({len(times)} sums typed, worked out and shown)")
    return 0
