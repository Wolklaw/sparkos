"""The pages: Displays, Sound, Network and Bluetooth here; the rest in pages2.py."""

import os
from typing import Dict, List, Optional

import tkinter as tk
from tkinter import filedialog

from . import bluetooth, core, displays, network, sound
from .app import Page
from .i18n import _
from .ui import Choice, Dialog, Slider, entry, label, rule
from .widgets import T, Toggle, WolkButton


def clear(frame: tk.Misc) -> None:
    for w in frame.winfo_children():
        w.destroy()


# ──────────────────────────── Displays ────────────────────────────
class DisplaysPage(Page):
    key, title, tool = 'displays', "Displays", 'kscreen-doctor'
    REVERT_SECONDS = 15
    index = [("Resolution", "size pixels 4k 1080p 1440p"),
             ("Refresh rate", "hz hertz fps 144 165 60"),
             ("Scale", "zoom dpi text size bigger"),
             ("Rotation", "portrait landscape orientation turn"),
             ("Variable refresh rate", "vrr freesync gsync adaptive sync"),
             ("HDR", "high dynamic range"),
             ("Primary display", "main monitor screen"),
             ("Arrange monitors", "layout position screens left right")]

    def __init__(self, app):
        super().__init__(app)
        self.outputs: List[displays.Output] = []
        self.selected: Optional[str] = None
        self.pending: Optional[dict] = None
        self.left = 0
        self.timer = None
        self.rects: List[tuple] = []
        self.drag = None
        app.closers.append(self.revert_now)

    def build(self, f):
        if not core.have('kscreen-doctor'):
            self.missing(f, 'kscreen-doctor', _("show your monitors"))
            self.canvas = None
            return
        self.bar = tk.Frame(f, bg=T["gold"], padx=14, pady=8)
        self.bar_text = tk.Label(self.bar, font=self.app.font(10), bg=T["gold"], fg=T["on_accent"])
        self.bar_text.pack(side='left')
        WolkButton(self.bar, _("Revert"), self.revert, self.app.font(9), 'danger').pack(side='right', padx=4)
        WolkButton(self.bar, _("Keep"), self.keep, self.app.font(9), 'primary').pack(side='right', padx=4)
        box = self.section(f, _("Arrange"))
        label(box, _("Drag a monitor to move it. Click one to change it."), self.app.font(9, False),
              fg=T["muted"]).pack(anchor='w', pady=(0, 6))
        self.canvas = tk.Canvas(box, height=230, bg=T["out_bg"], highlightthickness=1,
                                highlightbackground=T["line"])
        self.canvas.pack(fill='x')
        self.canvas.bind('<ButtonPress-1>', self.press)
        self.canvas.bind('<B1-Motion>', self.motion)
        self.canvas.bind('<ButtonRelease-1>', self.release)
        self.canvas.bind('<Configure>', lambda _e: self.draw())
        self.detail = self.section(f, '')

    def refresh(self):
        if self.canvas is None:
            return
        self.app.bg(displays.load, self.loaded)

    def loaded(self, outputs):
        if self.pending is not None and self.left <= 0 and outputs is None:
            return
        self.outputs = outputs or []
        if not any(o.name == self.selected for o in self.outputs):
            first = next((o for o in self.outputs if o.priority == 1), None) or \
                (self.outputs[0] if self.outputs else None)
            self.selected = first.name if first else None
        self.draw()
        self.show_detail()
        if not self.outputs:
            self.say(_("No monitors found."), True)

    # --- the map
    def scale_to_canvas(self):
        on = [o for o in self.outputs if o.enabled]
        if not on:
            return 1.0, 0, 0
        x0 = min(o.x for o in on)
        y0 = min(o.y for o in on)
        x1 = max(o.x + o.logical_size[0] for o in on)
        y1 = max(o.y + o.logical_size[1] for o in on)
        w = max(self.canvas.winfo_width(), 300)
        h = max(self.canvas.winfo_height(), 200)
        s = min((w - 80) / max(x1 - x0, 1), (h - 60) / max(y1 - y0, 1))
        s *= 0.8
        return s, (w - (x1 - x0) * s) / 2 - x0 * s, (h - (y1 - y0) * s) / 2 - y0 * s

    def draw(self):
        c = self.canvas
        if c is None:
            return
        c.delete('all')
        s, ox, oy = self.scale_to_canvas()
        self.rects = []
        for o in self.outputs:
            if not o.enabled:
                continue
            w, h = o.logical_size
            x, y = o.x, o.y
            if self.drag and self.drag['name'] == o.name:
                x, y = self.drag['x'], self.drag['y']
            x0, y0, x1, y1 = x * s + ox, y * s + oy, (x + w) * s + ox, (y + h) * s + oy
            on = o.name == self.selected
            c.create_rectangle(x0 + 3, y0, x1 + 3, y1, outline=T["ch_a"] if on else '', fill='')
            c.create_rectangle(x0 - 3, y0, x1 - 3, y1, outline=T["ch_b"] if on else '', fill='')
            c.create_rectangle(x0, y0, x1, y1, fill=T["panel2"],
                               outline=T["accent"] if on else T["line2"], width=2)
            name = o.name + ("  ★" if o.priority == 1 else '')
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2 - 8, text=name, fill=T["text"],
                          font=self.app.font(10))
            m = o.mode
            sub = f"{m.res} @ {m.rate} Hz" if m else ''
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2 + 10, text=sub, fill=T["muted"],
                          font=self.app.font(8, False))
            self.rects.append((o, x0, y0, x1, y1))
        for o in self.outputs:
            if not o.enabled and o.name == self.selected:
                c.create_text(12, 12, anchor='nw', fill=T["muted"], font=self.app.font(9, False),
                              text=_("{name} is off.").format(name=o.name))

    def press(self, e):
        self.drag = None
        for o, x0, y0, x1, y1 in reversed(self.rects):
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                self.selected = o.name
                s = self.scale_to_canvas()[0]
                self.drag = {'name': o.name, 'sx': e.x, 'sy': e.y, 'ox': o.x, 'oy': o.y,
                             'x': o.x, 'y': o.y, 's': s, 'moved': False}
                self.draw()
                self.show_detail()
                return

    def motion(self, e):
        d = self.drag
        if not d:
            return
        dx, dy = (e.x - d['sx']) / d['s'], (e.y - d['sy']) / d['s']
        if abs(e.x - d['sx']) + abs(e.y - d['sy']) > 4:
            d['moved'] = True
        d['x'], d['y'] = round(d['ox'] + dx), round(d['oy'] + dy)
        self.draw()

    def release(self, _e):
        d, self.drag = self.drag, None
        if not d:
            return
        o = next(o for o in self.outputs if o.name == d['name'])
        if not d['moved']:
            self.draw()
            return
        x, y = displays.snap(o, d['x'], d['y'], [p for p in self.outputs if p is not o and p.enabled])
        if (x, y) == (o.x, o.y):
            self.draw()
            return
        self.change([o.name], [displays.a_position(o, x, y)])

    # --- one monitor's settings
    def show_detail(self):
        d = self.detail
        clear(d)
        o = next((o for o in self.outputs if o.name == self.selected), None)
        if o is None:
            return
        f9 = self.app.font(9)
        label(d, o.label.upper(), self.app.font(8), fg=T["muted"]).pack(anchor='w', pady=(0, 6))
        r = self.row(d, _("Enabled"))
        Toggle(r, _("On"), o.enabled, lambda v, o=o: self.enable(o, v), f9).pack(anchor='w')
        if not o.enabled:
            return
        r = self.row(d, _("Primary display"))
        Toggle(r, _("Primary"), o.priority == 1,
               lambda v, o=o: self.change([o.name], [displays.a_primary(o)]) if v else self.refresh(),
               f9).pack(anchor='w')
        res = o.resolutions()
        m = o.mode
        if m:
            r = self.row(d, _("Resolution"))
            Choice(r, [(x, x) for x in res], m.res, lambda v, o=o: self.set_resolution(o, v),
                   self.app.font(10), 22).pack(anchor='w')
            r = self.row(d, _("Refresh rate"))
            Choice(r, [(f"{x.rate} Hz", x.id) for x in o.rates(m.res)], m.id,
                   lambda v, o=o: self.change([o.name], [displays.a_mode(o, v)]),
                   self.app.font(10), 22).pack(anchor='w')
        r = self.row(d, _("Scale"))
        scales = sorted(set(displays.SCALES + [o.scale]))
        Choice(r, [(f"{round(s * 100)}%", f"{s:g}") for s in scales], f"{o.scale:g}",
               lambda v, o=o: self.change([o.name], [displays.a_scale(o, float(v))]),
               self.app.font(10), 22).pack(anchor='w')
        r = self.row(d, _("Rotation"))
        Choice(r, [(_("Normal"), 'normal'), (_("Left"), 'left'), (_("Right"), 'right'),
                   (_("Upside down"), 'inverted')], o.rotation,
               lambda v, o=o: self.change([o.name], [displays.a_rotation(o, v)]),
               self.app.font(10), 22).pack(anchor='w')
        if o.vrr is not None:
            r = self.row(d, _("Variable refresh rate"))
            Choice(r, [(_("Never"), 'never'), (_("Always"), 'always'), (_("When needed"), 'automatic')],
                   o.vrr, lambda v, o=o: self.change([o.name], [displays.a_vrr(o, v)]),
                   self.app.font(10), 22).pack(anchor='w')
        if o.hdr is not None:
            r = self.row(d, _("HDR"))
            Toggle(r, _("On"), o.hdr, lambda v, o=o: self.change([o.name], [displays.a_hdr(o, v)]),
                   f9).pack(anchor='w')

    def set_resolution(self, o, res):
        cur = o.mode
        rates = o.rates(res)
        if not rates:
            return
        best = min(rates, key=lambda x: abs(x.hz - (cur.hz if cur else 60)))
        self.change([o.name], [displays.a_mode(o, best.id)])

    def enable(self, o, on):
        if not on and sum(1 for x in self.outputs if x.enabled) <= 1:
            self.say(_("Keep at least one monitor on."), True)
            self.show_detail()
            return
        self.change([o.name], [displays.a_enable(o, on)])

    # --- apply, then keep or go back
    def change(self, names: List[str], args: List[str]):
        if self.pending is None:
            self.pending = {'old': self.outputs, 'names': set(names)}
        else:
            self.pending['names'] |= set(names)
        self.say('')

        def work():
            ok = displays.apply(args)
            return ok, displays.load()

        def done(result):
            ok, outputs = result if result else (False, [])
            if outputs:
                self.outputs = outputs
            self.draw()
            self.show_detail()
            if not ok:
                self.say(_("The monitor didn't take that change."), True)
                self.revert()
                return
            self.start_countdown()
        self.app.bg(work, done)

    def start_countdown(self):
        self.left = self.REVERT_SECONDS
        self.bar.pack(fill='x', padx=24, pady=(0, 10), before=self.canvas.master.master)
        self.paint_bar()
        if self.timer:
            self.app.root.after_cancel(self.timer)
        self.timer = self.app.root.after(1000, self.tick)
        self.app.glitch.now(strong=True)

    def paint_bar(self):
        self.bar_text.config(text=_("Keep these display settings? Going back in {n} s").format(n=self.left))

    def tick(self):
        self.timer = None
        if self.pending is None:
            return
        self.left -= 1
        if self.left <= 0:
            self.revert()
            return
        self.paint_bar()
        self.timer = self.app.root.after(1000, self.tick)

    def stop_bar(self):
        if self.timer:
            try:
                self.app.root.after_cancel(self.timer)
            except tk.TclError:
                pass
        self.timer = None
        try:
            self.bar.pack_forget()
        except (tk.TclError, AttributeError):
            pass

    def keep(self):
        self.pending = None
        self.stop_bar()
        self.say(_("Display settings kept."))

    def revert(self):
        p, self.pending = self.pending, None
        self.stop_bar()
        if not p:
            return
        args = displays.restore_args(p['old'], sorted(p['names']))
        self.app.bg(lambda: (displays.apply(args), displays.load()), self.reverted)

    def reverted(self, result):
        if result and result[1]:
            self.outputs = result[1]
        self.draw()
        self.show_detail()
        self.say(_("Went back to the earlier display settings."))

    def revert_now(self):
        """The window is closing with a change not yet kept: go back before it's gone."""
        p, self.pending = self.pending, None
        if p:
            displays.apply(displays.restore_args(p['old'], sorted(p['names'])))


# ──────────────────────────── Sound ────────────────────────────
class SoundPage(Page):
    key, title, tool = 'sound', "Sound", 'wpctl'
    index = [("Output device", "speakers headphones dac fiio audio"),
             ("Input device", "microphone mic quadcast"),
             ("Volume", "loud quiet louder mute"),
             ("Volume per app", "application stream mixer"),
             ("Test tone", "beep check speakers")]

    def __init__(self, app):
        super().__init__(app)
        self.sig = None

    def build(self, f):
        if not core.have('wpctl'):
            self.missing(f, 'wpctl', _("show your sound devices"))
            self.holder = None
            return
        self.holder = tk.Frame(f, bg=T["bg"])
        self.holder.pack(fill='both', expand=True)

    def refresh(self):
        if self.holder is None:
            return
        self.app.bg(sound.status, self.render)
        if not self.watchers:
            self.watch(['pactl', 'subscribe'])

    def render(self, st):
        if st is None:
            return
        sig = [(n.id, n.name, n.volume, n.muted, n.default) for n in st.sinks + st.sources + st.streams]
        if sig == self.sig:
            return
        self.sig = sig
        h = self.holder
        clear(h)
        self.device_box(h, _("Output"), st.sinks, True)
        self.device_box(h, _("Input"), st.sources, False)
        box = self.section(h, _("Volume per app"))
        if not st.streams:
            label(box, _("No app is playing sound."), self.app.font(10), fg=T["muted"]).pack(anchor='w')
        for s in st.streams:
            r = tk.Frame(box, bg=T["panel"])
            r.pack(fill='x', pady=3)
            label(r, s.name, self.app.font(10), width=24).pack(side='left')
            sl = Slider(r, lambda v, s=s: self.vol(s, v), 0, 100, 240)
            sl.put(round((s.volume or 0) * 100))
            sl.pack(side='left', padx=8)
            Toggle(r, _("Muted"), s.muted, lambda v, s=s: sound.set_mute(s.id, v),
                   self.app.font(8)).pack(side='left')

    def device_box(self, h, title, nodes, is_out):
        box = self.section(h, title)
        if not nodes:
            label(box, _("No output device found.") if is_out else _("No input device found."),
                  self.app.font(10), fg=T["muted"]).pack(anchor='w')
            return
        cur = next((n for n in nodes if n.default), nodes[0])
        r = self.row(box, _("Device"))
        Choice(r, [(n.name, str(n.id)) for n in nodes], str(cur.id),
               lambda v: self.pick(int(v)), self.app.font(10), 40).pack(anchor='w')
        r = self.row(box, _("Volume"))
        line = tk.Frame(r, bg=T["panel"])
        line.pack(anchor='w')
        sl = Slider(line, lambda v, n=cur: self.vol(n, v), 0, 100, 300)
        sl.put(round((cur.volume or 0) * 100))
        sl.pack(side='left')
        pct = label(line, f"{round((cur.volume or 0) * 100)}%", self.app.font(10), width=6)
        pct.pack(side='left', padx=8)
        sl.bind('<B1-Motion>', lambda _e, sl=sl, pct=pct: pct.config(text=f"{sl.get()}%"))
        Toggle(line, _("Muted"), cur.muted, lambda v, n=cur: sound.set_mute(n.id, v),
               self.app.font(8)).pack(side='left')
        if is_out:
            WolkButton(line, _("Play a test tone"), lambda n=cur: self.tone(n), self.app.font(9),
                       'ghost').pack(side='left', padx=12)

    def pick(self, id_):
        self.app.bg(lambda: sound.set_default(id_), lambda ok: (self.say(
            _("Default device changed.") if ok else _("Could not change the device."), not ok),
            self.refresh_now()))

    def refresh_now(self):
        self.sig = None
        self.refresh()

    def vol(self, node, value):
        self.app.bg(lambda: sound.set_volume(node.id, value / 100))

    def tone(self, node):
        if not sound.play_tone(node.id):
            self.say(_("pw-play isn't installed, so there is no test tone."), True)
        else:
            self.say(_("Playing a short tone on {name}.").format(name=node.name))


# ──────────────────────────── Network ────────────────────────────
class NetworkPage(Page):
    key, title, tool = 'network', "Network", 'nmcli'
    index = [("Wi-Fi", "wireless wifi internet connect password"),
             ("Wired", "ethernet cable lan"),
             ("VPN", "wireguard openvpn import tunnel"),
             ("Proxy", "http server")]

    def build(self, f):
        if not core.have('nmcli'):
            self.missing(f, 'nmcli', _("show your connections"))
            self.holder = None
            return
        self.holder = tk.Frame(f, bg=T["bg"])
        self.holder.pack(fill='both', expand=True)

    def refresh(self, rescan=False):
        if self.holder is None:
            return

        def work():
            return (network.wifi_enabled(), network.wifi_list(rescan), network.devices(),
                    network.vpns(), network.proxy_get())
        self.app.bg(work, self.render)
        if not self.watchers:
            self.watch(['nmcli', 'monitor'], 800)

    def render(self, data):
        if not data:
            return
        wifi_on, wifis, devs, vpns, proxy = data
        h = self.holder
        clear(h)
        f9 = self.app.font(9)
        box = self.section(h, _("Wi-Fi"))
        top = tk.Frame(box, bg=T["panel"])
        top.pack(fill='x', pady=(0, 6))
        Toggle(top, _("Wi-Fi on"), wifi_on, self.wifi_power, f9).pack(side='left')
        WolkButton(top, _("Scan again"), lambda: self.refresh(True), f9, 'ghost').pack(side='left', padx=8)
        if wifi_on and not wifis:
            label(box, _("No networks found."), self.app.font(10), fg=T["muted"]).pack(anchor='w')
        for w in wifis[:12]:
            r = tk.Frame(box, bg=T["panel"])
            r.pack(fill='x', pady=2)
            bars = '▂▄▆█'[min(3, w.signal // 26)]
            label(r, f"{bars}  {w.ssid}" + ("  ·  " + _("connected") if w.active else '') +
                  ("  " + _("secured") if w.secured else ''), self.app.font(10),
                  fg=T["accent"] if w.active else T["text"], width=40).pack(side='left')
            if not w.active:
                WolkButton(r, _("Connect"), lambda w=w: self.connect(w), f9, 'ghost').pack(side='left')
        box = self.section(h, _("Wired"))
        wired = [d for d in devs if d.type == 'ethernet']
        if not wired:
            label(box, _("No wired adapter."), self.app.font(10), fg=T["muted"]).pack(anchor='w')
        for d in wired:
            up = d.state.startswith('connected')
            label(box, f"{d.name}   {_('connected') if up else _('not connected')}"
                  + (f"   ({d.connection})" if up and d.connection not in ('', '--') else ''),
                  self.app.font(10), fg=T["accent"] if up else T["muted"]).pack(anchor='w', pady=2)
        box = self.section(h, _("VPN"))
        if not vpns:
            label(box, _("No VPN connections. Import a WireGuard (.conf) or OpenVPN (.ovpn) file."),
                  self.app.font(10), fg=T["muted"], wraplength=640).pack(anchor='w')
        for v in vpns:
            r = tk.Frame(box, bg=T["panel"])
            r.pack(fill='x', pady=2)
            label(r, f"{v.name}  ({v.type})" + ("  ·  " + _("connected") if v.active else ''),
                  self.app.font(10), fg=T["accent"] if v.active else T["text"],
                  width=40).pack(side='left')
            WolkButton(r, _("Disconnect") if v.active else _("Connect"),
                       lambda v=v: self.vpn(v), f9, 'ghost').pack(side='left')
        WolkButton(box, _("Import a file"), self.vpn_import, f9, 'ghost').pack(anchor='w', pady=(8, 0))
        box = self.section(h, _("Proxy"))
        r = self.row(box, _("Mode"))
        self.proxy_mode = Choice(r, [(_("None"), 'none'), (_("Manual"), 'manual')],
                                 'manual' if proxy['mode'] == 'manual' else 'none',
                                 lambda v: None, self.app.font(10), 14)
        self.proxy_mode.pack(side='left')
        self.proxy_host = entry(r, self.app.font(10), 28)
        self.proxy_host.insert(0, proxy['http'].replace('http://', '').replace(' ', ':'))
        self.proxy_host.pack(side='left', padx=8, ipady=3)
        WolkButton(r, _("Apply"), self.proxy_apply, f9, 'primary').pack(side='left')
        label(box, _("The proxy applies to KDE and Spark apps. Other programs read their own settings."),
              self.app.font(8, False), fg=T["dim"]).pack(anchor='w')

    def wifi_power(self, on):
        self.app.bg(lambda: network.set_wifi(on), lambda ok: self.refresh())

    def connect(self, w):
        self.say(_("Connecting to {name}...").format(name=w.ssid))

        def done(msg):
            if msg is None:
                msg = _("could not connect")
            if msg and w.secured and ('ecret' in msg or 'assword' in msg):
                Dialog(self.app, _("Wi-Fi password"),
                       _("Password for {name}").format(name=w.ssid), _("Connect"), _("Cancel"),
                       field='', secret=True, on_ok=lambda pw: self.connect_pw(w, pw))
                return
            self.say(msg or _("Connected to {name}.").format(name=w.ssid), bool(msg))
            self.refresh()
        self.app.bg(lambda: network.connect_wifi(w.ssid), done)

    def connect_pw(self, w, pw):
        def done(msg):
            self.say(msg or _("Connected to {name}.").format(name=w.ssid), bool(msg))
            self.refresh()
        self.app.bg(lambda: network.connect_wifi(w.ssid, pw), done)

    def vpn(self, v):
        def done(msg):
            self.say(msg or _("Done."), bool(msg))
            self.refresh()
        self.app.bg(lambda: network.vpn_up(v.name, not v.active), done)

    def vpn_import(self):
        path = filedialog.askopenfilename(title=_("Import a VPN file"),
                                          filetypes=[("VPN", "*.conf *.ovpn"), ("*", "*")])
        if path:
            self.app.bg(lambda: network.vpn_import(path),
                        lambda msg: (self.say(msg or _("Imported."), bool(msg)), self.refresh()))

    def proxy_apply(self):
        mode, host = self.proxy_mode.value, self.proxy_host.get().strip()
        if mode == 'manual' and not host:
            self.say(_("Type the proxy as host:port."), True)
            return
        ok = network.proxy_set(mode, host)
        self.say(_("Proxy saved.") if ok else _("Could not save the proxy."), not ok)


# ──────────────────────────── Bluetooth ────────────────────────────
class BluetoothPage(Page):
    key, title, tool = 'bluetooth', "Bluetooth", 'bluetoothctl'
    index = [("Bluetooth on or off", "radio wireless"),
             ("Pair a device", "headphones controller keyboard mouse connect"),
             ("Forget a device", "remove unpair"),
             ("Battery", "level percent headset")]

    def build(self, f):
        if not core.have('bluetoothctl'):
            self.missing(f, 'bluetoothctl', _("show Bluetooth devices"))
            self.holder = None
            return
        self.holder = tk.Frame(f, bg=T["bg"])
        self.holder.pack(fill='both', expand=True)

    def refresh(self):
        if self.holder is None:
            return
        self.app.bg(lambda: (bluetooth.powered(), bluetooth.devices() if bluetooth.powered() else []),
                    self.render)
        if not self.watchers and core.have('dbus-monitor'):
            self.watch(['dbus-monitor', '--system', "type='signal',sender='org.bluez'"], 800)

    def render(self, data):
        if not data:
            return
        on, devs = data
        h = self.holder
        clear(h)
        f9 = self.app.font(9)
        box = self.section(h, _("Bluetooth"))
        if on is None:
            label(box, _("No Bluetooth adapter found."), self.app.font(10), fg=T["muted"]).pack(anchor='w')
            return
        top = tk.Frame(box, bg=T["panel"])
        top.pack(fill='x')
        Toggle(top, _("Bluetooth on"), on, self.power, f9).pack(side='left')
        if on:
            WolkButton(top, _("Look for devices"), self.scan, f9, 'ghost').pack(side='left', padx=8)
        if not on:
            return
        box = self.section(h, _("Devices"))
        if not devs:
            label(box, _("No devices yet. Put one in pairing mode and look for devices."),
                  self.app.font(10), fg=T["muted"], wraplength=640).pack(anchor='w')
        for d in devs:
            r = tk.Frame(box, bg=T["panel"])
            r.pack(fill='x', pady=3)
            state = _("connected") if d.connected else (_("paired") if d.paired else _("new"))
            bat = f"   {d.battery}%" if d.battery is not None else ''
            label(r, f"{d.name}   [{state}]{bat}", self.app.font(10),
                  fg=T["accent"] if d.connected else T["text"], width=46).pack(side='left')
            if not d.paired:
                WolkButton(r, _("Pair"), lambda d=d: self.act(bluetooth.pair, d), f9, 'primary').pack(side='left', padx=2)
            else:
                if d.connected:
                    WolkButton(r, _("Disconnect"), lambda d=d: self.act(bluetooth.disconnect, d), f9, 'ghost').pack(side='left', padx=2)
                else:
                    WolkButton(r, _("Connect"), lambda d=d: self.act(bluetooth.connect, d), f9, 'primary').pack(side='left', padx=2)
                WolkButton(r, _("Forget"), lambda d=d: self.act(bluetooth.forget, d), f9, 'danger').pack(side='left', padx=2)

    def power(self, on):
        self.app.bg(lambda: bluetooth.set_power(on), lambda ok: self.refresh())

    def scan(self):
        self.say(_("Looking for devices for 8 seconds..."))
        self.app.bg(bluetooth.scan, lambda _r: (self.say(''), self.refresh()))

    def act(self, func, d):
        self.say(_("Working on {name}...").format(name=d.name))

        def done(msg):
            self.say(msg or _("Done."), bool(msg))
            self.refresh()
        self.app.bg(lambda: func(d.mac), done)


from .pages2 import (AboutPage, DefaultAppsPage, DateTimePage, KdePage, MorePage,  # noqa: E402
                     PowerPage, PrintersPage, StartupPage, UpdatesPage)
from . import kcms  # noqa: E402


KDE_INDEX = {
    'appearance': [("Wallpaper", "background picture desktop"), ("Colours and accent", "color theme dark light mint"),
                   ("Cursor size", "mouse pointer"), ("Font size", "text fonts")],
    'input': [("Pointer speed", "mouse acceleration sensitivity"), ("Scroll direction", "natural scrolling touchpad"),
              ("Keyboard layout", "us international dead keys french language"), ("Key repeat rate", "delay"),
              ("Caps Lock", "flicker light fix"), ("Shortcuts", "keys hotkeys"),
              ("Game controllers", "gamepad joystick")],
    'users': [("Your name and picture", "avatar account"), ("Password", "login"), ("Add a user", "account")],
    'storage': [("Games drive", "steam library disk"), ("Removable drives", "usb automount mounted")],
}


def _kde_page(key, title, mods):
    return type(f"{key.title()}Page", (KdePage,), {'key': key, 'title': title, 'modules': mods,
                                                   'index': KDE_INDEX.get(key, [])})


PAGES: Dict[str, type] = {
    'displays': DisplaysPage, 'sound': SoundPage, 'network': NetworkPage,
    'bluetooth': BluetoothPage, 'power': PowerPage, 'defaultapps': DefaultAppsPage,
    'datetime': DateTimePage, 'printers': PrintersPage, 'startup': StartupPage,
}
for _key, _title, _mods in kcms.KDE_PAGES:
    PAGES[_key] = _kde_page(_key, _title, _mods)
PAGES.update({'updates': UpdatesPage, 'more': MorePage, 'about': AboutPage})

SIDEBAR: List[str] = ['displays', 'sound', 'network', 'bluetooth', 'appearance', 'input', 'power',
                      'defaultapps', 'startup', 'users', 'datetime', 'printers', 'storage',
                      'updates', 'more', 'about']
