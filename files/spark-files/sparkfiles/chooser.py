"""The windows the portal opens: a Spark Files window that picks files instead of opening them
(Open, Save, choose a folder) and the "Open with" picker apps get through AppChooser.

ChooserWindow is a Window with a bar at the bottom: the name to save as, the file type menu,
the app's extra options, Cancel and Open/Save. Double-clicking a file (or Enter) picks it; the
list shows only files of the chosen type. It answers the portal exactly once: closing the
window is a cancel."""

import os
import tkinter as tk
from typing import Callable, List, Optional

from . import gloop
from .core import home
from .portal import AppChooserAnswer, Ask, Choice, Filter, app_results, file_results
from .text import t
from .ui import Check, Dialog, ask as ask_question, entry, menu, separator
from .widgets import T, WolkButton
from .window import Window


def default_title(a: Ask) -> str:
    if a.method == 'SaveFile':
        return t('chooser.title_save')
    if a.directory:
        return t('chooser.title_folder')
    return t('chooser.title_open_many') if a.multiple else t('chooser.title_open')


def accept_text(a: Ask) -> str:
    if a.accept_label:
        return a.accept_label.replace('_', '')            # GTK mnemonics: "_Open"
    if a.method == 'SaveFile':
        return t('chooser.save')
    return t('chooser.choose') if a.directory else t('chooser.open')


class ChooserWindow(Window):
    picking = True

    def __init__(self, app, a: Ask, reply: Callable[[int, dict], None]):
        # read by the panes while Window builds them
        self.ask, self._reply = a, reply
        self.active_filter: Optional[Filter] = a.current_filter
        self.answered = False
        self.name_entry: Optional[tk.Entry] = None
        super().__init__(app, [a.start_folder(home())])
        px = app.px
        self.title(a.title or default_title(a))
        for b in (self.b_term, self.b_split):
            b.pack_forget()
        body = self.main.master
        bar = tk.Frame(self, bg=T["bg"])
        bar.pack(side='bottom', fill='x', padx=px(10), pady=(px(6), px(10)), before=body)
        separator(self).pack(side='bottom', fill='x', before=bar)

        font = app.font(10, False)
        small = app.font(9, False)
        top = tk.Frame(bar, bg=T["bg"])
        top.pack(fill='x')
        if a.method == 'SaveFile':
            tk.Label(top, text=t('chooser.name'), font=small, bg=T["bg"], fg=T["muted"]
                     ).pack(side='left', padx=(0, px(8)))
            self.name_entry = entry(top, font, width=40, bg=T["panel"])
            self.name_entry.pack(side='left', fill='x', expand=True, ipady=px(4))
            self.name_entry.insert(0, a.current_name)
            stem = a.current_name.rfind('.')
            self.name_entry.selection_range(0, stem if stem > 0 else 'end')
            self.name_entry.bind('<Return>', lambda _e: (self.accept(), 'break')[1])
            self.name_entry.bind('<Escape>', lambda _e: (self.close(), 'break')[1])
        self.filter_button: Optional[WolkButton] = None
        if a.filters and not a.directory:
            tk.Label(top, text=t('chooser.type'), font=small, bg=T["bg"], fg=T["muted"]
                     ).pack(side='left', padx=(px(12), px(8)))
            self.filter_button = WolkButton(top, self._filter_name(), self._filter_menu,
                                            small, padx=px(10), pady=px(3))
            self.filter_button.pack(side='left')

        low = tk.Frame(bar, bg=T["bg"])
        low.pack(fill='x', pady=(px(8), 0))
        self.choice_widgets = []
        for c in a.choices:
            self._add_choice(low, c, small)
        buttons = tk.Frame(low, bg=T["bg"])
        buttons.pack(side='right')
        bfont = app.font(9, True)
        WolkButton(buttons, t('button.cancel'), self.close, bfont, padx=px(12), pady=px(5)
                   ).pack(side='left', padx=(px(6), 0))
        self.accept_button = WolkButton(buttons, accept_text(a), self.accept, bfont,
                                        variant='primary', padx=px(12), pady=px(5))
        self.accept_button.pack(side='left', padx=(px(6), 0))
        self.geometry(f'{px(960)}x{px(620)}')

    # ─── what shows ──────────────────────────────────────────

    def keep_entry(self, e) -> bool:
        f = self.active_filter
        mime = gloop.content_type(e.path) if f is not None and f.uses_mime and not e.is_dir \
            else None
        return self.ask.shows(e.name, e.is_dir, mime, f)

    def _filter_name(self) -> str:
        return self.active_filter.name if self.active_filter else ''

    def _filter_menu(self) -> None:
        m = menu(self, self.app.font(10, False))
        for f in self.ask.filters:
            m.add_command(label=('● ' if f == self.active_filter else '   ') + f.name,
                          command=lambda f=f: self.set_filter(f))
        b = self.filter_button
        m.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())

    def set_filter(self, f: Filter) -> None:
        self.active_filter = f
        if self.filter_button is not None:
            self.filter_button.set_text(f.name)
        for tab in self.tabs:
            for p in tab.panes:
                p.apply()

    def _add_choice(self, parent, c: Choice, font) -> None:
        px = self.app.px
        if c.is_check:
            w = Check(parent, c.label, c.value == 'true', font, bg=T["bg"],
                      command=lambda on, c=c: setattr(c, 'value', 'true' if on else 'false'))
            w.pack(side='left', padx=(0, px(14)))
            self.choice_widgets.append(w)
            return
        tk.Label(parent, text=c.label, font=font, bg=T["bg"], fg=T["muted"]
                 ).pack(side='left', padx=(0, px(6)))
        labels = dict(c.options)
        button = WolkButton(parent, labels.get(c.value, c.value), lambda: None, font,
                            padx=px(10), pady=px(3))

        def pop():
            m = menu(self, self.app.font(10, False))
            for oid, label in c.options:
                def pick(oid=oid, label=label):
                    c.value = oid
                    button.set_text(label)
                m.add_command(label=('● ' if oid == c.value else '   ') + label, command=pick)
            m.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())
        button.command = pop
        button.pack(side='left', padx=(0, px(14)))
        self.choice_widgets.append(button)

    # ─── picking ─────────────────────────────────────────────

    def selection_changed(self, pane) -> None:
        super().selection_changed(pane)
        if self.name_entry is not None and pane is self.active:
            files = [e for e in pane.view.selected_entries() if not e.is_dir]
            if len(files) == 1:
                self.name_entry.delete(0, 'end')
                self.name_entry.insert(0, files[0].name)

    def folder(self) -> str:
        p = self.active
        return p.path if p.mode == 'folder' and os.path.isdir(p.path) else home()

    def pick(self, paths: List[str]) -> None:
        """A file was double-clicked or Enter was pressed on it."""
        if self.ask.method == 'SaveFile' and self.name_entry is not None:
            self.name_entry.delete(0, 'end')
            self.name_entry.insert(0, os.path.basename(paths[0]))
            self.accept()
        elif not self.ask.directory:
            self.finish(paths if self.ask.multiple else paths[:1])

    def accept(self) -> None:
        a = self.ask
        pane = self.active
        chosen = pane.view.selected_entries()
        if a.method == 'SaveFile':
            self._accept_save()
        elif a.directory:
            dirs = [e.path for e in chosen if e.is_dir]
            if a.multiple and dirs:
                self.finish(dirs)
                return
            target = dirs[0] if len(dirs) == 1 else self.folder()
            if a.method == 'SaveFiles':
                self._accept_save_files(target)
            else:
                self.finish([target])
        else:
            files = [e.path for e in chosen if not e.is_dir]
            if files:
                self.finish(files if a.multiple else files[:1])
                return
            dirs = [e.path for e in chosen if e.is_dir]
            if len(dirs) == 1:
                pane.go(dirs[0])
                return
            pane.flash(t('chooser.pick_file'), error=True)

    def _accept_save(self) -> None:
        name = self.name_entry.get().strip() if self.name_entry is not None else ''
        if not name:
            self.app.glitch.now(self.title_text)
            self.name_entry.focus_set()
            return
        path = os.path.join(self.folder(), os.path.expanduser(name))
        path = os.path.normpath(path)
        if os.path.isdir(path):
            self.active.go(path)
            self.name_entry.delete(0, 'end')
            return
        folder = os.path.dirname(path)
        if not os.path.isdir(folder):
            self.active.flash(t('chooser.no_folder', folder=folder), error=True)
            return
        if os.path.exists(path) and not self._replace([path], folder):
            return
        self.finish([path])

    def _accept_save_files(self, folder: str) -> None:
        from .portal import save_targets
        targets = save_targets(folder, self.ask.files)
        clash = [p for p in targets if os.path.exists(p)]
        if clash and not self._replace(clash, folder):
            return
        self.finish(targets)

    def _replace(self, paths: List[str], folder: str) -> bool:
        text = (t('chooser.replace', name=os.path.basename(paths[0]), folder=folder)
                if len(paths) == 1 else t('chooser.replace_many', n=len(paths), folder=folder))
        answer = ask_question(self.app, self, t('chooser.replace_title'), text,
                              [('cancel', t('button.cancel'), 'ghost'),
                               ('replace', t('chooser.replace_button'), 'danger')],
                              default='cancel')
        return answer == 'replace'

    # ─── answering ───────────────────────────────────────────

    def finish(self, paths: List[str]) -> None:
        if self.answered:
            return
        self.answered = True
        self._reply(*file_results(self.ask, paths, self.active_filter, self.ask.choices))
        Window.close(self)

    def close(self) -> None:
        """The window's ✕, Cancel, or the portal giving up."""
        if not self.answered:
            self.answered = True
            self._reply(*file_results(self.ask, []))
        Window.close(self)

    def _remember_size(self, event) -> None:
        pass                    # the chooser's size isn't the file manager's


class AppPicker(Dialog):
    """AppChooser: pick the app to open a file with. The portal sends the apps it found for
    the type (ids without .desktop); "Show every app" lists the rest."""

    def __init__(self, app, choices: List[str], options: dict,
                 reply: Callable[[int, dict], None]):
        super().__init__(app, app.root, t('openwith.title'))
        self.wm_transient('')                   # the root is hidden; a transient would be too
        self._reply = reply
        self.answered = False
        px = app.px
        self.answer = AppChooserAnswer(choices, options.get('last_choice') or '')
        mime = options.get('content_type') or ''
        name = options.get('filename') or os.path.basename(options.get('uri') or '') or '?'
        kind = gloop.type_description(mime) if mime else ''
        text = t('openwith.text.1', name=name, kind=kind) if kind else \
            t('chooser.app_text', name=name)
        tk.Label(self.content, text=text, font=app.font(10, False), bg=T["panel"],
                 fg=T["text"], anchor='w', justify='left', wraplength=px(440)
                 ).pack(anchor='w', pady=(0, px(8)))
        self.search = entry(self.content, app.font(10, False), width=40)
        self.search.pack(fill='x', ipady=px(3))
        self.search.bind('<KeyRelease>', lambda _e: self.fill())
        self.search.bind('<Down>', lambda _e: self.listbox.focus_set())
        self.listbox = tk.Listbox(self.content, height=12, font=app.font(10, False),
                                  bg=T["out_bg"], fg=T["text"], selectbackground=T["line2"],
                                  selectforeground=T["text"], activestyle='none',
                                  highlightthickness=1, highlightbackground=T["line"],
                                  highlightcolor=T["accent"], relief='flat', bd=0)
        self.listbox.pack(fill='both', expand=True, pady=(px(6), 0))
        self.listbox.bind('<Double-Button-1>', lambda _e: self.open())
        self.listbox.bind('<Return>', lambda _e: self.open())
        self.more = Check(self.content, t('openwith.all'), not choices, app.font(9, False),
                          command=lambda _v: self.fill())
        self.more.pack(anchor='w', pady=(px(6), 0))
        self.button(t('button.cancel'), self.cancel)
        self.button(t('openwith.open'), self.open, 'primary')
        self.bind('<Return>', lambda _e: self.open())
        self.shown: List[gloop.App] = []
        self._all: Optional[List[gloop.App]] = None
        self.fill()

    def update_choices(self, choices: List[str]) -> None:
        self.answer.choices = list(choices)
        self.fill()

    def fill(self) -> None:
        if self.more.value:
            if self._all is None:
                self._all = gloop.all_apps()
            apps = self._all
        else:
            apps = [a for a in (app_by_id(i) for i in self.answer.choices) if a is not None]
        q = self.search.get().strip().casefold()
        self.shown = [a for a in apps if q in a.name.casefold() or q in a.id.casefold()]
        self.listbox.delete(0, 'end')
        for a in self.shown:
            self.listbox.insert('end', a.name)
        if self.shown:
            at = self.answer.first_index([a.id for a in self.shown])
            self.listbox.selection_set(at)
            self.listbox.see(at)

    def show(self) -> None:
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = max(0, (self.winfo_screenwidth() - w) // 2)
        y = max(0, (self.winfo_screenheight() - h) // 3)
        self.geometry(f'+{x}+{y}')
        self.deiconify()
        self.lift()
        self.focus_force()
        self.search.focus_set()
        self.app.glitch.now(self.head, strong=True)

    def open(self) -> None:
        sel = self.listbox.curselection()
        if not sel:
            self.app.glitch.now(self.head)
            return
        self._answer(self.shown[sel[0]].id)

    def _answer(self, app_id: Optional[str]) -> None:
        if not self.answered:
            self.answered = True
            self._reply(*app_results(app_id))
        if self.winfo_exists():
            self.destroy()

    def cancel(self) -> None:
        self._answer(None)


def app_by_id(app_id: str) -> Optional[gloop.App]:
    if gloop.Gio is None or not app_id:
        return None
    try:
        info = gloop.Gio.DesktopAppInfo.new(app_id if app_id.endswith('.desktop')
                                            else app_id + '.desktop')
    except TypeError:
        info = None
    return gloop.App(info) if info is not None else None
