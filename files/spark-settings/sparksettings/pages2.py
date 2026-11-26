"""The other pages: Power, Default apps, Date time and language, Printers, Startup, Updates
and About."""

import time
from typing import List

import tkinter as tk

from . import APP_NAME, VERSION, clock, core, defaults, power, printers, startup, sysinfo
from .app import Page
from .i18n import _
from .ui import Choice, entry, label
from .widgets import T, Toggle, WolkButton


def clear(frame):
    for w in frame.winfo_children():
        w.destroy()


class PowerPage(Page):
    key, title, tool = 'power', "Power", 'busctl'
    index = [("Power profile", "performance balanced saver battery"),
             ("Screen off and sleep", "timer suspend idle"),
             ("Lock screen", "lock password idle resume")]

    def build(self, f):
        self.holder = tk.Frame(f, bg=T["bg"])
        self.holder.pack(fill='x')

    def refresh(self):
        self.app.bg(lambda: (power.profiles(), power.current(), power.timers(), power.lock_get(),
                             power.can_sleep()), self.render)

    def render(self, data):
        h = self.holder
        clear(h)
        profiles, now, self.timers, self.lock, self.can_sleep = data or ([], None, {}, {}, False)
        if not self.timers:
            return
        box = self.section(h, _("Power profile"))
        if not profiles:
            label(box, _("There is no power profile service on this system, "
                         "so the profile can't be changed here."), self.app.font(10), fg=T["gold"],
                  wraplength=640).pack(anchor='w')
        else:
            names = {'power-saver': _("Power saver"), 'balanced': _("Balanced"),
                     'performance': _("Performance")}
            r = self.row(box, _("Profile"))
            Choice(r, [(names[p], p) for p in profiles], now or profiles[0], self.pick,
                   self.app.font(10), 22).pack(anchor='w')
        box = self.section(h, _("Screen off and sleep"))
        f9, f10 = self.app.font(9), self.app.font(10)
        t = self.timers

        def minutes(m):
            return _("Never") if not m else _("{n} min").format(n=m)
        r = self.row(box, _("Turn the screen off after"))
        Choice(r, [(minutes(m), str(m)) for m in sorted(set(power.SCREEN_OFF_MINUTES) | {t['screen_off']})],
               str(t['screen_off']), lambda v: self.set_timer('screen_off', int(v)), f10, 12).pack(anchor='w')
        r = self.row(box, _("Sleep after"))
        if self.can_sleep:
            Choice(r, [(minutes(m), str(m)) for m in sorted(set(power.SLEEP_MINUTES) | {t['sleep']})],
                   str(t['sleep']), lambda v: self.set_timer('sleep', int(v)), f10, 12).pack(anchor='w')
        else:
            label(r, _("This computer can't sleep."), f10, fg=T["muted"]).pack(anchor='w')
        box = self.section(h, _("Lock screen"))
        lk = self.lock
        Toggle(box, _("Lock after a while without use"), bool(lk['autolock']),
               lambda v: self.set_lock(autolock=v), f9).pack(anchor='w', pady=2)
        r = self.row(box, _("Lock after"))
        Choice(r, [(minutes(m), str(m)) for m in sorted(set(power.LOCK_MINUTES) | {lk['minutes']})],
               str(lk['minutes']), lambda v: self.set_lock(minutes=int(v)), f10, 12).pack(anchor='w')
        Toggle(box, _("Lock when waking from sleep"), bool(lk['on_resume']),
               lambda v: self.set_lock(on_resume=v), f9).pack(anchor='w', pady=2)

    def set_timer(self, key, value):
        self.timers[key] = value
        t = self.timers
        self.app.bg(lambda: power.set_timers(t['screen_off'], t['sleep']),
                    lambda ok: self.say(_("Saved.") if ok else _("Could not save it."), not ok))

    def set_lock(self, **kw):
        self.lock.update(kw)
        lk = self.lock
        self.app.bg(lambda: power.lock_set(bool(lk['autolock']), int(lk['minutes']), bool(lk['on_resume'])),
                    lambda ok: self.say(_("Saved.") if ok else _("Could not save it."), not ok))

    def pick(self, name):
        self.app.bg(lambda: power.set_profile(name),
                    lambda ok: self.say(_("Power profile changed.") if ok else
                                        _("Could not change the power profile."), not ok))


class DefaultAppsPage(Page):
    key, title, tool = 'defaultapps', "Default apps", 'xdg-mime'
    index = [("Web browser", "firefox chrome internet links"),
             ("Email", "mail mailto"), ("Folders", "files file manager"),
             ("Text files", "editor txt"), ("Pictures", "image photo png jpg"),
             ("Videos", "movie mp4 mkv player"), ("Music", "audio mp3 flac player"),
             ("Archives", "zip 7z tar unpack extract"), ("Terminal", "console shell")]

    def build(self, f):
        self.holder = tk.Frame(f, bg=T["bg"])
        self.holder.pack(fill='x')

    def refresh(self):
        def work():
            apps = defaults.installed_apps()
            return apps, {k: defaults.current(m[0]) for k, _l, m in defaults.CATEGORIES}, \
                defaults.terminal_get()
        self.app.bg(work, self.render)

    def render(self, data):
        clear(self.holder)
        if not data:
            return
        apps, cur, term = data
        box = self.section(self.holder, _("Open with"))
        for key, text, mimes in defaults.CATEGORIES:
            cands = defaults.candidates(mimes, apps)
            opts = [(a.name, a.id) for a in cands]
            now = cur.get(key, '')
            if now and now not in [v for _t, v in opts]:
                opts.insert(0, (apps[now].name if now in apps else now, now))
            r = self.row(box, _(text))
            if not opts:
                label(r, _("No app found for this."), self.app.font(10), fg=T["muted"]).pack(anchor='w')
                continue
            Choice(r, opts, now or opts[0][1],
                   lambda v, mimes=mimes, text=text: self.pick(v, mimes, text),
                   self.app.font(10), 34).pack(anchor='w')
        terms = defaults.terminal_candidates(apps)
        if terms:
            r = self.row(box, _("Terminal"))
            Choice(r, [(a.name, a.id) for a in terms], term or terms[0].id, self.pick_term,
                   self.app.font(10), 34).pack(anchor='w')

    def pick(self, app_id, mimes, text):
        self.app.bg(lambda: defaults.set_default(app_id, mimes),
                    lambda ok: self.say(_("Changed: {what}.").format(what=_(text)) if ok else
                                        _("Could not change it."), not ok))

    def pick_term(self, app_id):
        ok = defaults.terminal_set(app_id)
        self.say(_("Changed: {what}.").format(what=_("Terminal")) if ok else _("Could not change it."), not ok)


class DateTimePage(Page):
    key, title, tool = 'datetime', "Date, time and language", 'busctl'
    index = [("Time zone", "eastern montreal toronto clock hour"),
             ("Set the time automatically", "ntp network time sync"),
             ("24-hour clock", "12 hour am pm format"),
             ("Language", "english french francais langue region formats")]

    def build(self, f):
        self.holder = tk.Frame(f, bg=T["bg"])
        self.holder.pack(fill='x')
        self.zones: List[str] = []

    def refresh(self):
        self.app.bg(lambda: (clock.zone(), clock.ntp(), clock.zones(), clock.languages_available(),
                             clock.language_now(), clock.clock_24h()), self.render)

    def render(self, data):
        clear(self.holder)
        if not data:
            return
        zone, ntp, zones, langs, lang, h24 = data
        self.zones = zones
        f9 = self.app.font(9)
        box = self.section(self.holder, _("Time zone"))
        if not zones:
            label(box, _("The time service (timedated) doesn't answer, so the time zone can't be changed here."),
                  self.app.font(10), fg=T["gold"], wraplength=640).pack(anchor='w')
        else:
            label(box, _("Now: {zone}").format(zone=zone or '?'), self.app.font(10)).pack(anchor='w')
            r = tk.Frame(box, bg=T["panel"])
            r.pack(fill='x', pady=6)
            self.filter = entry(r, self.app.font(10), 28)
            self.filter.pack(side='left', ipady=3)
            self.filter.bind('<KeyRelease>', lambda _e: self.fill())
            label(r, _("Type part of a city, e.g. Montreal"), self.app.font(8, False),
                  fg=T["dim"]).pack(side='left', padx=8)
            self.lb = tk.Listbox(box, height=5, bg=T["out_bg"], fg=T["text"], font=self.app.font(10),
                                 selectbackground=T["accent"], selectforeground=T["on_accent"],
                                 highlightthickness=1, highlightbackground=T["line"], bd=0,
                                 activestyle='none')
            self.lb.pack(fill='x')
            self.lb.bind('<Double-Button-1>', lambda _e: self.set_zone())
            WolkButton(box, _("Use this time zone"), self.set_zone, f9, 'primary').pack(anchor='w', pady=(8, 0))
            self.filter.insert(0, (zone or '').split('/')[-1])
            self.fill()
            r = self.row(box, _("Time"))
            Toggle(r, _("Set automatically"), bool(ntp), self.set_ntp, f9).pack(anchor='w')
            r = self.row(box, _("Set by hand"))
            self.when = entry(r, self.app.font(10), 18)
            self.when.insert(0, time.strftime('%Y-%m-%d %H:%M'))
            self.when.pack(side='left', ipady=3)
            WolkButton(r, _("Set the time"), self.set_time, f9, 'ghost').pack(side='left', padx=8)
            label(r, _("Year-month-day hour:minute. Turn off automatic time first."),
                  self.app.font(8, False), fg=T["dim"]).pack(side='left')
        box = self.section(self.holder, _("Language and formats"))
        r = self.row(box, _("Language"))
        opts = [(t, l) for t, l, _x in langs]
        self.chosen_lang = lang if lang in [l for _t, l in opts] else opts[0][1]
        Choice(r, opts, self.chosen_lang, self.set_lang, self.app.font(10), 28).pack(anchor='w')
        r = self.row(box, _("Whole computer"))
        WolkButton(r, _("Use this language for sign-in and every user"), self.set_system_lang, f9,
                   'ghost').pack(side='left')
        label(r, _("Now: {zone}").format(zone=clock.system_language() or '?'), self.app.font(8, False),
              fg=T["dim"]).pack(side='left', padx=8)
        r = self.row(box, _("Clock"))
        Toggle(r, _("24-hour clock"), h24, self.set_24, f9).pack(anchor='w')
        label(box, _("Language and clock apply the next time you sign in."), self.app.font(8, False),
              fg=T["dim"]).pack(anchor='w', pady=(6, 0))

    def fill(self):
        text = self.filter.get().strip().lower().replace(' ', '_')
        self.lb.delete(0, 'end')
        for z in self.zones:
            if text in z.lower():
                self.lb.insert('end', z)
                if self.lb.size() >= 60:
                    break
        if self.lb.size():
            self.lb.selection_set(0)

    def set_zone(self):
        sel = self.lb.curselection()
        if not sel:
            return
        name = self.lb.get(sel[0])
        self.app.bg(lambda: clock.set_zone(name), lambda msg: (
            self.say(msg or _("Time zone: {zone}").format(zone=name), bool(msg)), self.refresh()))

    def set_time(self):
        import re
        m = re.fullmatch(r'\s*(\d{4})-(\d{1,2})-(\d{1,2})[ T](\d{1,2}):(\d{2})\s*', self.when.get())
        if not m:
            self.say(_("Write it as 2026-11-25 14:30."), True)
            return
        parts = [int(x) for x in m.groups()]
        self.app.bg(lambda: clock.set_time(*parts), lambda msg: self.say(msg or _("Time set."), bool(msg)))

    def set_system_lang(self):
        lang = self.chosen_lang

        def done(msg):
            self.say(msg or _("Done. The sign-in screen uses it after a restart."), bool(msg))
            self.refresh()
        self.app.bg(lambda: clock.set_system_language(lang), done)

    def set_ntp(self, on):
        self.app.bg(lambda: clock.set_ntp(on), lambda msg: self.say(msg or _("Done."), bool(msg)))

    def set_lang(self, lang):
        self.chosen_lang = lang
        row = next((l for l in clock.LANGUAGES if l[1] == lang), None)
        ok = bool(row) and clock.set_language(row[1], row[2])
        self.say(_("Language saved. It applies the next time you sign in.") if ok
                 else _("Could not save the language."), not ok)

    def set_24(self, on):
        ok = clock.set_clock_24h(on)
        self.say(_("Clock saved. It applies the next time you sign in.") if ok
                 else _("Could not save the clock."), not ok)


class PrintersPage(Page):
    key, title, tool = 'printers', "Printers", 'lpstat'
    index = [("Printers", "print canon cups"), ("Add a printer", "network find ipp driverless"),
             ("Print a test page", "test"), ("Default printer", "")]

    def build(self, f):
        if not core.have('lpstat'):
            self.missing(f, 'lpstat', _("show your printers"))
            self.holder = None
            return
        self.holder = tk.Frame(f, bg=T["bg"])
        self.holder.pack(fill='x')
        self.found = []

    def refresh(self):
        if self.holder is not None:
            self.app.bg(printers.printers, self.render)

    def render(self, plist):
        h = self.holder
        clear(h)
        f9 = self.app.font(9)
        box = self.section(h, _("Your printers"))
        if not plist:
            label(box, _("No printers added yet."), self.app.font(10), fg=T["muted"]).pack(anchor='w')
        for p in plist or []:
            r = tk.Frame(box, bg=T["panel"])
            r.pack(fill='x', pady=3)
            state = {'idle': _("ready"), 'disabled': _("off"), 'busy': _("busy")}.get(p.state, '')
            label(r, f"{p.name}   [{state}]" + ("   ★" if p.default else ''), self.app.font(10),
                  width=40).pack(side='left')
            WolkButton(r, _("Test page"), lambda p=p: self.test(p), f9, 'ghost').pack(side='left', padx=2)
            if not p.default:
                WolkButton(r, _("Make default"), lambda p=p: self.default(p), f9, 'ghost').pack(side='left', padx=2)
            WolkButton(r, _("Remove"), lambda p=p: self.remove(p), f9, 'danger').pack(side='left', padx=2)
        box = self.section(h, _("Add a printer"))
        WolkButton(box, _("Look on the network"), self.discover, f9, 'primary').pack(anchor='w')
        self.found_box = tk.Frame(box, bg=T["panel"])
        self.found_box.pack(fill='x', pady=(8, 0))

    def discover(self):
        self.say(_("Looking for printers..."))
        self.app.bg(printers.discover, self.show_found)

    def show_found(self, found):
        clear(self.found_box)
        self.say('')
        if not found:
            label(self.found_box, _("No new printers found."), self.app.font(10),
                  fg=T["muted"]).pack(anchor='w')
        for fnd in found or []:
            r = tk.Frame(self.found_box, bg=T["panel"])
            r.pack(fill='x', pady=2)
            label(r, fnd.name, self.app.font(10), width=40).pack(side='left')
            WolkButton(r, _("Add"), lambda fnd=fnd: self.add(fnd), self.app.font(9), 'primary').pack(side='left')

    def _done(self, ok_text):
        return lambda msg: (self.say(msg or ok_text, bool(msg)), self.refresh())

    def add(self, fnd):
        self.app.bg(lambda: printers.add(fnd), self._done(_("Printer added.")))

    def remove(self, p):
        self.app.bg(lambda: printers.remove(p.name), self._done(_("Printer removed.")))

    def default(self, p):
        self.app.bg(lambda: printers.make_default(p.name), lambda ok: (
            self.say(_("Default printer changed.") if ok else _("Could not change it."), not ok),
            self.refresh()))

    def test(self, p):
        self.app.bg(lambda: printers.test_page(p.name), lambda msg: self.say(
            msg or _("Test page sent to {name}.").format(name=p.name), bool(msg)))


class StartupPage(Page):
    key, title = 'startup', "Startup"
    index = [("Apps that open at sign-in", "autostart login boot launch"),
             ("Startup sound", "hammer sign in sound")]

    def build(self, f):
        self.holder = tk.Frame(f, bg=T["bg"])
        self.holder.pack(fill='x')

    def refresh(self):
        self.app.bg(startup.items, self.render)

    def render(self, items):
        clear(self.holder)
        box = self.section(self.holder, _("Open at sign-in"))
        if not items:
            label(box, _("Nothing opens at sign-in."), self.app.font(10), fg=T["muted"]).pack(anchor='w')
        for it in items or []:
            r = tk.Frame(box, bg=T["panel"])
            r.pack(fill='x', pady=2)
            Toggle(r, it.name, it.enabled, lambda v, it=it: self.toggle(it, v),
                   self.app.font(9)).pack(side='left')
            if it.comment:
                label(r, it.comment, self.app.font(8, False), fg=T["dim"]).pack(side='left', padx=10)
            if startup.is_mine(it):
                WolkButton(r, _("Remove"), lambda it=it: self.remove(it), self.app.font(9),
                           'danger').pack(side='right')
        box = self.section(self.holder, _("Add an app"))
        r = tk.Frame(box, bg=T["panel"])
        r.pack(fill='x')
        opts = [(a.name, a.id) for a in sorted(defaults.installed_apps().values(),
                                               key=lambda a: a.name.lower()) if not a.hidden]
        if opts:
            self.pick_app = Choice(r, opts, opts[0][1], lambda _v: None, self.app.font(10), 34)
            self.pick_app.pack(side='left')
            WolkButton(r, _("Open at sign-in"), self.add, self.app.font(9), 'primary').pack(side='left', padx=8)

    def add(self):
        ok = startup.add_app(self.pick_app.value)
        self.say(_("Added. It opens at your next sign-in.") if ok else _("Could not add it."), not ok)
        self.refresh()

    def remove(self, it):
        ok = startup.remove(it)
        self.say(_("Removed.") if ok else _("Could not remove it."), not ok)
        self.refresh()

    def toggle(self, it, on):
        ok = startup.set_enabled(it, on)
        self.say(_("Saved. It applies at the next sign-in.") if ok else _("Could not save it."), not ok)


class UpdatesPage(Page):
    key, title = 'updates', "Updates"
    index = [("Check for updates", "upgrade update system roll back")]

    def build(self, f):
        box = self.section(f, _("Updates"))
        label(box, _("SparkOS updates, app updates and going back to the last version are in Spark Update."),
              self.app.font(10), wraplength=640).pack(anchor='w', pady=(0, 10))
        WolkButton(box, _("Open Spark Update"), self.open, self.app.font(9), 'primary').pack(anchor='w')

    def open(self):
        if not core.spawn(['spark-update']):
            self.say(_("Spark Update isn't installed."), True)


class AboutPage(Page):
    key, title = 'about', "About"
    index = [("SparkOS version", "release image kernel"), ("Hardware", "cpu gpu memory ram graphics"),
             ("Copy system info", "bug report")]

    def build(self, f):
        self.holder = tk.Frame(f, bg=T["bg"])
        self.holder.pack(fill='x')
        self.rows = []

    def refresh(self):
        self.app.bg(sysinfo.rows, self.render)

    def render(self, rows):
        clear(self.holder)
        self.rows = rows or []
        box = self.section(self.holder, _("This computer"))
        for k, v in self.rows:
            r = self.row(box, _(k))
            label(r, v, self.app.font(10)).pack(anchor='w')
        label(box, f"{APP_NAME} {VERSION}", self.app.font(8, False), fg=T["dim"]).pack(anchor='w', pady=(8, 0))
        WolkButton(box, _("Copy system info"), self.copy, self.app.font(9), 'primary').pack(anchor='w', pady=(10, 0))

    def copy(self):
        text = sysinfo.report(self.rows, VERSION)
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(text)
        self.app.root.update()
        self.say(_("Copied. Paste it into your bug report."))
