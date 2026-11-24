"""Pads: game controllers. A list of what is plugged in, a live tester (buttons, sticks, triggers,
d-pad, rumble), and the firmware fwupd can reach. Remapping is not here, on purpose (see the
brief)."""

import os
from typing import Dict, List, Optional

import tkinter as tk

from . import pads as padlib
from .fwupd import Fwupd, FwDevice
from .text import t
from .ui import make_table, scrollable
from .viewkit import View
from .widgets import T, GlitchPanel

POLL_MS = 25
MEASURE_S = 3
RUMBLE_MS = 600


def _dirs():
    """Where the kernel's files are; overridable so a fake tree can stand in."""
    return (os.environ.get("SPARK_CONTROLLER_PADS_SYS") or padlib.SYS_INPUT,
            os.environ.get("SPARK_CONTROLLER_PADS_DEV") or padlib.DEV_INPUT,
            os.environ.get("SPARK_CONTROLLER_PADS_POWER") or padlib.SYS_POWER)


class PadsView(View):
    def __init__(self, app):
        super().__init__(app)
        px = app.px
        self.fwupd = Fwupd()
        self.pads: List[padlib.Pad] = []
        self.known: Dict[str, str] = {}               # event path -> name, to spot arrivals
        self.picked: Optional[padlib.Pad] = None
        self.reader: Optional[padlib.PadReader] = None
        self.dirty = True
        self.polling = False
        self.measure_left = 0
        self.fw_devices: List[FwDevice] = []
        self.fw_updates: List[FwDevice] = []
        self.fw_loaded = False
        self.fw_busy = False
        self.armed: Optional[str] = None              # the device id waiting for a second click
        self._arm_id: Optional[str] = None
        self.first_scan = True

        outer, body = scrollable(self, T["bg"])
        outer.pack(fill="both", expand=True)
        pad = tk.Frame(body, bg=T["bg"])
        pad.pack(fill="both", expand=True, padx=px(14), pady=px(12))

        self.heading(pad, t("pads.list")).pack(anchor="w", pady=(0, px(4)))
        frame, self.tree = make_table(pad, ("name", "link", "battery", "access"), show="headings")
        for column, heading, width in (("name", "pads.col_name", 360), ("link", "pads.col_link", 130),
                                       ("battery", "pads.col_battery", 100),
                                       ("access", "pads.col_access", 110)):
            self.tree.heading(column, text=t(heading).upper(), anchor="w")
            self.tree.column(column, width=px(width), anchor="w", stretch=column == "name")
        self.tree.configure(height=4)
        frame.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", self._select)
        self.list_note = self.note(pad, "", px(860))
        self.list_note.pack(anchor="w", pady=(px(6), 0))

        self.heading(pad, t("pads.tester")).pack(anchor="w", pady=(px(14), px(4)))
        self.panel = GlitchPanel(pad, T["panel"])
        self.panel.pack(fill="x")
        self.canvas = tk.Canvas(self.panel.inner, height=px(318), bg=T["panel"],
                                highlightthickness=0, bd=0)
        self.canvas.pack(fill="x")
        self.canvas.bind("<Configure>", lambda _e: self._dirty())
        bar = tk.Frame(pad, bg=T["bg"])
        bar.pack(fill="x", pady=(px(8), 0))
        self.measure_button = self.button(bar, t("pads.measure"), self.measure)
        self.measure_button.pack(side="left")
        self.heavy_button = self.button(bar, t("pads.rumble_heavy"), lambda: self.rumble(1.0, 0.0))
        self.heavy_button.pack(side="left", padx=(px(8), 0))
        self.light_button = self.button(bar, t("pads.rumble_light"), lambda: self.rumble(0.0, 1.0))
        self.light_button.pack(side="left", padx=(px(8), 0))
        self.tester_note = self.note(pad, "", px(860))
        self.tester_note.pack(anchor="w", pady=(px(6), 0))
        self.note(pad, t("pads.axes_note"), px(860)).pack(anchor="w", pady=(px(2), 0))

        self.heading(pad, t("pads.firmware")).pack(anchor="w", pady=(px(16), 0))
        self.note(pad, t("pads.firmware_note"), px(860)).pack(anchor="w", pady=(0, px(6)))
        self.support = tk.Frame(pad, bg=T["bg"])
        self.support.pack(fill="x", pady=(0, px(6)))
        fbar = tk.Frame(pad, bg=T["bg"])
        fbar.pack(fill="x", pady=(0, px(6)))
        self.check_button = self.button(fbar, t("drivers.check"), self.fw_check)
        self.check_button.pack(side="left")
        self.install_button = self.button(fbar, t("pads.fw_install"), self.fw_install, "primary")
        self.install_button.pack(side="left", padx=(px(8), 0))
        self.fw_status = self.note(fbar, "", px(520))
        self.fw_status.pack(side="left", padx=(px(12), 0))
        ffr, self.fw_tree = make_table(pad, ("name", "version", "state"), show="headings")
        for column, heading, width in (("name", "col.device", 360), ("version", "col.version", 160),
                                       ("state", "col.state", 260)):
            self.fw_tree.heading(column, text=t(heading).upper(), anchor="w")
            self.fw_tree.column(column, width=px(width), anchor="w", stretch=column == "name")
        self.fw_tree.configure(height=3)
        ffr.pack(fill="x")
        self.fw_tree.bind("<<TreeviewSelect>>", lambda _e: self._fw_buttons())
        self.note(pad, t("pads.fw_warn"), px(860), T["gold"]).pack(anchor="w", pady=(px(6), 0))
        self.note(pad, t("pads.remap"), px(860)).pack(anchor="w", pady=(px(14), px(4)))
        self._fw_buttons()
        self._buttons()
        self.bind("<Destroy>", lambda _e: self._close_reader(), add="+")
        self.bind("<Map>", lambda _e: self._start_polling(), add="+")

    # — the list, and arrivals and departures —
    def refresh(self) -> None:
        sys_input, dev_input, power = _dirs()
        found = padlib.scan(sys_input, dev_input, power)
        self._announce(found)
        self.pads = found
        self._fill_list()
        if self.picked is None or all(p.path != self.picked.path for p in found):
            real = [p for p in found if p.bus != "virtual"] or found
            self._pick(real[0] if real else None)
        else:
            self.picked = next(p for p in found if p.path == self.picked.path)
            self._buttons()
        if not self.fw_loaded and not self.fw_busy:
            self.fw_loaded = True
            self.fw_load()
        else:
            self._support()
        self._start_polling()

    def _announce(self, found: List[padlib.Pad]) -> None:
        now = {p.path: p.name for p in found}
        if not self.first_scan:
            for path, name in now.items():
                if path not in self.known:
                    self._event(t("status.pads_in"), t("pads.connected", name=name), T["accent"])
            for path, name in self.known.items():
                if path not in now:
                    self._event(t("status.pads_out"), t("pads.gone", name=name), T["pink"])
        self.first_scan = False
        self.known = now

    def _event(self, status: str, line: str, colour: str) -> None:
        """A controller arriving or leaving tears the title and the tester's edge."""
        self.app.set_status(status, colour, hold_ms=4000)
        self.list_note.config(text=line, fg=colour)
        self.app.glitch.now(self.app.title, strong=colour == T["pink"])
        self.panel.burst(colour == T["pink"])

    def _fill_list(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for i, p in enumerate(self.pads):
            self.tree.insert("", "end", iid=str(i), values=(
                p.name, t(f"pads.{p.bus}"), p.battery_text() or t("pads.no_battery"),
                t("pads.ready") if p.can_read else t("pads.blocked")),
                tags=() if p.can_read else ("off",))
            if self.picked is not None and p.path == self.picked.path:
                self.tree.selection_set(str(i))
        if not self.pads:
            self.list_note.config(text=t("pads.none"), fg=T["muted"])
        elif any(p.bus == "virtual" for p in self.pads) and not self.list_note.cget("text"):
            self.list_note.config(text=t("pads.virtual_note"), fg=T["muted"])

    def _select(self, _event=None) -> None:
        chosen = self.tree.selection()
        if chosen:
            pad = self.pads[int(chosen[0])]
            if self.picked is None or pad.path != self.picked.path:
                self._pick(pad)

    def _pick(self, pad: Optional[padlib.Pad]) -> None:
        self._close_reader()
        self.picked = pad
        if pad is not None and pad.can_read:
            try:
                self.reader = padlib.PadReader(pad.path, pad.keys, pad.axes)
            except OSError:
                self.reader = None
        self.tester_note.config(text="")
        if pad is not None and pad.bus == "virtual":
            self.list_note.config(text=t("pads.virtual_note"), fg=T["muted"])
        self._buttons()
        self._support()
        self._dirty()

    def _close_reader(self) -> None:
        if self.reader is not None:
            self.reader.close()
            self.reader = None
        self.measure_left = 0

    def _buttons(self) -> None:
        pad = self.picked
        self.measure_button.set_enabled(self.reader is not None and self.measure_left == 0
                                        and bool(self.reader.state.layout["sticks"]))
        self.heavy_button.set_enabled(bool(pad and pad.has_rumble))
        self.light_button.set_enabled(bool(pad and pad.has_rumble))

    # — the live loop: only while this tab is on screen —
    def _start_polling(self) -> None:
        if not self.polling:
            self.polling = True
            self.after(POLL_MS, self._poll)

    def _poll(self) -> None:
        try:
            live = self.winfo_exists() and self.app.tab == "pads" and self.app.visible
        except tk.TclError:
            live = False
        if not live:
            self.polling = False
            return
        if self.reader is not None:
            if self.reader.poll():
                self._dirty()
            if self.reader.gone:
                self._close_reader()
                self.refresh()
        self.after(POLL_MS, self._poll)
        if self.dirty:
            self.draw()

    def _dirty(self) -> None:
        self.dirty = True

    # — drawing —
    def draw(self) -> None:
        self.dirty = False
        c, px = self.canvas, self.app.px
        c.delete("all")
        w = max(px(640), c.winfo_width())
        font = self.app.tkfont(8, True)
        small = self.app.tkfont(7, False)
        if self.picked is None:
            c.create_text(px(14), px(20), text=t("pads.none"), fill=T["muted"], font=font,
                          anchor="w", width=w - px(28))
            return
        if self.reader is None:
            c.create_text(px(14), px(20), text=t("pads.no_access"), fill=T["gold"], font=small,
                          anchor="nw", width=w - px(28))
            return
        st = self.reader.state
        layout = st.layout
        # triggers across the top
        bars = layout["triggers"]
        x = px(14)
        if bars:
            slot = min(px(260), (w - px(28)) // len(bars))
            for code in bars:
                value = st.trigger(code)
                c.create_text(x, px(10), text=padlib.axis_name(code), fill=T["muted"], font=small,
                              anchor="w")
                c.create_text(x + slot - px(14), px(10), text=f"{value * 100:.0f} %",
                              fill=T["text"], font=small, anchor="e")
                c.create_rectangle(x, px(18), x + slot - px(14), px(28), outline=T["line"],
                                   fill=T["panel2"])
                if value > 0:
                    full = value > 0.97
                    if full:
                        c.create_rectangle(x - px(2), px(18), x + (slot - px(14)) - px(2), px(28),
                                           outline=T["ch_a"])
                        c.create_rectangle(x + px(2), px(18), x + (slot - px(14)) + px(2), px(28),
                                           outline=T["ch_b"])
                    c.create_rectangle(x, px(18), x + (slot - px(14)) * value, px(28), width=0,
                                       fill=T["accent"])
                x += slot
        top = px(46)
        third = w / 3
        sticks = layout["sticks"]
        names = (t("pads.left"), t("pads.right"))
        for i, pair in enumerate(sticks[:2]):
            cx = third * (0.5 if i == 0 else 2.5)
            label = names[i] if len(sticks) <= 2 else t("pads.stick_n", n=i + 1)
            self._stick(st, pair, cx, top, label, font, small, i)
        # the middle: d-pad, then buttons
        mid = third * 1.5
        self._dpad(st, mid, top + px(4))
        self._buttons_grid(st, mid, top + px(112), third - px(20), font)
        for j, pair in enumerate(sticks[2:]):                     # more than two sticks: bars
            self._stick(st, pair, px(60) + j * px(130), top + px(150), t("pads.stick_n", n=j + 3),
                        font, small, j + 2, r=px(30))
        # axes that are neither: show them as bars so nothing is hidden
        if not any((layout["triggers"], sticks)):
            c.create_text(px(14), top, text=t("pads.press"), fill=T["muted"], font=font, anchor="w")

    def _stick(self, st: padlib.PadState, pair, cx: float, top: float, label: str, font, small,
               index: int, r: Optional[int] = None) -> None:
        c, px = self.canvas, self.app.px
        r = r or px(58)
        cy = top + px(14) + r
        x, y, mag = st.stick(pair)
        flat = st.flat(pair)
        pressed = bool(st.buttons.get(padlib.BTN_THUMBL if index == 0 else padlib.BTN_THUMBR))
        c.create_text(cx, top, text=label.upper(), fill=T["muted"], font=small)
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=T["accent"] if pressed else T["line2"],
                      width=2 if pressed else 1, fill=T["panel2"])
        c.create_line(cx - r, cy, cx + r, cy, fill=T["line"])
        c.create_line(cx, cy - r, cx, cy + r, fill=T["line"])
        if flat > 0:
            d = r * min(1.0, flat)
            c.create_oval(cx - d, cy - d, cx + d, cy + d, outline=T["gold"], dash=(3, 3))
        dx, dy = cx + x * r, cy + y * r
        dot = px(6)
        if mag > 0.97:                       # at the rim: the two channels slip
            for offset, colour in ((-px(3), T["ch_a"]), (px(3), T["ch_b"])):
                c.create_oval(dx - dot + offset, dy - dot, dx + dot + offset, dy + dot,
                              outline=colour)
        c.create_oval(dx - dot, dy - dot, dx + dot, dy + dot, fill=T["accent"], width=0)
        flat_pct = f"{flat * 100:.0f}"
        c.create_text(cx, cy + r + px(14), fill=T["text"], font=small, text=t(
            "pads.stick", x=f"{x * 100:+.0f}", y=f"{y * 100:+.0f}", mag=f"{mag * 100:.0f}",
            flat=flat_pct))
        if st.drift.get(pair[0]) is not None and pair[0] in st.drift:
            c.create_text(cx, cy + r + px(28), fill=T["gold"], font=small,
                          text=f"{st.drift[pair[0]] * 100:.1f} %")

    def _tile(self, x0, y0, x1, y1, label: str, on: bool, font) -> None:
        c, px = self.canvas, self.app.px
        if on:                               # lit: the channels sit a little apart
            c.create_rectangle(x0 - px(2), y0, x1 - px(2), y1, outline=T["ch_a"])
            c.create_rectangle(x0 + px(2), y0, x1 + px(2), y1, outline=T["ch_b"])
        c.create_rectangle(x0, y0, x1, y1, outline=T["accent"] if on else T["line"],
                           fill=T["accent"] if on else T["panel2"])
        c.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=label,
                      fill=T["on_accent"] if on else T["muted"], font=font)

    def _dpad(self, st: padlib.PadState, cx: float, top: float) -> None:
        px = self.app.px
        pad = st.dpad()
        s, g = px(30), px(4)
        for name, dx, dy in (("up", 0, -1), ("down", 0, 1), ("left", -1, 0), ("right", 1, 0)):
            x0 = cx - s / 2 + dx * (s + g)
            y0 = top + s + g + dy * (s + g)
            self._tile(x0, y0, x0 + s, y0 + s, {"up": "^", "down": "v", "left": "<",
                                                "right": ">"}[name], pad[name],
                       self.app.tkfont(8, True))

    def _buttons_grid(self, st: padlib.PadState, cx: float, top: float, width: float,
                      font) -> None:
        px = self.app.px
        codes = [k for k in padlib.BUTTON_ORDER if k in self.reader.keys]
        codes += sorted(k for k in self.reader.keys
                        if 0x100 <= k < 0x300 and k not in padlib.BUTTON_ORDER
                        and k not in padlib.DPAD_KEYS and k not in (padlib.BTN_THUMBL,))
        tw, th, g = px(46), px(24), px(4)
        cols = max(2, int(width // (tw + g)))
        x0 = cx - (min(cols, len(codes)) * (tw + g) - g) / 2
        for i, code in enumerate(codes[:cols * 5]):
            col, row = i % cols, i // cols
            x = x0 + col * (tw + g)
            y = top + row * (th + g)
            self._tile(x, y, x + tw, y + th, padlib.button_name(code),
                       bool(st.buttons.get(code)), font)

    # — rest drift —
    def measure(self) -> None:
        if self.reader is None or self.measure_left:
            return
        self.reader.state.start_rest()
        self.measure_left = MEASURE_S
        self._buttons()
        self._measure_tick()

    def _measure_tick(self) -> None:
        if self.reader is None:
            self.measure_left = 0
            return
        if self.measure_left > 0:
            self.tester_note.config(text=t("pads.measuring", n=self.measure_left), fg=T["gold"])
            self.measure_left -= 1
            self.after(1000, self._measure_tick)
            return
        drift = self.reader.state.finish_rest()
        items = []
        for i, pair in enumerate(self.reader.state.layout["sticks"]):
            value = drift.get(pair[0], 0.0)
            name = t("pads.left") if i == 0 else t("pads.right") if i == 1 else \
                t("pads.stick_n", n=i + 1)
            items.append(t("pads.drift_item", name=name, pct=f"{value * 100:.1f}",
                           dz=str(padlib.suggested_deadzone(value))))
        self.tester_note.config(text=t("pads.drift", values="; ".join(items)), fg=T["accent"])
        self.panel.burst()
        self._buttons()
        self._dirty()

    # — rumble —
    def rumble(self, strong: float, weak: float) -> None:
        pad = self.picked
        if pad is None:
            return
        if not pad.has_rumble:
            self.tester_note.config(text=t("pads.rumble_none"), fg=T["gold"])
            return
        if not pad.can_write:
            self.tester_note.config(text=t("pads.rumble_blocked"), fg=T["gold"])
            self.app.glitch.now(self.app.title)
            return
        try:
            motor = padlib.Rumble(pad.path)
            motor.play(strong, weak, RUMBLE_MS)
        except OSError as exc:
            self.tester_note.config(text=t("pads.rumble_failed", error=str(exc)), fg=T["pink"])
            self.app.glitch.now(self.app.title, strong=True)
            return
        self.app.set_status(t("status.rumble"), T["gold"], hold_ms=RUMBLE_MS)
        self.panel.burst()
        self.after(RUMBLE_MS + 250, motor.close)

    # — firmware —
    def _support(self) -> None:
        """One honest line per connected controller about what fwupd can do for it."""
        for child in self.support.winfo_children():
            child.destroy()
        real = [p for p in self.pads if p.bus in ("usb", "bluetooth")]
        for p in real:
            if p.bus == "bluetooth":
                line, colour = t("pads.fw_bluetooth", name=p.name), T["muted"]
            else:
                plugin = padlib.fwupd_plugin_for(p.vendor, p.product)
                if plugin:
                    line, colour = t("pads.fw_known", name=p.name, plugin=plugin), T["accent"]
                else:
                    line, colour = t("pads.fw_unknown", name=p.name, id=p.usb_id), T["muted"]
            self.note(self.support, line, self.app.px(860), colour).pack(anchor="w")

    def _fw_buttons(self) -> None:
        ok = self.fwupd.available and not self.fw_busy
        self.check_button.set_enabled(ok)
        chosen = self._fw_selected()
        pending = chosen is not None and any(u.id == chosen.id for u in self.fw_updates)
        self.install_button.set_enabled(ok and pending)
        self.install_button.set_text(t("pads.fw_confirm") if pending and chosen.id == self.armed
                                     else t("pads.fw_install"))

    def _fw_selected(self) -> Optional[FwDevice]:
        picked = self.fw_tree.selection()
        if not picked:
            return None
        index = int(picked[0])
        return self.fw_listed[index] if index < len(self.fw_listed) else None

    fw_listed: List[FwDevice] = []

    def _say(self, text: str, colour: str = "") -> None:
        self.fw_status.config(text=text, fg=colour or T["muted"])

    def fw_load(self, refresh: bool = False) -> None:
        if not self.fwupd.available:
            self._say(t("drivers.no_fwupd"), T["gold"])
            return
        self.fw_busy = True
        self._fw_buttons()
        self._say(t("drivers.checking") if refresh else t("drivers.reading"))
        if refresh:
            self.app.set_status(t("status.checking"), T["gold"])

        def job():
            if refresh:
                self.fwupd.refresh()
            return self.fwupd.devices(), self.fwupd.updates()

        def done(value, error) -> None:
            self.fw_busy = False
            if refresh:
                self.app.set_status(t("status.watching"), T["accent"])
            if error is not None:
                self._say(t("drivers.failed", error=str(error)), T["pink"])
                if refresh:
                    self.app.glitch.now(self.app.title, strong=True)
            else:
                self.fw_devices, self.fw_updates = value
                self._fw_fill()
            self._fw_buttons()
        self.app.worker.run(job, done)

    def fw_check(self) -> None:
        if not self.fw_busy:
            self.fw_load(refresh=True)

    def _fw_fill(self) -> None:
        self.fw_tree.delete(*self.fw_tree.get_children())
        self.fw_listed = padlib.firmware_for_pads(self.fw_devices, self.pads)
        pending = {d.id: d.releases[0].version for d in self.fw_updates if d.releases}
        for i, device in enumerate(self.fw_listed):
            if device.id in pending:
                state, tag = t("drivers.update_to", version=pending[device.id]), ("busy",)
            elif device.updatable:
                state, tag = t("drivers.up_to_date"), ()
            else:
                state, tag = t("drivers.not_updatable"), ("off",)
            self.fw_tree.insert("", "end", iid=str(i), values=(device.title, device.version, state),
                                tags=tag)
        self._say(t("pads.fw_listed", n=len(self.fw_listed)) if self.fw_listed
                  else t("pads.fw_none_listed"),
                  T["gold"] if any(d.id in pending for d in self.fw_listed) else T["muted"])

    def fw_install(self) -> None:
        """Two presses: the first arms the button, the second (within five seconds) installs
        the update for the chosen controller only."""
        device = self._fw_selected()
        if device is None or self.fw_busy or not any(u.id == device.id for u in self.fw_updates):
            return
        if self.armed != device.id:
            self.armed = device.id
            if self._arm_id:
                self.after_cancel(self._arm_id)
            self._arm_id = self.after(5000, self._disarm)
            self.app.glitch.now(self.app.title)
            self._fw_buttons()
            return
        self._disarm()
        self.fw_busy = True
        self._fw_buttons()
        self._say(t("drivers.installing"), T["gold"])
        self.app.set_status(t("status.updating"), T["gold"])

        def done(value, error) -> None:
            self.fw_busy = False
            self.app.set_status(t("status.watching"), T["accent"])
            if error is not None:
                self._say(t("drivers.failed", error=str(error)), T["pink"])
                self.app.glitch.now(self.app.title, strong=True)
                self._fw_buttons()
            else:
                self._say(t("drivers.installed", detail=value or ""), T["accent"])
                self.app.glitch.now(self.app.title)
                self.fw_load()
        self.app.worker.run(lambda: self.fwupd.update(device.id), done)

    def _disarm(self) -> None:
        self.armed = None
        if self._arm_id:
            try:
                self.after_cancel(self._arm_id)
            except tk.TclError:
                pass
            self._arm_id = None
        if self.winfo_exists():
            self._fw_buttons()
