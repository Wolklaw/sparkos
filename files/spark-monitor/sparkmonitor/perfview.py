"""The Performance tab: a list of devices on the left with small live graphs, and the chosen
one large on the right, with its numbers."""

import math
import os
from typing import Callable, Dict, List, Optional, Tuple

import tkinter as tk

from . import core
from .source import read_line
from .text import t
from .ui import PALETTE, Graph
from .widgets import T, GlitchText

Stat = Tuple[str, Callable[[], str]]


class SideItem(tk.Frame):
    def __init__(self, view, key: str, colour: str, title: str):
        app = view.app
        px = app.px
        super().__init__(view.side, bg=T["bg"], cursor="hand2")
        self.key, self.view = key, view
        self.edge = tk.Frame(self, bg=T["bg"], width=max(2, px(3)))
        self.edge.pack(side="left", fill="y")
        self.graph = Graph(self, colour, height=px(38), width=px(62), grid=False,
                           maximum=100.0 if not key.startswith('net') else None, floor=1024)
        self.graph.pack(side="left", padx=(px(8), px(10)), pady=px(6))
        col = tk.Frame(self, bg=T["bg"])
        col.pack(side="left", fill="x", expand=True)
        self.title = tk.Label(col, text=title, bg=T["bg"], fg=T["text"], font=app.font(9),
                              anchor="w")
        self.title.pack(fill="x")
        self.sub = tk.Label(col, text="", bg=T["bg"], fg=T["muted"], font=app.font(8, False),
                            anchor="w", justify="left")
        self.sub.pack(fill="x")
        for w in (self, self.edge, col, self.title, self.sub, self.graph):
            w.bind("<ButtonRelease-1>", lambda _e: view.select(key))
        self.bind("<Enter>", lambda _e: self.paint(hover=True))
        self.bind("<Leave>", lambda _e: self.paint())
        self.selected = False

    def paint(self, hover: bool = False):
        bg = T["hover"] if (self.selected or hover) else T["bg"]
        for w in (self, self.title.master, self.title, self.sub):
            w.config(bg=bg)
        self.edge.config(bg=T["accent"] if self.selected else bg)

    def set_sub(self, text: str):
        if self.sub.cget('text') != text:
            self.sub.config(text=text)


class Pane(tk.Frame):
    """One device, large. Built the first time it is chosen."""

    def __init__(self, view, key: str, title: str, model: str, colour: str,
                 series: List[str], stats: List[Stat], maximum: Optional[float] = 100.0,
                 label: Optional[Callable[[float], str]] = None,
                 extra: Optional[Tuple[str, List[str], Optional[float],
                                       Optional[Callable[[float], str]]]] = None,
                 threads: int = 0, note: str = ""):
        app = view.app
        px = app.px
        super().__init__(view.right, bg=T["bg"])
        self.app, self.series, self.stats_spec = app, series, stats
        head = tk.Frame(self, bg=T["bg"])
        head.pack(fill="x")
        self.title = GlitchText(head, title.upper(), app.tkfont(15), T["bg"])
        self.title.pack(side="left")
        self.model = tk.Label(head, text=model, bg=T["bg"], fg=T["muted"],
                              font=app.font(9, False), anchor="e")
        self.model.pack(side="right", anchor="s", pady=(0, px(4)))
        cap = tk.Label(self, text=t('perf.utilization').upper() + " · 60 S" if maximum else
                       "60 S", bg=T["bg"], fg=T["dim"], font=app.font(7), anchor="w")
        cap.pack(fill="x", pady=(px(4), px(2)))
        self.graph = Graph(self, colour, height=px(190), width=px(400), maximum=maximum,
                           colour2=T["pink"] if len(series) > 1 else None,
                           label=label or (lambda v: core.pct(v, 0)), font=app.font(7, False),
                           floor=1024)
        self.graph.pack(fill="both", expand=True)
        self.extra_graph = None
        self.extra_series: List[str] = []
        if extra:
            caption, ex_series, ex_max, ex_label = extra
            tk.Label(self, text=caption.upper() + " · 60 S", bg=T["bg"], fg=T["dim"],
                     font=app.font(7), anchor="w").pack(fill="x", pady=(px(8), px(2)))
            self.extra_graph = Graph(self, colour, height=px(80), width=px(400),
                                     maximum=ex_max,
                                     colour2=T["pink"] if len(ex_series) > 1 else None,
                                     label=ex_label or (lambda v: core.pct(v, 0)),
                                     font=app.font(7, False), floor=1024)
            self.extra_graph.pack(fill="x")
            self.extra_series = ex_series
        self.thread_graphs: List[Graph] = []
        if threads:
            tk.Label(self, text=t('perf.per_thread').upper(), bg=T["bg"], fg=T["dim"],
                     font=app.font(7), anchor="w").pack(fill="x", pady=(px(8), px(2)))
            grid = tk.Frame(self, bg=T["bg"])
            grid.pack(fill="x")
            cols = min(8, threads)
            for i in range(threads):
                g = Graph(grid, colour, height=px(34), width=px(60), grid=False)
                g.grid(row=i // cols, column=i % cols, sticky="ew", padx=(0, px(3)),
                       pady=(0, px(3)))
                self.thread_graphs.append(g)
            for c in range(cols):
                grid.columnconfigure(c, weight=1, uniform="t")
        if note:
            tk.Label(self, text=note, bg=T["bg"], fg=T["gold"], font=app.font(8, False),
                     anchor="w", justify="left", wraplength=px(560)).pack(fill="x",
                                                                           pady=(px(6), 0))
        self.grid_frame = tk.Frame(self, bg=T["bg"])
        self.grid_frame.pack(fill="x", pady=(px(10), 0))
        self.values: List[tk.Label] = []
        per_col = max(1, math.ceil(len(stats) / 3))
        for i, (label, _fn) in enumerate(stats):
            col, row = divmod(i, per_col)
            cell = tk.Frame(self.grid_frame, bg=T["bg"])
            cell.grid(row=row, column=col, sticky="w", padx=(0, px(26)), pady=(0, px(6)))
            tk.Label(cell, text=label.upper(), bg=T["bg"], fg=T["muted"], font=app.font(7),
                     anchor="w").pack(fill="x")
            value = tk.Label(cell, text="—", bg=T["bg"], fg=T["text"], font=app.font(11),
                             anchor="w")
            value.pack(fill="x")
            self.values.append(value)

    def refresh(self):
        hist = self.app.hist
        self.graph.set(*[hist.get(k, ()) for k in self.series])
        if self.extra_graph is not None:
            self.extra_graph.set(*[hist.get(k, ()) for k in self.extra_series])
        for i, g in enumerate(self.thread_graphs):
            g.set(hist.get(f'cpu{i}', ()))
        for (_label, fn), widget in zip(self.stats_spec, self.values):
            try:
                text = fn()
            except (AttributeError, IndexError, TypeError, ValueError, ZeroDivisionError):
                text = "—"
            if widget.cget('text') != text:
                widget.config(text=text)


class PerfView(tk.Frame):
    def __init__(self, app):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        px = app.px
        self.side = tk.Frame(self, bg=T["bg"], width=px(250))
        self.side.pack(side="left", fill="y", padx=(px(6), 0), pady=px(10))
        tk.Frame(self, bg=T["line"], width=1).pack(side="left", fill="y", pady=px(10))
        self.right = tk.Frame(self, bg=T["bg"])
        self.right.pack(side="left", fill="both", expand=True, padx=px(18), pady=px(12))
        self.items: Dict[str, SideItem] = {}
        self.panes: Dict[str, Pane] = {}
        self.current: Optional[str] = None
        self._build_side()
        wanted = app.settings.get('perf_item')
        self.select(wanted if wanted in self.items else 'cpu', glitch=False)

    def _build_side(self):
        sysm = self.app.system
        entries = [('cpu', PALETTE['cpu'], t('perf.cpu')), ('mem', PALETTE['mem'],
                                                           t('perf.memory'))]
        for i, _g in enumerate(sysm.gpus):
            entries.append((f'gpu{i}', PALETTE['gpu'], t('perf.gpu', n=i)))
        for i, d in enumerate(sysm.disks):
            entries.append((f'disk{i}', PALETTE['disk'], t('perf.disk', n=i, name=d.name)))
        for i, n in enumerate(sysm.nics):
            entries.append((f'net{i}', PALETTE['net'], n.kind))
        for key, colour, title in entries:
            item = SideItem(self, key, colour, title)
            item.pack(fill="x")
            self.items[key] = item

    def select(self, key: str, glitch: bool = True):
        if key not in self.items:
            return
        if self.current in self.items:
            self.items[self.current].selected = False
            self.items[self.current].paint()
        if self.current in self.panes:
            self.panes[self.current].pack_forget()
        self.current = key
        self.app.settings['perf_item'] = key
        self.items[key].selected = True
        self.items[key].paint()
        if key not in self.panes:
            self.panes[key] = self._make_pane(key)
        pane = self.panes[key]
        pane.pack(fill="both", expand=True)
        pane.refresh()
        if glitch:
            self.app.glitch.now(pane.title)

    # — the panes —
    def _make_pane(self, key: str) -> Pane:
        app, sysm = self.app, self.app.system

        def snap():
            return sysm.last

        if key == 'cpu':
            stats: List[Stat] = [
                (t('perf.utilization'), lambda: core.pct(snap().cpu, 0)),
                (t('perf.speed'), lambda: core.mhz(snap().cpu_mhz)),
                (t('perf.max_speed'), lambda: core.mhz(sysm.cpu_max_mhz)),
                (t('perf.temperature'), lambda: core.temp(snap().cpu_temp)
                 if sysm.cpu_temp_path else t('perf.not_readable')),
                (t('perf.processes'), lambda: str(app.process_count())),
                (t('perf.threads'), lambda: str(sysm.threads)),
                (t('perf.uptime'), lambda: core.uptime(app.uptime())),
            ]
            return Pane(self, key, t('perf.cpu'), sysm.model, PALETTE['cpu'], ['cpu'], stats,
                        threads=sysm.threads)
        if key == 'mem':
            def zram():
                m = snap().mem
                if m.zram_data is None:
                    return "—"
                return f"{core.size(m.zram_data)} → {core.size(m.zram_compressed)}"
            stats = [
                (t('perf.in_use'), lambda: core.size(snap().mem.used)),
                (t('perf.available'), lambda: core.size(snap().mem.available)),
                (t('perf.cached'), lambda: core.size(snap().mem.cached)),
                (t('perf.swap'), lambda: f"{core.size(snap().mem.swap_used)} / "
                                         f"{core.size(snap().mem.swap_total)}"),
                ("zram", zram),
            ]
            total = core.size(sysm.last.mem.total if sysm.last else 0)
            return Pane(self, key, t('perf.memory'), total, PALETTE['mem'], ['mem'], stats)
        if key.startswith('gpu'):
            i = int(key[3:])
            g = sysm.gpus[i]
            stats = [
                (t('perf.utilization'), lambda: core.pct(g.busy, 0) if g.busy is not None
                 else t('perf.not_readable')),
                (t('perf.vram'), lambda: f"{core.size(g.vram_used)} / {core.size(g.vram_total)}"
                 if g.vram_total else t('perf.not_readable')),
                (t('perf.gtt'), lambda: f"{core.size(g.gtt_used)} / {core.size(g.gtt_total)}"
                 if g.gtt_total else "—"),
                (t('perf.clock'), lambda: core.mhz(g.clock_mhz)),
                (t('perf.temperature'), lambda: core.temp(g.temp)),
                (t('perf.hotspot'), lambda: core.temp(g.temp_hot)),
                (t('perf.power'), lambda: core.watts(g.power_w)),
                (t('perf.fan'), lambda: f"{g.fan_rpm} RPM" if g.fan_rpm is not None else
                 core.pct(g.fan_pct, 0) if g.fan_pct is not None else "—"),
            ]
            vram = (t('perf.vram'), [f'gpu{i}.vram'], 100.0, None) if g.vram_total else None
            return Pane(self, key, t('perf.gpu', n=i), g.name, PALETTE['gpu'], [f'gpu{i}'],
                        stats, extra=vram, note=g.note)
        if key.startswith('disk'):
            i = int(key[4:])
            d = sysm.disks[i]

            def usage():
                if not d.usage:
                    return "—"
                return "  ".join(f"{m} {core.size(u, 0)}/{core.size(tot, 0)}"
                                 for m, u, tot in d.usage[:3])
            stats = [
                (t('perf.active'), lambda: core.pct(d.active, 0)),
                (t('perf.read'), lambda: core.rate(d.read_bps)),
                (t('perf.write'), lambda: core.rate(d.write_bps)),
                (t('perf.capacity'), lambda: core.size(d.size)),
                (t('perf.type'), lambda: d.kind),
                (t('perf.temperature'), lambda: core.temp(d.temp) if d.temp_path
                 else t('perf.not_readable')),
                (t('perf.in_use'), usage),
            ]
            return Pane(self, key, t('perf.disk', n=i, name=d.name), d.model, PALETTE['disk'],
                        [f'disk{i}.active'], stats,
                        extra=(f"{t('perf.read')} / {t('perf.write')}",
                               [f'disk{i}.read', f'disk{i}.write'], None, core.rate))
        i = int(key[3:])
        n = sysm.nics[i]
        stats = [
            (t('perf.send'), lambda: core.bits(n.tx_bps)),
            (t('perf.receive'), lambda: core.bits(n.rx_bps)),
            (t('perf.link'), lambda: f"{n.speed_mbps} Mbps" if n.speed_mbps else "—"),
            (t('perf.state'), lambda: t('perf.up') if n.up else t('perf.down')),
            (t('perf.type'), lambda: n.kind),
        ]
        return Pane(self, key, n.kind, n.name, PALETTE['net'], [f'net{i}.rx', f'net{i}.tx'],
                    stats, maximum=None, label=core.bits)

    # — every second —
    def refresh(self):
        app, snap = self.app, self.app.system.last
        if snap is None:
            return
        hist = app.hist
        for key, item in self.items.items():
            if key == 'cpu':
                item.graph.set(hist['cpu'])
                item.set_sub(f"{core.pct(snap.cpu, 0)}  {core.mhz(snap.cpu_mhz)}")
            elif key == 'mem':
                m = snap.mem
                item.graph.set(hist['mem'])
                item.set_sub(f"{core.size(m.used)} / {core.size(m.total)} "
                             f"({m.percent:.0f}%)")
            elif key.startswith('gpu'):
                g = snap.gpus[int(key[3:])]
                item.graph.set(hist[key])
                busy = core.pct(g.busy, 0) if g.busy is not None else "—"
                item.set_sub(f"{_short(g.name)}\n{busy}" +
                             (f"  {core.temp(g.temp)}" if g.temp is not None else ""))
            elif key.startswith('disk'):
                d = snap.disks[int(key[4:])]
                item.graph.set(hist[f'{key}.active'])
                item.set_sub(f"{d.kind}\n{core.pct(d.active, 0)}")
            else:
                n = snap.nics[int(key[3:])]
                item.graph.set(hist[f'{key}.rx'], hist[f'{key}.tx'])
                item.set_sub(f"{n.name}\nS: {core.bits(n.tx_bps)}  R: {core.bits(n.rx_bps)}")
        pane = self.panes.get(self.current)
        if pane is not None:
            pane.refresh()


def _short(name: str, width: int = 26) -> str:
    return name if len(name) <= width else name[:width - 1] + "…"


def read_uptime(proc: str) -> float:
    line = read_line(os.path.join(proc, 'uptime'))
    try:
        return float(line.split()[0]) if line else 0.0
    except ValueError:
        return 0.0
