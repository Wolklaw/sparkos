"""The alarm editor: a small window with the time, the days, a label, the sound and the snooze.
The tests fill its fields and call save(); nothing in it needs a mouse."""

import os
import tkinter as tk
from tkinter import filedialog
from typing import Any, Dict, Optional

from . import sound, store
from .schedule import EVERY_DAY, WEEKDAYS, parse_time
from .tabs import day_names
from .text import t
from .widgets import GlitchText, Segmented, T, Toggle, WolkButton


class AlarmEditor:
    def __init__(self, app, alarm: Optional[Dict[str, Any]]):
        self.app = app
        self.alarm = alarm
        settings = app.config['settings']
        self.sound = (alarm or {}).get('sound') or settings['sound']
        self.snooze = (alarm or {}).get('snooze') or settings['snooze']
        px = app.px
        win = tk.Toplevel(app.root, bg=T["bg"])
        self.win = win
        win.title(t('editor.edit') if alarm else t('editor.new'))
        win.transient(app.root)
        win.resizable(False, False)
        body = tk.Frame(win, bg=T["bg"])
        body.pack(fill="both", expand=True, padx=px(18), pady=px(14))
        self.heading = GlitchText(body, t('editor.edit') if alarm else t('editor.new'),
                                  app.f_title, T["bg"])
        self.heading.pack(anchor="w", pady=(0, px(10)))
        app.glitch.add(self.heading)

        self._label(body, 'editor.time')
        time_row = tk.Frame(body, bg=T["bg"])
        time_row.pack(anchor="w", pady=(px(2), px(10)))
        hour, minute = parse_time((alarm or {}).get('time', '07:00')) or (7, 0)
        self.hour = self._spin(time_row, 23, hour)
        tk.Label(time_row, text=":", bg=T["bg"], fg=T["muted"], font=app.f_big
                 ).pack(side="left", padx=px(4))
        self.minute = self._spin(time_row, 59, minute)

        self._label(body, 'editor.days')
        days_row = tk.Frame(body, bg=T["bg"])
        days_row.pack(anchor="w", pady=(px(2), px(4)))
        chosen = (alarm or {}).get('days', [] if alarm else WEEKDAYS)
        self.days = []
        for number, name in enumerate(day_names()):
            toggle = Toggle(days_row, name, number in chosen, lambda _v: self._days_changed(),
                            app.f_label)
            toggle.pack(side="left", padx=(0, px(4)))
            self.days.append(toggle)
        quick = tk.Frame(body, bg=T["bg"])
        quick.pack(anchor="w", pady=(0, px(2)))
        for key, days in (('days.every', EVERY_DAY), ('days.weekdays', WEEKDAYS),
                          ('days.once', [])):
            WolkButton(quick, t(key), lambda d=days: self.set_days(d), app.f_label, padx=6,
                       pady=2).pack(side="left", padx=(0, px(4)))
        self.once_note = tk.Label(body, text="", bg=T["bg"], fg=T["dim"], font=app.f_small,
                                  anchor="w")
        self.once_note.pack(fill="x", pady=(px(2), px(8)))

        self._label(body, 'editor.label')
        self.label = tk.Entry(body, font=app.f_body, bg=T["panel2"], fg=T["text"], width=36,
                              insertbackground=T["accent"], relief="flat", highlightthickness=1,
                              highlightbackground=T["line"], highlightcolor=T["accent"])
        self.label.pack(fill="x", pady=(px(2), px(10)), ipady=px(3))
        self.label.insert(0, (alarm or {}).get('label', ''))

        self._label(body, 'editor.sound')
        sound_row = tk.Frame(body, bg=T["bg"])
        sound_row.pack(anchor="w", pady=(px(2), px(10)))
        options = [(t('sound.' + name), name) for name in store.SOUNDS]
        shown = self.sound if self.sound in store.SOUNDS else 'file'
        self.sound_pick = Segmented(sound_row, options, shown, self.pick_sound, app.f_label)
        self.sound_pick.pack(side="left")
        WolkButton(sound_row, t('editor.file'), self.choose_file, app.f_label, padx=8, pady=3
                   ).pack(side="left", padx=(px(8), 0))
        WolkButton(sound_row, t('editor.preview'), self.preview, app.f_label, padx=8, pady=3
                   ).pack(side="left", padx=(px(8), 0))
        self.file_note = tk.Label(body, text="", bg=T["bg"], fg=T["muted"], font=app.f_small,
                                  anchor="w")
        self.file_note.pack(fill="x")

        self._label(body, 'editor.snooze')
        self.snooze_pick = Segmented(body, [(t('alarms.minutes', n=n), n) for n in store.SNOOZES],
                                     self.snooze, lambda v: setattr(self, 'snooze', v),
                                     app.f_label)
        self.snooze_pick.pack(anchor="w", pady=(px(2), px(10)))
        self.error = tk.Label(body, text="", bg=T["bg"], fg=T["pink"], font=app.f_small,
                              anchor="w", wraplength=px(420), justify="left")
        self.error.pack(fill="x")
        buttons = tk.Frame(body, bg=T["bg"])
        buttons.pack(fill="x", pady=(px(8), 0))
        WolkButton(buttons, t('editor.save'), self.save, app.f_label, variant="primary",
                   padx=14, pady=5).pack(side="right")
        WolkButton(buttons, t('editor.cancel'), self.close, app.f_label, padx=14, pady=5
                   ).pack(side="right", padx=(0, px(8)))
        win.bind("<Escape>", lambda _e: self.close())
        self._days_changed()
        self._file_note()
        win.update_idletasks()
        try:
            x = app.root.winfo_rootx() + (app.root.winfo_width() - win.winfo_reqwidth()) // 2
            y = app.root.winfo_rooty() + px(60)
            win.geometry(f"+{max(0, x)}+{max(0, y)}")
            win.grab_set()
        except tk.TclError:
            pass
        self.hour.focus_set()
        app.event(self.heading)

    # widgets

    def _label(self, parent, key):
        tk.Label(parent, text=t(key), bg=T["bg"], fg=T["muted"], font=self.app.f_label,
                 anchor="w").pack(fill="x")

    def _spin(self, parent, top: int, value: int):
        spin = tk.Spinbox(parent, from_=0, to=top, width=3, format="%02.0f", wrap=True,
                          font=self.app.f_big, bg=T["panel2"], fg=T["text"],
                          insertbackground=T["accent"], buttonbackground=T["panel2"],
                          relief="flat", highlightthickness=1, highlightbackground=T["line"],
                          highlightcolor=T["accent"], justify="center")
        spin.delete(0, "end")
        spin.insert(0, f"{value:02d}")
        spin.pack(side="left")
        return spin

    # state

    def chosen_days(self):
        return [n for n, toggle in enumerate(self.days) if toggle.value]

    def set_days(self, days):
        for number, toggle in enumerate(self.days):
            toggle.set(number in days)
        self._days_changed()

    def _days_changed(self):
        self.once_note.config(text=t('editor.once_note') if not self.chosen_days() else "")

    def pick_sound(self, name: str):
        self.sound = name
        self._file_note()

    def choose_file(self):
        path = filedialog.askopenfilename(
            parent=self.win, title=t('editor.file_title'),
            filetypes=[(t('editor.file_types'), "*.wav *.ogg *.oga *.mp3 *.flac *.opus"),
                       ("*", "*")])
        if path:
            self.sound = path
            self.sound_pick.set('file')
            self._file_note()

    def _file_note(self):
        self.file_note.config(text=(t('sound.file') + ": " + os.path.basename(self.sound))
                              if self.sound not in store.SOUNDS else "")

    def preview(self):
        if sound.play_once(self.sound, self.app.config['settings']['volume']) is None:
            self.error.config(text=t('alarms.test_none'))

    # finishing

    def values(self) -> Optional[Dict[str, Any]]:
        """The alarm as entered, or None (with the reason shown) if the time is not a time."""
        try:
            hour, minute = int(float(self.hour.get())), int(float(self.minute.get()))
        except ValueError:
            hour = minute = -1
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            self.error.config(text=t('editor.bad_time'))
            return None
        self.error.config(text="")
        return {'time': f"{hour:02d}:{minute:02d}", 'days': self.chosen_days(),
                'label': self.label.get().strip(), 'sound': self.sound, 'snooze': self.snooze}

    def save(self) -> bool:
        values = self.values()
        if values is None:
            self.app.event(self.heading, strong=True)
            return False
        alarm = self.alarm

        def change(config):
            if alarm is None:
                config['alarms'].append(dict(values, enabled=True))
                return
            for existing in config['alarms']:
                if existing['id'] == alarm['id']:
                    existing.update(values, enabled=True)
        store.update_config(change)
        self.close()
        self.app.refresh_data(force=True)
        self.app.event(strong=True)
        return True

    def close(self):
        try:
            self.win.grab_release()
        except tk.TclError:
            pass
        self.win.destroy()
