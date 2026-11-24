"""Ports: everything open in the zone, by number, with add and remove."""

from typing import List, Optional, Tuple

import tkinter as tk

from . import ops as opsmod
from .text import t
from .ui import make_table
from .viewkit import View
from .widgets import T, Segmented
from .zonebar import ZoneBar


class PortsView(View):
    def __init__(self, app):
        super().__init__(app)
        px = app.px
        pad = tk.Frame(self, bg=T["bg"])
        pad.pack(fill="both", expand=True, padx=px(14), pady=px(12))
        self.zonebar = ZoneBar(pad, self)
        self.zonebar.pack(anchor="w")
        self.note(pad, t("ports.intro"), px(860)).pack(anchor="w", pady=(px(6), px(8)))
        frame, self.tree = make_table(pad, ("kind", "what", "ports", "state"), show="headings")
        for column, heading, width, anchor in (
                ("kind", t("col.kind"), 100, "w"), ("what", t("col.what"), 260, "w"),
                ("ports", t("col.ports"), 300, "w"), ("state", t("col.state"), 160, "w")):
            self.tree.heading(column, text=heading.upper(), anchor=anchor)
            self.tree.column(column, width=px(width), anchor=anchor, stretch=column == "ports")
        frame.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._buttons())
        bar = tk.Frame(pad, bg=T["bg"])
        bar.pack(fill="x", pady=(px(8), 0))
        self.remove_button = self.button(bar, t("ports.remove"), self.remove, "danger")
        self.remove_button.pack(side="left")
        self.keep_button = self.button(bar, t("ports.keep"), self.keep)
        self.keep_button.pack(side="left", padx=(px(8), 0))

        self.heading(pad, t("ports.add")).pack(anchor="w", pady=(px(14), px(4)))
        add = tk.Frame(pad, bg=T["bg"])
        add.pack(fill="x")
        self.entry = tk.Entry(add, width=14, font=app.font(10), bg=T["panel2"], fg=T["text"],
                              insertbackground=T["accent"], relief="flat",
                              highlightthickness=1, highlightbackground=T["line2"],
                              highlightcolor=T["accent"])
        self.entry.pack(side="left", ipady=px(3))
        self.entry.bind("<Return>", lambda _e: self.add())
        self.proto = Segmented(add, [("TCP", "tcp"), ("UDP", "udp")], "tcp", lambda _v: None,
                               app.font(8))
        self.proto.pack(side="left", padx=px(8))
        self.add_button = self.button(add, t("ports.add_button"), self.add, "primary")
        self.add_button.pack(side="left")
        self.message = self.note(pad, t("ports.format"), px(860))
        self.message.pack(anchor="w", pady=(px(6), 0))
        self.rows: List[Tuple[str, str]] = []      # (kind, value) in table order

    # — the table —
    def refresh(self) -> None:
        app, snap = self.app, self.app.snap
        self.zonebar.update_zones()
        zone = app.zone()
        rows: List[Tuple[str, str, str, str, str]] = []     # iid, kind, what, ports, state
        names = list(zone.services)
        names += [op["name"] for op in (o for o in app.pending.ops() if o["op"] == "service"
                  and o["zone"] == zone.name and o["add"]) if op["name"] not in names]
        for name in names:
            waiting = app.pending.get("service", zone.name, name)
            state = t("state.removing") if waiting and not waiting["add"] else \
                t("state.adding") if waiting else t("state.open")
            rows.append((f"service:{name}", t("kind.service"), name,
                         ", ".join(snap.service_ports.get(name, [])) or "--", state))
        ports = list(zone.ports) + [op["port"] for op in (o for o in app.pending.ops()
                                    if o["op"] == "port" and o["zone"] == zone.name and o["add"])
                                    if op["port"] not in zone.ports]
        for port in ports:
            state = {"adding": t("state.adding"), "removing": t("state.removing")}.get(
                app.port_state(zone.name, port), t("state.open"))
            rows.append((f"port:{port}", t("kind.port"), "--", port, state))
        wanted = [r[0] for r in rows]
        keep = self.tree.selection()
        if list(self.tree.get_children()) != wanted:
            self.tree.delete(*self.tree.get_children())
            for iid, *_rest in rows:
                self.tree.insert("", "end", iid=iid, values=("", "", "", ""))
            if keep and keep[0] in wanted:
                self.tree.selection_set(keep[0])
        for iid, kind, what, ports_text, state in rows:
            tags = ("busy",) if state in (t("state.adding"), t("state.removing")) else ()
            self.tree.item(iid, values=(kind, what, ports_text, state), tags=tags)
        self._buttons()

    def _selected(self) -> Optional[str]:
        picked = self.tree.selection()
        return picked[0] if picked else None

    def _buttons(self) -> None:
        picked = self._selected()
        live = self.app.snap.running and not self.app.busy
        waiting = False
        if picked:
            kind, _sep, value = picked.partition(":")
            zone = self.app.zone_name
            waiting = self.app.pending.get(kind, zone, value) is not None
        self.remove_button.set_enabled(bool(picked) and live and not waiting)
        self.keep_button.set_enabled(bool(picked) and waiting)
        self.add_button.set_enabled(live)

    # — changes —
    def remove(self) -> None:
        picked = self._selected()
        if not picked:
            return
        kind, _sep, value = picked.partition(":")
        zone = self.app.zone_name
        if kind == "service":
            self.app.set_service(zone, value, False)
        else:
            self.app.set_port(zone, value, False)

    def keep(self) -> None:
        picked = self._selected()
        if not picked:
            return
        kind, _sep, value = picked.partition(":")
        zone = self.app.zone_name
        if kind == "service":
            self.app.set_service(zone, value, value in self.app.zone().services)
        else:
            self.app.set_port(zone, value, value in self.app.zone().ports)

    def add(self) -> None:
        raw = self.entry.get().strip().replace(" ", "")
        if raw and "/" not in raw:
            raw = f"{raw}/{self.proto.value}"
        try:
            port = opsmod.normalise_port(raw)
        except opsmod.OpError:
            self.message.config(text=t("ports.bad"), fg=T["pink"])
            self.app.glitch.now(self.app.title)
            return
        if self.app.port_state(self.app.zone_name, port) in ("open", "adding"):
            self.message.config(text=t("ports.already", port=port), fg=T["gold"])
            return
        self.app.set_port(self.app.zone_name, port, True)
        self.entry.delete(0, "end")
        self.message.config(text=t("ports.format"), fg=T["muted"])
