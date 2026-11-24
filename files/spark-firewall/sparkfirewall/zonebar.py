"""The line at the top of Rules and Ports: which zone the rules are for."""

from typing import Optional

import tkinter as tk

from .text import t
from .viewkit import View
from .widgets import T, Segmented


class ZoneBar(tk.Frame):
    def __init__(self, parent: tk.Misc, view: View):
        super().__init__(parent, bg=T["bg"])
        self.view = view
        self.label = view.text(self, "", 8, True, T["muted"])
        self.label.pack(side="left")
        self.holder = tk.Frame(self, bg=T["bg"])
        self.holder.pack(side="left", padx=(view.app.px(10), 0))
        self.segment: Optional[Segmented] = None
        self.names = ()

    def update_zones(self) -> None:
        app = self.view.app
        snap = app.snap
        # the zones of the networks that are connected, and the default one, are the ones whose
        # rules matter; any other zone is reached from the Overview
        names = []
        for name in [n.zone for n in snap.networks] + [snap.default_zone, app.zone_name]:
            if name and name in snap.zone and name not in names:
                names.append(name)
        self.label.config(text=t("zone.rules_for").upper())
        if tuple(names) != self.names:
            self.names = tuple(names)
            for child in self.holder.winfo_children():
                child.destroy()
            self.segment = Segmented(self.holder, [(n, n) for n in names], app.zone_name,
                                     app.choose_zone, app.font(8))
            self.segment.pack(side="left")
        elif self.segment is not None:
            self.segment.set(app.zone_name)
