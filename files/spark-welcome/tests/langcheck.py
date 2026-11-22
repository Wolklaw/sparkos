"""Checks shared by every Spark app's language tests (the same file is in each app's tests/).

table_problems(EN, FR): French keys that are missing, left over, empty, or whose {placeholders}
differ from the English. clipped(root): text that doesn't fit the widget showing it, measured
with the widget's own font, so it is checked under Xvfb in both languages."""

import string
import tkinter as tk
import tkinter.font as tkfont
from typing import Dict, Iterable, List, Tuple

TEXT_CLASSES = ('Label', 'Button', 'Checkbutton', 'Radiobutton', 'Menubutton',
                'TLabel', 'TButton', 'TCheckbutton', 'TRadiobutton', 'TMenubutton')


def fields(text: str) -> List[str]:
    """'{n} of {total:,}' -> ['n', 'total']; raises ValueError on a broken brace."""
    return sorted(name for _, name, _, _ in string.Formatter().parse(text) if name is not None)


def table_problems(en: Dict[str, str], fr: Dict[str, str]) -> List[str]:
    problems = []
    for key, text in en.items():
        if key not in fr:
            problems.append(f"missing: {key}")
            continue
        if not isinstance(fr[key], str) or (text and not fr[key].strip()):
            problems.append(f"empty: {key}")
            continue
        try:
            if fields(fr[key]) != fields(text):
                problems.append(f"placeholders differ: {key}: {fields(text)} vs {fields(fr[key])}")
        except ValueError as exc:
            problems.append(f"broken braces: {key}: {exc}")
    problems += [f"not in English: {key}" for key in fr if key not in en]
    return problems


def _px(widget: tk.Misc, option: str) -> int:
    try:
        return int(widget.winfo_fpixels(widget.cget(option)))
    except (tk.TclError, ValueError):
        return 0


def _walk(widget: tk.Misc) -> Iterable[tk.Misc]:
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def _headings(tree: tk.Misc, slack: int) -> List[str]:
    """Column titles wider than their column (the sort arrow included)."""
    from tkinter import ttk
    style = str(tree.cget('style') or 'Treeview') + '.Heading'
    name = ttk.Style(tree).lookup(style, 'font') or ttk.Style(tree).lookup('Heading', 'font')         or 'TkHeadingFont'
    try:
        font = tkfont.Font(root=tree, font=name)
    except tk.TclError:
        font = tkfont.nametofont('TkHeadingFont')
    out = []
    shown = ('#0',) if 'tree' in str(tree.cget('show')) else ()
    columns = tree.cget('displaycolumns')
    if columns in ('#all', ('#all',)):
        columns = tree.cget('columns')
    for col in shown + tuple(tree.tk.splitlist(columns) if isinstance(columns, str) else columns):
        title = str(tree.heading(col, 'text'))
        if not title.strip():
            continue
        need = font.measure(title) + 8          # a few pixels of padding at each side
        have = int(tree.column(col, 'width'))
        if need > have + slack:
            out.append(f"{tree} column {col}: {title!r} needs {need} px, has {have}")
    return out


def clipped(root: tk.Misc, canvases: Tuple[type, ...] = (), slack: int = 1) -> List[str]:
    """Every mapped text widget (and canvas of the given classes) whose text needs more room
    than it was given, and Treeview column titles wider than their column. Wrapping labels are
    left out: they grow downwards instead."""
    root.update_idletasks()
    root.update()
    out = []
    for w in _walk(root):
        try:
            if not w.winfo_ismapped():
                continue
        except tk.TclError:
            continue
        if w.winfo_class() == 'Treeview':
            out += _headings(w, slack)
            continue
        if canvases and isinstance(w, canvases):
            if w.winfo_reqwidth() > w.winfo_width() + slack:
                out.append(f"{w} ({type(w).__name__}): needs {w.winfo_reqwidth()} px, "
                           f"has {w.winfo_width()}")
            continue
        if w.winfo_class() not in TEXT_CLASSES:
            continue
        try:
            text = str(w.cget('text'))
        except tk.TclError:
            continue
        if not text.strip():
            continue
        try:
            if _px(w, 'wraplength') > 0:
                continue
        except tk.TclError:
            pass
        try:
            font = tkfont.Font(root=w, font=w.cget('font'))
        except tk.TclError:
            font = tkfont.nametofont('TkDefaultFont')
        need = max(font.measure(line) for line in text.split('\n'))
        pad = 2 * (_px(w, 'padx') + _px(w, 'borderwidth') + _px(w, 'highlightthickness'))
        if w.winfo_class().startswith('T'):
            pad = 0                     # ttk pads inside its own layout; reqwidth covers it
            need = min(need, w.winfo_reqwidth())
        have = w.winfo_width() - pad
        if need > have + slack:
            out.append(f"{w}: {text[:60]!r} needs {need} px, has {have}")
    return out
