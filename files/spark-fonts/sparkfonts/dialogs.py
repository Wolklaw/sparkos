"""Message boxes in the house style, in place of tkinter.messagebox.

Tk's own message boxes on Linux are drawn by Tk itself, in a style from the 1990s that matches
nothing else on the desktop. These take the same calls (showerror, showwarning, showinfo,
askyesno, askokcancel, with title, message, detail and parent), so a module only changes its
import:  from . import dialogs as messagebox

The same file is in every Spark app that shows message boxes; keep the copies in step."""

import os
import tkinter as tk
import tkinter.font as tkfont
from typing import List, Optional, Tuple

# BotWatch's palette, the one every Spark app is drawn in
C = {"bg": "#04090b", "panel": "#0a1517", "hover": "#12292c", "line": "#143a3d",
     "line2": "#1f6a66", "text": "#d4f1ec", "muted": "#6f9f98", "accent": "#3de8c8",
     "on_accent": "#02130f", "pink": "#ff4d8d", "gold": "#f4c95d", "ch_a": "#ff2e88",
     "ch_b": "#22d8ff"}
MONO = ("Cascadia Mono", "Cascadia Code", "JetBrains Mono", "Hack", "Noto Sans Mono",
        "DejaVu Sans Mono", "Liberation Mono", "Consolas", "Courier New")
WORDS = {'en': {'ok': "OK", 'yes': "YES", 'no': "NO", 'cancel': "CANCEL",
                'error': "ERROR", 'warning': "WARNING", 'info': "NOTE", 'question': "QUESTION"},
         'fr': {'ok': "OK", 'yes': "OUI", 'no': "NON", 'cancel': "ANNULER",
                'error': "ERREUR", 'warning': "ATTENTION", 'info': "NOTE", 'question': "QUESTION"}}
_family: Optional[str] = None


def _lang() -> str:
    forced = os.environ.get('SPARK_LANG', '').strip().lower()[:2]
    if forced in WORDS:
        return forced
    for var in ('LC_ALL', 'LC_MESSAGES', 'LANG'):
        value = os.environ.get(var, '')
        if value:
            return 'fr' if value.lower().startswith('fr') else 'en'
    return 'en'


def _word(key: str) -> str:
    return WORDS[_lang()][key]


def _mono(root: tk.Misc) -> str:
    global _family
    if _family is None:
        try:
            have = {f.lower(): f for f in tkfont.families(root)}
            _family = next((have[f.lower()] for f in MONO if f.lower() in have), "TkFixedFont")
        except tk.TclError:
            _family = "TkFixedFont"
    return _family


def _owner(parent: Optional[tk.Misc]) -> tk.Misc:
    if parent is not None:
        try:
            return parent.winfo_toplevel()
        except tk.TclError:
            pass
    root = tk._default_root      # type: ignore[attr-defined]
    if root is None:
        root = tk.Tk()
        root.withdraw()
    return root


def _show(kind: str, title: str, message: str, buttons: List[Tuple[str, object, bool]],
          parent: Optional[tk.Misc], detail: str = '', cancel_value: object = None) -> object:
    """buttons: (label, value, primary). Enter picks the primary one, Escape gives cancel_value."""
    owner = _owner(parent)
    colour = {'error': C["pink"], 'warning': C["gold"]}.get(kind, C["accent"])
    family = _mono(owner)
    try:
        scale = max(1.0, owner.winfo_fpixels('1i') / 96)
    except tk.TclError:
        scale = 1.0

    def px(v: float) -> int:
        return int(round(v * scale))

    top = tk.Toplevel(owner, bg=C["line"])
    top.withdraw()
    top.title(title or "")
    top.resizable(False, False)
    try:
        if owner.winfo_viewable():
            top.transient(owner)
    except tk.TclError:
        pass
    result: List[object] = [cancel_value]

    inner = tk.Frame(top, bg=C["panel"])
    inner.pack(fill="both", expand=True, padx=1, pady=1)
    tk.Frame(inner, bg=colour, height=px(2)).pack(fill="x")
    body = tk.Frame(inner, bg=C["panel"])
    body.pack(fill="both", expand=True, padx=px(18), pady=(px(14), px(8)))
    tk.Label(body, text="● " + _word(kind if kind in ('error', 'warning', 'info') else 'question'),
             bg=C["panel"], fg=colour, font=(family, 7, "bold"), anchor="w").pack(fill="x")
    if title:
        tk.Label(body, text=title, bg=C["panel"], fg=C["text"], font=(family, 11, "bold"),
                 anchor="w", justify="left", wraplength=px(440)).pack(fill="x", pady=(px(4), 0))
    tk.Label(body, text=message, bg=C["panel"], fg=C["text"], font=(family, 9),
             anchor="w", justify="left", wraplength=px(440)).pack(fill="x", pady=(px(8), 0))
    if detail:
        tk.Label(body, text=detail, bg=C["panel"], fg=C["muted"], font=(family, 8),
                 anchor="w", justify="left", wraplength=px(440)).pack(fill="x", pady=(px(6), 0))

    row = tk.Frame(inner, bg=C["panel"])
    row.pack(fill="x", padx=px(18), pady=(px(6), px(14)))

    def answer(value: object) -> None:
        result[0] = value
        top.destroy()

    primary_value = cancel_value
    for label, value, primary in reversed(buttons):
        idle_bg, idle_fg = (C["accent"], C["on_accent"]) if primary else (C["bg"], C["text"])
        border = tk.Frame(row, bg=C["accent"] if primary else C["line2"], padx=1, pady=1)
        button = tk.Label(border, text=label, bg=idle_bg, fg=idle_fg, font=(family, 8, "bold"),
                          padx=px(12), pady=px(4), cursor="hand2", takefocus=1)
        button.pack()
        border.pack(side="right", padx=(px(6), 0))

        def enter(_e, b=button, f=border):
            b.config(bg=C["hover"] if b.cget("bg") != C["accent"] else "#8cf5e2")
            f.config(bg=C["ch_b"])

        def leave(_e, b=button, f=border, bg=idle_bg, edge=C["accent"] if primary else C["line2"]):
            b.config(bg=bg)
            f.config(bg=edge)

        button.bind("<Enter>", enter)
        button.bind("<Leave>", leave)
        button.bind("<FocusIn>", enter)
        button.bind("<FocusOut>", leave)
        button.bind("<ButtonRelease-1>", lambda _e, v=value: answer(v))
        button.bind("<space>", lambda _e, v=value: answer(v))
        if primary:
            primary_value = value
    top.bind("<Return>", lambda _e: answer(primary_value))
    top.bind("<KP_Enter>", lambda _e: answer(primary_value))
    top.bind("<Escape>", lambda _e: answer(cancel_value))
    top.protocol("WM_DELETE_WINDOW", lambda: answer(cancel_value))

    top.update_idletasks()
    try:
        if owner.winfo_viewable():
            x = owner.winfo_rootx() + (owner.winfo_width() - top.winfo_reqwidth()) // 2
            y = owner.winfo_rooty() + (owner.winfo_height() - top.winfo_reqheight()) // 3
        else:
            x = (top.winfo_screenwidth() - top.winfo_reqwidth()) // 2
            y = (top.winfo_screenheight() - top.winfo_reqheight()) // 3
        top.geometry(f"+{max(0, x)}+{max(0, y)}")
    except tk.TclError:
        pass
    top.deiconify()
    top.lift()
    try:
        top.grab_set()
    except tk.TclError:
        pass
    top.focus_force()
    owner.wait_window(top)
    return result[0]


def showerror(title: str = '', message: str = '', **kw) -> str:
    _show('error', title, message, [(_word('ok'), 'ok', True)], kw.get('parent'),
          kw.get('detail', ''), 'ok')
    return 'ok'


def showwarning(title: str = '', message: str = '', **kw) -> str:
    _show('warning', title, message, [(_word('ok'), 'ok', True)], kw.get('parent'),
          kw.get('detail', ''), 'ok')
    return 'ok'


def showinfo(title: str = '', message: str = '', **kw) -> str:
    _show('info', title, message, [(_word('ok'), 'ok', True)], kw.get('parent'),
          kw.get('detail', ''), 'ok')
    return 'ok'


def askyesno(title: str = '', message: str = '', **kw) -> bool:
    return bool(_show('question', title, message,
                      [(_word('no'), False, False), (_word('yes'), True, True)],
                      kw.get('parent'), kw.get('detail', ''), False))


def askokcancel(title: str = '', message: str = '', **kw) -> bool:
    return bool(_show('question', title, message,
                      [(_word('cancel'), False, False), (_word('ok'), True, True)],
                      kw.get('parent'), kw.get('detail', ''), False))
