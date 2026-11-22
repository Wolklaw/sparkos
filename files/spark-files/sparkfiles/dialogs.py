"""Properties, batch rename and Open With."""

import grp
import os
import pwd
import stat
import threading
from typing import Dict, List, Optional, Tuple

import tkinter as tk

from . import gloop
from .core import full_date, home_short, human_size
from .listing import read_entry
from .ops import batch_names, find_replace_names, name_problem, rename, split_ext
from .places import free_space
from .text import t
from .ui import Check, Dialog, Progress, entry
from .widgets import T, Segmented


# ─── Properties ──────────────────────────────────────────────

def folder_size(paths: List[str], progress, stop: threading.Event) -> Tuple[int, int, int]:
    """(bytes, files, folders) below paths, counting each hard-linked file once."""
    size = files = folders = 0
    seen = set()
    for top in paths:
        try:
            st = os.lstat(top)
        except OSError:
            continue
        if not stat.S_ISDIR(st.st_mode):
            size += st.st_size
            files += 1
            continue
        for root, dirs, names in os.walk(top, onerror=lambda e: None):
            if stop.is_set():
                return size, files, folders
            folders += len(dirs)
            for name in names:
                try:
                    st = os.lstat(os.path.join(root, name))
                except OSError:
                    continue
                if st.st_nlink > 1:
                    key = (st.st_dev, st.st_ino)
                    if key in seen:
                        continue
                    seen.add(key)
                size += st.st_size
                files += 1
            progress(size, files, folders)
    return size, files, folders


class Properties(Dialog):
    def __init__(self, app, parent: tk.Misc, paths: List[str]):
        title = os.path.basename(paths[0].rstrip('/')) or paths[0] if len(paths) == 1 \
            else t('props.many', n=len(paths))
        super().__init__(app, parent, t('props.title', name=title))
        self.paths = paths
        self.stop = threading.Event()
        px = app.px
        self.f = app.font(10, False)
        self.grid_frame = tk.Frame(self.content, bg=T["panel"])
        self.grid_frame.pack(fill='both', expand=True)
        self.row = 0
        self.name_entry: Optional[tk.Entry] = None
        self.perm_checks: Dict[Tuple[str, str], Check] = {}
        self.exec_check: Optional[Check] = None
        single = len(paths) == 1
        e = read_entry(paths[0]) if single else None
        if single and e is not None:
            self.name_entry = entry(self.grid_frame, self.f, width=40)
            self.name_entry.insert(0, e.name)
            self._line(t('props.name'), widget=self.name_entry)
            mime = gloop.content_type(e.path, e.is_dir, sniff=True)
            kind = gloop.type_description(mime)
            self._line(t('props.type'), f"{kind} ({mime})" if mime != kind else mime)
            self._line(t('props.where'), home_short(os.path.dirname(e.path)))
            if e.is_link:
                try:
                    self._line(t('props.link_to'), os.readlink(e.path))
                except OSError:
                    pass
        else:
            self._line(t('props.where'), home_short(os.path.dirname(paths[0])))
        self.size_label = self._line(t('props.size'), t('props.counting'))
        self.contains_label = None
        if any(os.path.isdir(p) for p in paths):
            self.contains_label = self._line(t('props.contains'), '…')
        if single and e is not None:
            try:
                st = os.stat(e.path)
                self._line(t('props.modified'), full_date(st.st_mtime))
                self._line(t('props.accessed'), full_date(st.st_atime))
                try:
                    owner = pwd.getpwuid(st.st_uid).pw_name
                except KeyError:
                    owner = str(st.st_uid)
                try:
                    group = grp.getgrgid(st.st_gid).gr_name
                except KeyError:
                    group = str(st.st_gid)
                self._line(t('props.owner'), f"{owner} ({group})")
                self.mode = st.st_mode
                self.can_chmod = st.st_uid == os.getuid() or os.getuid() == 0
                self._permissions(st.st_mode, e.is_dir)
            except OSError:
                pass
            if e.is_dir and os.path.ismount(e.path):
                fs = free_space(e.path)
                if fs:
                    bar = Progress(self.grid_frame, height=px(6), width=px(260))
                    bar.set(1 - fs[0] / max(1, fs[1]))
                    self._line(t('props.drive'), widget=bar)
                    self._line('', t('side.free', free=human_size(fs[0]),
                                     total=human_size(fs[1])))
            if not e.is_dir:
                mime = gloop.content_type(e.path, False)
                app_ = gloop.default_app(mime)
                row = tk.Frame(self.grid_frame, bg=T["panel"])
                tk.Label(row, text=app_.name if app_ else t('props.no_app'), font=self.f,
                         bg=T["panel"], fg=T["text"]).pack(side='left')
                change = tk.Label(row, text=t('props.change'), font=app.font(9, True),
                                  bg=T["panel"], fg=T["accent"], cursor='hand2', padx=px(10))
                change.pack(side='left')
                change.bind('<ButtonRelease-1>',
                            lambda _e: OpenWith(app, self, [e.path]).place_and_show())
                self._line(t('props.opens_with'), widget=row)
        self.error = tk.Label(self.content, text='', font=app.font(9, False), bg=T["panel"],
                              fg=T["pink"], anchor='w')
        self.error.pack(fill='x', pady=(px(6), 0))
        self.button(t('button.cancel'), self.cancel)
        self.button(t('button.apply'), self.apply, 'primary')
        self.bind('<Return>', lambda _e: self.apply())
        threading.Thread(target=self._count, daemon=True).start()

    def _line(self, label: str, text: str = '', widget: Optional[tk.Widget] = None):
        px = self.app.px
        tk.Label(self.grid_frame, text=label.upper(), font=self.app.font(8, True),
                 bg=T["panel"], fg=T["muted"], anchor='nw').grid(row=self.row, column=0,
                                                                  sticky='nw',
                                                                  padx=(0, px(14)),
                                                                  pady=px(3))
        if widget is None:
            widget = tk.Label(self.grid_frame, text=text, font=self.f, bg=T["panel"],
                              fg=T["text"], anchor='w', justify='left',
                              wraplength=px(380))
        widget.grid(row=self.row, column=1, sticky='w', pady=px(3))
        self.row += 1
        return widget

    def _permissions(self, mode: int, is_dir: bool) -> None:
        box = tk.Frame(self.grid_frame, bg=T["panel"])
        f9 = self.app.font(9, False)
        who = (('owner', stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR),
               ('group', stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP),
               ('others', stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH))
        for r, (name, rb, wb, xb) in enumerate(who):
            tk.Label(box, text=t('perm.' + name), font=f9, bg=T["panel"], fg=T["muted"],
                     anchor='w').grid(row=r, column=0, sticky='w', padx=(0, self.app.px(10)))
            for c, (what, bit) in enumerate((('read', rb), ('write', wb))):
                ch = Check(box, t('perm.' + what), bool(mode & bit), f9)
                ch.grid(row=r, column=c + 1, sticky='w', padx=(0, self.app.px(10)))
                ch.set_enabled(self.can_chmod)
                self.perm_checks[(name, what)] = (ch, bit)
            if is_dir:
                ch = Check(box, t('perm.enter'), bool(mode & xb), f9)
                ch.grid(row=r, column=3, sticky='w')
                ch.set_enabled(self.can_chmod)
                self.perm_checks[(name, 'exec')] = (ch, xb)
        self._line(t('props.permissions'), widget=box)
        if not is_dir:
            self.exec_check = Check(self.grid_frame, t('perm.run'), bool(mode & 0o111), f9)
            self.exec_check.set_enabled(self.can_chmod)
            self._line('', widget=self.exec_check)
        if not self.can_chmod:
            self._line('', t('perm.not_yours'))

    def _count(self) -> None:
        last = [0.0]

        def progress(size, files, folders):
            import time
            now = time.monotonic()
            if now - last[0] > 0.2:
                last[0] = now
                self.app.bridge.post(lambda: self._show_size(size, files, folders, False))
        size, files, folders = folder_size(self.paths, progress, self.stop)
        if not self.stop.is_set():
            self.app.bridge.post(lambda: self._show_size(size, files, folders, True))

    def _show_size(self, size: int, files: int, folders: int, done: bool) -> None:
        if not self.winfo_exists():
            return
        text = f"{human_size(size)} ({t('props.bytes', n=f'{size:,}'.replace(',', ' '))})"
        if not done:
            text += ' …'
        self.size_label.configure(text=text)
        if self.contains_label is not None:
            self.contains_label.configure(text=t('props.contains_text', files=files,
                                                 folders=folders))

    def apply(self) -> None:
        path = self.paths[0]
        try:
            if self.perm_checks or self.exec_check:
                mode = stat.S_IMODE(os.stat(path).st_mode)
                new = mode
                for (_who, _what), (ch, bit) in self.perm_checks.items():
                    new = (new | bit) if ch.value else (new & ~bit)
                if self.exec_check is not None:
                    if self.exec_check.value and not mode & 0o111:
                        new |= (new & 0o444) >> 2           # x where there's r
                    elif not self.exec_check.value:
                        new &= ~0o111
                if new != mode:
                    os.chmod(path, new)
            if self.name_entry is not None:
                new_name = self.name_entry.get()
                if new_name != os.path.basename(path):
                    problem = name_problem(new_name)
                    if problem:
                        raise ValueError(t(problem))
                    rename(path, new_name)
        except (OSError, ValueError) as exc:
            why = exc.strerror if isinstance(exc, OSError) and exc.strerror else str(exc)
            if isinstance(exc, FileExistsError):
                why = t('error.name_taken')
            self.error.configure(text=why)
            self.app.glitch.now(self.head, strong=True)
            return
        self.cancel()

    def cancel(self) -> None:
        self.stop.set()
        super().cancel()


# ─── Batch rename ────────────────────────────────────────────

class BatchRename(Dialog):
    def __init__(self, app, parent: tk.Misc, paths: List[str], on_done):
        super().__init__(app, parent, t('batch.title', n=len(paths)))
        self.paths = sorted(paths, key=lambda p: os.path.basename(p).casefold())
        self.names = [os.path.basename(p) for p in self.paths]
        self.on_done = on_done
        px = app.px
        f = app.font(10, False)
        self.mode = 'pattern'
        Segmented(self.content, [(t('batch.pattern'), 'pattern'), (t('batch.replace'), 'find')],
                  'pattern', self._mode, app.font(9, True)).pack(anchor='w', pady=(0, px(10)))
        self.forms = tk.Frame(self.content, bg=T["panel"])
        self.forms.pack(fill='x')
        self.pattern_form = tk.Frame(self.forms, bg=T["panel"])
        tk.Label(self.pattern_form, text=t('batch.new_name'), font=app.font(8, True),
                 bg=T["panel"], fg=T["muted"]).grid(row=0, column=0, sticky='w')
        self.pattern = entry(self.pattern_form, f, width=32)
        stem = split_ext(self.names[0])[0]
        self.pattern.insert(0, (stem.rstrip('0123456789 _-') or stem) + ' ##')
        self.pattern.grid(row=1, column=0, sticky='we', ipady=px(3))
        tk.Label(self.pattern_form, text=t('batch.start'), font=app.font(8, True),
                 bg=T["panel"], fg=T["muted"]).grid(row=0, column=1, sticky='w', padx=(px(10), 0))
        self.start = entry(self.pattern_form, f, width=6)
        self.start.insert(0, '1')
        self.start.grid(row=1, column=1, sticky='w', padx=(px(10), 0), ipady=px(3))
        tk.Label(self.pattern_form, text=t('batch.pattern_help'), font=app.font(8, False),
                 bg=T["panel"], fg=T["dim"], justify='left', anchor='w').grid(
            row=2, column=0, columnspan=2, sticky='w', pady=(px(4), 0))
        self.find_form = tk.Frame(self.forms, bg=T["panel"])
        tk.Label(self.find_form, text=t('batch.find'), font=app.font(8, True), bg=T["panel"],
                 fg=T["muted"]).grid(row=0, column=0, sticky='w')
        tk.Label(self.find_form, text=t('batch.with'), font=app.font(8, True), bg=T["panel"],
                 fg=T["muted"]).grid(row=0, column=1, sticky='w', padx=(px(10), 0))
        self.find = entry(self.find_form, f, width=20)
        self.find.grid(row=1, column=0, ipady=px(3))
        self.repl = entry(self.find_form, f, width=20)
        self.repl.grid(row=1, column=1, padx=(px(10), 0), ipady=px(3))
        self.case = Check(self.find_form, t('batch.case'), False, app.font(9, False),
                          command=lambda _v: self.preview())
        self.case.grid(row=2, column=0, sticky='w', pady=(px(4), 0))
        self.pattern_form.pack(fill='x')
        tk.Label(self.content, text=t('batch.preview').upper(), font=app.font(8, True),
                 bg=T["panel"], fg=T["muted"], anchor='w').pack(fill='x', pady=(px(12), px(2)))
        self.list = tk.Text(self.content, height=min(14, len(paths) + 1), width=70, font=f,
                            bg=T["out_bg"], fg=T["text"], relief='flat', wrap='none',
                            highlightthickness=1, highlightbackground=T["line"])
        self.list.tag_configure('old', foreground=T["muted"])
        self.list.tag_configure('bad', foreground=T["pink"])
        self.list.pack(fill='both', expand=True)
        self.error = tk.Label(self.content, text='', font=app.font(9, False), bg=T["panel"],
                              fg=T["pink"], anchor='w')
        self.error.pack(fill='x', pady=(px(4), 0))
        for w in (self.pattern, self.start, self.find, self.repl):
            w.bind('<KeyRelease>', lambda _e: self.preview())
            w.bind('<Return>', lambda _e: self.apply())
        self.button(t('button.cancel'), self.cancel)
        self.ok = self.button(t('batch.do'), self.apply, 'primary')
        self.focus_first = lambda: (self.pattern.focus_set(),
                                    self.pattern.selection_range(0, 'end'))
        self.preview()

    def _mode(self, mode: str) -> None:
        self.mode = mode
        self.pattern_form.pack_forget()
        self.find_form.pack_forget()
        (self.pattern_form if mode == 'pattern' else self.find_form).pack(fill='x')
        (self.pattern if mode == 'pattern' else self.find).focus_set()
        self.preview()

    def new_names(self) -> List[str]:
        if self.mode == 'pattern':
            try:
                start = int(self.start.get() or '1')
            except ValueError:
                start = 1
            return batch_names(self.names, self.pattern.get(), start)
        return find_replace_names(self.names, self.find.get(), self.repl.get(), self.case.value)

    def problems(self, new: List[str]) -> Dict[int, str]:
        out: Dict[int, str] = {}
        seen: Dict[str, int] = {}
        moving = set(self.paths)
        for i, name in enumerate(new):
            problem = name_problem(name)
            if problem:
                out[i] = t(problem)
                continue
            if name in seen:
                out[i] = t('batch.twice')
                continue
            seen[name] = i
            target = os.path.join(os.path.dirname(self.paths[i]), name)
            if name != self.names[i] and os.path.lexists(target) and target not in moving:
                out[i] = t('error.name_taken')
        return out

    def preview(self) -> None:
        new = self.new_names()
        bad = self.problems(new)
        self.list.configure(state='normal')
        self.list.delete('1.0', 'end')
        for i, (old, name) in enumerate(zip(self.names, new)):
            self.list.insert('end', old, 'old')
            self.list.insert('end', '  →  ')
            self.list.insert('end', name + (f'   ({bad[i]})' if i in bad else '') + '\n',
                             'bad' if i in bad else ())
        self.list.configure(state='disabled')
        self.ok.set_enabled(not bad and new != self.names)
        self.error.configure(text=t('batch.fix', n=len(bad)) if bad else '')

    def apply(self) -> None:
        new = self.new_names()
        if self.problems(new) or new == self.names:
            self.app.glitch.now(self.head)
            return
        # two steps, so swapping names (a -> b, b -> a) works: first to temporary names
        temp = []
        done: List[str] = []
        errors = []
        for i, path in enumerate(self.paths):
            if new[i] == self.names[i]:
                temp.append(None)
                done.append(path)
                continue
            tmp = os.path.join(os.path.dirname(path), f'.spark-rename-{os.getpid()}-{i}')
            try:
                os.rename(path, tmp)
                temp.append(tmp)
            except OSError as exc:
                temp.append(None)
                errors.append(f"{self.names[i]}: {exc.strerror}")
        for i, tmp in enumerate(temp):
            if tmp is None:
                continue
            target = os.path.join(os.path.dirname(self.paths[i]), new[i])
            try:
                os.rename(tmp, target)
                done.append(target)
            except OSError as exc:
                os.rename(tmp, self.paths[i])
                errors.append(f"{self.names[i]}: {exc.strerror}")
        self.on_done(done, errors)
        self.done(True)


# ─── Open with ───────────────────────────────────────────────

class OpenWith(Dialog):
    def __init__(self, app, parent: tk.Misc, paths: List[str]):
        super().__init__(app, parent, t('openwith.title'))
        self.paths = paths
        px = app.px
        self.mime = gloop.content_type(paths[0], os.path.isdir(paths[0]), sniff=True)
        self.description = gloop.type_description(self.mime)
        self.apps = gloop.apps_for(self.mime)
        self.all_apps = None
        self.showing_all = not self.apps
        tk.Label(self.content, text=t('openwith.text', n=len(paths),
                                      name=os.path.basename(paths[0]), kind=self.description),
                 font=app.font(10, False), bg=T["panel"], fg=T["text"], anchor='w',
                 justify='left', wraplength=px(440)).pack(anchor='w', pady=(0, px(8)))
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
        self.more = Check(self.content, t('openwith.all'), self.showing_all,
                          app.font(9, False), command=self._toggle_all)
        self.more.pack(anchor='w', pady=(px(6), 0))
        self.remember = Check(self.content, t('openwith.always', kind=self.description),
                              False, app.font(9, False))
        self.remember.pack(anchor='w', pady=(px(2), 0))
        self.button(t('button.cancel'), self.cancel)
        self.button(t('openwith.open'), self.open, 'primary')
        self.focus_first = lambda: self.search.focus_set()
        self.shown: List[gloop.App] = []
        self.fill()

    def _toggle_all(self, value: bool) -> None:
        self.showing_all = value
        self.fill()

    def fill(self) -> None:
        if self.showing_all and self.all_apps is None:
            self.all_apps = gloop.all_apps()
        apps = self.all_apps if self.showing_all else self.apps
        q = self.search.get().strip().casefold()
        self.shown = [a for a in (apps or []) if q in a.name.casefold() or q in a.id.casefold()]
        self.listbox.delete(0, 'end')
        default = gloop.default_app(self.mime)
        for a in self.shown:
            mark = '  ' + t('openwith.default') if default and a.id == default.id else ''
            self.listbox.insert('end', a.name + mark)
        if self.shown:
            self.listbox.selection_set(0)

    def open(self) -> None:
        sel = self.listbox.curselection()
        if not sel:
            self.app.glitch.now(self.head)
            return
        chosen = self.shown[sel[0]]
        if self.remember.value:
            try:
                gloop.set_default(chosen, self.mime)
            except Exception as exc:                   # noqa: BLE001
                self.app.message(self.parent_window, str(exc), error=True)
        why = gloop.launch(chosen, self.paths)
        if why:
            self.app.message(self.parent_window, t('error.open_failed', why=why), error=True)
        self.done(chosen)
