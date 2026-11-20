"""The Home and Search pages, and the app cards both use."""

from typing import TYPE_CHECKING, List, Optional

import tkinter as tk

from . import sparkapps
from .appstream import App
from .catalog import ROWS
from .text import t
from .ui import Card, chip, scrollable
from .widgets import T, GlitchText, WolkButton

if TYPE_CHECKING:
    from .app import Store


def clear(frame: tk.Misc) -> None:
    for child in frame.winfo_children():
        child.destroy()


def section(store: 'Store', parent: tk.Misc, title: str, note: str = '') -> GlitchText:
    """A section heading; its channels tear when the page opens (store.headings)."""
    px = store.px
    head = tk.Frame(parent, bg=T["bg"])
    head.pack(fill="x", padx=px(16), pady=(px(16), px(6)))
    text = GlitchText(head, title.upper(), store.tkfont(11), T["bg"], split=1)
    text.pack(side="left")
    store.headings.append(text)
    if note:
        tk.Label(head, text=note, font=store.font(8, False), bg=T["bg"], fg=T["muted"],
                 anchor="w").pack(side="left", padx=(px(8), 0), pady=(px(3), 0))
    return text


def wrap_on_resize(container: tk.Misc, labels: List[tk.Label], pad: int,
                   slack: int = 0) -> None:
    """Wrap the labels' text at the container's width. With slack, text that already wraps
    a little early is left alone (each change lays out the page again)."""
    def fit(event):
        width = max(80, event.width - pad)
        for label in labels:
            if not label.winfo_exists():
                continue
            now = int(label.cget("wraplength") or 0)
            if now != width and not (0 < now <= width <= now + slack):
                label.config(wraplength=width)
    container.bind("<Configure>", fit, add="+")


def card_wrap(store: 'Store', columns: int, icon: int) -> int:
    """How wide a card's text will be, worked out before the cards exist, so the page is
    laid out once instead of once per card."""
    px = store.px
    width = store.body.winfo_width()
    if width < px(300):
        width = store.root.winfo_width()
    if width < px(300):
        width = px(1120)
    width -= px(28) + px(18)                    # page margins and the scrollbar
    column = width // columns - px(4)
    return max(px(120), column - icon - px(20) - px(10) - px(8))


def app_card(store: 'Store', parent: tk.Misc, app: App, compact: bool = False,
             wrap: int = 0) -> Card:
    """One app: icon, name, who makes it, summary, and chips."""
    px = store.px
    card = Card(parent, command=lambda: store.open_app(app))
    inner = card.inner
    bg = inner.cget("bg")
    icon = tk.Label(inner, bg=bg, bd=0)
    icon.pack(side="left", anchor="n", padx=(px(10), px(10)), pady=px(10))
    size = px(40) if compact else px(48)
    if app.kind == 'spark':
        spark = store.spark_by_id.get(app.id)
        store.icons.put(icon, app.id, sparkapps.icon_path(spark) if spark else None, size)
    else:
        store.icons.put(icon, app.id, store.catalog.icon_path(app, size), size)
    col = tk.Frame(inner, bg=bg)
    col.pack(side="left", fill="both", expand=True, pady=px(8), padx=(0, px(10)))
    name = tk.Label(col, text=app.name, font=store.font(10), bg=bg, fg=T["text"], anchor="w",
                    justify="left", wraplength=wrap)
    name.pack(fill="x")
    who = app.developer or app.id
    dev = tk.Label(col, text=who, font=store.font(8, False), bg=bg, fg=T["muted"], anchor="w",
                   justify="left", wraplength=wrap)
    dev.pack(fill="x")
    labels = [name, dev]
    if app.summary:
        summary = tk.Label(col, text=app.summary, font=store.font(9, False), bg=bg,
                           fg=T["text"], anchor="w", justify="left", wraplength=wrap)
        summary.pack(fill="x", pady=(px(3), 0))
        labels.append(summary)
    chips = tk.Frame(col, bg=bg)
    for text, colour, filled in store.chips_for(app):
        chip(chips, text, store.font(7), colour, filled, px).pack(side="left", padx=(0, px(4)))
    if chips.winfo_children():
        chips.pack(fill="x", pady=(px(5), 0))
    wrap_on_resize(col, labels, px(4), slack=px(40))
    card.wire()
    return card


def grid_cards(store: 'Store', parent: tk.Misc, apps: List[App], columns: int = 3,
               compact: bool = False) -> tk.Frame:
    px = store.px
    grid = tk.Frame(parent, bg=T["bg"])
    grid.pack(fill="x", padx=px(14))
    for c in range(columns):
        grid.columnconfigure(c, weight=1, uniform="cards")
    wrap = card_wrap(store, columns, px(40) if compact else px(48))
    for i, app in enumerate(apps):
        card = app_card(store, grid, app, compact, wrap)
        card.grid(row=i // columns, column=i % columns, sticky="nsew", padx=px(2), pady=px(2))
    return grid


def notice(store: 'Store', parent: tk.Misc, title: str, text: str, colour: str,
           button: Optional[tuple] = None) -> Card:
    """A flat panel with a coloured title: the catalog is missing, an error, a warning."""
    px = store.px
    card = Card(parent, bg=T["panel"])
    card.edge.config(bg=colour)
    card.pack(fill="x", padx=px(16), pady=(px(10), 0))
    inner = card.inner
    tk.Label(inner, text=title.upper(), font=store.font(8), bg=T["panel"], fg=colour,
             anchor="w").pack(fill="x", padx=px(12), pady=(px(8), 0))
    body = tk.Label(inner, text=text, font=store.font(9, False), bg=T["panel"], fg=T["text"],
                    anchor="w", justify="left")
    body.pack(fill="x", padx=px(12), pady=(px(2), px(8)))
    wrap_on_resize(inner, [body], px(28))
    if button:
        label, command = button
        WolkButton(inner, label, command, store.font(8)).pack(anchor="w", padx=px(10),
                                                              pady=(0, px(10)))
    return card


class HomePage:
    def __init__(self, store: 'Store'):
        self.store = store
        self.frame, self.inner, self.canvas = scrollable(store.body, T["bg"], store.px)
        self.built_for = None

    def refresh(self, force: bool = False):
        store = self.store
        key = (store.catalog.loaded, len(store.catalog.apps), store.catalog_busy,
               store.installed_stamp, store.spark_stamp, store.catalog.error)
        if key == self.built_for and not force:
            return
        self.built_for = key
        y = self.canvas.yview()[0]
        clear(self.inner)
        px = store.px
        spark_apps = [s.as_app() for s in store.spark]
        section(store, self.inner, t('home.spark'), t('home.spark_note'))
        if spark_apps:
            grid_cards(store, self.inner, spark_apps, compact=True)
        else:
            tk.Label(self.inner, text=t('home.spark_none'), font=store.font(9, False),
                     bg=T["bg"], fg=T["muted"], anchor="w").pack(fill="x", padx=px(16))
        cat = store.catalog
        if not cat.loaded or store.catalog_busy and not cat.apps:
            notice(store, self.inner, t('catalog.reading_title'), t('catalog.reading'),
                   T["accent"])
        elif not cat.apps:
            if cat.error:
                text = t('catalog.broken', error=cat.error)
            else:
                text = t('catalog.missing')
            notice(store, self.inner, t('catalog.missing_title'), text, T["gold"],
                   (t('catalog.get'), store.refresh_catalog) if store.flatpak_ok else None)
        else:
            exclude = set()
            for key, _ids, _cats in ROWS:
                apps = cat.row(key, exclude=exclude)
                exclude.update(a.id for a in apps)
                if apps:
                    section(store, self.inner, t(f'row.{key}'))
                    grid_cards(store, self.inner, apps)
            tk.Label(self.inner, text=t('home.more', n=len(cat.apps)), font=store.font(8, False),
                     bg=T["bg"], fg=T["muted"], anchor="w").pack(fill="x", padx=px(16),
                                                                  pady=(px(14), 0))
        tk.Frame(self.inner, bg=T["bg"], height=px(20)).pack()
        if y:
            self.inner.after_idle(lambda: self.canvas.yview_moveto(y))


class SearchPage:
    LIMIT = 60

    def __init__(self, store: 'Store'):
        self.store = store
        self.frame, self.inner, self.canvas = scrollable(store.body, T["bg"], store.px)
        self.query = None
        self.results: List[App] = []

    def show(self, query: str, force: bool = False):
        if query == self.query and not force:
            return
        self.query = query
        store, px = self.store, self.store.px
        spark_apps = [s.as_app() for s in store.spark]
        results, total = store.catalog.search(query, self.LIMIT, extra=spark_apps)
        self.results = results
        clear(self.inner)
        if total:
            note = t('search.count', n=total) if total <= self.LIMIT else \
                t('search.count_more', n=total, shown=self.LIMIT)
        else:
            note = ''
        section(store, self.inner, t('search.title', query=query.strip()), note)
        if not results:
            text = t('search.none') if store.catalog.apps else t('search.no_catalog')
            tk.Label(self.inner, text=text, font=store.font(9, False), bg=T["bg"],
                     fg=T["muted"], anchor="w", justify="left").pack(fill="x", padx=px(16))
        else:
            grid_cards(store, self.inner, results, columns=2)
        tk.Frame(self.inner, bg=T["bg"], height=px(20)).pack()
        self.canvas.yview_moveto(0)

    def first(self) -> Optional[App]:
        return self.results[0] if self.results else None


