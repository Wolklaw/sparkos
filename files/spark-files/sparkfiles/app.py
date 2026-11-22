"""The Spark Files process: one per session, with any number of windows. It owns the settings,
the jobs, the clipboard, the thumbnails and the GIO bridge, and does what menus and keys ask
for (open, copy, paste, rename, trash...)."""

import collections
import os
import re
import shutil
import subprocess
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import quote, unquote, urlparse

import tkinter as tk
import tkinter.font as tkfont

from . import APP_CLASS, APP_NAME, APP_SLUG, SERVICE_IDLE_MS, VERSION, core, gloop
from . import servicemenus, thumbs, trash as trash_mod
from .core import home, log
from .dnd import DragController
from .icons import Icons, to_photo
from .jobs import ClashDialog, show_errors
from .listing import Entry
from .ops import Job, name_problem, new_file, new_folder, rename
from .places import TRASH
from .text import t
from .ui import Dialog, Tooltip, ask, ask_text, menu, style_ttk
from .widgets import MONO_FAMILIES, T, Glitch

URI_SAFE = "/!$&'()*+,;=:@~-._"


def detect_scale(root: tk.Tk) -> float:
    """UI scale. Tk ignores the desktop's scaling on Linux, but Plasma publishes it to X
    programs as Xft.dpi, so read that."""
    forced = os.environ.get('SPARK_FILES_SCALE')
    if forced:
        try:
            return max(0.5, min(4.0, float(forced)))
        except ValueError:
            pass
    try:
        value = root.tk.call('option', 'get', root, 'dpi', 'Dpi')     # often empty
        if value:
            return max(1.0, min(4.0, float(value) / 96))
    except (tk.TclError, ValueError):
        pass
    if shutil.which('xrdb'):
        try:
            out = subprocess.run(['xrdb', '-query'], capture_output=True, text=True,
                                 timeout=3).stdout
            m = re.search(r'^Xft\.dpi:\s*([0-9.]+)', out, re.M)
            if m:
                return max(1.0, min(4.0, float(m.group(1)) / 96))
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    try:
        return max(1.0, min(4.0, root.winfo_fpixels('1i') / 96))
    except tk.TclError:
        return 1.0


def pick_mono_cached(root: tk.Tk) -> str:
    path = os.path.join(core.cache_dir(), 'font')
    try:
        with open(path, encoding='utf-8') as f:
            name = f.read().strip()
        if name and tkfont.Font(root, family=name).actual('family') == name:
            return name
    except OSError:
        pass
    families = {n.lower(): n for n in tkfont.families(root)}
    name = next((families[w.lower()] for w in MONO_FAMILIES if w.lower() in families),
                'TkFixedFont')
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(name)
    except OSError:
        pass
    return name


def load_icon(root: tk.Misc) -> Optional[tk.PhotoImage]:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in (f'{APP_SLUG}-64.png', f'{APP_SLUG}-256.png'):
        path = os.path.join(here, 'icons', name)
        if os.path.isfile(path):
            try:
                return tk.PhotoImage(master=root, file=path)
            except tk.TclError:
                pass
    return None


def path_to_uri(path: str) -> str:
    return 'file://' + quote(path, safe=URI_SAFE)


def uri_to_path(uri: str) -> Optional[str]:
    if uri.startswith('file://'):
        parsed = urlparse(uri)
        if parsed.netloc not in ('', 'localhost'):
            return None
        return unquote(parsed.path)
    if uri.startswith('trash:'):
        return TRASH
    if uri.startswith('/'):
        return uri
    if '://' in uri:
        return None
    return os.path.abspath(uri)


def terminal_command(folder: str) -> Optional[List[str]]:
    """Spark Terminal when it's there; then Konsole (kept for one release); then whatever
    the desktop says is the terminal."""
    if shutil.which('spark-terminal'):
        return ['spark-terminal', '--workdir', folder]
    if shutil.which('konsole'):
        return ['konsole', '--workdir', folder]
    for name in ('xdg-terminal-exec', 'x-terminal-emulator', 'gnome-terminal', 'xterm'):
        if shutil.which(name):
            return [name]
    return None


class App:
    def __init__(self, service: bool = False, bench: bool = False):
        self.service, self.bench = service, bench
        self.root = tk.Tk(className=APP_CLASS)
        self.root.withdraw()
        self.root.report_callback_exception = self._on_tk_error
        self.scale = detect_scale(self.root)
        try:
            self.root.tk.call('tk', 'scaling', self.scale * 96 / 72)
        except tk.TclError:
            pass
        self.mono = pick_mono_cached(self.root)
        self._fonts: Dict[Tuple[int, bool], tkfont.Font] = {}
        self.settings = core.load_settings()
        self.glitch = Glitch(self.root, enabled=not (bench or core.reduced_motion())
                             and self.settings['glitch'])
        style_ttk(self.root)
        icon = load_icon(self.root)
        if icon is not None:
            self.root.iconphoto(True, icon)
            self._icon = icon
        self.icons = Icons(self.root)
        self.tooltip = Tooltip(self.root, self.font(9, False))
        self.windows: list = []
        self.closed_tabs: List[str] = []
        self.jobs: List[Job] = []
        self.undo_stack: List[dict] = []
        self.cut: set = set()
        self.drop_labels: Dict[str, str] = {}
        self._save_id: Optional[str] = None
        self._menus: Optional[list] = None
        self._menus_time = 0.0
        self.volumes: List[dict] = []
        self._quitting = False

        self.view_var = tk.StringVar(self.root)
        self.sort_var = tk.StringVar(self.root)
        self.reverse_var = tk.BooleanVar(self.root)
        self.folders_first_var = tk.BooleanVar(self.root)
        self.hidden_var = tk.BooleanVar(self.root)
        self.thumbs_var = tk.BooleanVar(self.root)
        self.sidebar_var = tk.BooleanVar(self.root)
        self.preview_var = tk.BooleanVar(self.root)
        self.glitch_var = tk.BooleanVar(self.root)
        self.sync_vars()

        # thumbnails: Pillow images from the workers, Tk images per size made on demand
        self._thumb_src: 'collections.OrderedDict[str, tuple]' = collections.OrderedDict()
        self._thumb_tk: 'collections.OrderedDict[tuple, object]' = collections.OrderedDict()
        self._big_waiting: Dict[str, List[Tuple[int, Callable]]] = {}
        self.thumbnailer = thumbs.Thumbnailer(self._thumb_ready) if thumbs.Image else None

        self.bridge = gloop.Bridge(self.root, self.on_request, self.mounts_changed)
        self.dnd = DragController(self)
        from .xdnd import XDnd
        self.xdnd = XDnd(self.root, self._xdnd_over, self._xdnd_leave, self._xdnd_drop)
        self._xdnd_target = None
        if service:
            self.root.after(SERVICE_IDLE_MS, self._service_idle)

    # ─── look helpers ────────────────────────────────────────

    def px(self, n: float) -> int:
        return max(1, round(n * self.scale))

    def font(self, size: int, bold: bool = True) -> tkfont.Font:
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(self.root, family=self.mono, size=size,
                                           weight='bold' if bold else 'normal')
        return self._fonts[key]

    def _on_tk_error(self, exc, value, tb) -> None:
        import traceback
        log.error("unexpected error: %s", ''.join(traceback.format_exception(exc, value, tb)))
        w = self.focus_window()
        if w is not None:
            w.active.flash(t('error.unexpected', why=str(value)[:120]), error=True)

    def run(self) -> None:
        self.root.mainloop()

    # ─── windows ─────────────────────────────────────────────

    def new_window(self, path: Optional[str] = None, paths: Optional[List[str]] = None,
                   select: Optional[List[str]] = None):
        from .window import Window
        targets = paths or [path or home()]
        w = Window(self, targets, select=select)
        self.windows.append(w)
        w.deiconify()
        w.lift()
        self.glitch.add(w.title_text, w.mark, w.strip)
        self.root.after(200, lambda: self._after_map(w))
        return w

    def _after_map(self, w) -> None:
        if w.winfo_exists():
            self.xdnd.register(w)
            try:
                w.focus_force()
            except tk.TclError:
                pass
            w.active.view.canvas.focus_set()

    def window_closed(self, w) -> None:
        if w in self.windows:
            self.windows.remove(w)
            self.xdnd.unregister(w)
        if not self.windows:
            self.quit()

    def window_focused(self, w) -> None:
        if w in self.windows:
            self.windows.remove(w)
            self.windows.append(w)               # most recent last

    def focus_window(self):
        return self.windows[-1] if self.windows else None

    def quit(self) -> None:
        if self._quitting:
            return
        running = [j for j in self.jobs if j.active]
        if running:
            # keep going until the jobs finish; a hidden process with no window
            self._quitting_after_jobs = True
            self.root.after(500, self._quit_when_done)
            return
        self._quitting = True
        self.save_settings_now()
        self.shutdown()

    def shutdown(self) -> None:
        """Stop the threads and timers and close the window system connection."""
        if self.thumbnailer:
            self.thumbnailer.stop()
        try:
            self.xdnd.close()
        except Exception:                        # noqa: BLE001
            pass
        self.bridge.close()
        try:
            for pending in self.root.tk.splitlist(self.root.tk.call('after', 'info')):
                self.root.after_cancel(pending)
        except tk.TclError:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _quit_when_done(self) -> None:
        if self.windows:
            return
        if any(j.active for j in self.jobs):
            self.root.after(500, self._quit_when_done)
            return
        self.quit()

    def _service_idle(self) -> None:
        if not self.windows:
            log.info("started for D-Bus, but nothing was asked: quitting")
            self.quit()

    def on_request(self, mode: str, uris: List[str]) -> None:
        """From D-Bus: another spark-files, or "Show in folder" in another app."""
        paths = [p for p in (uri_to_path(u) for u in uris) if p]
        log.info("asked to %s: %s", mode, ' '.join(paths)[:500])
        if mode == 'properties':
            w = self.focus_window() or self.new_window(os.path.dirname(paths[0]) if paths
                                                       else home())
            if paths:
                self.properties(w, paths)
            return
        if mode == 'show-items':
            groups: Dict[str, List[str]] = {}
            for p in paths:
                groups.setdefault(os.path.dirname(p.rstrip('/')) or '/', []).append(p)
            if not groups:
                groups = {home(): []}
            w = self.new_window(paths=list(groups), select=[p for g in groups.values()
                                                            for p in g])
            self._raise(w)
            self.root.after(500, lambda: log.info("showing %s with %s selected", w.active.path,
                                                  ' '.join(sorted(w.active.view.selected))))
            return
        folders, files = [], []
        for p in paths:
            if p == TRASH or os.path.isdir(p):
                folders.append(p)
            elif os.path.exists(p):
                files.append(p)
        if files and not folders:
            folders = sorted({os.path.dirname(f) for f in files})
        if mode == 'tab' and self.windows:
            w = self.focus_window()
            for f in folders or [home()]:
                w.new_tab(f, select=True, select_items=files or None)
        else:
            w = self.new_window(paths=folders or [home()], select=files or None)
        self._raise(w)

    def _raise(self, w) -> None:
        try:
            w.deiconify()
            w.lift()
            w.focus_force()
        except tk.TclError:
            pass

    # ─── settings ────────────────────────────────────────────

    def sync_vars(self) -> None:
        s = self.settings
        self.view_var.set(s['view'])
        self.sort_var.set(s['sort'])
        self.reverse_var.set(s['sort_reverse'])
        self.folders_first_var.set(s['folders_first'])
        self.hidden_var.set(s['show_hidden'])
        self.thumbs_var.set(s['thumbnails'])
        self.sidebar_var.set(s['sidebar'])
        self.preview_var.set(s['preview'])
        self.glitch_var.set(s['glitch'])

    def set_setting(self, key: str, value) -> None:
        self.settings[key] = value
        if key == 'glitch':
            self.glitch.enabled = bool(value) and not core.reduced_motion()
        self.settings_changed(resort=True)

    def set_sort_key(self, key: str) -> None:
        self.settings['sort'] = key
        self.settings_changed(resort=True)

    def settings_changed(self, resort: bool = False) -> None:
        self.sync_vars()
        for w in self.windows:
            w.apply_settings()
            for tab in w.tabs:
                for p in tab.panes:
                    p.view.set_mode(self.settings['view'])
                    if resort:
                        p.apply()
                    else:
                        p.view.redraw()
            w.b_hidden.set_icon('eye')
        if self._save_id:
            self.root.after_cancel(self._save_id)
        self._save_id = self.root.after(800, self.save_settings_now)

    def save_settings_now(self) -> None:
        self._save_id = None
        core.save_settings(self.settings)

    def toggle_hidden(self) -> None:
        self.settings['show_hidden'] = not self.settings['show_hidden']
        self.settings_changed(resort=True)
        w = self.focus_window()
        if w:
            w.active.flash(t('status.hidden_on') if self.settings['show_hidden']
                           else t('status.hidden_off'), ms=2000)

    def toggle_view(self) -> None:
        self.set_view('grid' if self.settings['view'] == 'list' else 'list')

    def set_view(self, view: str) -> None:
        self.settings['view'] = view
        self.settings_changed()

    def zoom(self, step: int) -> None:
        z = self.settings['zoom']
        z = 1.0 if step == 0 else max(0.6, min(2.5, round(z * (1.15 if step > 0 else 1 / 1.15),
                                                          2)))
        self.settings['zoom'] = z
        if self.settings['view'] != 'grid' and step:
            self.settings['view'] = 'grid'
        self.settings_changed()

    # ─── thumbnails ──────────────────────────────────────────

    def thumb_for(self, e: Entry, box: int):
        if self.thumbnailer is None or not thumbs.can_thumbnail(e.ext):
            return None
        key = (e.path, e.mtime, box)
        photo = self._thumb_tk.get(key)
        if photo is not None:
            self._thumb_tk.move_to_end(key)
            return photo
        src = self._thumb_src.get(e.path)
        if src is not None and src[0] == e.mtime:
            image = src[1].copy()
            image.thumbnail((box, box))
            photo = to_photo(self.root, image)
            self._thumb_tk[key] = photo
            while len(self._thumb_tk) > 1500:
                self._thumb_tk.popitem(last=False)
            return photo
        flavour = 'normal' if box <= 128 else 'large'
        self.thumbnailer.request(e.path, e.ext, e.mtime, e.size, flavour)
        return None

    def _thumb_ready(self, path: str, mtime: float, image) -> None:
        def store():
            old = self._thumb_src.get(path)
            if old is None or old[1].width < image.width or old[0] != mtime:
                self._thumb_src[path] = (mtime, image)
            while len(self._thumb_src) > 2000:
                self._thumb_src.popitem(last=False)
            for size, cb in self._big_waiting.pop(path, []):
                img = image.copy()
                img.thumbnail((size, size))
                cb(to_photo(self.root, img))
            folder = os.path.dirname(path)
            for w in self.windows:
                for p in w.tab.panes if w.tab else []:
                    if path in p.view.index and (p.path == folder or p.mode == 'search'):
                        p.view.redraw()
        self.bridge.post(store)

    def big_thumb(self, e: Entry, size: int, cb: Callable) -> None:
        if self.thumbnailer is None or not thumbs.can_thumbnail(e.ext):
            return
        src = self._thumb_src.get(e.path)
        if src is not None and src[0] == e.mtime and src[1].width >= min(size, 200):
            img = src[1].copy()
            img.thumbnail((size, size))
            cb(to_photo(self.root, img))
            return
        self._big_waiting.setdefault(e.path, []).append((size, cb))
        self.thumbnailer.request(e.path, e.ext, e.mtime, e.size, 'large')

    # ─── opening ─────────────────────────────────────────────

    def open_files(self, paths: List[str], pane) -> None:
        groups: Dict[str, Tuple[object, List[str]]] = {}
        missing = []
        for p in paths:
            mime = gloop.content_type(p, False, sniff=not os.path.splitext(p)[1])
            app = gloop.default_app(mime)
            if app is None:
                missing.append(p)
                continue
            groups.setdefault(app.id, (app, []))[1].append(p)
        for app, files in groups.values():
            why = gloop.launch(app, files)
            if why:
                pane.flash(t('error.open_failed', why=why), error=True)
            else:
                pane.flash(t('status.opening', name=os.path.basename(files[0]),
                             app=app.name), ms=2500)
        if missing:
            from .dialogs import OpenWith
            OpenWith(self, pane.window, missing).place_and_show()

    def open_with(self, pane, paths: List[str], app=None) -> None:
        if app is None:
            from .dialogs import OpenWith
            OpenWith(self, pane.window, paths).place_and_show()
            return
        why = gloop.launch(app, paths)
        if why:
            pane.flash(t('error.open_failed', why=why), error=True)

    def open_terminal(self, pane, folder: Optional[str] = None) -> None:
        folder = folder or pane.current_folder() or home()
        cmd = terminal_command(folder)
        if not cmd:
            pane.flash(t('error.no_terminal'), error=True)
            return
        try:
            subprocess.Popen(cmd, cwd=folder, stdin=subprocess.DEVNULL, start_new_session=True)
        except OSError as exc:
            pane.flash(t('error.open_failed', why=exc.strerror or str(exc)), error=True)

    # ─── clipboard ───────────────────────────────────────────

    def copy_selection(self, pane, cut: bool) -> None:
        paths = [e.path for e in pane.view.selected_entries()]
        if not paths or pane.mode == 'trash':
            return
        self.set_clipboard(paths, cut)
        pane.flash(t('status.cut' if cut else 'status.copied', n=len(paths)), ms=2500)
        self._refresh_cut()

    def set_clipboard(self, paths: List[str], cut: bool) -> None:
        uris = [path_to_uri(p) for p in paths]
        r = self.root
        r.clipboard_clear()
        r.tk.call('clipboard', 'append', '-type', 'text/uri-list', '--',
                  ''.join(u + '\r\n' for u in uris))
        r.tk.call('clipboard', 'append', '-type', 'x-special/gnome-copied-files', '--',
                  ('cut' if cut else 'copy') + '\n' + '\n'.join(uris))
        r.tk.call('clipboard', 'append', '-type', 'application/x-kde-cutselection', '--',
                  '1' if cut else '0')
        r.tk.call('clipboard', 'append', '--', '\n'.join(paths))
        self.cut = set(paths) if cut else set()

    def read_clipboard(self) -> Tuple[List[str], bool]:
        """(paths, cut) from whatever app put files on the clipboard."""
        r = self.root

        def get(kind: str) -> Optional[str]:
            try:
                return str(r.tk.call('clipboard', 'get', '-type', kind))
            except tk.TclError:
                return None
        cut = False
        paths: List[str] = []
        gnome = get('x-special/gnome-copied-files')
        if gnome:
            lines = gnome.replace('\r', '').split('\n')
            cut = lines[0].strip() == 'cut'
            paths = [p for p in (uri_to_path(u) for u in lines[1:] if u.strip()) if p]
        if not paths:
            uris = get('text/uri-list')
            if uris:
                from .xdnd import uris_to_paths
                paths = uris_to_paths(uris)
                kde = get('application/x-kde-cutselection')
                cut = bool(kde and kde.strip().startswith('1'))
        if not paths:
            text = get('UTF8_STRING') or get('STRING') or ''
            lines = [ln.strip() for ln in text.split('\n') if ln.strip()]
            if lines and all(ln.startswith(('/', 'file://')) for ln in lines):
                candidates = [uri_to_path(ln) for ln in lines]
                paths = [p for p in candidates if p and os.path.exists(p)]
        return paths, cut

    def cut_paths(self) -> set:
        if not self.cut:
            return set()
        paths, cut = self.read_clipboard()
        if not cut or set(paths) != self.cut:
            self.cut = set()                     # someone copied something else since
        return self.cut

    def _refresh_cut(self) -> None:
        cut = self.cut_paths()
        for w in self.windows:
            for tab in w.tabs:
                for p in tab.panes:
                    p.view.cut = cut
                    p.view.redraw()

    def paste(self, pane, into: Optional[str] = None) -> None:
        dest = into or pane.current_folder()
        if not dest:
            pane.flash(t('error.cant_paste_here'), error=True)
            return
        paths, cut = self.read_clipboard()
        if not paths:
            pane.flash(t('status.clipboard_empty'), error=True)
            return
        self.start_job('move' if cut else 'copy', paths, dest, pane)
        if cut:
            self.root.clipboard_clear()
            self.cut = set()

    def copy_paths(self, pane) -> None:
        chosen = pane.view.selected_entries()
        paths = [e.path for e in chosen] or ([pane.current_folder()] if pane.current_folder()
                                             else [])
        if not paths:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append('\n'.join(paths))
        pane.flash(t('status.path_copied', n=len(paths)), ms=2500)

    # ─── jobs ────────────────────────────────────────────────

    def start_job(self, kind: str, sources: List[str], dest: Optional[str], pane,
                  then: Optional[Callable[[Job], None]] = None) -> Job:
        window = pane.window

        def ask(job, src, target):
            self.bridge.post(lambda: self._clash(window, job, src, target))

        def done(job):
            self.bridge.post(lambda: self._job_done(job, pane, window, then))

        job = Job(kind, sources, dest, ask=ask, on_done=done)
        self.jobs.append(job)
        # show the panel only when it takes a moment; quick jobs just finish
        if window.winfo_exists():
            self.root.after(400, lambda: window.jobs.add(job) if job.active and
                            window.winfo_exists() else None)
        job.start()
        return job

    def _clash(self, window, job: Job, src: str, target: str) -> None:
        parent = window if window.winfo_exists() else self.focus_window()
        if parent is None:
            job.answer('skip', True)
            return
        if job.active and id(job) not in parent.jobs.rows:
            parent.jobs.add(job)
        d = ClashDialog(self, parent, job, src, target)
        d.place_and_show()
        d.focus_first()

    def _job_done(self, job: Job, pane, window, then) -> None:
        if job in self.jobs:
            self.jobs.remove(job)
        if window.winfo_exists():
            window.jobs.remove(job)
        alive = pane.winfo_exists()
        target = pane if alive else (self.focus_window().active if self.focus_window() else None)
        if then is not None:
            then(job)
        if job.state == 'cancelled':
            if target:
                target.flash(t('job.cancelled'), ms=3000)
            return
        n = len(job.created)
        if target is not None:
            if job.kind in ('copy', 'move') and job.dest == target.current_folder() and n:
                target.load(select=job.created)
            if job.errors:
                show_errors(self, target.window, job)
            elif job.kind in ('copy', 'move'):
                target.flash(t(f'done.{job.kind}', n=n), ms=3000)
                self.glitch.now(target.window.strip)
        if job.kind == 'move' and job.pairs:
            self.undo_stack.append({'kind': 'move', 'pairs': [(new, old)
                                                              for old, new in job.pairs]})
        if job.kind == 'trash':
            if job.created:
                self.undo_stack.append({'kind': 'trash', 'items': list(job.created)})
            if target is not None and job.created:
                target.flash(t('done.trash', n=len(job.created)), ms=4000)
                self.glitch.now(target.window.strip)
            if job.untrashable and target is not None:
                self._offer_delete(target, job.untrashable)
            self._sidebars()
        if job.kind == 'restore':
            self._sidebars()
            if target is not None and job.created:
                target.flash(t('done.restore', n=len(job.created)), ms=3000)
        if job.kind == 'delete' and target is not None and not job.errors:
            target.flash(t('done.delete', n=len(job.sources)), ms=3000)
            self._sidebars()

    def _sidebars(self) -> None:
        for w in self.windows:
            w.sidebar.refresh()
            w.sidebar.highlight(w.active.path)

    # ─── file actions ────────────────────────────────────────

    def new_folder(self, pane) -> None:
        folder = pane.current_folder()
        if not folder:
            return
        from .ops import free_name
        initial = t('new.folder_name')
        if os.path.lexists(os.path.join(folder, initial)):
            initial = free_name(folder, initial, True)
        name = ask_text(self, pane.window, t('new.folder_title'), t('new.folder_prompt'),
                        initial, select_stem=False,
                        validate=lambda s: self._name_check(folder, s),
                        ok_label=t('new.create'), cancel_label=t('button.cancel'))
        if not name:
            return
        try:
            path = new_folder(folder, name)
        except OSError as exc:
            pane.flash(t('error.create_failed', why=exc.strerror or str(exc)), error=True)
            return
        self.undo_stack.append({'kind': 'new', 'path': path})
        pane.load(select=[path])

    def new_file(self, pane, template: Optional[str] = None) -> None:
        folder = pane.current_folder()
        if not folder:
            return
        from .ops import free_name
        initial = os.path.basename(template) if template else t('new.file_name')
        if os.path.lexists(os.path.join(folder, initial)):
            initial = free_name(folder, initial)
        name = ask_text(self, pane.window, t('new.file_title'), t('new.file_prompt'), initial,
                        validate=lambda s: self._name_check(folder, s),
                        ok_label=t('new.create'), cancel_label=t('button.cancel'))
        if not name:
            return
        try:
            if template:
                path = os.path.join(folder, name)
                if os.path.lexists(path):
                    raise FileExistsError(17, t('error.name_taken'))
                shutil.copyfile(template, path)
            else:
                path = new_file(folder, name)
        except OSError as exc:
            pane.flash(t('error.create_failed', why=exc.strerror or str(exc)), error=True)
            return
        self.undo_stack.append({'kind': 'new', 'path': path})
        pane.load(select=[path])

    def _name_check(self, folder: str, name: str) -> Optional[str]:
        problem = name_problem(name)
        if problem:
            return t(problem)
        if os.path.lexists(os.path.join(folder, name)):
            return t('error.name_taken')
        return None

    def templates(self) -> List[str]:
        from .places import user_dirs
        folder = user_dirs().get('TEMPLATES') or os.path.join(home(), 'Templates')
        try:
            return sorted(os.path.join(folder, n) for n in os.listdir(folder)
                          if os.path.isfile(os.path.join(folder, n)) and not n.startswith('.'))
        except OSError:
            return []

    def rename_selected(self, pane) -> None:
        chosen = pane.view.selected_entries()
        if not chosen or pane.mode == 'trash':
            return
        if len(chosen) == 1:
            pane.view.start_rename(chosen[0].path)
            return
        from .dialogs import BatchRename

        def done(paths, errors):
            pane.load(select=paths)
            if errors:
                pane.flash('; '.join(errors)[:200], error=True)
            else:
                pane.flash(t('done.rename', n=len(paths)), ms=3000)
        BatchRename(self, pane.window, [e.path for e in chosen], done).run()

    def rename(self, pane, path: str, new_name: str) -> None:
        try:
            new_path = rename(path, new_name)
        except ValueError as exc:
            pane.flash(t(str(exc)), error=True)
            return
        except FileExistsError:
            pane.flash(t('error.name_taken_named', name=new_name), error=True)
            return
        except OSError as exc:
            pane.flash(t('error.rename_failed', why=exc.strerror or str(exc)), error=True)
            return
        self.undo_stack.append({'kind': 'rename', 'path': new_path,
                                'old': os.path.basename(path)})
        pane.load(select=[new_path])
        self.glitch.now(pane.window.strip)

    def trash_selected(self, pane) -> None:
        chosen = [e.path for e in pane.view.selected_entries()]
        if not chosen:
            return
        if pane.mode == 'trash':
            self.delete_selected(pane)
            return
        if self.settings.get('confirm_trash'):
            key = ask(self, pane.window, t('trash.ask_title'), t('trash.ask', n=len(chosen)),
                      [('cancel', t('button.cancel'), 'ghost'),
                       ('trash', t('trash.do'), 'primary')], default='trash')
            if key != 'trash':
                return
        self._select_after_removal(pane, chosen)
        self.start_job('trash', chosen, None, pane)

    def _select_after_removal(self, pane, removed: List[str]) -> None:
        """Keep a cursor on the item after the removed ones, like other file managers."""
        v = pane.view
        gone = set(removed)
        idx = [v.index[p] for p in removed if p in v.index]
        if not idx:
            return
        after = [e.path for e in v.entries[max(idx) + 1:] if e.path not in gone]
        before = [e.path for e in v.entries[:min(idx)] if e.path not in gone]
        nxt = after[:1] or before[-1:]
        if nxt:
            pane.after(350, lambda: v.select_paths(nxt) if nxt[0] in v.index else None)

    def delete_selected(self, pane) -> None:
        chosen = [e.path for e in pane.view.selected_entries()]
        if not chosen:
            return
        name = os.path.basename(chosen[0])
        message = t('delete.ask_one', name=name) if len(chosen) == 1 else \
            t('delete.ask', n=len(chosen))
        key = ask(self, pane.window, t('delete.title'), message,
                  [('cancel', t('button.cancel'), 'ghost'),
                   ('delete', t('delete.do'), 'danger')], default='cancel')
        if key != 'delete':
            return
        self._select_after_removal(pane, chosen)
        self.start_job('delete', chosen, None, pane)

    def _offer_delete(self, pane, paths: List[str]) -> None:
        key = ask(self, pane.window, t('trash.none_title'), t('trash.none', n=len(paths),
                                                              name=os.path.basename(paths[0])),
                  [('cancel', t('button.cancel'), 'ghost'),
                   ('delete', t('delete.do'), 'danger')], default='cancel')
        if key == 'delete':
            self.start_job('delete', paths, None, pane)

    def restore(self, pane) -> None:
        chosen = [e.path for e in pane.view.selected_entries()] if pane.mode == 'trash' else []
        if not chosen:
            pane.flash(t('trash.pick'), error=True)
            return
        self.start_job('restore', chosen, None, pane)

    def empty_trash(self) -> None:
        w = self.focus_window()
        if w is None:
            return
        n = trash_mod.count()
        if not n:
            w.active.flash(t('trash.already_empty'), ms=2500)
            return
        key = ask(self, w, t('trash.empty_title'), t('trash.empty_ask', n=n),
                  [('cancel', t('button.cancel'), 'ghost'),
                   ('empty', t('trash.empty'), 'danger')], default='cancel')
        if key != 'empty':
            return
        pane = w.active

        def work():
            errors = trash_mod.empty()
            self.bridge.post(lambda: done(errors))

        def done(errors):
            self._sidebars()
            for win in self.windows:
                for tab in win.tabs:
                    for p in tab.panes:
                        if p.mode == 'trash':
                            p.load(reset=True)
            if pane.winfo_exists():
                pane.flash(t('trash.emptied') if not errors else
                           t('trash.empty_errors', n=len(errors)), error=bool(errors))
        threading.Thread(target=work, daemon=True).start()

    def drop(self, paths: List[str], folder: str, action: str, pane=None) -> None:
        pane = pane or (self.focus_window().active if self.focus_window() else None)
        if pane is None:
            return
        if action == 'pin':
            for p in folder[4:].split('\n'):
                self.pin(p)
            return
        if action == 'trash':
            self.start_job('trash', paths, None, pane)
            return
        self.start_job(action, paths, folder, pane)

    def undo(self, pane) -> None:
        if not self.undo_stack:
            pane.flash(t('undo.nothing'), ms=2000)
            return
        step = self.undo_stack.pop()
        kind = step['kind']
        try:
            if kind == 'rename':
                new_path = rename(step['path'], step['old'])
                pane.load(select=[new_path])
                pane.flash(t('undo.rename'), ms=2500)
            elif kind == 'new':
                path = step['path']
                if os.path.isdir(path) and not os.listdir(path):
                    os.rmdir(path)
                elif os.path.isfile(path) and os.path.getsize(path) == 0:
                    os.unlink(path)
                else:
                    pane.flash(t('undo.not_empty'), error=True)
                    return
                pane.load()
                pane.flash(t('undo.new'), ms=2500)
            elif kind == 'trash':
                self.start_job('restore', step['items'], None, pane)
            elif kind == 'move':
                for new, old in reversed(step['pairs']):
                    if os.path.lexists(old):
                        raise FileExistsError(17, t('error.name_taken_named',
                                                    name=os.path.basename(old)))
                    os.makedirs(os.path.dirname(old), exist_ok=True)
                    try:
                        os.rename(new, old)
                    except OSError as exc:
                        if exc.errno != 18:
                            raise
                        self.start_job('move', [new], os.path.dirname(old), pane)
                pane.load()
                pane.flash(t('undo.move'), ms=2500)
        except OSError as exc:
            pane.flash(t('undo.failed', why=exc.strerror or str(exc)), error=True)

    def properties(self, window, paths: List[str]) -> None:
        paths = [p for p in paths if p and p != TRASH]
        if not paths:
            return
        from .dialogs import Properties
        Properties(self, window, paths).place_and_show()

    # ─── the sidebar's pins and drives ───────────────────────

    def pin(self, path: str) -> None:
        if path not in self.settings['pinned']:
            self.settings['pinned'].append(path)
            self.settings_changed()
            self._sidebars()

    def unpin(self, path: str) -> None:
        if path in self.settings['pinned']:
            self.settings['pinned'].remove(path)
            self.settings_changed()
            self._sidebars()

    def mounts_changed(self) -> None:
        self.volumes = self.bridge_volumes()
        self._sidebars()

    def bridge_volumes(self) -> List[dict]:
        return getattr(self.bridge, 'volumes', [])

    def unmounted_volumes(self):
        from .places import Place
        out = []
        for v in self.bridge_volumes():
            if not v.get('mounted') and v.get('can_mount'):
                out.append(Place(f"vol-{v['id']}", v['name'], '', 'usb', removable=True,
                                 unmounted=True, uuid=v['id']))
        return out

    def mount_volume(self, place, then: Callable[[str], None]) -> None:
        w = self.focus_window()

        def done(path, why):
            if path:
                self._sidebars()
                then(path)
            elif w:
                w.active.flash(t('error.mount_failed', why=why or '?'), error=True)
        self.bridge.mount(place.uuid, done)

    def eject(self, place, window) -> None:
        dev = place.device

        def work():
            why = ''
            if shutil.which('udisksctl') and dev.startswith('/dev/'):
                r = subprocess.run(['udisksctl', 'unmount', '-b', dev], capture_output=True,
                                   text=True)
                if r.returncode != 0:
                    why = (r.stderr or r.stdout).strip().split('\n')[-1]
                else:
                    subprocess.run(['udisksctl', 'power-off', '-b', dev], capture_output=True)
            else:
                r = subprocess.run(['gio', 'mount', '-e', place.path], capture_output=True,
                                   text=True)
                if r.returncode != 0:
                    why = (r.stderr or r.stdout).strip()
            self.bridge.post(lambda: finish(why))

        def finish(why):
            for w in self.windows:
                for tab in w.tabs:
                    for p in tab.panes:
                        if p.mode == 'folder' and (p.path == place.path or
                                                   p.path.startswith(place.path + '/')):
                            p.go(home())
            self._sidebars()
            if window.winfo_exists():
                if why:
                    window.active.flash(t('error.eject_failed', why=why), error=True)
                else:
                    window.active.flash(t('status.ejected', name=place.label), ms=4000)
        threading.Thread(target=work, daemon=True).start()

    def drive_label(self, path: str) -> Optional[Tuple[str, str]]:
        """('C:', '/var/mnt/c') for a path on a Windows drive; a USB stick's label."""
        m = re.match(r'^(/var/mnt/([a-z]))(/|$)', path)
        if m:
            return t('place.drive', letter=m.group(2).upper()), m.group(1)
        user = os.environ.get('USER') or os.path.basename(home())
        m = re.match(rf'^(/run/media/{re.escape(user)}/([^/]+))(/|$)', path)
        if m:
            return m.group(2), m.group(1)
        return None

    def place_name(self, folder: str) -> str:
        if folder == TRASH:
            return t('place.trash')
        if folder.startswith('pin:'):
            return t('side.pinned')
        if folder == home():
            return t('place.home')
        label = self.drive_label(folder)
        if label and label[1] == folder:
            return label[0]
        return os.path.basename(folder.rstrip('/')) or folder

    # ─── drop targets ────────────────────────────────────────

    def register_drop_label(self, widget, path: str) -> None:
        self.drop_labels[str(widget)] = path

    def drop_target_at(self, widget, x: int, y: int, dragged: List[str]):
        """(the widget that shows the drop, the folder it goes into) for a point."""
        from .sidebar import Sidebar
        from .view import FileView
        from .ui import TabStrip
        w = widget
        while w is not None:
            if isinstance(w, FileView):
                return w, w.drop_target_at(x, y, dragged)
            if isinstance(w, Sidebar):
                return w, w.drop_target_at(x, y, dragged)
            if isinstance(w, TabStrip):
                key = w.key_at(x, y)
                window = w.winfo_toplevel()
                tab = window.tab_by_key(key) if key is not None else None
                if tab is not None:
                    folder = tab.panes[tab.active].drop_folder()
                    return _TabDrop(w, key), folder
                return None, None
            path = self.drop_labels.get(str(w))
            if path:
                return _LabelDrop(w), path
            w = getattr(w, 'master', None)
        return None, None

    # XDND from other apps

    def _xdnd_over(self, x: int, y: int, action: str) -> bool:
        widget = self.root.winfo_containing(x, y)
        target_widget, folder = self.drop_target_at(widget, x, y, []) if widget else (None,
                                                                                       None)
        if target_widget is not self._xdnd_target and self._xdnd_target is not None:
            try:
                self._xdnd_target.clear_drop()
            except (AttributeError, tk.TclError):
                pass
        self._xdnd_target = target_widget
        self._xdnd_folder = folder
        return bool(folder) and not folder.startswith('pin:')

    def _xdnd_leave(self) -> None:
        if self._xdnd_target is not None:
            try:
                self._xdnd_target.clear_drop()
            except (AttributeError, tk.TclError):
                pass
        self._xdnd_target = None

    def _xdnd_drop(self, paths: List[str], action: str, x: int, y: int) -> None:
        widget = self.root.winfo_containing(x, y)
        _target, folder = self.drop_target_at(widget, x, y, paths) if widget else (None, None)
        self._xdnd_leave()
        if not folder or folder.startswith('pin:'):
            return
        pane = None
        top = widget.winfo_toplevel() if widget else None
        if top in self.windows:
            pane = top.active
        if folder == TRASH:
            self.drop(paths, folder, 'trash', pane)
        else:
            self.drop(paths, folder, 'move' if action == 'move' else 'copy', pane)

    # ─── menus ───────────────────────────────────────────────

    def service_menus(self):
        now = time.monotonic()
        if self._menus is None or now - self._menus_time > 30:
            self._menus = servicemenus.load()
            self._menus_time = now
        return self._menus

    def context_menu(self, pane, event, entries: List[Entry]) -> None:
        m = menu(pane, self.font(10, False))
        if pane.mode == 'trash':
            if entries:
                m.add_command(label=t('trash.restore'), command=lambda: self.restore(pane))
                m.add_command(label=t('delete.do'), accelerator='Shift+Del',
                              command=lambda: self.delete_selected(pane))
                m.add_separator()
            m.add_command(label=t('trash.empty'), command=self.empty_trash,
                          state='normal' if trash_mod.count() else 'disabled')
            m.tk_popup(event.x_root, event.y_root)
            return
        if entries:
            self._item_menu(m, pane, entries)
        else:
            self._background_menu(m, pane)
        m.tk_popup(event.x_root, event.y_root)

    def _item_menu(self, m: tk.Menu, pane, entries: List[Entry]) -> None:
        paths = [e.path for e in entries]
        folders = [e for e in entries if e.is_dir]
        files = [e for e in entries if not e.is_dir]
        if len(folders) == 1 and not files:
            m.add_command(label=t('menu.open'), command=lambda: pane.go(folders[0].path))
        else:
            m.add_command(label=t('menu.open'), command=lambda: pane.open_entries(entries))
        if folders:
            m.add_command(label=t('menu.open_tab'),
                          command=lambda: [pane.window.new_tab(f.path, select=False)
                                           for f in folders])
            m.add_command(label=t('menu.open_window'),
                          command=lambda: self.new_window(paths=[f.path for f in folders]))
        if files and len(folders) == 0:
            mime = gloop.content_type(files[0].path, False)
            same = all(gloop.content_type(f.path, False) == mime for f in files)
            sub = menu(m, self.font(10, False))
            apps = gloop.apps_for(mime) if same else []
            default = gloop.default_app(mime) if same else None
            for app in apps[:12]:
                label = app.name + ('  ' + t('openwith.default') if default and
                                    app.id == default.id else '')
                sub.add_command(label=label, command=lambda a=app: self.open_with(pane, paths, a))
            if apps:
                sub.add_separator()
            sub.add_command(label=t('menu.other_app'), command=lambda: self.open_with(pane, paths))
            m.add_cascade(label=t('menu.open_with'), menu=sub)
        if len(folders) == 1 and not files:
            m.add_command(label=t('menu.terminal_here'),
                          command=lambda: self.open_terminal(pane, folders[0].path))
        m.add_separator()
        m.add_command(label=t('menu.cut'), accelerator='Ctrl+X',
                      command=lambda: self.copy_selection(pane, True))
        m.add_command(label=t('menu.copy'), accelerator='Ctrl+C',
                      command=lambda: self.copy_selection(pane, False))
        if len(folders) == 1 and not files:
            has = bool(self.read_clipboard()[0])
            m.add_command(label=t('menu.paste_into'), state='normal' if has else 'disabled',
                          command=lambda: self.paste(pane, into=folders[0].path))
        m.add_command(label=t('menu.copy_path'), accelerator='Ctrl+Shift+C',
                      command=lambda: self.copy_paths(pane))
        other = pane.window.other_pane(pane)
        if other is not None and other.current_folder():
            dest = other.current_folder()
            m.add_command(label=t('menu.copy_to_other', where=self.place_name(dest)),
                          command=lambda: self.start_job('copy', paths, dest, pane))
            m.add_command(label=t('menu.move_to_other', where=self.place_name(dest)),
                          command=lambda: self.start_job('move', paths, dest, pane))
        m.add_separator()
        m.add_command(label=t('menu.rename') if len(entries) == 1 else
                      t('menu.rename_many', n=len(entries)), accelerator='F2',
                      command=lambda: self.rename_selected(pane))
        m.add_command(label=t('menu.trash'), accelerator='Del',
                      command=lambda: self.trash_selected(pane))
        m.add_command(label=t('menu.delete'), accelerator='Shift+Del',
                      command=lambda: self.delete_selected(pane))
        self._add_service_actions(m, pane, entries)
        if folders and not files:
            m.add_separator()
            if all(f.path in self.settings['pinned'] for f in folders):
                m.add_command(label=t('side.unpin'),
                              command=lambda: [self.unpin(f.path) for f in folders])
            else:
                m.add_command(label=t('side.pin'),
                              command=lambda: [self.pin(f.path) for f in folders])
        m.add_separator()
        m.add_command(label=t('menu.properties'), accelerator='Alt+Enter',
                      command=lambda: self.properties(pane.window, paths))

    def _add_service_actions(self, m: tk.Menu, pane, entries: List[Entry]) -> None:
        items = [(e.path, gloop.content_type(e.path, e.is_dir), e.is_dir) for e in entries]
        actions = servicemenus.actions_for(self.service_menus(), items)
        if not actions:
            return
        m.add_separator()
        subs: Dict[str, tk.Menu] = {}
        paths = [e.path for e in entries]
        cwd = pane.current_folder()
        for action in actions:
            target = m
            if action.submenu:
                if action.submenu not in subs:
                    subs[action.submenu] = menu(m, self.font(10, False))
                    m.add_cascade(label=action.submenu, menu=subs[action.submenu])
                target = subs[action.submenu]
            target.add_command(label=action.name,
                               command=lambda a=action: self._run_action(pane, a, paths, cwd))

    def _run_action(self, pane, action, paths, cwd) -> None:
        if not servicemenus.run(action, paths, cwd):
            pane.flash(t('error.action_failed', name=action.name), error=True)

    def _background_menu(self, m: tk.Menu, pane) -> None:
        if pane.mode == 'search':
            m.add_command(label=t('search.back'), command=lambda: pane.stop_search(reload=True))
            return
        folder = pane.current_folder()
        m.add_command(label=t('menu.new_folder'), accelerator='Ctrl+Shift+N',
                      command=lambda: self.new_folder(pane))
        new = menu(m, self.font(10, False))
        new.add_command(label=t('menu.empty_file'), command=lambda: self.new_file(pane))
        templates = self.templates()
        if templates:
            new.add_separator()
            for tpl in templates[:20]:
                new.add_command(label=os.path.basename(tpl),
                                command=lambda p=tpl: self.new_file(pane, p))
        m.add_cascade(label=t('menu.new_file'), menu=new)
        m.add_separator()
        has = bool(self.read_clipboard()[0])
        m.add_command(label=t('menu.paste'), accelerator='Ctrl+V',
                      state='normal' if has else 'disabled', command=lambda: self.paste(pane))
        m.add_command(label=t('menu.select_all'), accelerator='Ctrl+A',
                      command=pane.view.select_all)
        m.add_separator()
        m.add_command(label=t('menu.terminal_here'), accelerator='Shift+F4',
                      command=lambda: self.open_terminal(pane))
        m.add_command(label=t('menu.copy_path'), command=lambda: self.copy_paths(pane))
        sort = menu(m, self.font(10, False))
        for key in ('name', 'modified', 'size', 'type'):
            sort.add_radiobutton(label=t('sort.' + key), value=key, variable=self.sort_var,
                                 command=lambda k=key: self.set_sort_key(k))
        sort.add_checkbutton(label=t('sort.reverse'), variable=self.reverse_var,
                             command=lambda: self.set_setting('sort_reverse',
                                                              self.reverse_var.get()))
        self.sync_vars()
        m.add_separator()
        m.add_cascade(label=t('menu.sort'), menu=sort)
        m.add_checkbutton(label=t('menu.hidden'), accelerator='Ctrl+H',
                          variable=self.hidden_var, command=self.toggle_hidden)
        if folder:
            fake = [Entry(os.path.basename(folder), folder, True, 0, 0, 0o755)]
            self._add_service_actions(m, pane, fake)
            m.add_separator()
            if folder in self.settings['pinned']:
                m.add_command(label=t('side.unpin'), command=lambda: self.unpin(folder))
            else:
                m.add_command(label=t('side.pin'), command=lambda: self.pin(folder))
            m.add_command(label=t('menu.properties'),
                          command=lambda: self.properties(pane.window, [folder]))

    # ─── small dialogs ───────────────────────────────────────

    def message(self, window, text: str, error: bool = False) -> None:
        if window is not None and hasattr(window, 'active'):
            window.active.flash(text, error=error)

    def about(self, window) -> None:
        d = Dialog(self, window, APP_NAME)
        tk.Label(d.content, text=t('about.text', version=VERSION), font=self.font(10, False),
                 bg=T["panel"], fg=T["text"], justify='left', anchor='w',
                 wraplength=self.px(440)).pack(anchor='w')
        d.button(t('button.close'), d.cancel, 'primary')
        d.place_and_show()

    def show_shortcuts(self, window) -> None:
        d = Dialog(self, window, t('menu.shortcuts'))
        grid = tk.Frame(d.content, bg=T["panel"])
        grid.pack()
        rows = t('shortcuts.list').split('\n')
        for i, row in enumerate(rows):
            keys, _, what = row.partition('|')
            tk.Label(grid, text=keys, font=self.font(9, True), bg=T["panel"], fg=T["accent"],
                     anchor='w').grid(row=i, column=0, sticky='w', padx=(0, self.px(16)))
            tk.Label(grid, text=what, font=self.font(9, False), bg=T["panel"], fg=T["text"],
                     anchor='w').grid(row=i, column=1, sticky='w')
        d.button(t('button.close'), d.cancel, 'primary')
        d.place_and_show()


class _TabDrop:
    """Highlights a tab while something is dragged over it."""

    def __init__(self, strip, key):
        self.strip, self.key = strip, key
        strip.drop_target = key
        strip.paint()

    def clear_drop(self) -> None:
        self.strip.drop_target = None
        self.strip.paint()


class _LabelDrop:
    def __init__(self, label):
        self.label = label
        try:
            label.configure(fg=T["ch_b"])
        except tk.TclError:
            pass

    def clear_drop(self) -> None:
        try:
            self.label.configure(fg=T["muted"])
        except tk.TclError:
            pass


def bench(folder: Optional[str], age: Callable[[], float]) -> int:
    """--bench: open a window on a folder, wait until its files are drawn, print the times."""
    app = App(bench=True)
    start = time.monotonic()
    folder = folder or home()
    w = app.new_window(folder)
    result = {}

    def check():
        p = w.active
        if p._loading_since == 0.0 and (p.view.entries or p.error or not p.all_entries):
            app.root.update_idletasks()
            result['shown'] = time.monotonic() - start
            result['n'] = len(p.view.entries)
            t0 = time.monotonic()
            p.view.top = p.view.content_height() // 2
            p.view.redraw(now=True)
            app.root.update_idletasks()
            result['scroll'] = time.monotonic() - t0
            t0 = time.monotonic()
            p.apply()
            app.root.update_idletasks()
            result['resort'] = time.monotonic() - t0
            app.quit()
            return
        app.root.after(5, check)
    app.root.after(5, check)
    app.run()
    print(f"bench, Python {'.'.join(map(str, __import__('sys').version_info[:3]))}, "
          f"Tk {tk.TkVersion}")
    print(f"  process start to window:   {age():.3f} s (includes Python itself)")
    print(f"  folder of {result.get('n', 0)} items shown: {result.get('shown', 0):.3f} s")
    print(f"  redraw after a long scroll: {result.get('scroll', 0) * 1000:.1f} ms")
    print(f"  sort and filter again:      {result.get('resort', 0) * 1000:.1f} ms")
    return 0
