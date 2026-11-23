"""The window: a sidebar of pages with search on top, and the page on the right. Pages are built
the first time they are opened and read their state then, not at start."""

import queue
import subprocess
import threading
from typing import Callable, Dict, List, Optional, Tuple

import tkinter as tk
import tkinter.font as tkfont

from . import APP_CLASS, APP_NAME, VERSION, core
from .i18n import _, both
from .ui import entry, label, rule
from .widgets import T, Glitch, GlitchText, Strip, WolkButton, pick_mono


class Watcher:
    """Runs a tool that prints a line per change (pactl subscribe, nmcli monitor, ...) in a
    thread and calls `on_line` in the Tk thread. Only runs while its page is on screen."""

    def __init__(self, app: 'App', cmd: List[str], on_event: Callable[[], None]):
        self.app, self.cmd, self.on_event = app, cmd, on_event
        self.proc: Optional[subprocess.Popen] = None
        self.stopped = False

    def start(self) -> bool:
        if not core.have(self.cmd[0]):
            return False
        try:
            self.proc = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                         stdin=subprocess.DEVNULL, text=True, errors='replace')
        except OSError:
            return False
        threading.Thread(target=self._read, daemon=True).start()
        return True

    def _read(self):
        assert self.proc and self.proc.stdout
        for _line in self.proc.stdout:
            if self.stopped:
                break
            self.app.post(self.on_event)

    def stop(self):
        self.stopped = True
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


class Page:
    """One page. Subclasses set key/title/index and fill build() and refresh()."""
    key = ''
    title = ''
    group = 'main'
    index: List[Tuple[str, str]] = []       # (what you can set, extra words to find it by)
    tool: Optional[str] = None              # the command the page needs

    def __init__(self, app: 'App'):
        self.app = app
        self.frame: Optional[tk.Frame] = None
        self.status: Optional[tk.Label] = None
        self.visible = False
        self.watchers: List[Watcher] = []

    # --- pieces
    def mount(self, parent: tk.Frame) -> tk.Frame:
        if self.frame is None:
            self.frame = tk.Frame(parent, bg=T["bg"])
            self.build(self.frame)
            self.status = label(self.frame, '', self.app.font(9, False), fg=T["muted"], bg=T["bg"])
            self.status.pack(side='bottom', fill='x', padx=24, pady=(0, 10))
        return self.frame

    def build(self, f: tk.Frame) -> None:
        raise NotImplementedError

    def refresh(self) -> None:
        pass

    def enter(self) -> None:
        self.visible = True
        self.refresh()

    def leave(self) -> None:
        self.visible = False
        for w in self.watchers:
            w.stop()
        self.watchers = []

    def watch(self, cmd: List[str], delay: int = 400) -> None:
        pending = {'id': None}

        def fire():
            pending['id'] = None
            if self.visible:
                self.refresh()

        def event():
            if self.visible and pending['id'] is None:
                pending['id'] = self.app.root.after(delay, fire)

        w = Watcher(self.app, cmd, event)
        if w.start():
            self.watchers.append(w)

    def say(self, text: str, error: bool = False) -> None:
        if self.status is not None:
            self.status.config(text=text, fg=T["pink"] if error else T["muted"])
        if error:
            self.app.glitch.now(strong=True)

    def section(self, f: tk.Frame, title: str, fill: bool = True) -> tk.Frame:
        """A flat panel with an uppercase micro-label; returns the inside to add to."""
        outer = tk.Frame(f, bg=T["line"], padx=1, pady=1)
        outer.pack(fill='x' if fill else 'none', padx=24, pady=(0, 12), anchor='w')
        inner = tk.Frame(outer, bg=T["panel"], padx=16, pady=12)
        inner.pack(fill='both', expand=True)
        if title:
            label(inner, title.upper(), self.app.font(8), fg=T["muted"]).pack(anchor='w', pady=(0, 8))
        return inner

    def row(self, parent: tk.Frame, text: str, hint: str = '') -> tk.Frame:
        """A line: the name on the left; returns the frame the control goes into."""
        r = tk.Frame(parent, bg=T["panel"])
        r.pack(fill='x', pady=4)
        col = tk.Frame(r, bg=T["panel"], width=190)
        col.pack(side='left', anchor='n')
        col.pack_propagate(False)
        label(col, text, self.app.font(10)).pack(anchor='w', fill='x')
        right = tk.Frame(r, bg=T["panel"])
        right.pack(side='left', fill='x', expand=True)
        if hint:
            label(r, hint, self.app.font(8, False), fg=T["dim"]).pack(side='right')
        return right

    def missing(self, f: tk.Frame, tool: str, what: str) -> None:
        box = self.section(f, '')
        label(box, _("{tool} isn't installed here, so this page can't {what}.").format(
            tool=tool, what=what), self.app.font(10), fg=T["gold"], wraplength=640).pack(anchor='w')


class App:
    def __init__(self, page: Optional[str] = None):
        from .pages import PAGES, SIDEBAR
        self.root = tk.Tk(className=APP_CLASS)
        self.root.title(APP_NAME)
        self.root.configure(bg=T["bg"])
        self.root.geometry("1080x720")
        self.root.minsize(760, 520)
        self.root.option_add('*Font', 'TkDefaultFont')
        self.mono = pick_mono(self.root)
        self._fonts: Dict[Tuple[int, bool], tkfont.Font] = {}
        self.glitch = Glitch(self.root, not core.reduced_motion())
        self.jobs: 'queue.Queue[Callable[[], None]]' = queue.Queue()
        self.pumping = False
        self.busy = 0
        self.closers: List[Callable[[], None]] = []
        self.pages: Dict[str, Page] = {k: cls(self) for k, cls in PAGES.items()}
        self.sidebar_order = SIDEBAR
        self.current: Optional[Page] = None
        self.items: Dict[str, tk.Label] = {}
        self.kcm_index: List[Tuple[str, str]] = []
        self.kcm_loaded = False
        self.search_results: List[Tuple[str, str]] = []
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.bind('<Control-f>', lambda _e: self.search_entry.focus_set())
        self.root.bind('<Control-q>', lambda _e: self.quit())
        self.open_page(page if page in self.pages else self.sidebar_order[0])

    # --- fonts and threads
    def font(self, size: int, bold: bool = True) -> tkfont.Font:
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(self.root, family=self.mono, size=size,
                                           weight='bold' if bold else 'normal')
        return self._fonts[key]

    def bg(self, work: Callable[[], object], done: Optional[Callable[[object], None]] = None):
        """Run `work` off the Tk thread; `done(result)` runs back on it."""
        self.busy += 1

        def run():
            try:
                result = work()
            except Exception as exc:         # noqa: BLE001
                core.log.warning("background job failed: %s", exc)
                result = None
            self.post(lambda: self._finish(done, result))
        threading.Thread(target=run, daemon=True).start()

    def _finish(self, done, result):
        self.busy -= 1
        if done:
            try:
                done(result)
            except tk.TclError:
                pass                          # the page was closed meanwhile

    def post(self, func: Callable[[], None]) -> None:
        """Hand a function to the Tk thread (safe from any thread)."""
        self.jobs.put(func)
        if not self.pumping:
            self.pumping = True
            try:
                self.root.after(0, self._pump)
            except (tk.TclError, RuntimeError):
                pass

    def _pump(self):
        self.pumping = False
        try:
            while True:
                self.jobs.get_nowait()()
        except queue.Empty:
            pass
        except tk.TclError:
            pass
        if self.busy > 0 or any(p.watchers for p in self.pages.values()):
            self.pumping = True
            self.root.after(120, self._pump)

    def idle(self, timeout: float = 10.0) -> None:
        """For tests: run until no background job is left."""
        import time
        end = time.time() + timeout
        while time.time() < end:
            self.root.update()
            try:
                while True:
                    self.jobs.get_nowait()()
            except queue.Empty:
                pass
            if self.busy <= 0:
                self.root.update()
                return
            time.sleep(0.01)

    # --- layout
    def _build(self):
        side = tk.Frame(self.root, bg=T["panel"], width=268)
        side.pack(side='left', fill='y')
        side.pack_propagate(False)
        head = tk.Frame(side, bg=T["panel"])
        head.pack(fill='x', padx=16, pady=(14, 8))
        self.logo = GlitchText(head, APP_NAME.upper(), self.font(11), T["panel"], T["accent"])
        self.logo.pack(anchor='w')
        self.glitch.add(self.logo)
        self.search_var = tk.StringVar()
        self.search_entry = entry(side, self.font(10), 22)
        self.search_entry.configure(textvariable=self.search_var)
        self.search_entry.pack(fill='x', padx=16, pady=(0, 4), ipady=4)
        self.hint = label(side, _("Search every setting"), self.font(8, False), fg=T["dim"])
        self.hint.pack(fill='x', padx=16, pady=(0, 8))
        self.search_var.trace_add('write', lambda *_a: self.on_search())
        self.search_entry.bind('<Return>', lambda _e: self.open_first_result())
        self.search_entry.bind('<Escape>', lambda _e: self.search_var.set(''))
        rule(side).pack(fill='x')
        self.list = tk.Frame(side, bg=T["panel"])
        self.list.pack(fill='both', expand=True, pady=6)
        for key in self.sidebar_order:
            page = self.pages[key]
            item = tk.Label(self.list, text='  ' + _(page.title), font=self.font(10), anchor='w',
                            bg=T["panel"], fg=T["muted"], padx=10, pady=5, cursor='hand2',
                            takefocus=1)
            item.pack(fill='x')
            item.bind('<ButtonRelease-1>', lambda _e, k=key: self.open_page(k))
            item.bind('<Return>', lambda _e, k=key: self.open_page(k))
            item.bind('<Enter>', lambda _e, k=key: self._hover(k, True))
            item.bind('<Leave>', lambda _e, k=key: self._hover(k, False))
            self.items[key] = item
        tk.Frame(self.root, bg=T["line"], width=1).pack(side='left', fill='y')
        right = tk.Frame(self.root, bg=T["bg"])
        right.pack(side='left', fill='both', expand=True)
        self.title_bar = tk.Frame(right, bg=T["bg"])
        self.title_bar.pack(fill='x', padx=24, pady=(18, 6))
        self.title = GlitchText(self.title_bar, '', self.font(16), T["bg"])
        self.title.pack(anchor='w')
        self.glitch.add(self.title)
        Strip(right).pack(fill='x', padx=24, pady=(0, 12))
        self.body = tk.Frame(right, bg=T["bg"])
        self.body.pack(fill='both', expand=True)
        self.results = tk.Frame(right, bg=T["bg"])

    def _hover(self, key: str, on: bool):
        if self.current is not self.pages[key]:
            self.items[key].config(bg=T["hover"] if on else T["panel"])

    # --- pages
    def open_page(self, key: str, burst: bool = True):
        page = self.pages[key]
        self.results.pack_forget()
        if self.current is not None:
            self.current.leave()
            if self.current.frame is not None:
                self.current.frame.pack_forget()
        for k, item in self.items.items():
            on = k == key
            item.config(bg=T["accent"] if on else T["panel"],
                        fg=T["on_accent"] if on else T["muted"])
        self.current = page
        self.body.pack(fill='both', expand=True)
        self.title.set_text(_(page.title).upper(), T["text"])
        page.mount(self.body).pack(fill='both', expand=True)
        page.enter()
        if burst:
            self.glitch.now(self.title)

    # --- search
    def on_search(self):
        text = self.search_var.get().strip().lower()
        if text and not self.kcm_loaded:
            self.kcm_loaded = True
            from . import kcms
            self.bg(kcms.more_settings, self._kcms_ready)
        self.hint.config(text='' if text else _("Search every setting"))
        if not text:
            self.results.pack_forget()
            self.body.pack(fill='both', expand=True)
            return
        self.search_results = self.find(text)
        self._show_results(text)

    def _kcms_ready(self, mods):
        self.kcm_index = [(k.name, k.id) for k in (mods or [])]
        if self.search_var.get().strip():
            self.on_search()

    def find(self, text: str) -> List[Tuple[str, str]]:
        """(shown, target) pairs: target is a page key, or 'kcm:<module>'. Every word typed
        must be in the setting's English or French name or its keywords."""
        words = text.lower().split()
        found: List[Tuple[str, str]] = []
        for key in self.sidebar_order:
            page = self.pages[key]
            if all(w in both(page.title) for w in words):
                found.append((_(page.title), key))
            for name, extra in page.index:
                hay = both(name) + ' ' + both(page.title) + ' ' + extra.lower()
                if all(w in hay for w in words):
                    found.append((f"{_(page.title)} › {_(name)}", key))
        for name, module in self.kcm_index:
            if all(w in name.lower() + ' ' + module.lower() for w in words):
                found.append((f"{_('More settings')} › {name}", 'kcm:' + module))
        return found[:40]

    def _show_results(self, text: str):
        self.body.pack_forget()
        for w in self.results.winfo_children():
            w.destroy()
        self.results.pack(fill='both', expand=True)
        label(self.results, _("Results").upper(), self.font(8), fg=T["muted"],
              bg=T["bg"]).pack(anchor='w', padx=24, pady=(4, 6))
        if not self.search_results:
            label(self.results, _("Nothing matches. Try another word."), self.font(10),
                  fg=T["muted"], bg=T["bg"]).pack(anchor='w', padx=24)
        for shown, target in self.search_results:
            row = tk.Label(self.results, text=shown, font=self.font(10), anchor='w',
                           bg=T["panel"], fg=T["text"], padx=12, pady=6, cursor='hand2')
            row.pack(fill='x', padx=24, pady=1)
            row.bind('<Enter>', lambda _e, r=row: r.config(bg=T["hover"], fg=T["accent"]))
            row.bind('<Leave>', lambda _e, r=row: r.config(bg=T["panel"], fg=T["text"]))
            row.bind('<ButtonRelease-1>', lambda _e, t=target: self.go(t))

    def go(self, target: str):
        if target.startswith('kcm:'):
            from . import kcms
            kcms.open_module(target[4:])
            return
        self.search_var.set('')
        self.open_page(target)

    def open_first_result(self):
        if self.search_results:
            self.go(self.search_results[0][1])

    # --- life
    def quit(self):
        for c in self.closers:
            try:
                c()
            except Exception as exc:       # noqa: BLE001
                core.log.warning("closing: %s", exc)
        if self.current:
            self.current.leave()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
