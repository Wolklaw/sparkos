"""The screens: the overview (a card per machine, a row per website) and the machine view
(services, health, tunnel, failover, logs). They only draw what app.App hands them; they never
talk to a machine themselves, so a later transport or a tablet view slots in beside them."""

import collections
import time
import tkinter as tk
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import core
from .config import USER, Machine
from .probe import (BAD, DOWN, FAILED, HOSTKEY_CHANGED, HOSTKEY_UNKNOWN, MISSING, OK,
                    RESTARTING, RUNNING, STOPPED, WARN, Problem, Result, hottest, is_taken_over,
                    level, memory_used_pct, worst_disk)
from .text import t, verdict_text
from .widgets import T, GlitchPanel, GlitchText, IconButton, Segmented, WolkButton

LEVEL_COLOUR = {OK: T["accent"], WARN: T["gold"], BAD: T["pink"], DOWN: T["pink"]}
STATE_COLOUR = {RUNNING: T["accent"], FAILED: T["pink"], RESTARTING: T["pink"],
                STOPPED: T["pink"], MISSING: T["gold"]}


class Scroll(tk.Frame):
    """A vertically scrolling area; put widgets in .inner."""

    def __init__(self, parent: tk.Misc, bg: str = T["bg"]):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.bar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview, width=10,
                                bg=T["panel2"], troughcolor=bg, activebackground=T["line2"],
                                highlightthickness=0, bd=0, relief="flat")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.window = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window,
                                                                             width=e.width))
        self.canvas.bind("<Enter>", lambda _e: self._wheel(True))
        self.canvas.bind("<Leave>", lambda _e: self._wheel(False))

    def _wheel(self, on: bool):
        if on:
            self.canvas.bind_all("<MouseWheel>", lambda e: self._scroll(-e.delta // 120 or
                                                                        (-1 if e.delta > 0 else 1)))
            self.canvas.bind_all("<Button-4>", lambda _e: self._scroll(-1))
            self.canvas.bind_all("<Button-5>", lambda _e: self._scroll(1))
        else:
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                self.canvas.unbind_all(seq)

    def _scroll(self, units: int):
        if self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(units, "units")


def clear(frame: tk.Misc):
    for child in frame.winfo_children():
        child.destroy()


def micro(parent: tk.Misc, app, text: str, fg: str = T["muted"], bg: Optional[str] = None,
          **kw) -> tk.Label:
    return tk.Label(parent, text=text.upper(), bg=bg or parent.cget("bg"), fg=fg,
                    font=app.font(7), anchor="w", **kw)


def heading(parent: tk.Misc, app, text: str, count: Optional[str] = None) -> tk.Frame:
    row = tk.Frame(parent, bg=parent.cget("bg"))
    micro(row, app, text, fg=T["text"]).pack(side="left")
    if count:
        micro(row, app, count).pack(side="left", padx=(app.px(8), 0))
    tk.Frame(row, bg=T["line"], height=1).pack(side="left", fill="x", expand=True,
                                               padx=(app.px(10), 0))
    return row


def bind_tree(widget: tk.Misc, seq: str, fn: Callable):
    widget.bind(seq, fn, add="+")
    for child in widget.winfo_children():
        if not isinstance(child, (WolkButton, IconButton)):
            bind_tree(child, seq, fn)


# ─── Overview ─────────────────────────────────────────────────

def desktop_line(app, machine: Machine, result: Optional[Result]):
    """(text, colour) for a desktop machine's card: whether someone is logged in, the screen is
    locked, or a screen share is open. None for machines without a desktop."""
    if not machine.desktop:
        return None
    share = app.shares.get(machine.name)
    if share is not None:
        return t('card.sharing', m=int(share.elapsed() // 60)), T["pink"]
    d = result.data.get('desktop') if result is not None and result.ok else None
    if not d:
        return None
    if d['state'] == 'in_use':
        return (t('desktop.in_use_user', user=d['user']) if d['user'] else
                t('desktop.in_use')), T["muted"]
    if d['state'] == 'locked':
        return t('desktop.locked'), T["gold"]
    return t('desktop.none'), T["muted"]


class MachineCard(GlitchPanel):
    def __init__(self, parent: tk.Misc, app, machine: Machine):
        super().__init__(parent, T["panel"])
        self.app, self.machine = app, machine
        px, box = app.px, self.inner
        pad = tk.Frame(box, bg=T["panel"])
        pad.pack(fill="both", expand=True, padx=px(12), pady=px(10))
        top = tk.Frame(pad, bg=T["panel"])
        top.pack(fill="x")
        self.name = tk.Label(top, text=machine.name, bg=T["panel"], fg=T["text"],
                             font=app.font(11), anchor="w")
        self.name.pack(side="left")
        self.state = micro(top, app, "")
        self.state.pack(side="right")
        tk.Label(pad, text=machine.host, bg=T["panel"], fg=T["dim"], font=app.font(8, False),
                 anchor="w").pack(fill="x")
        self.verdict = tk.Label(pad, text="", bg=T["panel"], fg=T["muted"], font=app.font(9),
                                anchor="w", justify="left", wraplength=px(300))
        self.verdict.pack(fill="x", pady=(px(8), 0))
        self.more = tk.Label(pad, text="", bg=T["panel"], fg=T["muted"],
                             font=app.font(8, False), anchor="w")
        self.more.pack(fill="x")
        self.deskrow = tk.Frame(pad, bg=T["panel"])
        self.desk = tk.Label(self.deskrow, text="", bg=T["panel"], fg=T["muted"],
                             font=app.font(8), anchor="w")
        self.desk.pack(side="left")
        self.stop = WolkButton(self.deskrow, t('action.stop'),
                               lambda: app.stop_share(machine.name), app.font(8), "danger",
                               padx=10, pady=2)
        grid = tk.Frame(pad, bg=T["panel"])
        grid.pack(fill="x", pady=(px(8), 0))
        self.grid_frame = grid
        self.values: Dict[str, tk.Label] = {}
        for i, key in enumerate(('uptime', 'load', 'memory', 'disk', 'temp')):
            micro(grid, app, t(f'card.{key}')).grid(row=0, column=i, sticky="w",
                                                     padx=(0, px(12)))
            self.values[key] = tk.Label(grid, text="—", bg=T["panel"], fg=T["text"],
                                        font=app.font(9, False), anchor="w")
            self.values[key].grid(row=1, column=i, sticky="w", padx=(0, px(12)))
        self.level = None
        bind_tree(self, "<ButtonRelease-1>", lambda _e: app.open_machine(machine.name))
        bind_tree(self, "<Enter>", lambda _e: self.configure(cursor="hand2"))

    def update(self, result: Optional[Result], found: List[Problem]):
        lvl = level(found) if result is not None else WARN
        colour = LEVEL_COLOUR[lvl]
        if result is None:
            state = t('card.waiting')
        elif not result.ok:
            state = t('card.down')
        else:
            state = t('card.up') if lvl == OK else t('card.trouble')
        self.state.config(text="● " + state, fg=colour if result is not None else T["muted"])
        self.verdict.config(text=verdict_text(found[0]) if found else t('verdict.ok'),
                            fg=colour if result is not None else T["muted"])
        extra = len(found) - 1
        self.more.config(text=t('card.more', n=extra) if extra > 0 else "")
        line = desktop_line(self.app, self.machine, result)
        if line is None:
            self.deskrow.pack_forget()
        else:
            self.desk.config(text="● " + line[0], fg=line[1])
            self.deskrow.pack(fill="x", pady=(self.app.px(4), 0), before=self.grid_frame)
            if self.machine.name in self.app.shares:
                self.stop.pack(side="right")
            else:
                self.stop.pack_forget()
        d = result.data if result is not None and result.ok else None
        if d:
            disk = worst_disk(d)
            load = d['load'][0]
            self.values['uptime'].config(text=core.duration(d['uptime_s']))
            self.values['load'].config(text="—" if load is None else f"{load:.2f}")
            self.values['memory'].config(text=core.pct(memory_used_pct(d)))
            self.values['disk'].config(text=core.pct(disk['pct']) if disk else "—")
            self.values['temp'].config(text=core.temp(hottest(d)))
        else:
            for label in self.values.values():
                label.config(text="—")
        trouble = result is not None and lvl in (BAD, DOWN, WARN)
        self.set_slip(trouble)
        if self.level is not None and lvl != self.level and lvl != OK:
            self.app.glitch.now(self, strong=lvl == DOWN)
        self.level = lvl


class SiteRow(GlitchPanel):
    def __init__(self, parent: tk.Misc, app, site):
        super().__init__(parent, T["panel"])
        px = app.px
        row = tk.Frame(self.inner, bg=T["panel"])
        row.pack(fill="x", padx=px(12), pady=px(6))
        self.dot = micro(row, app, "●")
        self.dot.pack(side="left")
        tk.Label(row, text=site.name, bg=T["panel"], fg=T["text"], font=app.font(9),
                 anchor="w").pack(side="left", padx=(px(8), 0))
        tk.Label(row, text=site.url, bg=T["panel"], fg=T["dim"], font=app.font(8, False),
                 anchor="w").pack(side="left", padx=(px(10), 0))
        self.ms = tk.Label(row, text="", bg=T["panel"], fg=T["muted"], font=app.font(9, False),
                           width=8, anchor="e")
        self.ms.pack(side="right")
        self.status = tk.Label(row, text=t('site.checking'), bg=T["panel"], fg=T["muted"],
                               font=app.font(9), anchor="e")
        self.status.pack(side="right", padx=(0, px(10)))
        self.ok: Optional[bool] = None

    def update(self, result):
        if result is None:
            return
        ok = result.ok
        colour = T["accent"] if ok else T["pink"]
        self.dot.config(fg=colour)
        self.status.config(text=f"HTTP {result.status}" if result.status else result.error,
                           fg=colour)
        self.ms.config(text=f"{result.ms:.0f} ms" if result.ms is not None else "")
        self.set_slip(not ok)
        if self.ok is not None and ok != self.ok and not ok:
            self.app_glitch()
        self.ok = ok

    def app_glitch(self):
        self.burst(True)


class OverviewView(tk.Frame):
    def __init__(self, app):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        self.scroll = Scroll(self)
        self.scroll.pack(fill="both", expand=True)
        self.cards: Dict[str, MachineCard] = {}
        self.sites: Dict[str, SiteRow] = {}
        self.order: List[str] = []
        self.site_order: List[str] = []
        self.columns = 0
        self.build()
        self.scroll.canvas.bind("<Configure>", lambda _e: self.after_idle(self.layout), add="+")

    def build(self):
        app, px, inner = self.app, self.app.px, self.scroll.inner
        clear(inner)
        self.cards.clear()
        self.sites.clear()
        self.order, self.site_order, self.columns = [], [], 0
        cfg = app.config
        if app.config_error or not cfg.machines:
            self._message(inner)
            if app.config_error or not cfg.sites:
                return
        heading(inner, app, t('overview.machines'),
                str(len(cfg.machines)) if cfg.machines else None).pack(
            fill="x", padx=px(14), pady=(px(12), px(6)))
        self.grid_box = tk.Frame(inner, bg=T["bg"])
        self.grid_box.pack(fill="x", padx=px(10))
        for m in cfg.machines:
            self.cards[m.name] = MachineCard(self.grid_box, app, m)
        heading(inner, app, t('overview.sites'),
                str(len(cfg.sites)) if cfg.sites else None).pack(
            fill="x", padx=px(14), pady=(px(16), px(6)))
        self.site_box = tk.Frame(inner, bg=T["bg"])
        self.site_box.pack(fill="x", padx=px(10), pady=(0, px(12)))
        if not cfg.sites:
            tk.Label(self.site_box, text=t('overview.no_sites'), bg=T["bg"], fg=T["muted"],
                     font=app.font(9, False), anchor="w").pack(fill="x", padx=px(4))
        for s in cfg.sites:
            self.sites[s.name] = SiteRow(self.site_box, app, s)
        self.refresh()

    def _message(self, inner):
        app, px = self.app, self.app.px
        panel = GlitchPanel(inner, T["panel"])
        panel.pack(fill="x", padx=px(14), pady=px(14))
        box = tk.Frame(panel.inner, bg=T["panel"])
        box.pack(fill="x", padx=px(16), pady=px(14))
        if app.config_error:
            title = t('overview.error_title')
            body = t('overview.error_body', error=app.config_error, path=app.config.path)
            panel.set_slip(True)
        else:
            title = t('overview.empty_title')
            body = t('overview.empty_body', path=app.config.path, example=app.example_path)
        micro(box, app, "● " + title, fg=T["pink"] if app.config_error else T["accent"]).pack(
            fill="x")
        tk.Label(box, text=body, bg=T["panel"], fg=T["text"], font=app.font(9, False),
                 justify="left", anchor="w", wraplength=px(640)).pack(fill="x",
                                                                      pady=(px(8), 0))
        self.message_panel = panel

    def refresh(self):
        app = self.app
        ranked = []
        for i, m in enumerate(app.config.machines):
            result = app.results.get(m.name)
            found = app.problems_of(m)
            card = self.cards.get(m.name)
            if card is not None:
                card.update(result, found)
            lvl = level(found) if result is not None else OK
            ranked.append((0 if lvl in (DOWN, BAD) else 1 if lvl == WARN else 2, i, m.name))
        order = [name for _, _, name in sorted(ranked)]
        if order != self.order:
            self.order = order
            self.layout(force=True)
        site_rank = []
        for i, s in enumerate(app.config.sites):
            res = app.site_results.get(s.name)
            row = self.sites.get(s.name)
            if row is not None:
                row.update(res)
            site_rank.append((0 if res is not None and not res.ok else 1, i, s.name))
        site_order = [name for _, _, name in sorted(site_rank)]
        if site_order != self.site_order:
            self.site_order = site_order
            for row in self.sites.values():
                row.pack_forget()
            for name in site_order:
                self.sites[name].pack(fill="x", pady=(0, self.app.px(4)))

    def layout(self, force: bool = False):
        if not self.cards:
            return
        width = max(1, self.scroll.canvas.winfo_width() - self.app.px(20))
        cols = max(1, min(3, width // self.app.px(340)))
        if cols == self.columns and not force:
            return
        self.columns = cols
        for card in self.cards.values():
            card.grid_forget()
        for c in range(3):
            self.grid_box.grid_columnconfigure(c, weight=1 if c < cols else 0, uniform="c"
                                               if c < cols else "")
        for i, name in enumerate(self.order):
            self.cards[name].grid(row=i // cols, column=i % cols, sticky="nsew",
                                  padx=self.app.px(4), pady=self.app.px(4))


# ─── Machine view ─────────────────────────────────────────────

class TabBar(tk.Frame):
    """Uppercase mono tabs; the open one is lit with an accent bar under it (as Spark
    Monitor's)."""

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
            self.labels[key] = (label, bar)

    def select(self, key: str):
        self.current = key
        for k, (label, bar) in self.labels.items():
            on = k == key
            label.config(fg=T["text"] if on else T["muted"])
            bar.config(bg=T["accent"] if on else T["bg"])


class MachineView(tk.Frame):
    def __init__(self, app, machine: Machine):
        super().__init__(app.body, bg=T["bg"])
        self.app, self.machine = app, machine
        px = app.px
        top = tk.Frame(self, bg=T["bg"])
        top.pack(fill="x", padx=px(12), pady=(px(10), px(4)))
        IconButton(top, "back", app.show_overview, px(26), tip=t('action.back')).pack(
            side="left", anchor="n")
        col = tk.Frame(top, bg=T["bg"])
        col.pack(side="left", padx=(px(8), 0), fill="x", expand=True)
        row = tk.Frame(col, bg=T["bg"])
        row.pack(fill="x")
        self.title = GlitchText(row, machine.name.upper(), app.tkfont(12), T["bg"])
        self.title.pack(side="left")
        self.state = micro(row, app, "")
        self.state.pack(side="left", padx=(px(10), 0))
        self.verdict = tk.Label(col, text="", bg=T["bg"], fg=T["muted"], font=app.font(9),
                                anchor="w", justify="left", wraplength=px(460))
        self.verdict.pack(fill="x", padx=(px(6), 0))
        self.sub = tk.Label(col, text=machine.host, bg=T["bg"], fg=T["dim"],
                            font=app.font(8, False), anchor="w")
        self.sub.pack(fill="x", padx=(px(6), 0))
        self.desk = tk.Label(col, text="", bg=T["bg"], fg=T["muted"], font=app.font(8),
                             anchor="w", justify="left", wraplength=px(460))
        if machine.desktop:       # their own row: the names are long, the top row is full
            self.sharebar = tk.Frame(col, bg=T["bg"])
            self.stop = WolkButton(self.sharebar, t('action.stop'),
                                   lambda: app.stop_share(machine.name), app.font(8), "danger")
            self.control = WolkButton(self.sharebar, t('action.take_control'),
                                      lambda: app.ask_share(machine, False), app.font(8),
                                      "primary")
            self.control_sudo = WolkButton(self.sharebar, t('action.take_control_sudo'),
                                           lambda: app.ask_share(machine, True), app.font(8),
                                           "danger")
        elif machine.console:     # a server with no desktop: its console is the screen
            self.sharebar = tk.Frame(col, bg=T["bg"])
            WolkButton(self.sharebar, t('action.console'), lambda: app.ask_console(machine),
                       app.font(8), "danger").pack(side="left")
        buttons = tk.Frame(top, bg=T["bg"])
        buttons.pack(side="right", anchor="n", before=col)   # buttons keep their room
        self.failback = WolkButton(buttons, t('action.failback'),
                                   lambda: app.ask_failback(machine), app.font(8), "danger")
        WolkButton(buttons, t('action.refresh'), lambda: app.refresh_machine(machine.name),
                   app.font(8)).pack(side="right", padx=(px(4), 0))
        WolkButton(buttons, t('action.report'), lambda: app.copy_report(machine),
                   app.font(8)).pack(side="right", padx=(px(4), 0))
        WolkButton(buttons, t('action.terminal'), lambda: app.ask_terminal(machine),
                   app.font(8), "primary").pack(side="right", padx=(px(4), 0))
        if 'update' in machine.allow:
            WolkButton(buttons, t('action.update'), lambda: app.ask_update(machine),
                       app.font(8)).pack(side="right", padx=(px(4), 0))
        if 'reboot' in machine.allow:
            WolkButton(buttons, t('action.reboot_menu'), lambda: app.ask_reboot(machine),
                       app.font(8), "danger").pack(side="right", padx=(px(4), 0))
        self.buttons = buttons

        tabs = [('services', t('tab.services')), ('health', t('tab.health')),
                ('tunnel', t('tab.tunnel'))]
        if machine.failover:
            tabs.append(('failover', t('tab.failover')))
        tabs.append(('logs', t('tab.logs')))
        self.tabbar = TabBar(self, tabs, self.show, app.font(9), px)
        self.tabbar.pack(fill="x", padx=px(10), pady=(px(4), 0))
        tk.Frame(self, bg=T["line"], height=1).pack(fill="x")
        self.holder = tk.Frame(self, bg=T["bg"])
        self.holder.pack(fill="both", expand=True)
        self.pages: Dict[str, tk.Frame] = {}
        self.tab: Optional[str] = None
        self.logs: Optional[LogsPage] = None
        self.show('services')

    def show(self, tab: str):
        if tab == self.tab:
            return
        if self.tab:
            self.pages[self.tab].pack_forget()
        if self.tab == 'logs' and self.logs:
            self.logs.stop()
        self.tab = tab
        self.tabbar.select(tab)
        if tab not in self.pages:
            self.pages[tab] = LogsPage(self) if tab == 'logs' else Scroll(self.holder)
            if tab == 'logs':
                self.logs = self.pages[tab]
        self.pages[tab].pack(fill="both", expand=True)
        self.refresh()
        self.app.glitch.now(self.title)

    def close(self):
        if self.logs:
            self.logs.stop()

    def refresh(self):
        app, m = self.app, self.machine
        result = app.results.get(m.name)
        found = app.problems_of(m)
        lvl = level(found) if result is not None else WARN
        colour = LEVEL_COLOUR[lvl] if result is not None else T["muted"]
        state = t('card.waiting') if result is None else t('card.down') if not result.ok else \
            t('card.up') if lvl == OK else t('card.trouble')
        self.state.config(text="● " + state, fg=colour)
        lines = [verdict_text(p) for p in found] or [t('verdict.ok')]
        self.verdict.config(text='\n'.join(lines[:4]), fg=colour)
        sub = m.host
        if result is not None:
            sub += "  ·  " + t('machine.refreshed', time=core.clock(result.at))
        self.sub.config(text=sub)
        self._desktop(result)
        if result is not None and result.ok and is_taken_over(result.data) \
                and m.failover and m.failover.failback:
            self.failback.pack(side="right", padx=(app.px(4), 0))
        else:
            self.failback.pack_forget()
        page = self.pages.get(self.tab or '')
        if page is None:
            return
        if self.tab == 'logs':
            page.refresh()
            return
        inner = page.inner
        clear(inner)
        box = tk.Frame(inner, bg=T["bg"])
        box.pack(fill="both", expand=True, padx=app.px(14), pady=app.px(10))
        if result is None or not result.ok:
            self._no_data(box, result)
            return
        getattr(self, f'_{self.tab}')(box, result)

    def _desktop(self, result: Optional[Result]):
        """The desktop line under the host, the notes that say a prompt won't be answered, and
        Stop in place of Take control while a share is open."""
        m, app = self.machine, self.app
        line = desktop_line(app, m, result)
        if line is None:
            self.desk.pack_forget()
        else:
            d = result.data.get('desktop') if result is not None and result.ok else None
            notes = [line[0]]
            if m.name not in app.shares and d:
                if d['state'] == 'locked':
                    notes.append(t('desktop.locked_note'))
                elif d['state'] == 'none':
                    notes.append(t('desktop.none_note'))
                if not d['spark_share']:
                    notes.append(t('desktop.no_tool'))
            self.desk.config(text='\n'.join(notes), fg=line[1])
            self.desk.pack(fill="x", padx=(app.px(6), 0))
        if m.console:
            self.sharebar.pack(fill="x", padx=(app.px(6), 0), pady=(app.px(6), 0))
        if not m.desktop:
            return
        self.sharebar.pack(fill="x", padx=(app.px(6), 0), pady=(app.px(6), 0))
        for b in (self.stop, self.control, self.control_sudo):
            b.pack_forget()
        if m.name in app.shares:
            self.stop.pack(side="left")
        else:
            self.control.pack(side="left")
            self.control_sudo.pack(side="left", padx=(app.px(6), 0))

    # — pages —
    def _no_data(self, box, result: Optional[Result]):
        app, px = self.app, self.app.px
        tk.Label(box, text=t('machine.no_data'), bg=T["bg"], fg=T["text"], font=app.font(9),
                 anchor="w").pack(fill="x")
        if result is None:
            return
        tk.Label(box, text=t('machine.ssh_said', message=result.message), bg=T["bg"],
                 fg=T["pink"], font=app.font(9, False), anchor="w", justify="left",
                 wraplength=px(720)).pack(fill="x", pady=(px(8), 0))
        if result.fingerprint:
            tk.Label(box, text=t('machine.fingerprint', fp=result.fingerprint), bg=T["bg"],
                     fg=T["text"], font=app.font(9, False), anchor="w").pack(fill="x",
                                                                            pady=(px(6), 0))
        if result.problem in (HOSTKEY_CHANGED, HOSTKEY_UNKNOWN):
            tk.Label(box, text=t('machine.hostkey_help'), bg=T["bg"], fg=T["muted"],
                     font=app.font(9, False), anchor="w", justify="left",
                     wraplength=px(720)).pack(fill="x", pady=(px(8), 0))

    def _services(self, box, result: Result):
        app, px, m = self.app, self.app.px, self.machine
        d = result.data
        heading(box, app, t('services.watched'), str(len(d['units']))).pack(fill="x")
        if not d['units']:
            tk.Label(box, text=t('services.none'), bg=T["bg"], fg=T["muted"],
                     font=app.font(9, False), anchor="w").pack(fill="x", pady=(px(6), 0))
        for u in d['units']:
            self._unit_row(box, u)
        watched = {(u['scope'], u['name']) for u in d['units']}
        others = [f for f in d['failed']
                  if (f['scope'], f['name'].removesuffix('.service')) not in watched]
        if others:
            heading(box, app, t('services.other_failed'), str(len(others))).pack(
                fill="x", pady=(px(14), 0))
            for f in others:
                known = m.is_known_failed(f['name'])
                row = tk.Frame(box, bg=T["bg"])
                row.pack(fill="x", pady=(px(4), 0))
                micro(row, app, t(f"scope.{f['scope']}")).pack(side="left")
                tk.Label(row, text=f['name'], bg=T["bg"], fg=T["dim"] if known else T["pink"],
                         font=app.font(9), anchor="w").pack(side="left", padx=(px(8), 0))
                if known:
                    tk.Label(row, text=t('services.known_failed'), bg=T["bg"], fg=T["dim"],
                             font=app.font(8, False)).pack(side="left", padx=(px(8), 0))

    def _unit_row(self, box, u):
        app, px, m = self.app, self.app.px, self.machine
        trouble = u['state'] != RUNNING and not m.is_takeover_unit(u['scope'], u['name'])
        panel = GlitchPanel(box, T["panel"])
        panel.pack(fill="x", pady=(px(6), 0))
        panel.set_slip(trouble)
        inner = tk.Frame(panel.inner, bg=T["panel"])
        inner.pack(fill="x", padx=px(10), pady=px(6))
        row = tk.Frame(inner, bg=T["panel"])
        row.pack(fill="x")
        micro(row, app, t(f"scope.{u['scope']}"), fg=T["dim"]).pack(side="left")
        tk.Label(row, text=u['name'], bg=T["panel"], fg=T["text"], font=app.font(10),
                 anchor="w").pack(side="left", padx=(px(8), 0))
        colour = STATE_COLOUR.get(u['state'], T["muted"])
        if m.is_takeover_unit(u['scope'], u['name']) and u['state'] == STOPPED:
            colour = T["muted"]
        micro(row, app, "● " + t(f"state.{u['state']}"), fg=colour).pack(side="left",
                                                                       padx=(px(10), 0))
        facts = []
        if u['since_s'] is not None:
            facts.append(t('services.for', time=core.duration(u['since_s'])))
        if u['restarts']:
            facts.append(t('services.restarts', n=int(u['restarts'])))
        tk.Label(row, text="  ·  ".join(facts), bg=T["panel"], fg=T["muted"],
                 font=app.font(8, False)).pack(side="left", padx=(px(10), 0))
        if m.can_restart(u['scope'], u['name']):
            WolkButton(row, t('action.restart'),
                       lambda s=u['scope'], n=u['name']: app.ask_restart(m, s, n),
                       app.font(7), "danger", padx=8, pady=2).pack(side="right")
        WolkButton(row, t('action.logs'),
                   lambda s=u['scope'], n=u['name']: self.open_logs(s, n),
                   app.font(7), padx=8, pady=2).pack(side="right", padx=(0, px(4)))
        log_text = '\n'.join(u['log']) if u['log'] else t('services.no_log')
        tk.Label(inner, text=log_text, bg=T["panel"], fg=T["muted"] if u['log'] else T["dim"],
                 font=app.font(8, False), anchor="w", justify="left").pack(fill="x",
                                                                         pady=(px(4), 0))

    def _kv(self, box, rows: List[Tuple[str, str]], colours: Optional[Dict[int, str]] = None):
        app, px = self.app, self.app.px
        grid = tk.Frame(box, bg=T["bg"])
        grid.pack(fill="x", pady=(px(6), 0))
        for i, (k, v) in enumerate(rows):
            micro(grid, app, k).grid(row=i, column=0, sticky="nw", padx=(0, px(16)),
                                     pady=px(2))
            tk.Label(grid, text=v, bg=T["bg"], fg=(colours or {}).get(i, T["text"]),
                     font=app.font(9, False), anchor="w", justify="left").grid(
                row=i, column=1, sticky="w", pady=px(2))

    def _health(self, box, result: Result):
        app, d = self.app, result.data
        mem = d['memory']
        load = ' '.join('—' if v is None else f"{v:.2f}" for v in d['load'])
        swap_used = (mem['swap_total'] or 0) - (mem['swap_free'] or 0)
        rows = [
            (t('health.os'), f"{d['os'] or '?'} · {d['kernel'] or '?'}"),
            (t('health.uptime'), core.duration(d['uptime_s'])),
            (t('health.boot'), core.day_clock(result.at - d['uptime_s'])
             if d['uptime_s'] else "—"),
            (t('health.cpu'), f"{core.pct(d['cpu_pct'])} · "
                              f"{t('health.cpus', n=int(d['cpus'] or 0))}"),
            (t('health.load'), load),
            (t('health.memory'), t('health.used_of',
                                   used=core.size((mem['total'] or 0) - (mem['available'] or 0)),
                                   total=core.size(mem['total']))),
            (t('health.swap'), t('health.used_of', used=core.size(swap_used),
                                 total=core.size(mem['swap_total']))),
        ]
        colours = {}
        for disk in d['disks']:
            if disk['pct'] is not None and disk['pct'] >= 90:
                colours[len(rows)] = T["pink"]
            rows.append((f"{t('health.disks')} {disk['mount']}",
                         t('health.free_of', pct=core.pct(disk['pct']),
                           free=core.size(disk['free']), total=core.size(disk['size']))))
        for tmp in sorted(d['temps'], key=lambda x: -x['c'])[:6]:
            rows.append((f"{t('health.temps')} {tmp['name']}", core.temp(tmp['c'])))
        rates = app.net_rates(self.machine.name)
        for n in d['net']:
            r = rates.get(n['iface'])
            value = t('health.rx_tx', rx=core.rate(r[0]), tx=core.rate(r[1])) if r \
                else t('health.rate_next')
            rows.append((f"{t('health.network')} {n['iface']}", value))
        pk = d['packages']
        if pk['updates'] is not None:
            rows.append((t('health.updates'),
                         t('health.updates_n', n=int(pk['updates']),
                           security=int(pk['security'] or 0)) if pk['updates']
                         else t('health.updates_none')))
        if pk['reboot'] is not None:
            colours[len(rows)] = T["gold"]
            rows.append((t('health.reboot'),
                         t('health.reboot_needed', day=core.date(pk['reboot']['since']),
                           pkgs=', '.join(pk['reboot']['pkgs']) or '?')))
        self._kv(box, rows, colours)

    def _tunnel(self, box, result: Result):
        app, m = self.app, self.machine
        tun = result.data['tunnel']
        if not m.tunnel or tun is None:
            tk.Label(box, text=t('tunnel.none'), bg=T["bg"], fg=T["muted"],
                     font=app.font(9, False), anchor="w").pack(fill="x")
            return
        conns = tun['connections']
        if tun['active'] != 'active':
            state, colour = t('tunnel.down'), T["pink"]
        elif conns == 0:
            state, colour = t('tunnel.no_conns'), T["pink"]
        else:
            state, colour = t('tunnel.connected'), T["accent"]
        if m.is_takeover_unit(*m.tunnel) and tun['active'] != 'active':
            colour = T["muted"]
        rows = [(t('tunnel.state'), f"{state} ({tun['unit']}: {tun['active']})"),
                (t('tunnel.connections'), t('tunnel.conns_unknown') if conns is None
                 else str(int(conns))),
                (t('tunnel.hostnames'), '\n'.join(m.tunnel_hostnames) or
                 t('tunnel.no_hostnames'))]
        self._kv(box, rows, {0: colour})

    def _failover(self, box, result: Result):
        app, px, m = self.app, self.app.px, self.machine
        fo = result.data['failover'] or {}
        if not fo.get('active_unit'):
            state, note, colour = "?", t('failover.unknown'), T["gold"]
        elif is_taken_over(result.data):
            state, note, colour = (t('failover.taken_over'), t('failover.taken_over_note'),
                                   T["pink"])
        else:
            state, note, colour = (t('failover.standing_by'), t('failover.standing_by_note'),
                                   T["accent"])
        micro(box, app, "● " + state, fg=colour).pack(fill="x")
        tk.Label(box, text=note, bg=T["bg"], fg=T["text"], font=app.font(9, False),
                 anchor="w").pack(fill="x", pady=(px(4), 0))
        heading(box, app, t('failover.failback')).pack(fill="x", pady=(px(14), 0))
        cmd = m.failover.failback if m.failover else ''
        tk.Label(box, text=cmd or t('failover.no_failback'), bg=T["bg"],
                 fg=T["text"] if cmd else T["muted"], font=app.font(9, False),
                 anchor="w").pack(fill="x", pady=(px(4), 0))
        heading(box, app, t('failover.incidents'), str(len(fo.get('incidents', [])))).pack(
            fill="x", pady=(px(14), 0))
        if not fo.get('incidents'):
            tk.Label(box, text=t('failover.no_incidents'), bg=T["bg"], fg=T["muted"],
                     font=app.font(9, False), anchor="w").pack(fill="x", pady=(px(4), 0))
        for inc in fo.get('incidents', []):
            row = tk.Frame(box, bg=T["bg"])
            row.pack(fill="x", pady=(px(4), 0))
            tk.Label(row, text=core.day_clock(inc['mtime']), bg=T["bg"], fg=T["muted"],
                     font=app.font(8, False)).pack(side="left")
            tk.Label(row, text=inc['name'], bg=T["bg"], fg=T["text"], font=app.font(9)).pack(
                side="left", padx=(px(8), 0))
            tk.Label(row, text=inc['first_line'], bg=T["bg"], fg=T["muted"],
                     font=app.font(8, False), anchor="w").pack(side="left", padx=(px(8), 0))
        heading(box, app, t('failover.netmon')).pack(fill="x", pady=(px(14), 0))
        lines = fo.get('netmon') or []
        tk.Label(box, text='\n'.join(lines) if lines else t('failover.no_netmon'), bg=T["bg"],
                 fg=T["muted"], font=app.font(8, False), anchor="w", justify="left").pack(
            fill="x", pady=(px(4), 0))

    def open_logs(self, scope: str, unit: str):
        self.show('logs')
        if self.logs:
            self.logs.follow(scope, unit)


class LogsPage(tk.Frame):
    """A live tail of one unit's journal, with a filter box. The tail runs only while this
    page is open."""

    def __init__(self, view: MachineView):
        super().__init__(view.holder, bg=T["bg"])
        self.view, self.app = view, view.app
        app, px, m = self.app, self.app.px, view.machine
        bar = tk.Frame(self, bg=T["bg"])
        bar.pack(fill="x", padx=px(14), pady=(px(10), px(6)))
        micro(bar, app, t('logs.unit')).pack(side="left")
        units = [(f"{s}:{u}", f"{s}:{u}") for s, u in m.watched()]
        self.picker = Segmented(bar, [(u.split(':', 1)[1], v) for u, v in units] or
                                [("—", "")], "", self._picked, app.font(8)) if units else None
        if self.picker:
            self.picker.pack(side="left", padx=(px(8), 0))
        self.toggle = WolkButton(bar, t('logs.stop'), self.stop, app.font(8), padx=8, pady=2)
        micro(bar, app, t('logs.filter')).pack(side="left", padx=(px(16), 0))
        self.filter = tk.StringVar()
        entry = tk.Entry(bar, textvariable=self.filter, bg=T["panel"], fg=T["text"],
                         insertbackground=T["accent"], relief="flat", font=app.font(9, False),
                         highlightthickness=1, highlightbackground=T["line"],
                         highlightcolor=T["accent"], width=24)
        entry.pack(side="left", padx=(px(8), 0))
        self.filter.trace_add("write", lambda *_a: self.redraw())
        self.status = micro(self, app, t('logs.pick'))
        self.status.pack(fill="x", padx=px(14))
        self.text = tk.Text(self, bg=T["out_bg"], fg=T["text"], font=app.font(8, False),
                            relief="flat", highlightthickness=1, highlightbackground=T["line"],
                            wrap="none", state="disabled")
        self.text.pack(fill="both", expand=True, padx=px(14), pady=(px(6), px(12)))
        self.lines: collections.deque = collections.deque(maxlen=2000)
        self.tail = None
        self.unit: Optional[Tuple[str, str]] = None

    def _picked(self, value: str):
        if value:
            scope, unit = value.split(':', 1)
            self.follow(scope, unit)

    def follow(self, scope: str, unit: str):
        self.stop()
        self.unit = (scope, unit)
        if self.picker:
            self.picker.set(f"{scope}:{unit}")
        self.lines.clear()
        self.redraw()
        self.status.config(text=t('logs.following', unit=unit).upper(), fg=T["accent"])
        self.toggle.pack(side="left", padx=(self.app.px(8), 0))
        self.tail = self.app.start_tail(self.view.machine, scope, unit, self.add)

    def add(self, line: str):
        self.lines.append(line)
        needle = self.filter.get().strip().lower()
        if needle and needle not in line.lower():
            return
        self.text.configure(state="normal")
        self.text.insert("end", line + "\n")
        if int(self.text.index('end-1c').split('.')[0]) > 2000:
            self.text.delete('1.0', '200.0')
        self.text.configure(state="disabled")
        self.text.see("end")

    def redraw(self):
        needle = self.filter.get().strip().lower()
        self.text.configure(state="normal")
        self.text.delete('1.0', 'end')
        shown = [ln for ln in self.lines if not needle or needle in ln.lower()]
        if shown:
            self.text.insert('end', '\n'.join(shown) + '\n')
        self.text.configure(state="disabled")
        self.text.see("end")

    def stop(self):
        if self.tail is not None:
            self.tail.stop()
            self.tail = None
            self.status.config(text=t('logs.pick').upper(), fg=T["muted"])
            self.toggle.pack_forget()

    def refresh(self):
        pass
