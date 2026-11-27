"""Appearance, Mouse and keyboard, Shortcuts, Users, Storage and Notifications. Each talks to the
system through its own module (appearance.py, inputdev.py, shortcuts.py, accounts.py, storage.py,
notifications.py)."""

import os
from . import pickdialog as filedialog
from typing import List

import tkinter as tk

from . import accounts, appearance, core, inputdev, notifications, shortcuts, storage, taskbar
from .app import Page
from .i18n import _
from .lang import local_units
from .ui import Choice, Dialog, Slider, entry, label
from .widgets import T, Toggle, WolkButton


def clear(frame):
    for w in frame.winfo_children():
        w.destroy()


def size_text(n: int) -> str:
    for unit, step in (('TB', 1 << 40), ('GB', 1 << 30), ('MB', 1 << 20)):
        if n >= step:
            return local_units(f"{n / step:.1f} {unit}")
    return local_units(f"{n >> 10} KB")


class Holder(Page):
    """A page that is one frame redrawn from data."""

    def build(self, f):
        self.holder = tk.Frame(f, bg=T["bg"])
        self.holder.pack(fill='x')

    def link_row(self, box, text: str, button: str, command, tool: str = ''):
        r = tk.Frame(box, bg=T["panel"])
        r.pack(fill='x', pady=3)
        label(r, text, self.app.font(10), width=40).pack(side='left')
        if tool and not core.have(tool):
            label(r, _("Not installed."), self.app.font(9, False), fg=T["dim"]).pack(side='left')
        else:
            WolkButton(r, button, command, self.app.font(9), 'ghost').pack(side='left')

    def open_app(self, cmd: str, name: str):
        if not core.spawn([cmd]):
            self.say(_("{app} isn't installed.").format(app=name), True)


# ──────────────────────────── Appearance ────────────────────────────
class AppearancePage(Holder):
    key, title = 'appearance', "Appearance"
    index = [("Wallpaper", "background picture desktop"),
             ("Cursor", "mouse pointer size theme"),
             ("Window animations", "effects windows motion reduced"),
             ("Fonts", "text font size install"),
             ("Spark Connect status in the tray", "taskbar panel widget servers monitor"),
             ("Workspaces", "taskbar virtual desktops count number")]

    def refresh(self):
        self.app.bg(lambda: (appearance.wallpapers(),
                             appearance.cursor_themes(), appearance.get()), self.render)

    def render(self, data):
        if not data:
            return
        papers, cursors, now = data
        self.now = now
        clear(self.holder)
        h, f10, f9 = self.holder, self.app.font(10), self.app.font(9)
        box = self.section(h, _("Wallpaper"))
        r = self.row(box, _("Picture"))
        opts = [(n, p) for n, p in papers]
        cur = now['wallpaper']
        if cur and cur not in [p for _n, p in opts]:
            opts.insert(0, (os.path.basename(cur), cur))
        if opts:
            Choice(r, opts, cur or opts[0][1], self.pick_wallpaper, f10, 28).pack(side='left')
        WolkButton(r, _("Choose a picture"), self.browse, f9, 'ghost').pack(side='left', padx=8)
        box = self.section(h, _("Cursor"))
        if cursors:
            r = self.row(box, _("Cursor theme"))
            Choice(r, [(c, c) for c in cursors], now['cursor'] if now['cursor'] in cursors
                   else cursors[0], self.pick_cursor, f10, 28).pack(anchor='w')
        r = self.row(box, _("Cursor size"))
        sizes = sorted(set(appearance.CURSOR_SIZES) | {now['cursor_size']})
        Choice(r, [(str(s), str(s)) for s in sizes], str(now['cursor_size']), self.pick_size,
               f10, 8).pack(anchor='w')
        box = self.section(h, _("Windows"))
        Toggle(box, _("Window animations"), bool(now['animations']),
               self.animations, f9).pack(anchor='w', pady=2)
        label(box, _("Spark apps skip their animations when this is off."), self.app.font(8, False),
              fg=T["dim"]).pack(anchor='w', pady=(6, 0))
        self.taskbar_box(h, f10, f9)
        box = self.section(h, _("Fonts"))
        self.link_row(box, _("Manage fonts (see, install, remove)"), _("Open Spark Fonts"),
                      lambda: self.open_app('spark-fonts', "Spark Fonts"), 'spark-fonts')

    def taskbar_box(self, h, f10, f9):
        box = self.section(h, _("Taskbar"))
        have = taskbar.connect_installed()
        cw = taskbar.connect_get()
        t = Toggle(box, _("Spark Connect status in the tray"), bool(cw['enabled']) and have,
                   lambda on: self.connect_toggle(on), f9)
        t.pack(anchor='w', pady=2)
        if not have:
            t.unbind("<ButtonRelease-1>")
            t.unbind("<Return>")
            t.unbind("<space>")
            t.config(fg=T["dim"], cursor="arrow")
            label(box, _("Spark Connect is not installed."), self.app.font(8, False),
                  fg=T["dim"]).pack(anchor='w', pady=(4, 0))
        else:
            r = self.row(box, _("Show it on"))
            names = [(_("Main screen"), '')] + [(lbl, c) for c, lbl in taskbar.screens()]
            if cw['monitor'] and cw['monitor'] not in [c for _l, c in names]:
                names.append((cw['monitor'], cw['monitor']))
            Choice(r, names, cw['monitor'], self.connect_screen, f10, 18).pack(anchor='w')
        r = self.row(box, _("Workspaces"))
        n = taskbar.workspaces_get()
        Choice(r, [(str(i), str(i)) for i in range(taskbar.MIN_WORKSPACES,
                                                   taskbar.MAX_WORKSPACES + 1)],
               str(n), self.workspaces, f10, 4).pack(anchor='w')
        label(box, _("The switcher shows in the taskbar when there is more than one. "
                     "Super+Ctrl+Left and Right change workspace."),
              self.app.font(8, False), fg=T["dim"]).pack(anchor='w', pady=(6, 0))

    def connect_toggle(self, on):
        self.app.bg(lambda: taskbar.connect_set(enabled=on),
                    lambda ok: self.done(ok, _("Saved.")))

    def connect_screen(self, monitor):
        self.app.bg(lambda: taskbar.connect_set(monitor=monitor),
                    lambda ok: self.done(ok, _("Saved.")))

    def workspaces(self, count):
        self.app.bg(lambda: taskbar.workspaces_set(count),
                    lambda ok: self.done(ok, _("Saved.")))

    def done(self, ok, text):
        self.say(text if ok else _("Could not change it."), not ok)

    def pick_wallpaper(self, path):
        self.app.bg(lambda: appearance.set_wallpaper(path),
                    lambda ok: self.done(ok, _("Wallpaper changed.")))

    def browse(self):
        path = filedialog.askopenfilename(
            title=_("Choose a picture"),
            filetypes=[(_("Pictures"), '*.png *.jpg *.jpeg *.webp *.svg')])
        if path:
            self.pick_wallpaper(path)
            self.refresh()

    def pick_cursor(self, theme):
        self.now['cursor'] = theme
        self.app.bg(lambda: appearance.set_cursor(theme, int(self.now['cursor_size'])),
                    lambda ok: self.done(ok, _("Cursor changed. Apps already open keep theirs until they restart.")))

    def pick_size(self, size):
        self.now['cursor_size'] = int(size)
        self.app.bg(lambda: appearance.set_cursor(self.now['cursor'], int(size)),
                    lambda ok: self.done(ok, _("Cursor changed. Apps already open keep theirs until they restart.")))

    def animations(self, on):
        self.app.bg(lambda: appearance.set_animations(on), lambda ok: self.done(ok, _("Done.")))


# ──────────────────────────── Mouse and keyboard ────────────────────────────
class InputPage(Holder):
    key, title = 'input', "Mouse and keyboard"
    index = [("Pointer speed", "mouse acceleration sensitivity touchpad"),
             ("Scroll direction", "natural scrolling touchpad reverse"),
             ("Tap to click", "touchpad"), ("Left-handed", "mouse buttons swap"),
             ("Keyboard layout", "us international dead keys french canada language"),
             ("Key repeat", "delay rate speed"),
             ("Game controllers", "gamepad joystick dpi gaming mouse")]

    def refresh(self):
        self.app.bg(lambda: (inputdev.devices(), inputdev.keyboard_get(),
                             inputdev.layouts_available()), self.render)

    def render(self, data):
        if not data:
            return
        devs, kb, layouts = data
        self.kb, self.layouts = kb, layouts
        clear(self.holder)
        h, f10, f9 = self.holder, self.app.font(10), self.app.font(9)
        for dev in devs:
            # one entry per kind; the settings apply to every device listed
            box = self.section(h, _("Touchpads") if dev.touchpad else _("Mice"))
            label(box, dev.name, self.app.font(8, False), fg=T["dim"]).pack(anchor='w', pady=(0, 4))
            for prop, _key, kind in dev.settings():
                if prop == 'pointerAcceleration':
                    r = self.row(box, _("Pointer speed"))
                    s = Slider(r, lambda v, d=dev: self.set(d, 'pointerAcceleration', 'd', v),
                               -1, 1, 220)
                    s.pack(anchor='w')
                    s.put(float(dev.props.get(prop, 0) or 0))
                else:
                    names = {'pointerAccelerationProfileFlat': _("No pointer acceleration"),
                             'naturalScroll': _("Natural scrolling"), 'leftHanded': _("Left-handed"),
                             'tapToClick': _("Tap to click"),
                             'disableWhileTyping': _("Pause while typing")}
                    Toggle(box, names[prop], bool(dev.props.get(prop)),
                           lambda v, d=dev, p=prop: self.set(d, p, 'b', v), f9).pack(anchor='w', pady=2)
        if not devs:
            box = self.section(h, _("Mouse"))
            label(box, _("No mouse or touchpad found."), f10, fg=T["muted"]).pack(anchor='w')
        box = self.section(h, _("Keyboard layouts"))
        opts = [(f"{n} ({c})", c) for n, c in layouts] or [(c, c) for c in kb['layouts']]
        for i, code in enumerate(kb['layouts']):
            r = tk.Frame(box, bg=T["panel"])
            r.pack(fill='x', pady=2)
            Choice(r, opts, code, lambda v, i=i: self.layout(i, v), f10, 34).pack(side='left')
            if len(kb['layouts']) > 1:
                WolkButton(r, _("Remove"), lambda i=i: self.layout(i, None), f9, 'danger').pack(side='left', padx=6)
        if len(kb['layouts']) < 4:
            WolkButton(box, _("Add a layout"), lambda: self.layout(len(kb['layouts']), 'us'), f9,
                       'ghost').pack(anchor='w', pady=(6, 0))
        label(box, _("The first layout is the one in use; switch with Alt+Shift."),
              self.app.font(8, False), fg=T["dim"]).pack(anchor='w', pady=(6, 0))
        box = self.section(h, _("Key repeat"))
        r = self.row(box, _("Delay before repeating"))
        Choice(r, [(local_units(f"{d} ms").replace(' ms', ' ms'), str(d)) for d in
                   sorted(set(inputdev.REPEAT_DELAYS) | {kb['delay']})], str(kb['delay']),
               lambda v: self.repeat(int(v), None), f10, 12).pack(anchor='w')
        r = self.row(box, _("Repeats a second"))
        Choice(r, [(str(d), str(d)) for d in sorted(set(inputdev.REPEAT_RATES) | {kb['rate']})],
               str(kb['rate']), lambda v: self.repeat(None, int(v)), f10, 12).pack(anchor='w')
        box = self.section(h, _("More"))
        self.link_row(box, _("Game controllers and gaming mouse DPI"), _("Open Spark Controller"),
                      lambda: self.open_app('spark-controller', "Spark Controller"), 'spark-controller')
        label(box, _("Not set here: button mapping, calibration, drawing tablets and touchscreens."),
              self.app.font(8, False), fg=T["dim"]).pack(anchor='w', pady=(6, 0))

    def set(self, dev, prop, kind, value):
        def work():
            ok = inputdev.set_property(dev, prop, kind, value)
            return ok and inputdev.save(dev)
        self.app.bg(work, lambda ok: self.say(_("Saved.") if ok else _("Could not change it."), not ok))

    def layout(self, index, code):
        layouts = list(self.kb['layouts'])
        variants = list(self.kb['variants'])
        if code is None:
            del layouts[index]
            del variants[index:index + 1]
        elif index >= len(layouts):
            layouts.append(code)
            variants.append('')
        else:
            layouts[index] = code
            variants[index:index + 1] = ['']
        self.kb['layouts'], self.kb['variants'] = layouts, variants
        self.app.bg(lambda: inputdev.keyboard_set(layouts, variants, self.kb['delay'], self.kb['rate']),
                    lambda ok: (self.say(_("Saved.") if ok else _("Could not change it."), not ok),
                                self.refresh()))

    def repeat(self, delay, rate):
        self.kb['delay'] = delay or self.kb['delay']
        self.kb['rate'] = rate or self.kb['rate']
        self.app.bg(lambda: inputdev.keyboard_set(self.kb['layouts'], self.kb['variants'],
                                                  self.kb['delay'], self.kb['rate']),
                    lambda ok: self.say(_("Saved.") if ok else _("Could not change it."), not ok))


# ──────────────────────────── Shortcuts ────────────────────────────
class KeyCapture(tk.Toplevel):
    """A small window that waits for the key combination to use."""

    def __init__(self, app, name: str, on_key):
        super().__init__(app.root, bg=T["line2"], padx=1, pady=1)
        self.title(_("New shortcut"))
        self.transient(app.root)
        self.on_key = on_key
        body = tk.Frame(self, bg=T["panel"], padx=22, pady=18)
        body.pack()
        label(body, _("Press the keys for {name}").format(name=name), app.font(10),
              wraplength=360).pack(anchor='w')
        self.shown = label(body, _("Waiting for a key..."), app.font(12), fg=T["accent"])
        self.shown.pack(anchor='w', pady=10)
        label(body, _("Esc cancels."), app.font(8, False), fg=T["dim"]).pack(anchor='w')
        self.bind('<KeyPress>', self.press)
        self.update_idletasks()
        self.geometry(f"+{app.root.winfo_rootx() + 160}+{app.root.winfo_rooty() + 160}")
        self.focus_force()
        self.grab_set()

    def press(self, e):
        if e.keysym == 'Escape':
            self.destroy()
            return
        code = shortcuts.key_code(e.keysym, e.state)
        if code is None:
            return
        self.destroy()
        self.on_key(code)


class ShortcutsPage(Holder):
    key, title = 'shortcuts', "Shortcuts"
    index = [("Keyboard shortcuts", "keys hotkeys windows desktops"),
             ("Change a shortcut", "rebind key combination"),
             ("Reset a shortcut", "default")]

    def build(self, f):
        top = self.section(f, '')
        r = tk.Frame(top, bg=T["panel"])
        r.pack(fill='x')
        self.comp = Choice(r, [], '', self.pick_component, self.app.font(10), 30)
        self.comp.pack(side='left')
        self.filter = entry(r, self.app.font(10), 24)
        self.filter.pack(side='left', padx=10, ipady=3)
        self.filter.bind('<KeyRelease>', lambda _e: self.fill())
        label(r, _("Filter"), self.app.font(8, False), fg=T["dim"]).pack(side='left')
        self.lb = tk.Listbox(top, height=14, bg=T["out_bg"], fg=T["text"], font=self.app.font(10),
                             selectbackground=T["accent"], selectforeground=T["on_accent"],
                             highlightthickness=1, highlightbackground=T["line"], bd=0,
                             activestyle='none', exportselection=False)
        self.lb.pack(fill='x', pady=8)
        self.lb.bind('<Double-Button-1>', lambda _e: self.change())
        b = tk.Frame(top, bg=T["panel"])
        b.pack(anchor='w')
        for text, cmd, style in ((_("Change"), self.change, 'primary'), (_("Reset"), self.reset, 'ghost'),
                                 (_("Clear"), self.clear_key, 'ghost')):
            WolkButton(b, text, cmd, self.app.font(9), style).pack(side='left', padx=(0, 6))
        self.components: List[dict] = []
        self.actions: List[shortcuts.Action] = []
        self.shown: List[shortcuts.Action] = []
        self.path = ''
        self.holder = None

    def refresh(self):
        self.app.bg(shortcuts.components, self.got_components)

    def got_components(self, comps):
        self.components = comps or []
        if not self.components:
            return
        self.comp.set_options([(c['name'], c['path']) for c in self.components],
                              self.path or self.components[0]['path'])
        self.pick_component(self.comp.value)

    def pick_component(self, path):
        self.path = path
        self.app.bg(lambda: shortcuts.actions(path), self.got_actions)

    def got_actions(self, acts):
        self.actions = acts or []
        self.fill()

    def fill(self):
        text = self.filter.get().strip().lower()
        self.shown = [a for a in self.actions if text in a.name.lower() or text in a.text.lower()]
        self.lb.delete(0, 'end')
        for a in self.shown:
            self.lb.insert('end', f"{a.name}    {a.text or '-'}")

    def selected(self):
        sel = self.lb.curselection()
        return self.shown[sel[0]] if sel else None

    def change(self):
        a = self.selected()
        if a is None:
            self.say(_("Pick a shortcut in the list first."), True)
            return
        KeyCapture(self.app, a.name, lambda code, a=a: self.apply(a, code))

    def apply(self, a, code):
        clash = shortcuts.conflict(self.actions, a, code)
        if clash is not None:
            self.say(_("{key} is already used by {name}.").format(
                key=shortcuts.key_text(code), name=clash.name), True)
            return
        self.set_key(a, code)

    def set_key(self, a, code):
        def done(msg):
            self.say(msg or _("Saved."), bool(msg))
            self.fill()
        self.app.bg(lambda: shortcuts.set_key(a, code), done)

    def reset(self):
        a = self.selected()
        if a is None:
            return
        def done(msg):
            self.say(msg or _("Saved."), bool(msg))
            self.fill()
        self.app.bg(lambda: shortcuts.reset(a), done)

    def clear_key(self):
        a = self.selected()
        if a is not None:
            self.set_key(a, 0)


# ──────────────────────────── Users ────────────────────────────
class UsersPage(Holder):
    key, title = 'users', "Users"
    index = [("Your name", "account real name avatar"), ("Password", "login change"),
             ("Add a user", "account new"), ("Administrator", "admin sudo standard")]

    def refresh(self):
        self.app.bg(accounts.users, self.render)

    def render(self, users):
        clear(self.holder)
        h, f10, f9 = self.holder, self.app.font(10), self.app.font(9)
        box = self.section(h, _("Accounts"))
        if not users:
            label(box, _("AccountsService doesn't answer, so users can't be listed here."), f10,
                  fg=T["gold"], wraplength=640).pack(anchor='w')
        for u in users or []:
            r = tk.Frame(box, bg=T["panel"])
            r.pack(fill='x', pady=3)
            role = _("administrator") if u.admin else _("standard")
            label(r, f"{u.real_name}  ({u.name})  [{role}]" + ("  " + _("you") if u.me else ''),
                  f10, width=50).pack(side='left')
            WolkButton(r, _("Rename"), lambda u=u: self.rename(u), f9, 'ghost').pack(side='left', padx=2)
            if not u.me:
                WolkButton(r, _("Make standard") if u.admin else _("Make administrator"),
                           lambda u=u: self.role(u), f9, 'ghost').pack(side='left', padx=2)
                WolkButton(r, _("Remove"), lambda u=u: self.remove(u), f9, 'danger').pack(side='left', padx=2)
            else:
                WolkButton(r, _("Change password"), self.password, f9, 'ghost').pack(side='left', padx=2)
        box = self.section(h, _("Add a user"))
        r = self.row(box, _("User name"))
        self.new_name = entry(r, f10, 22)
        self.new_name.pack(anchor='w', ipady=3)
        r = self.row(box, _("Full name"))
        self.new_real = entry(r, f10, 28)
        self.new_real.pack(anchor='w', ipady=3)
        self.new_admin = False
        Toggle(box, _("Administrator"), False, lambda v: setattr(self, 'new_admin', v), f9).pack(anchor='w', pady=4)
        WolkButton(box, _("Add"), self.add, f9, 'primary').pack(anchor='w', pady=(4, 0))
        label(box, _("The new user has no password yet: set one from their own sign-in or with passwd."),
              self.app.font(8, False), fg=T["dim"], wraplength=640).pack(anchor='w', pady=(6, 0))

    def result(self, msg, ok_text):
        self.say(msg or ok_text, bool(msg))
        self.refresh()

    def rename(self, u):
        Dialog(self.app, _("Rename"), _("Full name for {name}").format(name=u.name), _("Save"),
               _("Cancel"), field=u.real_name,
               on_ok=lambda v: self.app.bg(lambda: accounts.set_real_name(u, v.strip()),
                                           lambda m: self.result(m, _("Saved."))) if v.strip() else None)

    def role(self, u):
        self.app.bg(lambda: accounts.set_admin(u, not u.admin), lambda m: self.result(m, _("Saved.")))

    def remove(self, u):
        Dialog(self.app, _("Remove a user"),
               _("Remove {name}? Their files stay in /home.").format(name=u.name), _("Remove"),
               _("Cancel"), on_ok=lambda _v: self.app.bg(
                   lambda: accounts.remove(u, False), lambda m: self.result(m, _("User removed."))))

    def add(self):
        name, real = self.new_name.get().strip(), self.new_real.get().strip()
        if not accounts.valid_name(name):
            self.say(_("Use lower-case letters, digits, - and _, starting with a letter."), True)
            return
        admin = self.new_admin
        self.app.bg(lambda: accounts.create(name, real or name, admin),
                    lambda m: self.result(m, _("User added.")))

    def password(self):
        if not accounts.change_password():
            self.say(_("Spark Terminal isn't installed, so run passwd in a terminal."), True)


# ──────────────────────────── Storage ────────────────────────────
class StoragePage(Holder):
    key, title = 'storage', "Storage"
    index = [("Drives", "disk usb mounted free space games drive steam library"),
             ("Format or check a drive", "disks usb")]

    def refresh(self):
        self.app.bg(storage.volumes, self.render)

    def render(self, data):
        if data is None:
            return
        vols = data
        clear(self.holder)
        h, f10, f9 = self.holder, self.app.font(10), self.app.font(9)
        box = self.section(h, _("Drives"))
        if not vols:
            label(box, _("No mounted drives found."), f10, fg=T["muted"]).pack(anchor='w')
        for v in vols:
            r = tk.Frame(box, bg=T["panel"])
            r.pack(fill='x', pady=3)
            label(r, f"{v.title}   {v.mount}", f10, width=46).pack(side='left')
            label(r, _("{free} free of {size}").format(free=size_text(v.free), size=size_text(v.size)),
                  self.app.font(9, False), fg=T["muted"], width=26).pack(side='left')
            WolkButton(r, _("Open"), lambda v=v: storage.open_folder(v.mount), f9, 'ghost').pack(side='left')
        self.link_row(box, _("Mount, format, check or image a drive"), _("Open Spark Disks"),
                      lambda: self.open_app('spark-disks', "Spark Disks"), 'spark-disks')


# ──────────────────────────── Notifications ────────────────────────────
class NotificationsPage(Holder):
    key, title = 'notifications', "Notifications"
    index = [("Pop-up time", "seconds how long toast"), ("Pop-up position", "corner where")]

    def refresh(self):
        self.app.bg(notifications.get, self.render)

    def render(self, now):
        if not now:
            return
        clear(self.holder)
        f10, f9 = self.app.font(10), self.app.font(9)
        box = self.section(self.holder, _("Pop-ups"))
        r = self.row(box, _("Stay on screen for"))
        secs = sorted(set(notifications.SECONDS) | {now['seconds']})
        Choice(r, [(local_units(f"{s} s").replace(' s', ' s'), str(s)) for s in secs],
               str(now['seconds']), lambda v: self.save(seconds=int(v)), f10, 8).pack(anchor='w')
        r = self.row(box, _("Appear in the"))
        Choice(r, [(_(n), c) for n, c in notifications.POSITIONS], now['position'],
               lambda v: self.save(position=v), f10, 16).pack(anchor='w')

    def save(self, **kw):
        self.app.bg(lambda: notifications.save(**kw),
                    lambda ok: self.say(_("Saved.") if ok else _("Could not change it."), not ok))
