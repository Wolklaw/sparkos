"""Rules: the things people want to allow, in plain words. Each is a firewalld service."""

from typing import Dict

import tkinter as tk

from . import catalog
from .fw import covered
from .overviewview import wide_open
from .text import t
from .ui import scrollable
from .viewkit import View
from .widgets import T, Toggle
from .zonebar import ZoneBar


class RulesView(View):
    def __init__(self, app):
        super().__init__(app)
        px = app.px
        outer, body = scrollable(self, T["bg"])
        outer.pack(fill="both", expand=True)
        pad = tk.Frame(body, bg=T["bg"])
        pad.pack(fill="both", expand=True, padx=px(14), pady=px(12))
        self.zonebar = ZoneBar(pad, self)
        self.zonebar.pack(anchor="w")
        self.note(pad, t("rules.intro"), px(860)).pack(anchor="w", pady=(px(6), px(8)))
        self.info = self.note(pad, "", px(860), T["gold"])
        self.list = tk.Frame(pad, bg=T["bg"])
        self.list.pack(fill="x")
        self.rows: Dict[str, dict] = {}
        self.built = ()

    def _build(self, rules) -> None:
        for child in self.list.winfo_children():
            child.destroy()
        self.rows = {}
        px = self.app.px
        for rule in rules:
            panel = tk.Frame(self.list, bg=T["panel"], highlightthickness=1,
                             highlightbackground=T["line"])
            panel.pack(fill="x", pady=(0, px(6)))
            toggle = Toggle(panel, t("rules.allow"), False,
                            lambda on, r=rule: self._toggle(r, on), self.app.font(8))
            toggle.pack(side="left", padx=px(10), pady=px(10), anchor="n")
            col = tk.Frame(panel, bg=T["panel"])
            col.pack(side="left", fill="x", expand=True, pady=px(8))
            title = self.text(col, t(f"rule.{rule.id}.title"), 10, True)
            title.pack(anchor="w")
            self.note(col, t(f"rule.{rule.id}.detail"), px(640)).pack(anchor="w")
            state = self.text(col, "", 8, False, T["muted"], justify="left", wraplength=px(640))
            state.pack(anchor="w", pady=(px(2), 0))
            self.rows[rule.service] = {"toggle": toggle, "state": state, "panel": panel,
                                       "rule": rule}

    def _toggle(self, rule, on: bool) -> None:
        self.app.set_service(self.app.zone_name, rule.service, on)

    def refresh(self) -> None:
        app, snap = self.app, self.app.snap
        self.zonebar.update_zones()
        if not snap.running:
            self.info.config(text=t("rules.off"))
            self.info.pack(anchor="w", pady=(0, app.px(8)), before=self.list)
        else:
            zone = app.zone()
            if wide_open(zone.ports):
                self.info.config(text=t("hint.wide", zone=zone.name))
                self.info.pack(anchor="w", pady=(0, app.px(8)), before=self.list)
            else:
                self.info.pack_forget()
        rules = catalog.available(snap.services)
        if tuple(r.id for r in rules) != self.built:
            self.built = tuple(r.id for r in rules)
            self._build(rules)
        zone = app.zone()
        for service, row in self.rows.items():
            on = app.service_on(zone.name, service)
            toggle = row["toggle"]
            if toggle.value != on:
                toggle.set(on)
            waiting = app.pending.get("service", zone.name, service) is not None
            ports = snap.service_ports.get(service, [])
            if waiting:
                text, colour = t("rules.waiting_on" if on else "rules.waiting_off"), T["gold"]
            elif not on and ports and covered(ports, zone.ports):
                text, colour = t("rules.covered"), T["gold"]
            else:
                text = (t("rules.open") if on else t("rules.closed")) + \
                    ("  ·  " + ", ".join(ports) if ports else "")
                colour = T["accent"] if on else T["dim"]
            row["state"].config(text=text, fg=colour)
