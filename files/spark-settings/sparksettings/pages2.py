"""The other pages: Power, Default apps, Date time and language, Printers, Startup, Updates,
the pages that open KDE's modules, More settings, and About."""

from typing import List

import tkinter as tk

from . import APP_NAME, VERSION, clock, core, defaults, kcms, power, printers, startup, sysinfo
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
             ("Screen off and sleep", "timer suspend idle lock screen"),
             ("Power button", "shutdown sleep hibernate action")]

    def build(self, f):
        self.holder = tk.Frame(f, bg=T["bg"])
        self.holder.pack(fill='x')

    def refresh(self):
        self.app.bg(lambda: (power.profiles(), power.current()), self.render)

    def render(self, data):
        h = self.holder
        clear(h)
        profiles, now = data or ([], None)
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
        box = self.section(h, _("Screen off, sleep and the power button"))
        label(box, _("These timers still open in KDE's own module for now."), self.app.font(10),
              fg=T["muted"]).pack(anchor='w', pady=(0, 8))
        WolkButton(box, _("Open the timers (KDE)"),
                   lambda: kcms.open_module('kcm_powerdevilprofilesconfig'), self.app.font(9),
                   'ghost').pack(anchor='w')

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
        cmd = app_id.replace('.desktop', '').split('.')[-1].lower()
        cmd = {'sparkterminal': 'spark-terminal'}.get(cmd, cmd)
        ok = defaults.terminal_set(app_id, cmd)
        self.say(_("Changed: {what}.").format(what=_("Terminal")) if ok else _("Could not change it."), not ok)


class DateTimePage(Page):
    key, title, tool = 'datetime', "Date, time and language", 'timedatectl'
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
            label(box, _("timedatectl isn't installed, so the time zone can't be changed here."),
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
        box = self.section(self.holder, _("Language and formats"))
        r = self.row(box, _("Language"))
        opts = [(t, l) for t, l, _x in langs]
        Choice(r, opts, lang if lang in [l for _t, l in opts] else opts[0][1], self.set_lang,
               self.app.font(10), 28).pack(anchor='w')
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

    def set_ntp(self, on):
        self.app.bg(lambda: clock.set_ntp(on), lambda msg: self.say(msg or _("Done."), bool(msg)))

    def set_lang(self, lang):
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


class KdePage(Page):
    """A page whose settings still live in KDE's modules."""
    modules: List[str] = []

    def build(self, f):
        self.holder = tk.Frame(f, bg=T["bg"])
        self.holder.pack(fill='x')

    def refresh(self):
        self.app.bg(kcms.all_modules, self.render)

    def render(self, mods):
        clear(self.holder)
        box = self.section(self.holder, '')
        label(box, _("These settings open in KDE's own module for now. Each one opens in its own window."),
              self.app.font(10), fg=T["muted"], wraplength=640).pack(anchor='w', pady=(0, 6))
        known = {k.id: k.name for k in (mods or [])}
        shown = [m for m in self.modules if m in known] or []
        if not shown:
            label(box, _("KDE's settings modules aren't installed here."), self.app.font(10),
                  fg=T["gold"]).pack(anchor='w')
        for m in shown:
            r = tk.Frame(box, bg=T["panel"])
            r.pack(fill='x', pady=3)
            label(r, known[m], self.app.font(10), width=36).pack(side='left')
            WolkButton(r, _("Open"), lambda m=m: kcms.open_module(m), self.app.font(9), 'ghost').pack(side='left')


class MorePage(Page):
    key, title = 'more', "More settings"
    index = [("Every KDE settings module", "kcm kde plasma advanced")]

    def build(self, f):
        box = self.section(f, '')
        label(box, _("Everything Spark Settings doesn't cover yet, from KDE. Each opens in its own window."),
              self.app.font(10), fg=T["muted"], wraplength=640).pack(anchor='w')
        self.listbox = tk.Frame(f, bg=T["bg"])
        self.listbox.pack(fill='both', expand=True, padx=24)
        self.mods = []

    def refresh(self):
        self.app.bg(kcms.more_settings, self.render)

    def render(self, mods):
        clear(self.listbox)
        mods = mods or []
        if not mods:
            label(self.listbox, _("KDE's settings modules aren't installed here."),
                  self.app.font(10), fg=T["gold"], bg=T["bg"]).pack(anchor='w')
        cols = 2
        for i, k in enumerate(mods):
            b = tk.Label(self.listbox, text=k.name, font=self.app.font(9), anchor='w', bg=T["panel"],
                         fg=T["text"], padx=10, pady=5, cursor='hand2', takefocus=1)
            b.grid(row=i // cols, column=i % cols, sticky='ew', padx=2, pady=2)
            b.bind('<Enter>', lambda _e, b=b: b.config(bg=T["hover"], fg=T["accent"]))
            b.bind('<Leave>', lambda _e, b=b: b.config(bg=T["panel"], fg=T["text"]))
            b.bind('<ButtonRelease-1>', lambda _e, k=k: kcms.open_module(k.id))
            b.bind('<Return>', lambda _e, k=k: kcms.open_module(k.id))
        for c in range(cols):
            self.listbox.columnconfigure(c, weight=1, uniform='c')


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
