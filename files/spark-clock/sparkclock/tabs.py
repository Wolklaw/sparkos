"""The four tabs. Each is a frame with reload() (rebuild from the app's data, when a file
changed) and tick(now) (update the numbers that move)."""

import datetime as dt
import time
import tkinter as tk
from typing import Any, Dict, List, Optional

from . import cities, core, sound, store, wake
from .schedule import days_words, next_alarm_time, until_words
from .text import t
from .widgets import GlitchPanel, GlitchText, Segmented, Strip, T, Toggle, WolkButton, make_table


def day_names() -> List[str]:
    return [t(f'day.{d}') for d in range(7)]


def days_text(days: List[int]) -> str:
    return days_words(days, day_names(), t('days.every'), t('days.weekdays'), t('days.weekend'),
                      t('days.once'))


class ScrollList(tk.Frame):
    """A column of rows that scrolls when there are more than fit."""

    def __init__(self, parent: tk.Misc):
        super().__init__(parent, bg=T["bg"])
        self.canvas = tk.Canvas(self, bg=T["bg"], highlightthickness=0, bd=0)
        self.bar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview, width=10,
                                bg=T["panel2"], troughcolor=T["bg"], bd=0, highlightthickness=0,
                                activebackground=T["line2"])
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=T["bg"])
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window,
                                                                              width=e.width))
        for widget in (self.canvas, self.inner):
            widget.bind("<Button-4>", lambda _e: self.canvas.yview_scroll(-2, "units"))
            widget.bind("<Button-5>", lambda _e: self.canvas.yview_scroll(2, "units"))

    def clear(self):
        for child in self.inner.winfo_children():
            child.destroy()


class Tab(tk.Frame):
    def __init__(self, app, heading: str, sub: str):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        px = app.px
        top = tk.Frame(self, bg=T["bg"])
        top.pack(fill="x", padx=px(22), pady=(px(14), px(4)))
        self.top = top
        self.heading = GlitchText(top, heading, app.f_head, T["bg"])
        self.heading.pack(anchor="w")
        tk.Label(top, text=sub, bg=T["bg"], fg=T["muted"], font=app.f_body, anchor="w",
                 justify="left").pack(fill="x", pady=(px(2), 0))
        app.glitch.add(self.heading)

    def panel(self, parent: tk.Misc, pady: int = 4):
        """A flat panel; returns (panel, inner)."""
        px = self.app.px
        panel = GlitchPanel(parent, T["panel"])
        panel.pack(fill="x", padx=px(16), pady=px(pady))
        inner = tk.Frame(panel.inner, bg=T["panel"])
        inner.pack(fill="both", expand=True, padx=px(14), pady=px(10))
        return panel, inner

    def reload(self):
        pass

    def tick(self, now: float):
        pass


# ─── alarms ───

class AlarmsTab(Tab):
    def __init__(self, app):
        super().__init__(app, t('alarms.heading'), t('alarms.sub'))
        px = app.px
        WolkButton(self.top, t('alarms.new'), self.new, app.f_label, variant="primary",
                   padx=10, pady=4).place(relx=1.0, y=0, anchor="ne")
        footer = tk.Frame(self, bg=T["bg"])
        footer.pack(side="bottom", fill="x", padx=px(18), pady=(0, px(6)))
        self.footer = footer
        wake_row = tk.Frame(self, bg=T["bg"])
        wake_row.pack(side="bottom", fill="x", padx=px(18), pady=(0, px(4)))
        self.wake = Toggle(wake_row, t('wake.label'), bool(app.config['settings']['wake']),
                           self.set_wake, app.f_label)
        self.wake.pack(side="left", anchor="n")
        self.wake_text = tk.Label(wake_row, text="", bg=T["bg"], fg=T["muted"], font=app.f_small,
                                  anchor="w", justify="left", wraplength=px(640))
        self.wake_text.pack(side="left", fill="x", expand=True, padx=(px(10), 0))
        tk.Label(footer, text=t('alarms.sound_volume'), bg=T["bg"], fg=T["muted"],
                 font=app.f_label).pack(side="left")
        self.volume = Segmented(footer, [(f"{v}", v) for v in (25, 50, 80, 100)],
                                app.config['settings']['volume'], self.set_volume, app.f_label)
        self.volume.pack(side="left", padx=(px(8), px(16)))
        tk.Label(footer, text=t('alarms.ring_for'), bg=T["bg"], fg=T["muted"],
                 font=app.f_label).pack(side="left")
        self.ring_for = Segmented(footer, [(t('alarms.minutes', n=n), n) for n in (1, 5, 10, 30)],
                                  app.config['settings']['ring_minutes'], self.set_ring_for,
                                  app.f_label)
        self.ring_for.pack(side="left", padx=(px(8), px(16)))
        self.test = WolkButton(footer, t('alarms.test'), self.test_sound, app.f_label,
                               padx=8, pady=3)
        self.test.pack(side="left")
        self.list = ScrollList(self)
        self.list.pack(fill="both", expand=True, padx=px(8), pady=px(4))
        self.rows: List[Dict[str, Any]] = []

    # editing

    def new(self):
        from .editor import AlarmEditor
        return AlarmEditor(self.app, None)

    def edit(self, alarm: Dict[str, Any]):
        from .editor import AlarmEditor
        return AlarmEditor(self.app, alarm)

    def toggle(self, alarm_id: str, on: bool):
        def change(config):
            for alarm in config['alarms']:
                if alarm['id'] == alarm_id:
                    alarm['enabled'] = on
        store.update_config(change)
        self.app.refresh_data(force=True)
        self.app.event()

    def delete(self, alarm: Dict[str, Any]):
        if not self.app.ask(t('alarms.delete_title'),
                            t('alarms.delete_body', time=alarm['time'], label=alarm['label']),
                            parent=self.app.root):
            return
        store.update_config(lambda c: c.update(
            alarms=[a for a in c['alarms'] if a['id'] != alarm['id']]))
        self.app.refresh_data(force=True)
        self.app.event(strong=True)

    def set_volume(self, value: int):
        store.update_config(lambda c: c['settings'].update(volume=value))
        self.app.refresh_data(force=True)

    def set_wake(self, value: bool):
        store.update_config(lambda c: c['settings'].update(wake=value))
        self.app.refresh_data(force=True)
        self.app.event()

    def wake_words(self) -> str:
        """The honest state of the wake option, from what the service last wrote."""
        app = self.app
        if not wake.available():
            return t('wake.unavailable')
        text = t('wake.note')
        if not app.config['settings']['wake']:
            return text
        note = app.service.get('wake') or {}
        state = note.get('state')
        if not store.service_alive(app.clock(), app.service) or state is None:
            return text + "  " + t('wake.pending')
        if state == 'failed':
            return text + "  " + t('wake.failed', error=note.get('error', ''))
        if state == 'armed' and isinstance(note.get('at'), (int, float)):
            when = time.strftime('%a %H:%M', time.localtime(note['at']))
            return text + "  " + t('wake.armed', when=when)
        return text + "  " + t('wake.none')

    def set_ring_for(self, value: int):
        store.update_config(lambda c: c['settings'].update(ring_minutes=value))
        self.app.refresh_data(force=True)

    def test_sound(self):
        sound_name = self.app.config['settings']['sound']
        if sound.play_once(sound_name, self.app.config['settings']['volume']) is None:
            self.app.flash(t('alarms.test_none'), T["pink"])
            self.app.event(strong=True)

    # drawing

    def reload(self):
        app, px = self.app, self.app.px
        self.volume.set(app.config['settings']['volume'])
        self.ring_for.set(app.config['settings']['ring_minutes'])
        self.wake.set(bool(app.config['settings']['wake']))
        self.wake_text.config(text=self.wake_words())
        self.list.clear()
        self.rows = []
        alarms = sorted(app.config['alarms'], key=lambda a: a['time'])
        if not alarms:
            tk.Label(self.list.inner, text=t('alarms.empty'), bg=T["bg"], fg=T["muted"],
                     font=app.f_body, anchor="w", wraplength=px(600), justify="left"
                     ).pack(fill="x", padx=px(14), pady=px(14))
            return
        for alarm in alarms:
            panel = GlitchPanel(self.list.inner, T["panel"])
            panel.pack(fill="x", padx=px(8), pady=px(4))
            inner = tk.Frame(panel.inner, bg=T["panel"])
            inner.pack(fill="both", expand=True, padx=px(14), pady=px(10))
            on = alarm['enabled']
            clock = tk.Label(inner, text=alarm['time'], bg=T["panel"], font=app.f_big,
                             fg=T["text"] if on else T["dim"])
            clock.pack(side="left")
            mid = tk.Frame(inner, bg=T["panel"])
            mid.pack(side="left", fill="x", expand=True, padx=(px(16), 0))
            tk.Label(mid, text=alarm['label'] or t('alarms.no_label'), bg=T["panel"],
                     fg=T["text"] if on else T["muted"], font=app.f_title, anchor="w"
                     ).pack(fill="x")
            sub = tk.Label(mid, text="", bg=T["panel"], fg=T["muted"], font=app.f_small,
                           anchor="w")
            sub.pack(fill="x")
            right = tk.Frame(inner, bg=T["panel"])
            right.pack(side="right")
            Toggle(right, t('alarms.on'), on, lambda v, i=alarm['id']: self.toggle(i, v),
                   app.f_label).pack(side="left", padx=(0, px(8)))
            WolkButton(right, t('alarms.edit'), lambda a=alarm: self.edit(a), app.f_label,
                       padx=8, pady=3).pack(side="left", padx=(0, px(6)))
            WolkButton(right, t('alarms.delete'), lambda a=alarm: self.delete(a), app.f_label,
                       variant="danger", padx=8, pady=3).pack(side="left")
            self.rows.append({'alarm': alarm, 'sub': sub, 'panel': panel})
        self.tick(app.clock())

    def tick(self, now: float):
        for row in self.rows:
            alarm = row['alarm']
            if alarm['enabled']:
                at = next_alarm_time(alarm, now)
                when = until_words(at - now, t('until.h'), t('until.m'), t('until.d')) if at else ''
                text = f"{days_text(alarm['days'])}  ·  " + t('alarms.next', when=when)
            else:
                text = f"{days_text(alarm['days'])}  ·  " + t('alarms.off')
            if row['sub'].cget('text') != text:
                row['sub'].config(text=text)


# ─── timers ───

class TimersTab(Tab):
    def __init__(self, app):
        super().__init__(app, t('timers.heading'), t('timers.sub'))
        px = app.px
        self.remove_mode = False
        panel, inner = self.panel(self, pady=6)
        self.new_panel = panel
        row = tk.Frame(inner, bg=T["panel"])
        row.pack(fill="x")
        self.fields = {}
        for name, top in (('hours', 99), ('minutes', 59), ('seconds', 59)):
            box = tk.Frame(row, bg=T["panel"])
            box.pack(side="left", padx=(0, px(8)))
            tk.Label(box, text=t('timers.' + name), bg=T["panel"], fg=T["muted"],
                     font=app.f_label).pack(anchor="w")
            spin = tk.Spinbox(box, from_=0, to=top, width=3, format="%02.0f", wrap=True,
                              font=app.f_title, bg=T["panel2"], fg=T["text"],
                              insertbackground=T["accent"], buttonbackground=T["panel2"],
                              relief="flat", highlightthickness=1, highlightbackground=T["line"],
                              highlightcolor=T["accent"], justify="center")
            spin.delete(0, "end")
            spin.insert(0, "00")
            spin.pack()
            self.fields[name] = spin
        label_box = tk.Frame(row, bg=T["panel"])
        label_box.pack(side="left", fill="x", expand=True, padx=(px(8), px(8)))
        tk.Label(label_box, text=t('timers.label'), bg=T["panel"], fg=T["muted"],
                 font=app.f_label).pack(anchor="w")
        self.label = tk.Entry(label_box, font=app.f_title, bg=T["panel2"], fg=T["text"],
                              insertbackground=T["accent"], relief="flat", highlightthickness=1,
                              highlightbackground=T["line"], highlightcolor=T["accent"])
        self.label.pack(fill="x")
        self.label.bind("<Return>", lambda _e: self.start())
        start_box = tk.Frame(row, bg=T["panel"])
        start_box.pack(side="right", anchor="s")
        WolkButton(start_box, t('timers.start'), self.start, app.f_label, variant="primary",
                   padx=12, pady=6).pack()
        presets = tk.Frame(inner, bg=T["panel"])
        presets.pack(fill="x", pady=(px(10), 0))
        self.presets = presets
        self.preset_row = tk.Frame(presets, bg=T["panel"])
        self.preset_row.pack(fill="x")
        tools = tk.Frame(inner, bg=T["panel"])
        tools.pack(fill="x", pady=(px(8), 0))
        WolkButton(tools, t('timers.save_preset'), self.save_preset, app.f_label, padx=8,
                   pady=3).pack(side="left", padx=(0, px(8)))
        self.remove_toggle = Toggle(tools, t('timers.remove_presets'), False,
                                    self.set_remove_mode, app.f_label)
        self.remove_toggle.pack(side="left")
        self.zero = tk.Label(tools, text="", bg=T["panel"], fg=T["pink"], font=app.f_label)
        self.zero.pack(side="right")
        self.list = ScrollList(self)
        self.list.pack(fill="both", expand=True, padx=px(8), pady=px(4))
        self.rows: Dict[str, Dict[str, Any]] = {}

    # the entry

    def entered(self) -> int:
        total = 0
        for name, mult in (('hours', 3600), ('minutes', 60), ('seconds', 1)):
            try:
                total += int(float(self.fields[name].get() or 0)) * mult
            except ValueError:
                return 0
        return total

    def set_entry(self, seconds: int):
        h, rest = divmod(int(seconds), 3600)
        m, s = divmod(rest, 60)
        for name, value in (('hours', h), ('minutes', m), ('seconds', s)):
            self.fields[name].delete(0, "end")
            self.fields[name].insert(0, f"{value:02d}")

    def start(self, seconds: Optional[int] = None):
        seconds = self.entered() if seconds is None else seconds
        if seconds <= 0:
            self.zero.config(text=t('timers.zero'))
            self.app.event(strong=True)
            return None
        self.zero.config(text="")
        if len(self.app.timers) >= store.MAX_TIMERS:
            self.zero.config(text=t('timers.too_many'))
            return None
        timer = store.add_timer(seconds, self.label.get().strip(), now=self.app.clock())
        self.label.delete(0, "end")
        self.app.refresh_data(force=True)
        self.app.event()
        return timer

    def save_preset(self):
        seconds = self.entered()
        if seconds <= 0:
            self.zero.config(text=t('timers.zero'))
            self.app.event(strong=True)
            return
        store.update_config(lambda c: c['presets'].append(seconds))
        self.app.refresh_data(force=True)

    def set_remove_mode(self, on: bool):
        self.remove_mode = on
        self.reload()

    def preset_click(self, seconds: int):
        if self.remove_mode:
            store.update_config(lambda c: c.update(
                presets=[p for p in c['presets'] if p != seconds]))
            self.app.refresh_data(force=True)
        else:
            self.set_entry(seconds)
            self.start(seconds)

    # a timer's buttons

    def change(self, timer_id: str, what: str):
        now = self.app.clock()

        def edit(timers):
            for timer in list(timers):
                if timer['id'] != timer_id:
                    continue
                if what == 'delete':
                    timers.remove(timer)
                elif what == 'pause' and timer['state'] == 'running':
                    timer.update(state='paused', remaining=max(0.0, timer['end'] - now),
                                 end=None)
                elif what == 'resume' and timer['state'] == 'paused':
                    timer.update(state='running', end=now + timer['remaining'])
                elif what == 'restart':
                    timer.update(state='running', end=now + timer['duration'],
                                 remaining=timer['duration'])
        store.update_timers(edit)
        if what in ('stop', 'delete'):
            store.send_command('stop', f"timer:{timer_id}")
        self.app.refresh_data(force=True)
        self.app.event()

    # drawing

    def reload(self):
        app, px = self.app, self.app.px
        for child in self.preset_row.winfo_children():
            child.destroy()
        for seconds in app.config['presets']:
            WolkButton(self.preset_row, ("× " if self.remove_mode else "") + core.duration_words(
                seconds), lambda s=seconds: self.preset_click(s), app.f_label,
                variant="danger" if self.remove_mode else "ghost", padx=8, pady=3
            ).pack(side="left", padx=(0, px(6)), pady=(0, px(4)))
        self.list.clear()
        self.rows = {}
        if not app.timers:
            tk.Label(self.list.inner, text=t('timers.empty'), bg=T["bg"], fg=T["muted"],
                     font=app.f_body, anchor="w").pack(fill="x", padx=px(14), pady=px(14))
            return
        for timer in app.timers:
            panel = GlitchPanel(self.list.inner, T["panel"])
            panel.pack(fill="x", padx=px(8), pady=px(4))
            inner = tk.Frame(panel.inner, bg=T["panel"])
            inner.pack(fill="both", expand=True, padx=px(14), pady=px(10))
            top = tk.Frame(inner, bg=T["panel"])
            top.pack(fill="x")
            left = tk.Frame(top, bg=T["panel"])
            left.pack(side="left")
            clock = tk.Label(left, text="", bg=T["panel"], font=app.f_big, fg=T["text"])
            clock.pack(side="left")
            mid = tk.Frame(top, bg=T["panel"])
            mid.pack(side="left", fill="x", expand=True, padx=(px(16), 0))
            tk.Label(mid, text=timer['label'] or t('timers.no_label'), bg=T["panel"],
                     fg=T["text"], font=app.f_title, anchor="w").pack(fill="x")
            sub = tk.Label(mid, text="", bg=T["panel"], fg=T["muted"], font=app.f_small,
                           anchor="w")
            sub.pack(fill="x")
            right = tk.Frame(top, bg=T["panel"])
            right.pack(side="right")
            main = WolkButton(right, t('timers.pause'), lambda: None, app.f_label, padx=8, pady=3)
            main.pack(side="left", padx=(0, px(6)))
            again = WolkButton(right, t('timers.restart'),
                               lambda i=timer['id']: self.change(i, 'restart'), app.f_label,
                               padx=8, pady=3)
            again.pack(side="left", padx=(0, px(6)))
            WolkButton(right, t('timers.delete'), lambda i=timer['id']: self.change(i, 'delete'),
                       app.f_label, variant="danger", padx=8, pady=3).pack(side="left")
            bar = Strip(inner, height=3)
            bar.pack(fill="x", pady=(px(8), 0))
            self.rows[timer['id']] = {'timer': timer, 'clock': clock, 'sub': sub, 'bar': bar,
                                      'main': main, 'again': again, 'state': None,
                                      'panel': panel}
        self.tick(app.clock())

    def tick(self, now: float):
        for row in self.rows.values():
            timer = row['timer']
            left = store.timer_left(timer, now)
            state = timer['state']
            if state == 'running' and left <= 0:
                state = 'ringing'         # the service is about to say so
            clock = core.hms(left if state != 'running' else left + 0.99)
            if row['clock'].cget('text') != clock:
                row['clock'].config(text=clock)
            colour = {'ringing': T["pink"], 'done': T["dim"], 'paused': T["muted"]}.get(
                state, T["text"])
            row['clock'].config(fg=colour)
            row['bar'].draw(fraction=(left / timer['duration']) if timer['duration'] else 0)
            if row['state'] != state:
                row['state'] = state
                names = {'ringing': t('timers.ringing'), 'done': t('timers.done'),
                         'paused': t('timers.paused')}
                row['sub'].config(text=core.duration_words(timer['duration']) + (
                    "  ·  " + names[state] if state in names else ""))
                tid = timer['id']
                if state == 'running':
                    row['main'].set_text(t('timers.pause'))
                    row['main'].command = lambda i=tid: self.change(i, 'pause')
                elif state == 'paused':
                    row['main'].set_text(t('timers.resume'))
                    row['main'].command = lambda i=tid: self.change(i, 'resume')
                else:
                    row['main'].set_text(t('timers.stop'))
                    row['main'].command = lambda i=tid: self.change(i, 'stop')
                row['main'].set_enabled(state != 'done')
                if state == 'ringing':
                    self.app.event(row['panel'], strong=True)


# ─── stopwatch ───

class StopwatchTab(Tab):
    def __init__(self, app):
        super().__init__(app, t('sw.heading'), t('sw.sub'))
        px = app.px
        panel, inner = self.panel(self, pady=8)
        self.big = tk.Label(inner, text="00:00.0", bg=T["panel"], fg=T["text"], font=app.f_huge)
        self.big.pack(pady=(px(8), px(10)))
        buttons = tk.Frame(inner, bg=T["panel"])
        buttons.pack(pady=(0, px(6)))
        self.main = WolkButton(buttons, t('sw.start'), self.toggle, app.f_title,
                               variant="primary", padx=18, pady=6)
        self.main.pack(side="left", padx=px(4))
        self.lap_button = WolkButton(buttons, t('sw.lap'), self.lap, app.f_title, padx=18, pady=6)
        self.lap_button.pack(side="left", padx=px(4))
        self.reset_button = WolkButton(buttons, t('sw.reset'), self.reset, app.f_title,
                                       padx=18, pady=6)
        self.reset_button.pack(side="left", padx=px(4))
        self.panel_ = panel
        frame, tree = make_table(self, ("lap", "split", "total"), show="headings")
        frame.pack(fill="both", expand=True, padx=px(16), pady=(px(4), px(10)))
        for column, key, width in (("lap", 'sw.col_lap', 80), ("split", 'sw.col_split', 200),
                                   ("total", 'sw.col_total', 200)):
            tree.heading(column, text=t(key))
            tree.column(column, width=px(width), anchor="w")
        tree.tag_configure("best", foreground=T["accent"])
        tree.tag_configure("worst", foreground=T["pink"])
        self.tree = tree
        self.empty = tk.Label(frame, text=t('sw.empty'), bg=T["panel"], fg=T["muted"],
                              font=app.f_body)
        self.shown = None

    def now_total(self, now: float) -> float:
        return store.stopwatch_total(self.app.stopwatch, now)

    def toggle(self):
        sw, now = dict(self.app.stopwatch), self.app.clock()
        if sw['started']:
            sw.update(elapsed=store.stopwatch_total(sw, now), started=None)
        else:
            sw.update(started=now)
        store.save_stopwatch(sw)
        self.app.refresh_data(force=True)
        self.app.event()

    def lap(self):
        sw, now = dict(self.app.stopwatch), self.app.clock()
        if not sw['started']:
            return
        sw['laps'] = sw['laps'] + [store.stopwatch_total(sw, now)]
        store.save_stopwatch(sw)
        self.app.refresh_data(force=True)
        self.app.event(self.panel_)

    def reset(self):
        store.save_stopwatch({'started': None, 'elapsed': 0.0, 'laps': []})
        self.app.refresh_data(force=True)
        self.app.event()

    def reload(self):
        sw = self.app.stopwatch
        running = bool(sw['started'])
        self.main.set_text(t('sw.stop') if running else t('sw.start'))
        self.lap_button.set_enabled(running)
        self.reset_button.set_enabled(not running and (sw['elapsed'] > 0 or bool(sw['laps'])))
        self.tree.delete(*self.tree.get_children())
        laps = sw['laps']
        splits = [b - a for a, b in zip([0.0] + laps[:-1], laps)]
        best = min(splits) if len(splits) >= 3 else None
        worst = max(splits) if len(splits) >= 3 else None
        for n in range(len(laps), 0, -1):
            split = splits[n - 1]
            tag = "best" if split == best else "worst" if split == worst else ""
            self.tree.insert("", "end", values=(n, core.hms(split, True), core.hms(laps[n - 1],
                                                                                  True)),
                             tags=(tag,) if tag else ())
        if laps:
            self.empty.place_forget()
        else:
            self.empty.place(relx=0.5, rely=0.5, anchor="center")

    def tick(self, now: float):
        text = core.hms(self.now_total(now), tenths=True)
        if self.big.cget('text') != text:
            self.big.config(text=text)


# ─── world clocks ───

class WorldTab(Tab):
    def __init__(self, app):
        super().__init__(app, t('world.heading'), t('world.sub'))
        px = app.px
        self.list = ScrollList(self)
        panel, inner = self.panel(self, pady=6)
        panel.pack_configure(side="bottom")
        self.list.pack(fill="both", expand=True, padx=px(8), pady=px(4))
        tk.Label(inner, text=t('world.add'), bg=T["panel"], fg=T["muted"], font=app.f_label
                 ).pack(anchor="w")
        row = tk.Frame(inner, bg=T["panel"])
        row.pack(fill="x", pady=(px(4), 0))
        self.entry = tk.Entry(row, font=app.f_body, bg=T["panel2"], fg=T["text"],
                              insertbackground=T["accent"], relief="flat", highlightthickness=1,
                              highlightbackground=T["line"], highlightcolor=T["accent"])
        self.entry.pack(side="left", fill="x", expand=True, ipady=px(3))
        self.entry.bind("<KeyRelease>", lambda _e: self.filter())
        self.entry.bind("<Return>", lambda _e: self.add())
        WolkButton(row, t('world.add_button'), self.add, app.f_label, variant="primary",
                   padx=10, pady=3).pack(side="left", padx=(px(8), 0))
        self.hint = tk.Label(inner, text=t('world.search'), bg=T["panel"], fg=T["dim"],
                             font=app.f_small, anchor="w")
        self.hint.pack(fill="x", pady=(px(4), 0))
        self.choices = tk.Listbox(inner, height=4, font=app.f_body, bg=T["panel2"], fg=T["text"],
                                  selectbackground=T["hover"], selectforeground=T["accent"],
                                  relief="flat", highlightthickness=1,
                                  highlightbackground=T["line"], activestyle="none")
        self.choices.pack(fill="x", pady=(px(4), 0))
        self.choices.bind("<Double-Button-1>", lambda _e: self.add())
        self.matches: tuple = ()
        self.rows: List[Dict[str, Any]] = []
        self.filter()

    def filter(self):
        self.matches = cities.search(self.entry.get())
        self.choices.delete(0, "end")
        for _zone, name in self.matches:
            self.choices.insert("end", name)

    def add(self) -> Optional[str]:
        """Add the selected city, else the only match, else a zone typed in full."""
        selection = self.choices.curselection()
        zone = None
        if selection:
            zone = self.matches[selection[0]][0]
        elif len(self.matches) == 1:
            zone = self.matches[0][0]
        else:
            typed = self.entry.get().strip()
            if typed and cities.zone_info(typed) is not None and '/' in typed:
                zone = typed
        if zone is None:
            self.hint.config(text=t('world.unknown'), fg=T["pink"])
            self.app.event(strong=True)
            return None
        self.hint.config(text=t('world.search'), fg=T["dim"])
        if zone not in self.app.config['world']:
            store.update_config(lambda c: c['world'].append(zone))
        self.entry.delete(0, "end")
        self.filter()
        self.app.refresh_data(force=True)
        self.app.event()
        return zone

    def remove(self, zone: str):
        store.update_config(lambda c: c.update(world=[z for z in c['world'] if z != zone]))
        self.app.refresh_data(force=True)
        self.app.event()

    def zones(self) -> List[str]:
        others = [z for z in self.app.config['world'] if z != cities.HOME_ZONE]
        return [cities.HOME_ZONE] + others

    def reload(self):
        app, px = self.app, self.app.px
        self.list.clear()
        self.rows = []
        for zone in self.zones():
            panel = GlitchPanel(self.list.inner, T["panel"])
            panel.pack(fill="x", padx=px(8), pady=px(4))
            inner = tk.Frame(panel.inner, bg=T["panel"])
            inner.pack(fill="both", expand=True, padx=px(14), pady=px(8))
            left = tk.Frame(inner, bg=T["panel"])
            left.pack(side="left", fill="x", expand=True)
            tk.Label(left, text=cities.city_name(zone).upper(), bg=T["panel"], fg=T["text"],
                     font=app.f_title, anchor="w").pack(fill="x")
            sub = tk.Label(left, text="", bg=T["panel"], fg=T["muted"], font=app.f_small,
                           anchor="w")
            sub.pack(fill="x")
            if zone != cities.HOME_ZONE:
                WolkButton(inner, t('world.remove'), lambda z=zone: self.remove(z), app.f_label,
                           variant="danger", padx=8, pady=3).pack(side="right",
                                                                  padx=(px(10), 0))
            clock = tk.Label(inner, text="", bg=T["panel"], fg=T["accent"] if zone ==
                             cities.HOME_ZONE else T["text"], font=app.f_big)
            clock.pack(side="right")
            self.rows.append({'zone': zone, 'clock': clock, 'sub': sub})
        self.tick(app.clock())

    def tick(self, now: float):
        for row in self.rows:
            there = cities.time_in(row['zone'], now)
            if there is None:
                row['clock'].config(text="--:--:--")
                row['sub'].config(text=t('world.zone_missing'))
                continue
            clock = there.strftime('%H:%M:%S')
            if row['clock'].cget('text') != clock:
                row['clock'].config(text=clock)
            if row['zone'] == cities.HOME_ZONE:
                diff_text = there.strftime('%Z')
            else:
                diff = cities.hours_from_home(row['zone'], now) or 0.0
                n = f"{abs(diff):g}"
                diff_text = (t('world.same') if diff == 0 else
                             t('world.ahead', n=n) if diff > 0 else t('world.behind', n=n))
            day = cities.day_offset(row['zone'], now)
            word = {-1: t('world.yesterday'), 0: t('world.today'), 1: t('world.tomorrow')}.get(day, '')
            text = f"{t('day.%d' % there.weekday())} {there.day}  ·  {word}  ·  {diff_text}"
            if row['sub'].cget('text') != text:
                row['sub'].config(text=text)
