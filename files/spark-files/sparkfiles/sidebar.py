"""The sidebar: your folders, the drives (Windows drives, USB sticks), pinned folders and the
Trash. Drop files on a place to move or copy them there, on the Trash to trash them, and a
folder on the empty part to pin it. Right-click a place for more."""

import os
from typing import Dict, List, Optional

import tkinter as tk

from . import trash as trash_mod
from .core import human_size
from .places import (TRASH, Place, free_space, home_places, network_places, pinned_places,
                     removable_drives, windows_drives)
from .text import t
from .ui import Progress, menu
from .widgets import T


class Sidebar(tk.Frame):
    def __init__(self, parent: tk.Misc, window):
        super().__init__(parent, bg=T["panel"])
        self.window = window
        self.app = window.app
        self.rows: Dict[str, tuple] = {}            # key -> (frame, label, icon, place)
        self.places: List[Place] = []
        self.current = ''
        self.drop_key: Optional[str] = None
        self.drop_pin = False
        self.inner = tk.Frame(self, bg=T["panel"])
        self.inner.pack(fill='both', expand=True)
        self.pin_hint = tk.Label(self, text='', font=self.app.font(8, False), bg=T["panel"],
                                 fg=T["dim"], anchor='w', padx=self.app.px(12), wraplength=1)
        self.pin_hint.pack(fill='x', side='bottom', pady=(0, self.app.px(6)))
        self.bind('<ButtonPress-3>', lambda e: None)
        self.refresh()

    def refresh(self) -> None:
        for w in self.inner.winfo_children():
            w.destroy()
        self.rows.clear()
        px = self.app.px
        a = self.app
        groups = [
            (t('side.places'), home_places(t)),
            (t('side.drives'), windows_drives(t) + removable_drives(t) +
             a.unmounted_volumes()),
            (t('side.network'), network_places(t, a.settings['servers'], a.gdrive_state)),
            (t('side.pinned'), pinned_places(a.settings['pinned'])),
            ('', [Place('trash', t('place.trash'), TRASH,
                        'trash')]),
        ]
        self.places = []
        for title, places in groups:
            if not places and title != t('side.pinned'):
                continue
            if title:
                tk.Label(self.inner, text=title.upper(), font=a.font(8, True), bg=T["panel"],
                         fg=T["dim"], anchor='w', padx=px(12)).pack(fill='x',
                                                                    pady=(px(10), px(2)))
            if not places:
                tk.Label(self.inner, text=t('side.pin_hint'), font=a.font(8, False),
                         bg=T["panel"], fg=T["dim"], anchor='w', padx=px(14), justify='left',
                         wraplength=px(170)).pack(fill='x')
            for place in places:
                self._row(place)
        self.highlight(self.current)

    def _row(self, place: Place) -> None:
        a, px = self.app, self.app.px
        self.places.append(place)
        row = tk.Frame(self.inner, bg=T["panel"], cursor='hand2')
        row.pack(fill='x')
        bar = tk.Frame(row, bg=T["panel"], width=px(3))
        bar.pack(side='left', fill='y')
        kind = place.icon
        if place.key == 'trash':
            kind = 'trash'
        image = a.icons.get(kind if kind in ('home', 'desktop', 'download', 'drive', 'usb',
                                             'trash', 'game', 'pin', 'network') else
                            {'document': 'document', 'image': 'image', 'audio': 'audio',
                             'video': 'video'}.get(kind, 'folder'), px(16))
        icon = tk.Label(row, image=image, bg=T["panel"], padx=px(6))
        icon.pack(side='left')
        text = place.label
        lab = tk.Label(row, text=text, font=a.font(10, False), bg=T["panel"],
                       fg=T["dim"] if place.unmounted else T["text"], anchor='w',
                       pady=px(4))
        lab.pack(side='left', fill='x', expand=True)
        widgets = [row, icon, lab]
        if place.key == 'trash':
            n = trash_mod.count()
            if n:
                badge = tk.Label(row, text=str(n), font=a.font(8, True), bg=T["panel"],
                                 fg=T["muted"], padx=px(8))
                badge.pack(side='right')
                widgets.append(badge)
        if place.removable and not place.unmounted:
            eject = tk.Label(row, text='⏏', font=a.font(10, False), bg=T["panel"],
                             fg=T["muted"], padx=px(8), cursor='hand2')
            eject.pack(side='right')
            eject.bind('<ButtonRelease-1>', lambda _e, p=place: self.eject(p))
            a.tooltip.attach(eject, t('side.eject'))
            widgets.append(eject)
        usage = None
        if place.icon in ('drive', 'usb') and not place.unmounted:
            fs = free_space(place.path)
            if fs and fs[1]:
                usage = Progress(self.inner, height=max(3, px(3)), bg=T["panel"])
                used = 1 - fs[0] / fs[1]
                usage.set(used, T["pink"] if used > 0.92 else T["line2"])
                usage.pack(fill='x', padx=(px(36), px(12)), pady=(0, px(3)))
                a.tooltip.attach(row, t('side.free', free=human_size(fs[0]),
                                        total=human_size(fs[1])))
        for w in widgets:
            w.bind('<ButtonRelease-1>', lambda _e, p=place: self.open(p), add='+')
            w.bind('<ButtonRelease-2>', lambda _e, p=place: self.open(p, tab=True))
            w.bind('<ButtonPress-3>', lambda e, p=place: self.place_menu(e, p))
            w.bind('<Enter>', lambda _e, k=place.key: self._hover(k, True), add='+')
            w.bind('<Leave>', lambda _e, k=place.key: self._hover(k, False), add='+')
        self.rows[place.key] = (row, lab, icon, place, bar, widgets)

    def _paint(self, key: str, hover: bool = False) -> None:
        row = self.rows.get(key)
        if not row:
            return
        frame, lab, icon, place, bar, widgets = row
        on = key == self.current
        drop = key == self.drop_key
        bg = T["hover"] if (on or hover or drop) else T["panel"]
        for w in widgets:
            w.configure(bg=bg)
        lab.configure(fg=T["accent"] if on else (T["dim"] if place.unmounted else T["text"]))
        bar.configure(bg=T["ch_b"] if drop else (T["accent"] if on else bg))

    def _hover(self, key: str, on: bool) -> None:
        self._paint(key, on)

    def highlight(self, path: str) -> None:
        self.current = ''
        best = 0
        for place in self.places:
            if place.unmounted:
                continue
            if path == place.path:
                self.current = place.key
                break
            if place.key.startswith(('drive-', 'mount-')) and path.startswith(
                    place.path.rstrip('/') + '/') and len(place.path) > best:
                best = len(place.path)
                self.current = place.key
        for key in self.rows:
            self._paint(key)

    def open(self, place: Place, tab: bool = False) -> None:
        if place.key.startswith('net-'):
            self.app.network_open(self.window, place)
            return
        if place.unmounted:
            self.app.mount_volume(place, lambda path: self.window.active.go(path))
            return
        if tab:
            self.window.new_tab(place.path, select=False)
        else:
            self.window.active.go(place.path)

    def place_menu(self, event, place: Place) -> None:
        m = menu(self, self.app.font(10, False))
        if place.key.startswith('net-'):
            if place.key.startswith('net-server-'):
                m.add_command(label=t('net.forget_password'),
                              command=lambda: self.app.network_forget_password(self.window,
                                                                               place))
                m.add_command(label=t('net.forget'),
                              command=lambda: self.app.network_remove(place))
                m.tk_popup(event.x_root, event.y_root)
            return
        if not place.unmounted:
            m.add_command(label=t('menu.open_tab'), command=lambda: self.open(place, tab=True))
            m.add_command(label=t('menu.open_window'),
                          command=lambda: self.app.new_window(place.path))
        if place.key.startswith('pin-'):
            m.add_separator()
            m.add_command(label=t('side.unpin'), command=lambda: self.app.unpin(place.path))
        elif place.path not in (TRASH,) and not place.unmounted:
            m.add_separator()
            m.add_command(label=t('side.pin'), command=lambda: self.app.pin(place.path))
        if place.key == 'trash':
            m.add_separator()
            m.add_command(label=t('trash.empty'), command=self.app.empty_trash,
                          state='normal' if trash_mod.count() else 'disabled')
        if place.removable and not place.unmounted:
            m.add_separator()
            m.add_command(label=t('side.eject'), command=lambda: self.eject(place))
        if place.path != TRASH and not place.unmounted:
            m.add_separator()
            m.add_command(label=t('menu.properties'),
                          command=lambda: self.app.properties(self.window, [place.path]))
        m.tk_popup(event.x_root, event.y_root)

    def eject(self, place: Place) -> None:
        """Unmount (and power off when it's a USB drive) through udisks, as the desktop
        does."""
        self.app.eject(place, self.window)

    # ─── drops ───────────────────────────────────────────────

    def drop_target_at(self, x_root: int, y_root: int, dragged: List[str]) -> Optional[str]:
        key = None
        for k, (frame, *_rest) in self.rows.items():
            x0, y0 = frame.winfo_rootx(), frame.winfo_rooty()
            if x0 <= x_root < x0 + frame.winfo_width() and y0 <= y_root < y0 + frame.winfo_height():
                key = k
                break
        old = self.drop_key
        self.drop_key = key
        if old != key:
            if old:
                self._paint(old)
            if key:
                self._paint(key)
        if key:
            place = self.rows[key][3]
            if place.unmounted or place.key.startswith('net-'):
                return None
            return place.path
        folders = [p for p in dragged if os.path.isdir(p)]
        if folders and len(folders) == len(dragged):
            self._pin_hint(True)
            return 'pin:' + '\n'.join(folders)
        return None

    def _pin_hint(self, on: bool) -> None:
        self.pin_hint.configure(text=t('side.drop_to_pin') if on else '',
                                wraplength=self.winfo_width() - self.app.px(20),
                                fg=T["ch_b"] if on else T["dim"])

    def clear_drop(self) -> None:
        old = self.drop_key
        self.drop_key = None
        if old:
            self._paint(old)
        self._pin_hint(False)
