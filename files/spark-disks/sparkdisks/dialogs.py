"""The question window every change goes through. It shows what is about to be touched (device,
size, what is on it, whether it is the system's or Windows'), takes the few choices, and asks for
the device name to be typed when safety.py says the case is hard. Cancel is the default button:
Enter and Escape both cancel; the action needs a click."""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import tkinter as tk

from .text import t
from .widgets import T, Segmented, Toggle, WolkButton


@dataclass
class Field:
    key: str
    label: str
    kind: str                                   # 'choice', 'text' or 'check'
    options: Sequence[Tuple[str, str]] = ()     # (shown, value) for 'choice'
    default: Any = ''
    hint: str = ''


@dataclass
class Ask:
    title: str
    action: str                                 # the button's text
    facts: Sequence[Tuple[str, str]] = ()       # (name, value) rows
    notes: Sequence[str] = ()                   # warnings, shown in gold
    fields: Sequence[Field] = ()
    typed: str = ''                             # the text that must be typed ('' = not needed)
    danger: bool = True
    validate: Optional[Callable[[Dict[str, Any]], str]] = None   # returns an error sentence or ''
    result: Optional[Dict[str, Any]] = field(default=None, init=False)


def ask(app, spec: Ask) -> Optional[Dict[str, Any]]:
    """Show the window and wait. Returns the values (and 'confirm' when a name was typed) or
    None when cancelled."""
    win = _Window(app, spec)
    app.root.wait_window(win)
    return spec.result


class _Window(tk.Toplevel):
    def __init__(self, app, spec: Ask):
        super().__init__(app.root, bg=T["bg"])
        self.app, self.spec = app, spec
        px = app.px
        self.title(spec.title)
        self.transient(app.root)
        self.resizable(False, False)
        self.values: Dict[str, Any] = {f.key: f.default for f in spec.fields}
        self.entries: Dict[str, tk.Entry] = {}
        edge = tk.Frame(self, bg=T["pink"] if spec.danger else T["line2"], padx=1, pady=1)
        edge.pack(fill="both", expand=True)
        body = tk.Frame(edge, bg=T["panel"])
        body.pack(fill="both", expand=True)
        pad = tk.Frame(body, bg=T["panel"])
        pad.pack(fill="both", expand=True, padx=px(16), pady=px(14))
        tk.Label(pad, text=spec.title.upper(), bg=T["panel"], font=app.font(10, True),
                 fg=T["pink"] if spec.danger else T["accent"], anchor="w").pack(anchor="w")
        facts = tk.Frame(pad, bg=T["panel"])
        facts.pack(anchor="w", pady=(px(8), px(6)))
        for i, (name, value) in enumerate(spec.facts):
            tk.Label(facts, text=name, bg=T["panel"], fg=T["muted"], font=app.font(8, False),
                     anchor="w").grid(row=i, column=0, sticky="w", padx=(0, px(16)))
            tk.Label(facts, text=value, bg=T["panel"], fg=T["text"], font=app.font(9, True),
                     anchor="w", justify="left", wraplength=px(420)).grid(row=i, column=1,
                                                                          sticky="w")
        for note in spec.notes:
            tk.Label(pad, text=note, bg=T["panel"], fg=T["gold"], font=app.font(8, False),
                     justify="left", wraplength=px(520), anchor="w").pack(anchor="w",
                                                                        pady=(px(2), 0))
        if spec.fields:
            form = tk.Frame(pad, bg=T["panel"])
            form.pack(anchor="w", pady=(px(10), 0), fill="x")
            for i, f in enumerate(spec.fields):
                self._field(form, i, f)
        self.typed_var = tk.StringVar()
        if spec.typed:
            tk.Label(pad, text=t('dialog.type', name=spec.typed), bg=T["panel"], fg=T["pink"],
                     font=app.font(8, True), anchor="w", justify="left",
                     wraplength=px(520)).pack(anchor="w", pady=(px(12), px(3)))
            self.typed_entry = self._entry(pad, self.typed_var)
            self.typed_entry.pack(anchor="w", fill="x")
            self.typed_var.trace_add('write', lambda *_: self._sync())
        self.error = tk.Label(pad, text="", bg=T["panel"], fg=T["pink"], font=app.font(8, False),
                              justify="left", wraplength=px(520), anchor="w")
        self.error.pack(anchor="w", pady=(px(8), 0))
        bar = tk.Frame(pad, bg=T["panel"])
        bar.pack(anchor="e", pady=(px(10), 0))
        self.go = WolkButton(bar, spec.action, self._go, app.font(8),
                             "danger" if spec.danger else "primary", padx=px(12), pady=px(5))
        self.go.pack(side="right", padx=(px(8), 0))
        self.cancel = WolkButton(bar, t('dialog.cancel'), self.close, app.font(8), "ghost",
                                 padx=px(12), pady=px(5))
        self.cancel.pack(side="right")
        self.bind("<Escape>", lambda _e: self.close())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self._sync()
        self.update_idletasks()
        self._centre()
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.cancel.label.focus_set()           # Enter on a fresh dialog cancels

    def _centre(self) -> None:
        root = self.app.root
        x = root.winfo_rootx() + max(0, (root.winfo_width() - self.winfo_reqwidth()) // 2)
        y = root.winfo_rooty() + max(0, (root.winfo_height() - self.winfo_reqheight()) // 3)
        self.geometry(f"+{x}+{y}")

    def _entry(self, parent: tk.Misc, var: tk.StringVar) -> tk.Entry:
        return tk.Entry(parent, textvariable=var, bg=T["out_bg"], fg=T["text"],
                        insertbackground=T["accent"], relief="flat", highlightthickness=1,
                        highlightbackground=T["line2"], highlightcolor=T["accent"],
                        font=self.app.font(9, False), width=34)

    def _field(self, form: tk.Frame, row: int, f: Field) -> None:
        px = self.app.px
        tk.Label(form, text=f.label, bg=T["panel"], fg=T["muted"], font=self.app.font(8, False),
                 anchor="w").grid(row=row, column=0, sticky="nw", padx=(0, px(14)), pady=px(3))
        if f.kind == 'choice':
            widget: tk.Misc = Segmented(
                form, [(text, val) for text, val in f.options], str(f.default),
                lambda v, k=f.key: self.values.__setitem__(k, v), self.app.font(8))
        elif f.kind == 'check':
            widget = Toggle(form, f.hint or f.label, bool(f.default),
                            lambda v, k=f.key: self.values.__setitem__(k, v), self.app.font(8))
        else:
            var = tk.StringVar(value=str(f.default))
            var.trace_add('write', lambda *_a, k=f.key, v=var: self.values.__setitem__(k, v.get()))
            widget = self._entry(form, var)
            self.entries[f.key] = widget
        widget.grid(row=row, column=1, sticky="w", pady=px(3))

    def _sync(self) -> None:
        ok = not self.spec.typed or self.typed_var.get().strip() == self.spec.typed
        self.go.set_enabled(ok)

    def _go(self) -> None:
        if not self.go.enabled:
            return
        values = dict(self.values)
        if self.spec.validate is not None:
            problem = self.spec.validate(values)
            if problem:
                self.error.config(text=problem)
                self.app.glitch.now(self.app.title, strong=True)
                return
        if self.spec.typed:
            values['confirm'] = self.typed_var.get().strip()
        self.spec.result = values
        self.close()

    def close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
