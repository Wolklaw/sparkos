"""One file browser: back/forward/up, the path bar (click a part, or click the empty end or
press Ctrl+L to type a path), the filter box, the file view and its status line. A tab holds
one pane, or two side by side in the split view (F3).

The pane lists a folder, the Trash, or the results of a search below a folder (Ctrl+F)."""

import os
import re
import threading
import time
from typing import Dict, List, Optional, Tuple

import tkinter as tk

from . import network, trash as trash_mod
from .core import home, home_short, human_size, expand_path
from .network import is_remote
from .listing import Entry, filter_entries, list_dir, read_entry, sort_entries
from .places import TRASH, free_space
from .search import Search
from .text import t
from .ui import Timers, entry as make_entry
from .view import FileView
from .widgets import T, IconButton


class PathBar(Timers, tk.Frame):
    """Breadcrumbs: one button per folder level; the left ones fold into '…' when the bar is
    too narrow. Clicking the empty end (or Ctrl+L) turns it into a text field."""

    def __init__(self, parent: tk.Misc, pane: 'Pane'):
        super().__init__(parent, bg=T["out_bg"], highlightthickness=1,
                         highlightbackground=T["line"], highlightcolor=T["accent"])
        self.pane = pane
        self.app = pane.app
        self.font = self.app.font(10, False)
        self.crumbs = tk.Frame(self, bg=T["out_bg"], cursor='xterm')
        self.crumbs.pack(fill='both', expand=True)
        self.crumbs.bind('<ButtonRelease-1>', lambda _e: self.edit())
        self.field = make_entry(self, self.font, width=20)
        self.field.configure(highlightthickness=0)
        self.field.bind('<Return>', self._commit)
        self.field.bind('<KP_Enter>', self._commit)
        self.field.bind('<Escape>', lambda _e: self.show())
        self.field.bind('<FocusOut>', lambda _e: self.after(150, self._focus_lost))
        self.field.bind('<Tab>', self._complete)
        self.path = ''
        self.editing = False
        self.bind('<Configure>', lambda _e: self.after_idle(self._layout))

    def set_path(self, path: str) -> None:
        self.path = path
        if not self.editing:
            self._layout()

    def _segments(self) -> List[Tuple[str, str]]:
        path = self.path
        if path == TRASH:
            return [(t('place.trash'), TRASH)]
        if self.pane.mode == 'search':
            return self._segments_for(path) + [(t('search.results'), '')]
        return self._segments_for(path)

    def _segments_for(self, path: str) -> List[Tuple[str, str]]:
        h = home()
        out = []
        if path == h or path.startswith(h + os.sep):
            out.append((t('place.home'), h))
            rest = path[len(h):].strip(os.sep)
            base = h
        else:
            m = self.app.drive_label(path)
            if m:
                label, base = m
                out.append((label, base))
                rest = path[len(base):].strip(os.sep)
            else:
                out.append(('/', '/'))
                rest = path.strip(os.sep)
                base = '/'
        for part in [p for p in rest.split(os.sep) if p]:
            base = os.path.join(base, part)
            out.append((part, base))
        return out

    def _layout(self) -> None:
        if self.editing or not self.winfo_exists():
            return
        for w in self.crumbs.winfo_children():
            w.destroy()
        segs = self._segments()
        px = self.app.px
        avail = max(px(80), self.winfo_width() - px(30))
        widths = [self.font.measure(name) + px(22) for name, _p in segs]
        start = 0
        while start < len(segs) - 1 and sum(widths[start:]) + (px(30) if start else 0) > avail:
            start += 1
        if start:
            self._crumb('…', segs[start - 1][1], False)
        for i in range(start, len(segs)):
            name, path = segs[i]
            self._crumb(name, path, i == len(segs) - 1)
            if i < len(segs) - 1:
                tk.Label(self.crumbs, text='›', font=self.font, bg=T["out_bg"],
                         fg=T["dim"]).pack(side='left')

    def _crumb(self, name: str, path: str, last: bool) -> None:
        px = self.app.px
        lab = tk.Label(self.crumbs, text=name, font=self.font, bg=T["out_bg"],
                       fg=T["text"] if last else T["muted"], padx=px(6), pady=px(3),
                       cursor='hand2')
        lab.pack(side='left')
        lab.bind('<Enter>', lambda _e: lab.configure(bg=T["hover"], fg=T["accent"]))
        lab.bind('<Leave>', lambda _e: lab.configure(bg=T["out_bg"],
                                                     fg=T["text"] if last else T["muted"]))
        if path:
            lab.bind('<ButtonRelease-1>', lambda _e: self.pane.go(path))
            lab.bind('<ButtonRelease-2>', lambda _e: self.pane.window.new_tab(path, select=False))
            lab.drop_path = path
            self.app.register_drop_label(lab, path)

    def edit(self) -> None:
        if self.pane.mode == 'trash' or self.editing:
            return
        self.editing = True
        self.crumbs.pack_forget()
        self.field.pack(fill='both', expand=True, ipady=self.app.px(3))
        self.field.delete(0, 'end')
        self.field.insert(0, self.path if self.path != TRASH else '')
        self.field.focus_set()
        self.field.selection_range(0, 'end')
        self.field.icursor('end')

    def show(self) -> None:
        if not self.editing:
            return
        self.editing = False
        self.field.pack_forget()
        self.crumbs.pack(fill='both', expand=True)
        self._layout()
        self.pane.view.canvas.focus_set()

    def _focus_lost(self) -> None:
        if self.editing and self.focus_get() is not self.field:
            self.show()

    def _commit(self, _e=None) -> str:
        text = self.field.get().strip()
        if not text:
            self.show()
            return 'break'
        if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*://', text):
            return self._commit_address(text)
        path = expand_path(text, self.path if self.path != TRASH else home())
        if os.path.isdir(path):
            self.show()
            self.pane.go(path)
        elif os.path.exists(path):
            self.show()
            self.pane.go(os.path.dirname(path), select=[path])
        else:
            self.pane.flash(t('error.no_such_folder', path=home_short(path)), error=True)
        return 'break'

    def _commit_address(self, text: str) -> str:
        """sftp://host/folder or smb://host/share typed in the bar: connect (a typed
        password is used once and never kept)."""
        try:
            server, password = network.parse_address(text)
        except network.NetworkError as err:
            self.pane.flash(self.app.network_error_text(err, text), error=True)
            return 'break'
        self.show()
        self.app.network_go(self.pane.window, server, password, saved=password is None)
        return 'break'

    def _complete(self, _e=None) -> str:
        """Tab completes the folder name being typed."""
        text = self.field.get()
        path = os.path.expanduser(text)
        folder, part = os.path.split(path)
        try:
            names = sorted(n for n in os.listdir(folder or '/')
                           if n.startswith(part) and os.path.isdir(os.path.join(folder, n))
                           and (part.startswith('.') or not n.startswith('.')))
        except OSError:
            return 'break'
        if not names:
            return 'break'
        common = os.path.commonprefix(names)
        done = os.path.join(folder, common) + (os.sep if len(names) == 1 else '')
        if text.startswith('~'):
            done = '~' + done[len(home()):] if done.startswith(home()) else done
        self.field.delete(0, 'end')
        self.field.insert(0, done)
        self.field.icursor('end')
        return 'break'


class Pane(Timers, tk.Frame):
    def __init__(self, parent: tk.Misc, window, path: str):
        super().__init__(parent, bg=T["bg"])
        self.window = window
        self.app = window.app
        px = self.app.px
        self.path = ''
        self.mode = 'folder'               # folder | trash | search
        self.history: List[str] = []
        self.hist_pos = -1
        self.all_entries: List[Entry] = []
        self.trash_info: Dict[str, Tuple[str, str]] = {}
        self.filter_text = ''
        self.watch_id = 0
        self._load_token = 0
        self._reload_id: Optional[str] = None
        self._loading_since = 0.0
        self.search: Optional[Search] = None
        self.search_results: List[Entry] = []
        self._search_flush: Optional[str] = None
        self.error = ''
        self.free = ''
        self.message = ''
        self._message_id: Optional[str] = None
        self.active = False

        nav = tk.Frame(self, bg=T["bg"])
        nav.pack(fill='x', padx=px(6), pady=(px(6), px(4)))
        size = px(28)
        self.b_back = IconButton(nav, 'back', self.back, size)
        self.b_fwd = IconButton(nav, 'forward', self.forward, size)
        self.b_up = IconButton(nav, 'parent', self.go_up, size)
        self.b_refresh = IconButton(nav, 'refresh', lambda: self.reload(user=True), size)
        for b, tip in ((self.b_back, 'tip.back'), (self.b_fwd, 'tip.forward'),
                       (self.b_up, 'tip.up'), (self.b_refresh, 'tip.refresh')):
            b.pack(side='left', padx=(0, px(2)))
            self.app.tooltip.attach(b, t(tip))
        self.filter = make_entry(nav, self.app.font(10, False), width=18)
        self.filter.pack(side='right', ipady=px(4), padx=(px(6), 0))
        self.filter_hint = tk.Label(nav, text=t('filter.hint'), font=self.app.font(9, False),
                                    bg=T["out_bg"], fg=T["dim"], cursor='xterm')
        self.filter_hint.bind('<ButtonRelease-1>', lambda _e: self.filter.focus_set())
        self.filter.bind('<KeyRelease>', self._filter_changed)
        self.filter.bind('<Escape>', lambda _e: (self.escape(), 'break')[1])
        self.filter.bind('<Return>', self._filter_enter)
        self.filter.bind('<Down>', lambda _e: (self.view.canvas.focus_set(),
                                               self.view.move_cursor(0), 'break')[2])
        self.filter.bind('<FocusIn>', lambda _e: (self.focused(), self._paint_hint()))
        self.filter.bind('<FocusOut>', lambda _e: self._paint_hint())
        self.pathbar = PathBar(nav, self)
        self.pathbar.pack(side='left', fill='x', expand=True, padx=(px(4), 0))

        self.view = FileView(self, self.app, self)
        self.view.set_mode(self.app.settings['view'])
        self.view.pack(fill='both', expand=True)

        self.status = tk.Frame(self, bg=T["panel"])
        self.status.pack(fill='x')
        self.status_left = tk.Label(self.status, text='', font=self.app.font(9, False),
                                    bg=T["panel"], fg=T["muted"], anchor='w', padx=px(8),
                                    pady=px(3))
        self.status_left.pack(side='left', fill='x', expand=True)
        self.status_right = tk.Label(self.status, text='', font=self.app.font(9, False),
                                     bg=T["panel"], fg=T["dim"], anchor='e', padx=px(8))
        self.status_right.pack(side='right')
        self.trash_bar: Optional[tk.Frame] = None
        self.after_idle(self._paint_hint)
        self.go(path)

    # ─── where we are ────────────────────────────────────────

    def go(self, path: str, add_history: bool = True, select: Optional[List[str]] = None
           ) -> None:
        if path != TRASH:
            path = os.path.normpath(path)
        if self.search is not None:
            self.stop_search()
        same = path == self.path and self.mode != 'search'
        self.mode = 'trash' if path == TRASH else 'folder'
        if add_history and not same:
            del self.history[self.hist_pos + 1:]
            self.history.append(path)
            self.hist_pos = len(self.history) - 1
        self.path = path
        if not same:
            self.filter_text = ''
            self.filter.delete(0, 'end')
            self._paint_hint()
        self.pathbar.set_path(path)
        self._watch()
        self._trash_bar()
        self.view.show_folder_column = self.mode == 'trash'
        self.view.search_root = ''
        self.view.where_fn = self._trash_where if self.mode == 'trash' else None
        self.load(reset=not same, select=select)
        self._nav_buttons()
        self.window.pane_moved(self)
        f = free_space(path) if path != TRASH else None
        self.free = t('status.free', size=human_size(f[0])) if f else ''

    def _nav_buttons(self) -> None:
        self.b_back.set_enabled(self.hist_pos > 0)
        self.b_fwd.set_enabled(self.hist_pos < len(self.history) - 1)
        self.b_up.set_enabled(self.mode == 'search' or
                              (self.mode == 'folder' and self.path != '/' and
                               not self._at_server_root()))

    def _at_server_root(self) -> bool:
        """The top of a server's mount: above it is spark-net's own folder, not a place."""
        remote = network.split_remote(self.path)
        return bool(remote) and self.path.rstrip('/') == remote[0]

    def back(self) -> None:
        if self.hist_pos > 0:
            came_from = self.path
            self.hist_pos -= 1
            self.go(self.history[self.hist_pos], add_history=False,
                    select=[came_from] if os.path.dirname(came_from) ==
                    self.history[self.hist_pos] else None)

    def forward(self) -> None:
        if self.hist_pos < len(self.history) - 1:
            self.hist_pos += 1
            self.go(self.history[self.hist_pos], add_history=False)

    def go_up(self) -> None:
        if self.mode == 'search':
            self.stop_search(reload=True)
            return
        if self.mode == 'trash' or self.path == '/' or self._at_server_root():
            return
        parent = os.path.dirname(self.path)
        self.go(parent, select=[self.path])

    def drop_folder(self) -> Optional[str]:
        if self.mode == 'search':
            return None
        return self.path

    def current_folder(self) -> Optional[str]:
        return self.path if self.mode == 'folder' else None

    def title(self) -> str:
        if self.mode == 'trash':
            return t('place.trash')
        if self.path == home():
            name = t('place.home')
        else:
            label = self.app.drive_label(self.path)
            name = label[0] if label and label[1] == self.path else \
                (os.path.basename(self.path) or '/')
        if self.mode == 'search':
            return t('search.tab', text=self.search.text if self.search else '', where=name)
        return name

    # ─── loading ─────────────────────────────────────────────

    def load(self, reset: bool = False, select: Optional[List[str]] = None) -> None:
        self._load_token += 1
        token = self._load_token
        path, mode = self.path, self.mode
        self._loading_since = time.monotonic()
        keep_top = self.view.top

        def work():
            error = ''
            entries: List[Entry] = []
            info: Dict[str, Tuple[str, str]] = {}
            try:
                if mode == 'trash':
                    for item in trash_mod.items():
                        e = read_entry(item.path)
                        if e is not None:
                            entries.append(e)
                            info[item.path] = (item.original, item.deleted)
                else:
                    entries = list_dir(path)
            except PermissionError:
                error = t('error.no_permission_folder')
            except FileNotFoundError:
                error = t('error.folder_gone')
            except OSError as exc:
                error = exc.strerror or str(exc)
            self.app.bridge.post(lambda: self._loaded(token, entries, info, error, reset,
                                                      select, keep_top))

        threading.Thread(target=work, name='list', daemon=True).start()
        # a slow drive: say so if it takes more than a moment
        self.after(250, lambda: self._still_loading(token))

    def _still_loading(self, token: int) -> None:
        if token == self._load_token and self._loading_since:
            self.view.empty_text = t('status.loading')
            if not self.view.entries:
                self.view.redraw()

    def _loaded(self, token: int, entries: List[Entry], info, error: str, reset: bool,
                select: Optional[List[str]], keep_top: int) -> None:
        if token != self._load_token or not self.winfo_exists():
            return
        self._loading_since = 0.0
        self.error = error
        self.all_entries = entries
        self.trash_info = info
        if error and reset and self.mode == 'folder' and not os.path.isdir(self.path):
            # the folder went away (unplugged drive, deleted): go to the nearest one left
            parent = self.path
            while parent != '/' and not os.path.isdir(parent):
                parent = os.path.dirname(parent)
            if parent != self.path and os.path.isdir(parent):
                self.flash(error, error=True)
                self.go(parent, add_history=False)
                return
        self.view.empty_text = error or (t('status.empty_trash') if self.mode == 'trash'
                                         else t('status.empty_folder'))
        self.apply(reset=reset, select=select)
        if not reset:
            self.view.top = keep_top
            self.view.redraw()
        if error:
            self.flash(error, error=True)

    def apply(self, reset: bool = False, select: Optional[List[str]] = None) -> None:
        """Sort and filter what was read, and show it."""
        s = self.app.settings
        source = self.search_results if self.mode == 'search' else self.all_entries
        shown = filter_entries(source, self.filter_text, s['show_hidden'] or
                               self.mode == 'trash')
        keep = getattr(self.window, 'keep_entry', None)        # the portal's file chooser
        if keep is not None:
            shown = [e for e in shown if keep(e)]
        key = self.sort_key()
        if self.mode == 'trash' and key == 'modified':
            shown = sorted(shown, key=lambda e: self.trash_info.get(e.path, ('', ''))[1],
                           reverse=not s['sort_reverse'])
        else:
            shown = sort_entries(shown, key, s['sort_reverse'], s['folders_first'])
        self.view.cut = self.app.cut_paths()
        self.view.set_entries(shown, reset=reset, select=select)
        if self.filter_text and not shown and source:
            self.view.empty_text = t('filter.none', text=self.filter_text)
            self.view.redraw()
        self.update_status()

    def reload(self, user: bool = False) -> None:
        if self.mode == 'search':
            if user and self.search is not None:
                self.start_search(self.search.text)
            return
        self.load(select=None)
        if user:
            self.app.glitch.now(self.view_glitch_target())

    def view_glitch_target(self):
        return self.window.strip

    def _watch(self) -> None:
        self.app.bridge.unwatch(self.watch_id)
        self.watch_id = 0
        if self.mode == 'folder' and not is_remote(self.path):    # a server tells no one
            self.watch_id = self.app.bridge.watch(self.path, self._changed)
        elif self.mode == 'trash':
            self.watch_id = self.app.bridge.watch(os.path.join(trash_mod.home_trash(), 'files'),
                                                  self._changed)

    def _changed(self, event: str, path: Optional[str], other: Optional[str]) -> None:
        if event in ('deleted',) and path == self.path:
            self.load(reset=True)
            return
        if self._reload_id is None:
            # changes come in bursts (a copy writes many files): reload once per burst
            self._reload_id = self.after(250, self._reload_now)

    def _reload_now(self) -> None:
        self._reload_id = None
        if self.mode != 'search':
            self.load()

    def close(self) -> None:
        self.app.bridge.unwatch(self.watch_id)
        self.watch_id = 0
        if self.search is not None:
            self.search.cancel()

    # ─── sorting, filtering ──────────────────────────────────

    def sort_key(self) -> str:
        return self.app.settings['sort']

    def sort_reverse(self) -> bool:
        return self.app.settings['sort_reverse']

    def set_sort(self, key: str) -> None:
        s = self.app.settings
        if s['sort'] == key:
            s['sort_reverse'] = not s['sort_reverse']
        else:
            s['sort'] = key
            s['sort_reverse'] = key in ('modified', 'size')     # newest and biggest first
        self.app.settings_changed(resort=True)

    def _filter_changed(self, _e=None) -> None:
        text = self.filter.get()
        if text != self.filter_text:
            self.filter_text = text
            self.apply()
        self._paint_hint()

    def _filter_enter(self, _e=None) -> str:
        if self.window.search_mode_requested(self):
            self.start_search(self.filter.get())
            return 'break'
        if self.view.entries:
            self.view.canvas.focus_set()
            self.view.move_cursor(0)
            if len(self.view.entries) == 1:
                self.open_entries(self.view.entries)
        return 'break'

    def _paint_hint(self) -> None:
        empty = not self.filter.get()
        hint = t('search.hint') if self.window.searching(self) else t('filter.hint')
        self.filter_hint.configure(text=hint)
        if empty and self.focus_get() is not self.filter:
            self.filter_hint.place(in_=self.filter, x=self.app.px(6), rely=0.5, anchor='w')
        else:
            self.filter_hint.place_forget()

    def type_to_filter(self, char: str) -> None:
        self.filter.focus_set()
        self.filter.insert('end', char)
        self._filter_changed()

    def focus_filter(self, search: bool = False) -> None:
        self.filter.focus_set()
        self.filter.selection_range(0, 'end')
        self._paint_hint()

    def escape(self) -> None:
        if self.view.renaming:
            self.view.cancel_rename()
        elif self.filter.get():
            self.filter.delete(0, 'end')
            self._filter_changed()
            self.view.canvas.focus_set()
        elif self.mode == 'search':
            self.stop_search(reload=True)
        elif self.window.searching(self):
            self.window.end_search_prompt(self)
            self.view.canvas.focus_set()
        elif self.view.selected:
            self.view.clear_selection()
        else:
            self.view.canvas.focus_set()

    # ─── search below this folder ────────────────────────────

    def start_search(self, text: str) -> None:
        text = text.strip()
        if not text or self.mode == 'trash':
            return
        if self.search is not None:
            self.search.cancel()
        root = self.path
        self.mode = 'search'
        self.search_results = []
        self.filter_text = ''
        self.filter.delete(0, 'end')
        self.window.end_search_prompt(self)
        self.view.show_folder_column = True
        self.view.search_root = root
        self.view.where_fn = None
        self.view.empty_text = t('search.running')
        self.search = Search(root, text, self.app.settings['show_hidden'], self._search_batch,
                             self._search_done).start()
        self.pathbar.set_path(root)
        self._nav_buttons()
        self.view.set_entries([], reset=True)
        self.window.pane_moved(self)
        self.update_status()
        self.view.canvas.focus_set()

    def _search_batch(self, search: Search, batch: List[Entry]) -> None:
        def add():
            if search is not self.search:
                return
            self.search_results.extend(batch)
            if self._search_flush is None:
                self._search_flush = self.after(120, self._flush_search)
        self.app.bridge.post(add)

    def _flush_search(self) -> None:
        self._search_flush = None
        if self.mode == 'search':
            self.apply()

    def _search_done(self, search: Search) -> None:
        def done():
            if search is not self.search:
                return
            self.view.empty_text = t('search.none', text=search.text)
            self.apply()
            self.app.glitch.now(self.window.strip)
        self.app.bridge.post(done)

    def stop_search(self, reload: bool = False) -> None:
        if self.search is not None:
            self.search.cancel()
            self.search = None
        if self.mode == 'search':
            self.mode = 'folder'
            self.view.show_folder_column = False
            self.view.search_root = ''
            self.search_results = []
            self._nav_buttons()
            if reload:
                self.pathbar.set_path(self.path)
                self.load(reset=True)
                self.window.pane_moved(self)

    # ─── the Trash ───────────────────────────────────────────

    def _trash_where(self, e: Entry) -> str:
        original = self.trash_info.get(e.path, ('', ''))[0]
        return home_short(os.path.dirname(original)) if original else '?'

    def _trash_bar(self) -> None:
        if self.mode == 'trash' and self.trash_bar is None:
            px = self.app.px
            bar = tk.Frame(self, bg=T["panel"])
            from .widgets import WolkButton
            tk.Label(bar, text=t('trash.bar'), font=self.app.font(9, False), bg=T["panel"],
                     fg=T["muted"], padx=px(8)).pack(side='left', pady=px(4))
            WolkButton(bar, t('trash.empty'), self.app.empty_trash, self.app.font(9, True),
                       variant='danger', padx=px(10), pady=px(3)).pack(side='right',
                                                                        padx=px(6),
                                                                        pady=px(4))
            WolkButton(bar, t('trash.restore'), lambda: self.app.restore(self),
                       self.app.font(9, True), padx=px(10), pady=px(3)).pack(side='right',
                                                                              pady=px(4))
            bar.pack(fill='x', before=self.view)
            self.trash_bar = bar
        elif self.mode != 'trash' and self.trash_bar is not None:
            self.trash_bar.destroy()
            self.trash_bar = None

    # ─── actions the view asks for ───────────────────────────

    def open_entries(self, entries: List[Entry]) -> None:
        folders = [e for e in entries if e.is_dir]
        files = [e for e in entries if not e.is_dir]
        if self.mode == 'trash':
            self.flash(t('trash.cant_open'), error=True)
            return
        if len(folders) == 1 and not files:
            self.go(folders[0].path)
            return
        for e in folders:
            self.window.new_tab(e.path, select=False)
        if files and getattr(self.window, 'picking', False):
            self.window.pick([e.path for e in files])             # the portal's file chooser
        elif files:
            self.app.open_files([e.path for e in files], self)

    def context_menu(self, event, entries: List[Entry]) -> None:
        self.app.context_menu(self, event, entries)

    def selection_changed(self) -> None:
        self.update_status()
        self.window.selection_changed(self)

    def hovered(self, entry: Optional[Entry]) -> None:
        pass

    def focused(self) -> None:
        self.window.set_active(self)

    def rename_one(self, path: str, new_name: str) -> None:
        self.app.rename(self, path, new_name)

    # ─── status line ─────────────────────────────────────────

    def update_status(self) -> None:
        if self.message:
            return
        v = self.view
        n = len(v.entries)
        if self.mode == 'search':
            s = self.search
            if s is not None and not s.done:
                text = t('search.status_running', n=len(self.search_results),
                         folders=s.scanned_dirs)
            else:
                text = t('search.status_done', n=n)
                if s is not None and s.limited:
                    text += ' ' + t('search.limited')
        else:
            text = t('status.items', n=n)
            hidden = len(self.all_entries) - n if not self.filter_text else 0
            if hidden > 0 and not self.app.settings['show_hidden']:
                text += ' ' + t('status.hidden', n=hidden)
        chosen = v.selected_entries() if v.selected else []
        if chosen:
            size = sum(e.size for e in chosen if not e.is_dir)
            dirs = sum(1 for e in chosen if e.is_dir)
            part = t('status.selected', n=len(chosen))
            if size or len(chosen) > dirs:
                part += f" ({human_size(size)})"
            text += ' · ' + part
            if len(chosen) == 1 and self.mode == 'trash':
                original = self.trash_info.get(chosen[0].path, ('', ''))[0]
                if original:
                    text += ' · ' + t('trash.from', path=home_short(original))
        self.status_left.configure(text=text, fg=T["muted"])
        self.status_right.configure(text=self.free)

    def flash(self, text: str, error: bool = False, ms: int = 5000) -> None:
        """A message in the status line for a few seconds; errors in pink, and they tear."""
        self.message = text
        self.status_left.configure(text=text, fg=T["pink"] if error else T["accent"])
        if error:
            self.app.glitch.now(self.window.title_text, self.window.strip, strong=True)
        if self._message_id:
            self.after_cancel(self._message_id)

        def clear():
            self._message_id = None
            self.message = ''
            self.update_status()
        self._message_id = self.after(ms, clear)

    def set_active(self, on: bool) -> None:
        self.active = on
        self.pathbar.configure(highlightbackground=T["line2"] if on else T["line"])
