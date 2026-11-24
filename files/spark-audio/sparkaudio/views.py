"""The pages: outputs, inputs, apps, EQ and Scarlett. Rows are kept by node id and updated in
place, so a slider you are dragging is never rebuilt under your hand."""

import re
import tkinter as tk
from typing import Any, Callable, Dict, List, Optional

from . import eq as eqmod
from .controls import Chip, Dropdown, Meter, ScrollFrame, Slider, VSlider
from .core import run
from .model import Card, Node, State
from .scarlett import Control, Interface, classify
from .text import t
from .widgets import T, GlitchPanel, Toggle, WolkButton


def pct(v: Optional[float]) -> str:
    return "--" if v is None else f"{round(v * 100)}%"


def label(parent, text, font, fg=None, bg=None, anchor="w", **kw) -> tk.Label:
    return tk.Label(parent, text=text, font=font, fg=fg or T["text"],
                    bg=bg or parent.cget("bg"), anchor=anchor, **kw)


class Page(tk.Frame):
    """A scrolling page. Subclasses fill self.body and implement refresh()."""

    def __init__(self, app):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill="both", expand=True)
        self.body = self.scroll.body
        self.pad = app.px(14)

    def heading(self, text: str, hint: str = "") -> tk.Frame:
        app = self.app
        row = tk.Frame(self.body, bg=T["bg"])
        row.pack(fill="x", padx=self.pad, pady=(app.px(16), app.px(6)))
        label(row, text.upper(), app.font(8), T["muted"]).pack(side="left")
        if hint:
            label(row, hint, app.font(8, False), T["dim"]).pack(side="left", padx=(app.px(10), 0))
        tk.Frame(row, bg=T["line"], height=1).pack(side="left", fill="x", expand=True,
                                                   padx=(app.px(10), 0))
        return row

    def note(self, text: str, colour: str = None) -> tk.Label:
        lab = label(self.body, text, self.app.font(8, False), colour or T["muted"],
                    justify="left", wraplength=self.app.px(860))
        lab.pack(fill="x", padx=self.pad, pady=(self.app.px(4), 0))
        return lab

    def refresh(self) -> None:
        pass

    def wanted_meters(self) -> Dict[str, bool]:
        return {}

    def tick(self) -> None:
        pass

    def mic_changed(self) -> None:
        pass


# ─── Outputs and inputs ───────────────────────────────────────

class DeviceRow:
    def __init__(self, app, parent, node: Node, on_default: Callable[[Node], None], is_sink: bool):
        self.app, self.node, self.on_default, self.is_sink = app, node, on_default, is_sink
        self.is_default = False
        px = app.px
        bg = T["panel"]
        self.panel = GlitchPanel(parent, bg)
        f = self.panel.inner
        top = tk.Frame(f, bg=bg)
        top.pack(fill="x", padx=px(12), pady=(px(10), px(2)))
        self.mute = Toggle(top, t('row.mute'), False, self._muted, app.font(8))
        self.mute.pack(side="right")
        self.slot = tk.Frame(top, bg=bg)
        self.slot.pack(side="right", padx=(0, px(8)))
        self.default_btn = WolkButton(self.slot, t('row.set_default'), self._set_default,
                                      app.font(8), padx=px(10), pady=px(3))
        self.default_chip = Chip(self.slot, t('row.default'), app.font(8))
        self.title = label(top, "", app.font(10), bg=bg)
        self.title.pack(side="left")
        self.chips = tk.Frame(top, bg=bg)
        self.chips.pack(side="left", padx=(px(8), 0))
        self.eq_chip = Chip(self.chips, t('row.eq'), app.font(8), T["ch_b"])
        self.detail = label(f, "", app.font(8, False), T["muted"], bg=bg)
        self.detail.pack(fill="x", padx=px(12))
        mid = tk.Frame(f, bg=bg)
        mid.pack(fill="x", padx=px(12), pady=(px(4), px(2)))
        self.value = label(mid, "", app.font(9), bg=bg, width=5, anchor="e")
        self.value.pack(side="right")
        self.slider = Slider(mid, self._volume, height=px(24))
        self.slider.pack(side="left", fill="x", expand=True)
        self.meter = Meter(f, height=px(6))
        self.meter.pack(fill="x", padx=px(12), pady=(px(2), px(10)))

    def _volume(self, v: float):
        self.value.config(text=pct(v))
        self.app.backend.set_volume(self.node, v)

    def _muted(self, on: bool):
        self.slider.set(self.slider.value, muted=on)
        self.app.backend.set_mute(self.node, on)

    def _set_default(self):
        self.on_default(self.node)

    def update(self, node: Node, is_default: bool, eq_on: bool):
        self.node, self.is_default = node, is_default
        self.title.config(text=node.title)
        self.detail.config(text=node.detail)
        if node.volume is None:
            self.slider.set_enabled(False)
            self.value.config(text="--")
        else:
            self.slider.set_enabled(True)
            self.slider.set(node.volume, muted=node.mute)
            if not self.slider.dragging:
                self.value.config(text=pct(node.volume))
        self.mute.set(node.mute)
        if is_default:
            self.default_btn.pack_forget()
            self.default_chip.pack()
        else:
            self.default_chip.pack_forget()
            self.default_btn.pack()
        if eq_on:
            self.eq_chip.pack()
        else:
            self.eq_chip.pack_forget()
        if not is_default:
            self.meter.set(0.0, active=False)


class DevicesView(Page):
    is_sink = True

    def __init__(self, app):
        super().__init__(app)
        self.rows: Dict[int, DeviceRow] = {}
        self.order: List[int] = []
        self.top = tk.Frame(self.body, bg=T["bg"])
        self.top.pack(fill="x")
        self.list = tk.Frame(self.body, bg=T["bg"])
        self.list.pack(fill="x", pady=(app.px(12), 0))
        self.empty = self.note(t('empty.outputs' if self.is_sink else 'empty.inputs'), T["muted"])
        self.empty.pack_forget()
        self.extra = tk.Frame(self.body, bg=T["bg"])
        self.extra.pack(fill="x")
        self.build_top()

    def build_top(self) -> None:
        pass

    def nodes(self, st: State) -> List[Node]:
        return st.sinks if self.is_sink else st.sources

    def default_id(self, st: State) -> Optional[int]:
        return st.default_sink if self.is_sink else st.default_source

    def on_default(self, node: Node):
        st = self.app.backend.state()
        target = st.eq_sinks.get(node.name, node) if self.is_sink else node
        self.app.backend.set_default(target)
        self.app.message(t('msg.default', name=node.title))

    def refresh(self):
        app = self.app
        st = app.backend.state()
        nodes = self.nodes(st)
        default = self.default_id(st)
        ids = [n.id for n in nodes]
        for gone in [i for i in self.rows if i not in ids]:
            self.rows.pop(gone).panel.destroy()
        for n in nodes:
            if n.id not in self.rows:
                self.rows[n.id] = DeviceRow(app, self.list, n, self.on_default, self.is_sink)
        if ids != self.order:
            for i in self.order:
                if i in self.rows:
                    self.rows[i].panel.pack_forget()
            for i in ids:
                self.rows[i].panel.pack(fill="x", padx=self.pad, pady=(0, app.px(8)))
            self.order = ids
        for n in nodes:
            self.rows[n.id].update(n, n.id == default, self.is_sink and n.name in st.eq_sinks)
        if nodes:
            self.empty.pack_forget()
        else:
            self.empty.pack(fill="x", padx=self.pad, pady=(app.px(10), 0))
        self.refresh_extra(st)

    def refresh_extra(self, st: State) -> None:
        pass

    def wanted_meters(self):
        st = self.app.backend.state()
        node = (st.sink_by_id(st.default_sink) if self.is_sink else st.source_by_id(st.default_source))
        return {node.name: self.is_sink} if node else {}

    def tick(self):
        for row in self.rows.values():
            if row.is_default:
                row.meter.set(self.app.meters.read(row.node.name))


class OutputsView(DevicesView):
    is_sink = True

    def build_top(self):
        self.cards: Dict[int, Dict[str, Any]] = {}

    def refresh_extra(self, st: State):
        app = self.app
        cards = [c for c in st.cards if len([p for p in c.profiles if p.available]) > 1]
        ids = [c.id for c in cards]
        if ids != list(self.cards):
            for child in self.extra.winfo_children():
                child.destroy()
            self.cards = {}
            if cards:
                head = tk.Frame(self.extra, bg=T["bg"])
                head.pack(fill="x", padx=self.pad, pady=(app.px(10), app.px(6)))
                label(head, t('cards.title').upper(), app.font(8), T["muted"]).pack(side="left")
                tk.Frame(head, bg=T["line"], height=1).pack(side="left", fill="x", expand=True,
                                                            padx=(app.px(10), 0))
                label(self.extra, t('cards.hint'), app.font(8, False), T["muted"],
                      justify="left", wraplength=app.px(860)).pack(fill="x", padx=self.pad)
            for card in cards:
                panel = GlitchPanel(self.extra, T["panel"])
                panel.pack(fill="x", padx=self.pad, pady=(app.px(6), 0))
                inner = panel.inner
                row = tk.Frame(inner, bg=T["panel"])
                row.pack(fill="x", padx=app.px(12), pady=app.px(8))
                name = label(row, card.title, app.font(10))
                name.pack(side="left")
                menu = Dropdown(row, app.font(8, False), width=34)
                menu.pack(side="right")
                self.cards[card.id] = {'menu': menu, 'card': card, 'name': name}
        for card in cards:
            entry = self.cards.get(card.id)
            if not entry:
                continue
            entry['card'] = card
            options = [(p.description, p.name) for p in card.profiles if p.available]
            entry['menu'].set_options(options, card.current_name,
                                      lambda v, cid=card.id: self._profile(cid, v))

    def _profile(self, card_id: int, profile: str):
        card: Card = self.cards[card_id]['card']
        self.app.backend.set_profile(card.name, profile)
        self.app.message(t('msg.profile', card=card.title))


class InputsView(DevicesView):
    is_sink = False

    def build_top(self):
        app = self.app
        panel = GlitchPanel(self.top, T["panel"])
        panel.pack(fill="x", padx=self.pad, pady=(app.px(12), app.px(8)))
        self.mic_panel = panel
        inner = panel.inner
        row = tk.Frame(inner, bg=T["panel"])
        row.pack(fill="x", padx=app.px(12), pady=app.px(10))
        col = tk.Frame(row, bg=T["panel"])
        col.pack(side="left", fill="x", expand=True)
        label(col, t('mic.title').upper(), app.font(9)).pack(fill="x")
        label(col, t('mic.hint'), app.font(8, False), T["muted"], justify="left",
              wraplength=app.px(560)).pack(fill="x")
        self.mic_status = label(col, "", app.font(8), T["accent"])
        self.mic_status.pack(fill="x", pady=(app.px(4), 0))
        self.mic_btn = WolkButton(row, t('mic.start'), self._mic_click, app.font(9), "primary",
                                  padx=app.px(14), pady=app.px(6))
        self.mic_btn.pack(side="right")
        self._mic_job: Optional[str] = None
        self.mic_changed()

    def _mic_click(self):
        app = self.app
        if app.mic.state in ('recording', 'playing'):
            app.mic.cancel()
            return
        st = app.backend.state()
        src = st.source_by_id(st.default_source)
        if src is None:
            app.message(t('mic.no_input'), T["pink"])
            return
        raw = st.nodes.get(st.default_sink_raw) if st.default_sink_raw else None
        app.mic.start(src.name, raw.name if raw else None)

    def mic_changed(self):
        mic = self.app.mic
        busy = mic.state in ('recording', 'playing')
        self.mic_btn.set_text(t('mic.stop') if busy else t('mic.start'))
        if mic.state == 'recording':
            import time
            left = max(0, int(mic.SECONDS - (time.monotonic() - mic.started)) + 1)
            self.mic_status.config(text="● " + t('mic.recording', secs=left), fg=T["pink"])
        elif mic.state == 'playing':
            self.mic_status.config(text="● " + t('mic.playing'), fg=T["accent"])
        elif mic.state == 'failed':
            self.mic_status.config(text="● " + t('mic.failed', error=mic.error), fg=T["pink"])
        else:
            self.mic_status.config(text="")
        if busy and self._mic_job is None:
            self._mic_job = self.after(250, self._mic_again)

    def _mic_again(self):
        self._mic_job = None
        self.mic_changed()


# ─── Apps ─────────────────────────────────────────────────────

class AppRow:
    def __init__(self, app, parent, node: Node, playback: bool):
        self.app, self.node, self.playback = app, node, playback
        px = app.px
        bg = T["panel"]
        self.panel = GlitchPanel(parent, bg)
        f = self.panel.inner
        top = tk.Frame(f, bg=bg)
        top.pack(fill="x", padx=px(12), pady=(px(10), px(2)))
        self.mute = Toggle(top, t('row.mute'), False, self._muted, app.font(8))
        self.mute.pack(side="right")
        self.menu = Dropdown(top, app.font(8, False), width=26)
        self.menu.pack(side="right", padx=(0, px(8)))
        self.title = label(top, "", app.font(10), bg=bg)
        self.title.pack(side="left")
        self.detail = label(f, "", app.font(8, False), T["muted"], bg=bg)
        self.detail.pack(fill="x", padx=px(12))
        mid = tk.Frame(f, bg=bg)
        mid.pack(fill="x", padx=px(12), pady=(px(4), px(10)))
        self.value = label(mid, "", app.font(9), bg=bg, width=5, anchor="e")
        self.value.pack(side="right")
        self.slider = Slider(mid, self._volume, height=px(24))
        self.slider.pack(side="left", fill="x", expand=True)

    def _volume(self, v: float):
        self.value.config(text=pct(v))
        self.app.backend.set_volume(self.node, v)

    def _muted(self, on: bool):
        self.slider.set(self.slider.value, muted=on)
        self.app.backend.set_mute(self.node, on)

    def _move(self, target_id: int):
        st = self.app.backend.state()
        target = st.nodes.get(target_id)
        if target is None:
            return
        self.app.backend.move_stream(self.node, target)
        self.app.message(t('msg.moved', app=self.node.title, to=target.title))

    def update(self, node: Node, st: State):
        self.node = node
        self.title.config(text=node.title)
        self.detail.config(text=node.detail)
        if node.volume is None:
            self.slider.set_enabled(False)
        else:
            self.slider.set_enabled(True)
            self.slider.set(node.volume, muted=node.mute)
            if not self.slider.dragging:
                self.value.config(text=pct(node.volume))
        self.mute.set(node.mute)
        options = []
        if self.playback:
            for s in st.sinks:
                options.append((s.title, s.id))
                if s.name in st.eq_sinks:
                    options.append((t('row.with_eq', name=s.title), st.eq_sinks[s.name].id))
        else:
            options = [(s.title, s.id) for s in st.sources]
        self.menu.set_options(options, node.target, self._move)


class AppsView(Page):
    def __init__(self, app):
        super().__init__(app)
        self.rows: Dict[int, AppRow] = {}
        self.order: List[int] = []
        self.sections = {}
        for key in ('playing', 'recording'):
            head = self.heading(t(f'apps.{key}'))
            frame = tk.Frame(self.body, bg=T["bg"])
            frame.pack(fill="x")
            empty = label(frame, t(f'apps.none_{key}'), app.font(8, False), T["muted"])
            self.sections[key] = (head, frame, empty)

    def refresh(self):
        app = self.app
        st = app.backend.state()
        wanted = [(n, True) for n in st.playing] + [(n, False) for n in st.recording]
        ids = [n.id for n, _ in wanted]
        for gone in [i for i in self.rows if i not in ids]:
            self.rows.pop(gone).panel.destroy()
        for n, playback in wanted:
            if n.id not in self.rows:
                frame = self.sections['playing' if playback else 'recording'][1]
                self.rows[n.id] = AppRow(app, frame, n, playback)
        if ids != self.order:
            for i in self.order:
                if i in self.rows:
                    self.rows[i].panel.pack_forget()
            for n, _ in wanted:
                self.rows[n.id].panel.pack(fill="x", padx=self.pad, pady=(0, app.px(8)))
            self.order = ids
        for n, _ in wanted:
            self.rows[n.id].update(n, st)
        for key, group in (('playing', st.playing), ('recording', st.recording)):
            empty = self.sections[key][2]
            if group:
                empty.pack_forget()
            else:
                empty.pack(fill="x", padx=self.pad)


# ─── EQ ───────────────────────────────────────────────────────

class EqView(Page):
    def __init__(self, app):
        super().__init__(app)
        self.sel: Optional[str] = None            # node.name of the output being edited
        self.gains: List[float] = [0.0] * len(eqmod.BANDS)
        self.pending_default: Optional[str] = None
        self._save_job: Optional[str] = None
        px = app.px
        self.note(t('eq.intro'))
        self.heading(t('eq.output'))
        row = tk.Frame(self.body, bg=T["bg"])
        row.pack(fill="x", padx=self.pad)
        self.menu = Dropdown(row, app.font(9, False), width=36)
        self.menu.pack(side="left")
        self.state_label = label(row, "", app.font(8), T["muted"])
        self.state_label.pack(side="left", padx=(px(12), 0))
        panel = GlitchPanel(self.body, T["panel"])
        panel.pack(fill="x", padx=self.pad, pady=(px(10), 0))
        self.panel = panel
        inner = panel.inner
        bar = tk.Frame(inner, bg=T["panel"])
        bar.pack(fill="x", padx=px(12), pady=(px(10), px(4)))
        self.toggle = Toggle(bar, t('eq.on'), False, self._enable, app.font(9))
        self.toggle.pack(side="left")
        label(bar, t('eq.preset').upper(), app.font(8), T["muted"]).pack(side="left", padx=(px(18), px(6)))
        self.preset = Dropdown(bar, app.font(8, False), width=12)
        self.preset.pack(side="left")
        cols = tk.Frame(inner, bg=T["panel"])
        cols.pack(fill="x", padx=px(12), pady=(px(6), px(12)))
        self.sliders: List[VSlider] = []
        self.values: List[tk.Label] = []
        for i, (name, _kind, freq, _q) in enumerate(eqmod.BANDS):
            col = tk.Frame(cols, bg=T["panel"])
            col.pack(side="left", expand=True, fill="x")
            val = label(col, "0 dB", app.font(9), bg=T["panel"], anchor="center")
            val.pack(fill="x")
            slider = VSlider(col, lambda v, i=i: self._band(i, v), width=px(60), height=px(170))
            slider.pack()
            label(col, t(f'eq.band.{i + 1}').upper(), app.font(8), T["muted"], bg=T["panel"],
                  anchor="center").pack(fill="x")
            label(col, f"{freq / 1000:g} kHz" if freq >= 1000 else f"{freq:g} Hz",
                  app.font(8, False), T["dim"], bg=T["panel"], anchor="center").pack(fill="x")
            self.sliders.append(slider)
            self.values.append(val)
        buttons = tk.Frame(self.body, bg=T["bg"])
        buttons.pack(fill="x", padx=self.pad, pady=(px(12), 0))
        self.remove_one = WolkButton(buttons, t('eq.remove_one'), self._remove_one, app.font(8),
                                     "ghost", padx=px(10), pady=px(4))
        self.remove_one.pack(side="left")
        self.remove_all = WolkButton(buttons, t('eq.remove_all'), self._remove_all, app.font(8),
                                     "danger", padx=px(10), pady=px(4))
        self.remove_all.pack(side="left", padx=(px(8), 0))
        self.footer = self.note(t('eq.footer'))
        self.footer.config(fg=T["dim"])

    def _node(self, st: State) -> Optional[Node]:
        return next((n for n in st.sinks if n.name == self.sel), None)

    def refresh(self):
        app = self.app
        st = app.backend.state()
        if not st.sinks:
            self.menu.set_options([], None)
            return
        if self.sel not in [n.name for n in st.sinks]:
            default = st.sink_by_id(st.default_sink) or st.sinks[0]
            self.sel = default.name
        node = self._node(st)
        self.menu.set_options([(n.title, n.name) for n in st.sinks], self.sel, self._select)
        saved = app.eqm.get(node.name)
        self.toggle.set(saved.enabled)
        if not any(s.dragging for s in self.sliders):
            self.gains = list(saved.gains)
            for i, g in enumerate(self.gains):
                self.sliders[i].set(g)
                self.values[i].config(text=self._db(g))
        self.preset.set_options([(t(f'eq.p.{p}'), p) for p in eqmod.PRESETS] + [(t('eq.p.custom'), 'custom')],
                                eqmod.preset_name(self.gains), self._preset)
        live = node.name in st.eq_sinks
        if saved.enabled and live:
            self.state_label.config(text="● " + t('eq.active'), fg=T["accent"])
        elif saved.enabled:
            self.state_label.config(text="● " + t('eq.starting'), fg=T["gold"])
        else:
            self.state_label.config(text=t('eq.off'), fg=T["muted"])
        if self.pending_default and self.pending_default in st.eq_sinks:
            sink = st.eq_sinks[self.pending_default]
            self.pending_default = None
            app.backend.set_default(sink)
        installed = app.eqm.installed() or app.eqm.any_enabled()
        if installed:
            self.remove_all.pack(side="left", padx=(app.px(8), 0))
        else:
            self.remove_all.pack_forget()

    @staticmethod
    def _db(v: float) -> str:
        return f"{v:+.1f} dB" if abs(v) >= 0.05 else "0 dB"

    def _select(self, name: str):
        self.sel = name
        self.refresh()

    # — changing bands —
    def _push(self, st: State):
        """Send the gains to the running chain, if there is one."""
        sink = st.eq_sinks.get(self.sel)
        if sink is None or not self.app.eqm.get(self.sel).enabled:
            return
        params: List[Any] = []
        for i, g in enumerate(self.gains):
            params += [f"{eqmod.control_names(i)}:Gain", g]
        params += ["preamp:Mult", eqmod.preamp_gain(self.gains)]
        self.app.backend.set_param(sink.id, params)

    def _band(self, i: int, v: float):
        self.gains[i] = v
        self.values[i].config(text=self._db(v))
        self._push(self.app.backend.state())
        self._save_soon()

    def _preset(self, name: str):
        if name == 'custom':
            return
        self.gains = [float(g) for g in eqmod.PRESETS[name]]
        for i, g in enumerate(self.gains):
            self.sliders[i].set(g)
            self.values[i].config(text=self._db(g))
        self._push(self.app.backend.state())
        self._save_soon()
        self.app.glitch.now(self.panel)

    def _save_soon(self):
        if self._save_job:
            self.after_cancel(self._save_job)
        self._save_job = self.after(400, self._save)

    def _save(self):
        self._save_job = None
        st = self.app.backend.state()
        node = self._node(st)
        if node is not None:
            self.app.eqm.save_gains(node.name, node.title, self.gains)
        self.preset.show(eqmod.preset_name(self.gains))

    # — on, off, remove —
    def _leave_eq(self, names: List[str], work: Callable[[], Any], message: str):
        """Make sure no EQ'd output is the default before its chain goes away."""
        app = self.app
        st = app.backend.state()
        back = []
        for name in names:
            sink = st.eq_sinks.get(name)
            real = next((n for n in st.sinks if n.name == name), None)
            if sink is not None and real is not None and st.default_sink_raw == sink.id:
                back.append(real)

        def job():
            for real in back:
                if app.backend.fake:
                    app.backend.set_default(real)
                else:
                    run(['wpctl', 'set-default', str(real.id)])
            return work()

        app.backend.submit(job, lambda _r: (app.message(message), self.refresh()))

    def _enable(self, on: bool):
        app = self.app
        st = app.backend.state()
        node = self._node(st)
        if node is None:
            return
        if on:
            if st.default_sink == node.id:
                self.pending_default = node.name
            self.state_label.config(text="● " + t('eq.starting'), fg=T["gold"])
            gains = list(self.gains)
            app.backend.submit(lambda: app.eqm.enable(node.name, node.title, gains),
                               lambda ok: (app.message(t('msg.eq_on' if ok is True else 'msg.eq_failed'),
                                                       None if ok is True else T["pink"]),
                                           self.refresh()))
        else:
            self.pending_default = None
            self._leave_eq([node.name], lambda: app.eqm.disable(node.name), t('msg.eq_off'))

    def _remove_one(self):
        node = self._node(self.app.backend.state())
        if node is not None:
            self._leave_eq([node.name], lambda: self.app.eqm.remove(node.name), t('msg.eq_removed'))

    def _remove_all(self):
        app = self.app
        names = list(app.eqm.outputs) + [n for n in app.backend.state().eq_sinks]
        self.pending_default = None
        self._leave_eq(names, app.eqm.remove_all, t('msg.eq_removed_all'))


# ─── Scarlett ─────────────────────────────────────────────────

def short_name(name: str, prefix: str = "") -> str:
    name = name[len(prefix):] if prefix and name.startswith(prefix) else name
    name = re.sub(r'\s+(Playback|Capture)?\s*(Switch|Volume|Enum)$', '', name).strip()
    return name or "?"


class ControlWidget:
    """One amixer control: a toggle, a slider or a menu, kept in step with the card."""

    def __init__(self, view: "ScarlettView", parent, control: Control, name: str):
        self.view, self.control = view, control
        app = view.app
        px = app.px
        self.row = tk.Frame(parent, bg=T["panel"])
        self.row.pack(fill="x", padx=px(12), pady=px(3))
        self.kind = control.kind
        self.dragging = False
        self.job: Optional[str] = None
        if not control.writable:
            label(self.row, name, app.font(9), T["muted"], bg=T["panel"]).pack(side="left")
            self.text = label(self.row, "", app.font(9), bg=T["panel"])
            self.text.pack(side="right")
            self.kind = 'READONLY'
        elif control.kind == 'BOOLEAN':
            self.toggle = Toggle(self.row, name, control.on, self._toggle, app.font(8))
            self.toggle.pack(side="left")
        elif control.kind == 'ENUMERATED':
            label(self.row, name, app.font(9), bg=T["panel"]).pack(side="left")
            self.menu = Dropdown(self.row, app.font(8, False), width=22)
            self.menu.pack(side="right")
        elif control.kind == 'INTEGER':
            label(self.row, name, app.font(9), bg=T["panel"], width=26).pack(side="left")
            self.text = label(self.row, "", app.font(8), T["muted"], bg=T["panel"], width=10, anchor="e")
            self.text.pack(side="right")
            self.slider = Slider(self.row, self._slide, height=px(22), lo=control.lo, hi=max(control.hi, control.lo + 1),
                                 step=1)
            self.slider.pack(side="left", fill="x", expand=True)
        else:
            label(self.row, name, app.font(9), T["muted"], bg=T["panel"]).pack(side="left")
            self.kind = 'READONLY'
            self.text = label(self.row, "", app.font(8), bg=T["panel"])
            self.text.pack(side="right")
        self.update(control)

    def update(self, control: Control):
        self.control = control
        if self.kind == 'BOOLEAN':
            self.toggle.set(control.on)
        elif self.kind == 'ENUMERATED':
            self.menu.set_options([(item, i) for i, item in enumerate(control.items)], control.value,
                                  self._pick)
        elif self.kind == 'INTEGER':
            self.slider.set(control.value)
            self.text.config(text=self._show(control, control.value))
        else:
            vals = control.values
            if control.items and vals and vals[0].isdigit() and int(vals[0]) < len(control.items):
                self.text.config(text=control.items[int(vals[0])])
            else:
                self.text.config(text=','.join(vals[:4]) + ('...' if len(vals) > 4 else ''))

    @staticmethod
    def _show(c: Control, v: float) -> str:
        if c.db_lo is not None and c.db_hi is not None and c.hi > c.lo:
            return f"{c.db_lo + (v - c.lo) / (c.hi - c.lo) * (c.db_hi - c.db_lo):+.1f} dB"
        return str(int(v))

    def _toggle(self, on: bool):
        self.view.write(self.control, on)

    def _pick(self, index: int):
        self.view.write(self.control, index)

    def _slide(self, v: float):
        self.text.config(text=self._show(self.control, v))
        if self.job:
            self.row.after_cancel(self.job)
        self.job = self.row.after(60, lambda: self.view.write(self.control, int(v)))


class ScarlettView(Page):
    def __init__(self, app):
        super().__init__(app)
        self.iface: Optional[Interface] = None
        self.signature: Any = None
        self.widgets: Dict[int, ControlWidget] = {}
        self.mix_letter = 'A'
        self._busy = False
        self.content = tk.Frame(self.body, bg=T["bg"])
        self.content.pack(fill="x")

    def interfaces(self) -> List[Interface]:
        return self.app.scarlett

    def refresh(self):
        faces = self.interfaces()
        if not faces:
            return
        if self.iface is None or self.iface not in faces:
            self.iface = faces[0]
            self.signature = None
        self.poll()

    def poll(self):
        iface = self.iface
        if iface is None or self._busy:
            return
        self._busy = True

        def done(controls):
            self._busy = False
            if isinstance(controls, Exception) or not self.winfo_exists():
                return
            self.show(iface, controls)
        self.app.backend.submit(iface.read, done)

    def write(self, control: Control, value):
        iface = self.iface
        if iface is None:
            return

        def done(ok):
            if ok is not True:
                self.app.message(t('scarlett.write_failed', name=control.name), T["pink"])
            self.poll()
        self.app.backend.submit(lambda: iface.set(control, value), done)

    def show(self, iface: Interface, controls: List[Control]):
        controls = [c for c in controls if c.name != 'Level Meter']
        signature = (iface.card, tuple(c.numid for c in controls), self.mix_letter)
        if signature != self.signature:
            self.signature = signature
            self.build(iface, controls)
        for c in controls:
            w = self.widgets.get(c.numid)
            if w is None:
                continue
            slider = getattr(w, 'slider', None)
            if slider is not None and slider.dragging:
                continue
            w.update(c)

    def build(self, iface: Interface, controls: List[Control]):
        app = self.app
        for child in self.content.winfo_children():
            child.destroy()
        self.widgets = {}
        page = classify(controls)

        def section(title: str, hint: str = ""):
            head = tk.Frame(self.content, bg=T["bg"])
            head.pack(fill="x", padx=self.pad, pady=(app.px(16), app.px(6)))
            label(head, title.upper(), app.font(8), T["muted"]).pack(side="left")
            if hint:
                label(head, hint, app.font(8, False), T["dim"]).pack(side="left", padx=(app.px(10), 0))
            tk.Frame(head, bg=T["line"], height=1).pack(side="left", fill="x", expand=True,
                                                        padx=(app.px(10), 0))
            panel = GlitchPanel(self.content, T["panel"])
            panel.pack(fill="x", padx=self.pad)
            box = tk.Frame(panel.inner, bg=T["panel"])
            box.pack(fill="x", pady=app.px(6))
            return box

        def add(box, c: Control, name: str):
            self.widgets[c.numid] = ControlWidget(self, box, c, name)

        intro = label(self.content, t('scarlett.note', name=iface.name), app.font(8, False), T["muted"],
                      justify="left", wraplength=app.px(860))
        intro.pack(fill="x", padx=self.pad, pady=(app.px(8), 0))
        if len(self.interfaces()) > 1:
            row = tk.Frame(self.content, bg=T["bg"])
            row.pack(fill="x", padx=self.pad, pady=(app.px(8), 0))
            menu = Dropdown(row, app.font(9, False), width=30)
            menu.pack(side="left")
            menu.set_options([(f.name, f.card) for f in self.interfaces()], iface.card, self._switch)

        for number in sorted(page.inputs):
            box = section(t('scarlett.input', n=number))
            for c in page.inputs[number]:
                add(box, c, short_name(c.name, f"Line In {number} "))
        if page.phantom:
            box = section(t('scarlett.phantom'), t('scarlett.phantom_hint'))
            for c in page.phantom:
                add(box, c, short_name(c.name))
        if page.monitor:
            box = section(t('scarlett.monitor'))
            for c in page.monitor:
                add(box, c, short_name(c.name))
        if page.outputs:
            box = section(t('scarlett.outputs'))
            for c in page.outputs:
                add(box, c, short_name(c.name))
        if page.mix:
            letters = sorted(page.mix)
            if self.mix_letter not in letters:
                self.mix_letter = letters[0]
            box = section(t('scarlett.mix'), t('scarlett.mix_hint'))
            sel = tk.Frame(box, bg=T["panel"])
            sel.pack(fill="x", padx=app.px(12), pady=(0, app.px(4)))
            menu = Dropdown(sel, app.font(8, False), width=10)
            menu.pack(side="left")
            menu.set_options([(t('scarlett.mix_n', letter=l), l) for l in letters], self.mix_letter,
                             self._mix)
            for n in sorted(page.mix[self.mix_letter]):
                add(box, page.mix[self.mix_letter][n], t('scarlett.mix_input', n=n))
        if page.routing:
            box = section(t('scarlett.routing'), t('scarlett.routing_hint'))
            for c in page.routing:
                add(box, c, short_name(c.name))
        if page.status:
            box = section(t('scarlett.status'))
            for c in page.status:
                add(box, c, short_name(c.name))
        if page.other:
            box = section(t('scarlett.other'))
            for c in page.other:
                add(box, c, short_name(c.name))
        if not controls:
            label(self.content, t('scarlett.empty'), app.font(9), T["muted"]).pack(
                fill="x", padx=self.pad, pady=app.px(12))

    def _switch(self, card: int):
        self.iface = next((f for f in self.interfaces() if f.card == card), self.iface)
        self.signature = None
        self.poll()

    def _mix(self, letter: str):
        self.mix_letter = letter
        self.signature = None
        self.poll()
