"""Spark Controller's own widgets: the tab bar and the table look. The shared ones are in
widgets.py (copied from Spark Monitor, which copied them from Spark Media)."""

from typing import Callable, Dict, Sequence, Tuple

import tkinter as tk
from tkinter import ttk

from .widgets import T


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
