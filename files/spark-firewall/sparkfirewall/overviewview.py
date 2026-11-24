"""Overview: is the firewall on, which zone each network is in, and what a zone means."""

from typing import List, Optional

import tkinter as tk

from . import catalog
from .fw import Network, covered
from .text import t
from .ui import make_table, scrollable
from .viewkit import View
from .widgets import T, GlitchPanel, Segmented

WIDE = ["1025-65535/tcp", "1025-65535/udp"]


def zone_words(name: str) -> str:
    key = catalog.ZONE_WORDS.get(name)
    return t(key) if key else t("zone.other")


def zone_label(name: str) -> str:
    return name or "--"


def wide_open(ports: List[str]) -> bool:
    """True when the zone already opens every port above 1024 (Fedora's desktop zone does)."""
    return covered(WIDE, ports)


class OverviewView(View):
    def __init__(self, app):
        super().__init__(app)
        px = app.px
        outer, body = scrollable(self, T["bg"])
        outer.pack(fill="both", expand=True)
        pad = tk.Frame(body, bg=T["bg"])
        pad.pack(fill="both", expand=True, padx=px(14), pady=px(12))
        self.pad = pad
        self.banner = tk.Label(pad, text="", font=app.font(8), fg=T["gold"], bg=T["panel"],
                               anchor="w", justify="left", wraplength=px(900), padx=px(10),
                               pady=px(6), highlightthickness=1, highlightbackground=T["line"])
        self.tile_row = tk.Frame(pad, bg=T["bg"])
        self.tile_row.pack(fill="x", pady=(0, px(10)))
        self.tiles = {}
        self.panels: List[GlitchPanel] = []
        for key in ("state", "boot", "default", "open"):
            panel = GlitchPanel(self.tile_row, T["panel"])
            panel.pack(side="left", fill="x", expand=True, padx=(0, px(8)))
            self.panels.append(panel)
            self.text(panel.inner, t(f"tile.{key}").upper(), 7, True, T["muted"]).pack(
                anchor="w", padx=px(10), pady=(px(8), 0))
            value = self.text(panel.inner, "--", 15, True, T["accent"])
            value.pack(anchor="w", padx=px(10), pady=(0, px(8)))
            self.tiles[key] = value
        app.glitch.add(*self.panels)

        power = tk.Frame(pad, bg=T["bg"])
        power.pack(fill="x", pady=(0, px(4)))
        self.power_button = self.button(power, t("power.off"), self.power, "danger")
        self.power_button.pack(side="left")
        self.power_note = self.note(power, "", px(640))
        self.power_note.pack(side="left", padx=(px(12), 0))
        self.confirming = False
        self.after_id: Optional[str] = None

        self.heading(pad, t("net.heading")).pack(anchor="w", pady=(px(14), px(4)))
        frame, self.tree = make_table(pad, ("name", "device", "zone"), show="headings")
        for column, heading, width, anchor in (
                ("name", t("col.network"), 340, "w"), ("device", t("col.device"), 140, "w"),
                ("zone", t("col.zone"), 300, "w")):
            self.tree.heading(column, text=heading.upper(), anchor=anchor)
            self.tree.column(column, width=px(width), anchor=anchor, stretch=column == "name")
        self.tree.configure(height=5)
        frame.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._picked())
        self.none = self.note(pad, t("net.none"))

        self.pick = tk.Frame(pad, bg=T["bg"])
        self.pick_title = self.heading(self.pick, "")
        self.pick_title.pack(anchor="w", pady=(px(10), px(4)))
        self.pick_row = tk.Frame(self.pick, bg=T["bg"])
        self.pick_row.pack(anchor="w")
        self.pick_note = self.note(self.pick, "", px(860))
        self.pick_note.pack(anchor="w", pady=(px(6), 0))
        self.selected: Optional[Network] = None
        self.segment: Optional[Segmented] = None

        self.default_head = self.heading(pad, t("default.heading"))
        self.default_head.pack(anchor="w", pady=(px(16), px(2)))
        self.note(pad, t("default.note"), px(860)).pack(anchor="w", pady=(0, px(4)))
        self.default_row = tk.Frame(pad, bg=T["bg"])
        self.default_row.pack(anchor="w")
        self.default_segment: Optional[Segmented] = None
        self.error = self.note(pad, "", px(860), T["pink"])
        self._shown = None

    # — pieces —
    def _zones(self) -> List[str]:
        have = set(self.app.snap.zones)
        return [z for z in catalog.CHOOSABLE if z in have]

    def _segment(self, parent: tk.Frame, current: str, command, old: Optional[Segmented],
                 owner: object = None) -> Segmented:
        """The zone pills. Kept as they are while nothing changed, so a hover isn't lost every
        time the firewall is read again."""
        zones = self._zones()
        if current and current not in zones:
            zones = zones + [current]
        if old is not None and old.winfo_exists() and set(old.labels) == set(zones) \
                and getattr(old, "owner", None) is owner:
            old.set(current)
            return old
        for child in parent.winfo_children():
            child.destroy()
        segment = Segmented(parent, [(z, z) for z in zones], current, command, self.app.font(8))
        segment.owner = owner
        segment.pack(side="left")
        return segment

    def power(self) -> None:
        snap = self.app.snap
        if self.app.busy or not snap.available:
            return
        if snap.running and not self.confirming:
            # turning it off needs a second click: nothing here is a lock, but it is the one
            # button that stops all protection
            self.confirming = True
            self.power_button.set_text(t("power.confirm"))
            self.after_id = self.after(5000, self._unconfirm)
            return
        self._unconfirm()
        turn_on = not snap.running
        self.app.send([{"op": "power", "on": turn_on}],
                      t("status.starting") if turn_on else t("status.stopping"))

    def _unconfirm(self) -> None:
        self.confirming = False
        if self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None
        self.refresh()

    def _picked(self) -> None:
        chosen = self.tree.selection()
        nets = [n for n in self.app.snap.networks if n.device == (chosen[0] if chosen else "")]
        self.selected = nets[0] if nets else None
        self._pick_fill()

    def _pick_fill(self) -> None:
        net = self.selected
        if net is None:
            self.pick.pack_forget()
            return
        zone = self.app.network_zone(net)
        self.pick_title.config(text=t("net.zone_for", name=net.name).upper())
        self.segment = self._segment(self.pick_row, zone,
                                     lambda z: self.app.set_network_zone(net, z), self.segment,
                                     net.device)
        self.pick_note.config(text=zone_words(zone))
        self.pick.pack(fill="x", before=self.default_head)

    # — refresh —
    def refresh(self) -> None:
        app, snap = self.app, self.app.snap
        if not snap.available:
            state, colour = t("state.missing"), T["pink"]
        elif snap.running:
            state, colour = t("state.on"), T["accent"]
        else:
            state, colour = t("state.off"), T["pink"]
        self.tiles["state"].config(text=state, fg=colour)
        boot = snap.at_boot
        self.tiles["boot"].config(text="--" if boot is None else (t("yes") if boot else t("no")),
                                  fg=T["accent"] if boot else T["gold"])
        self.tiles["default"].config(text=zone_label(app.default_zone()))
        info = snap.zone.get(app.zone_name)
        count = len(info.services) + len(info.ports) if info else 0
        self.tiles["open"].config(text=str(count) if info else "--")

        # on/off button
        self.power_button.set_enabled(snap.available and not app.busy)
        if not snap.running:
            self.power_button.set_text(t("power.on"))
            self.power_button.variant = "primary"
            self.power_note.config(text=t("power.off_note") if snap.available else t("power.missing"))
        elif not self.confirming:
            self.power_button.set_text(t("power.off"))
            self.power_note.config(text=t("power.on_note"))

        messages: List[str] = []
        if snap.available and not snap.running:
            messages.append(t("hint.stopped"))
        elif snap.running and info and wide_open(info.ports):
            messages.append(t("hint.wide", zone=info.name))
        if messages:
            self.banner.config(text="\n".join(messages))
            self.banner.pack(fill="x", pady=(0, app.px(10)), before=self.tile_row)
        else:
            self.banner.pack_forget()
        if app.fail:
            self.error.config(text=t("hint.failed", error=app.fail))
            self.error.pack(anchor="w", pady=(app.px(10), 0))
        else:
            self.error.pack_forget()

        # networks
        wanted = [n.device for n in snap.networks]
        if list(self.tree.get_children()) != wanted:
            self.tree.delete(*self.tree.get_children())
            for net in snap.networks:
                self.tree.insert("", "end", iid=net.device, values=("", "", ""))
        for net in snap.networks:
            zone = app.network_zone(net)
            waiting = zone != net.zone
            shown = (t("net.zone_changing", zone=zone) if waiting else zone_label(zone)) \
                if snap.running else "--"
            self.tree.item(net.device, values=(net.name, net.device, shown),
                           tags=("busy",) if waiting else ())
        if snap.networks:
            self.none.pack_forget()
        else:
            self.none.pack(anchor="w", pady=app.px(6))
        if self.selected and self.selected.device not in wanted:
            self.selected = None
        if self.selected:
            fresh = [n for n in snap.networks if n.device == self.selected.device]
            self.selected = fresh[0] if fresh else None
        self._pick_fill()

        # default zone
        self.default_segment = self._segment(self.default_row, app.default_zone(),
                                             self.app.set_default_zone, self.default_segment)
