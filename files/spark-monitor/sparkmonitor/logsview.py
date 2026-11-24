"""The Logs tab: the systemd journal in plain words, and the crashes systemd kept.

Nothing is read until the tab is opened. Opening it starts one `journalctl -f` for the chosen
boot and level; leaving the tab stops it. At most CAP entries are held (journal.CAP). Programs
that take a moment (coredumpctl, systemctl) run on a thread, never on the window's."""

import os
import queue
import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import ttk

from . import journal
from .core import log
from .host import Host, Stream
from .journal import CAP, Crash, Entry
from .sysinfo import os_line, parse_ostree
from .text import t
from .ui import make_table
from .widgets import T, Segmented, WolkButton

BATCH = 400                    # entries put into the table per pass: the window stays responsive
POLL_MS = 400
SLOW_S = 30.0                  # how often failed units and crashes are looked at again
LEVELS = (('err', 'logs.level_err'), ('warning', 'logs.level_warn'), ('all', 'logs.level_all'))


class Field(tk.Frame):
    """A small uppercase label over a text box."""

    def __init__(self, parent: tk.Misc, label: str, width: int, font, label_font,
                 command: Callable[[], None]):
        super().__init__(parent, bg=T["bg"])
        tk.Label(self, text=label.upper(), bg=T["bg"], fg=T["muted"], font=label_font,
                 anchor="w").pack(fill="x")
        self.var = tk.StringVar()
        self.entry = tk.Entry(self, textvariable=self.var, width=width, font=font,
                              bg=T["panel2"], fg=T["text"], insertbackground=T["accent"],
                              relief="flat", highlightthickness=1,
                              highlightbackground=T["line2"], highlightcolor=T["accent"],
                              selectbackground=T["hover"], selectforeground=T["accent"])
        self.entry.pack(fill="x", ipady=3)
        self._after: Optional[str] = None
        self._command = command
        self.var.trace_add('write', lambda *_: self._later())

    def _later(self) -> None:
        if self._after:
            self.after_cancel(self._after)
        self._after = self.after(250, self._fire)

    def _fire(self) -> None:
        self._after = None
        self._command()

    def get(self) -> str:
        return self.var.get().strip()

    def set(self, text: str) -> None:
        self.var.set(text)


def read_only_text(parent: tk.Misc, font, height: int) -> Tuple[tk.Frame, tk.Text]:
    frame = tk.Frame(parent, bg=T["line"], padx=1, pady=1)
    box = tk.Text(frame, height=height, wrap="word", font=font, bg=T["panel"], fg=T["text"],
                  relief="flat", highlightthickness=0, padx=8, pady=6, state="disabled",
                  selectbackground=T["hover"], selectforeground=T["accent"], cursor="arrow",
                  insertwidth=0)
    bar = ttk.Scrollbar(frame, orient="vertical", command=box.yview,
                        style="Spark.Vertical.TScrollbar")
    box.configure(yscrollcommand=bar.set)
    bar.pack(side="right", fill="y")
    box.pack(side="left", fill="both", expand=True)
    box.tag_configure("label", foreground=T["muted"])
    box.tag_configure("err", foreground=T["pink"])
    return frame, box


def put_text(box: tk.Text, text: str) -> None:
    box.config(state="normal")
    box.delete("1.0", "end")
    box.insert("end", text)
    box.config(state="disabled")


class LogsView(tk.Frame):
    def __init__(self, app, host: Optional[Host] = None):
        super().__init__(app.body, bg=T["bg"])
        self.app = app
        self.host = host or Host(app.src)
        px = app.px
        self.entries: Deque[Entry] = deque(maxlen=CAP)
        self.by_iid: Dict[str, Entry] = {}
        self.seq = 0
        self.stream: Optional[Stream] = None
        self.boot, self.level = 0, 'warning'
        self.loaded = 0                        # entries read for this choice of boot and level
        self.live = False                      # initial batch done: new errors are events now
        self.crashes: List[Crash] = []
        self.crash_info: Dict[Tuple[int, int], str] = {}
        self.mode = 'entries'
        self.visible = False
        self._poll_id: Optional[str] = None
        self._results: "queue.Queue[Tuple[str, object]]" = queue.Queue()
        self._busy: set = set()
        self._slow_at = 0.0
        self._crash_mark: Optional[float] = None
        self.os_text = ""
        self.failed: List[str] = []
        self.shutdown_state: Optional[Tuple[Optional[bool], int]] = None
        self.crashes_loaded = False
        self.started = time.monotonic()

        top = tk.Frame(self, bg=T["bg"])
        top.pack(fill="x", padx=px(14), pady=(px(10), 0))
        self.mode_switch = Segmented(top, [(t('logs.mode_entries').upper(), 'entries'),
                                           (t('logs.mode_crashes').upper(), 'crashes')],
                                     'entries', self.set_mode, app.font(8))
        self.mode_switch.pack(side="left")
        self.state = tk.Label(top, text="", bg=T["bg"], fg=T["muted"], font=app.font(8),
                              anchor="e")
        self.state.pack(side="right")

        # problems found when the tab opened: failed units, a bad last shutdown
        self.banner = tk.Frame(self, bg=T["bg"])
        self.banner_rows: List[tk.Label] = []

        self.entries_pane = tk.Frame(self, bg=T["bg"])
        self.crashes_pane = tk.Frame(self, bg=T["bg"])
        self._build_entries(px)
        self._build_crashes(px)
        self.banner.pack(fill="x", padx=px(14), pady=(px(8), 0))
        self.entries_pane.pack(fill="both", expand=True)

    # — building —
    def _build_entries(self, px) -> None:
        app, pane = self.app, self.entries_pane
        bar = tk.Frame(pane, bg=T["bg"])
        bar.pack(fill="x", padx=px(14), pady=(px(10), 0))
        for label, attr, options, value, command in (
                (t('logs.boot'), 'boot_switch',
                 [(t('logs.this_boot').upper(), '0'), (t('logs.prev_boot').upper(), '-1')],
                 '0', self.set_boot),
                (t('logs.level'), 'level_switch',
                 [(t(key).upper(), k) for k, key in LEVELS], 'warning', self.set_level)):
            col = tk.Frame(bar, bg=T["bg"])
            col.pack(side="left", padx=(0, px(14)), anchor="s")
            tk.Label(col, text=label.upper(), bg=T["bg"], fg=T["muted"], font=app.font(7),
                     anchor="w").pack(fill="x")
            seg = Segmented(col, options, value, command, app.font(8))
            seg.pack()
            setattr(self, attr, seg)
        self.app_field = Field(bar, t('logs.app'), 18, app.font(9, False), app.font(7),
                               self.rerender)
        self.app_field.pack(side="left", padx=(0, px(10)), anchor="s")
        self.text_field = Field(bar, t('logs.search'), 24, app.font(9, False), app.font(7),
                                self.rerender)
        self.text_field.pack(side="left", fill="x", expand=True, anchor="s")

        columns = ('time', 'level', 'source', 'what')
        frame, self.tree = make_table(pane, columns, show="headings")
        frame.pack(fill="both", expand=True, padx=px(14), pady=(px(10), 0))
        for col, key, width, stretch in (('time', 'logs.col_time', 110, False),
                                         ('level', 'logs.col_level', 80, False),
                                         ('source', 'logs.col_app', 190, False),
                                         ('what', 'logs.col_what', 480, True)):
            self.tree.heading(col, text=t(key).upper(), anchor="w")
            self.tree.column(col, width=px(width), minwidth=px(50), anchor="w", stretch=stretch)
        self.tree.tag_configure('err', foreground=T["pink"])
        self.tree.tag_configure('warn', foreground=T["gold"])
        self.tree.tag_configure('fresh', background=T["panel2"])
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.select_entry())

        lower = tk.Frame(pane, bg=T["bg"])
        lower.pack(fill="x", padx=px(14), pady=px(10))
        box, self.detail = read_only_text(lower, app.font(8, False), 7)
        box.pack(side="left", fill="x", expand=True)
        buttons = tk.Frame(lower, bg=T["bg"])
        buttons.pack(side="right", anchor="n", padx=(px(10), 0))
        self.copy_button = WolkButton(buttons, t('logs.copy_entry'), self.copy_entry,
                                      app.font(9))
        self.copy_button.pack(fill="x")
        self.only_button = WolkButton(buttons, t('logs.only_app'), self.only_this_app,
                                      app.font(9))
        self.only_button.pack(fill="x", pady=(px(6), 0))
        self.summary = tk.Label(buttons, text="", bg=T["bg"], fg=T["muted"], font=app.font(7),
                                anchor="e", justify="right")
        self.summary.pack(fill="x", pady=(px(8), 0))
        for b in (self.copy_button, self.only_button):
            b.set_enabled(False)
        self.show_hint(t('logs.pick'))

    def _build_crashes(self, px) -> None:
        app, pane = self.app, self.crashes_pane
        columns = ('time', 'app', 'signal', 'size')
        frame, self.crash_tree = make_table(pane, columns, show="headings")
        frame.pack(fill="both", expand=True, padx=px(14), pady=(px(10), 0))
        for col, key, width, stretch in (('time', 'logs.col_time', 150, False),
                                         ('app', 'logs.col_app', 240, True),
                                         ('signal', 'crash.signal', 280, False),
                                         ('size', 'crash.size', 90, False)):
            self.crash_tree.heading(col, text=t(key).upper(), anchor="w")
            self.crash_tree.column(col, width=px(width), minwidth=px(50), anchor="w",
                                   stretch=stretch)
        self.crash_tree.bind("<<TreeviewSelect>>", lambda _e: self.select_crash())
        lower = tk.Frame(pane, bg=T["bg"])
        lower.pack(fill="x", padx=px(14), pady=px(10))
        box, self.crash_detail = read_only_text(lower, app.font(8, False), 9)
        box.pack(side="left", fill="x", expand=True)
        buttons = tk.Frame(lower, bg=T["bg"])
        buttons.pack(side="right", anchor="n", padx=(px(10), 0))
        self.report_button = WolkButton(buttons, t('crash.copy'), self.copy_report,
                                        app.font(9), variant="primary")
        self.report_button.pack(fill="x")
        self.report_button.set_enabled(False)
        tk.Label(buttons, text=t('crash.note'), bg=T["bg"], fg=T["muted"], font=app.font(7),
                 justify="right", wraplength=px(190), anchor="e").pack(fill="x", pady=(px(8), 0))
        put_text(self.crash_detail, t('crash.pick'))

    # — life cycle: nothing runs while the tab is not open —
    def on_show(self) -> None:
        self.visible = True
        if self.stream is None and self.mode == 'entries':
            self.start_stream()
        self._slow_at = 0.0
        if self._poll_id is None:
            self._poll_id = self.after(50, self._poll)

    def on_hide(self) -> None:
        self.visible = False
        self.stop_stream()
        if self._poll_id:
            self.after_cancel(self._poll_id)
            self._poll_id = None

    def shutdown(self) -> None:
        self.on_hide()

    def refresh(self) -> None:
        pass                              # everything here is driven by its own poll

    def reload(self) -> None:
        """F5: look again at the journal, crashes and failed units."""
        self.start_stream()
        self._slow_at = 0.0

    # — the journal stream —
    def start_stream(self) -> None:
        self.stop_stream()
        self.entries.clear()
        self.by_iid.clear()
        self.tree.delete(*self.tree.get_children(''))
        self.loaded = 0
        self.live = False
        self.started = time.monotonic()
        follow = self.boot == 0
        key = f"journal-{'this' if follow else 'prev'}-{self.level}.jsonl"
        self.stream = self.host.stream(key, journal.journal_args(self.boot, self.level, follow))
        if self.stream is None:
            self.show_hint(t('logs.no_journalctl'))
        self._status()

    def stop_stream(self) -> None:
        if self.stream is not None:
            self.stream.stop()
            self.stream = None

    def _poll(self) -> None:
        self._poll_id = None
        if not self.visible:
            return
        try:
            self._pump_stream()
            self._pump_results()
            self._slow_work()
        except tk.TclError:
            return
        self._poll_id = self.after(POLL_MS, self._poll)

    def _pump_stream(self) -> None:
        stream = self.stream
        if stream is None:
            return
        lines = stream.drain(BATCH)
        fresh_errors = 0
        for line in lines:
            entry = journal.parse_entry(line)
            if entry is None:
                continue
            self.loaded += 1
            if self.live and entry.prio <= 3:
                fresh_errors += 1
            self.add(entry, fresh=self.live)
        if not self.live and not lines and (stream.idle or self.loaded or
                                            time.monotonic() - self.started > 1.5):
            self.live = True            # the initial batch is in; what follows is new
            self.after_load()
        if fresh_errors:
            self.app.glitch.now(self.app.title, strong=fresh_errors > 2)
            self.app.glitch.now(self.state)
        if lines:
            self._status()

    def after_load(self) -> None:
        if not self.tree.get_children(''):
            self.show_hint(t('logs.empty_all') if self.level == 'all' else t('logs.empty'))
        self._status()

    def add(self, e: Entry, fresh: bool = False) -> None:
        self.seq += 1
        e.seq = self.seq
        if len(self.entries) == CAP:
            old = self.entries[0]
            iid = str(old.seq)
            if self.tree.exists(iid):
                self.tree.delete(iid)
            self.by_iid.pop(iid, None)
        self.entries.append(e)
        if journal.matches(e, self.app_field.get(), self.text_field.get()):
            self._insert(e, 0, fresh)

    def _insert(self, e: Entry, index, fresh: bool = False) -> None:
        iid = str(e.seq)
        tags = ('err',) if e.prio <= 3 else ('warn',) if e.prio == 4 else ()
        if fresh:
            tags += ('fresh',)
        self.tree.insert('', index, iid=iid, tags=tags, values=(
            journal.when(e.ts), journal.level_name(e.prio), journal.source_name(e),
            journal.headline(e)))
        self.by_iid[iid] = e
        if self.tree.exists('hint'):
            self.tree.delete('hint')

    def rerender(self) -> None:
        """The filters changed: show again what is already loaded."""
        app, text = self.app_field.get(), self.text_field.get()
        self.tree.delete(*self.tree.get_children(''))
        self.by_iid.clear()
        count = 0
        for e in reversed(self.entries):
            if journal.matches(e, app, text):
                self._insert(e, 'end')
                count += 1
        if not count:
            self.show_hint(t('logs.none_match') if self.entries else t('logs.empty'))
        self.select_entry()
        self._status()

    def show_hint(self, text: str) -> None:
        if self.tree.exists('hint'):
            self.tree.delete('hint')
        self.tree.insert('', 0, iid='hint', values=("", "", "", text), tags=('off',))

    def _status(self) -> None:
        shown = len(self.by_iid)
        text = t('logs.summary', shown=shown, loaded=len(self.entries), cap=CAP)
        if self.summary.cget('text') != text:
            self.summary.config(text=text)
        if self.stream is None:
            word, colour = t('logs.state_off'), T["muted"]
        elif self.boot != 0:
            word, colour = t('logs.state_prev'), T["gold"]
        elif not self.live:
            word, colour = t('logs.state_loading'), T["muted"]
        else:
            word, colour = t('logs.state_follow'), T["accent"]
        self.state.config(text=f"● {word}", fg=colour)

    # — choices —
    def set_boot(self, value: str) -> None:
        self.boot = int(value)
        self.boot_switch.set(value)
        self.start_stream()
        self.app.glitch.now(self.app.title)

    def set_level(self, value: str) -> None:
        self.level = value
        self.level_switch.set(value)
        self.start_stream()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.mode_switch.set(mode)
        if mode == 'entries':
            self.crashes_pane.pack_forget()
            self.entries_pane.pack(fill="both", expand=True)
            if self.stream is None and self.visible:
                self.start_stream()
        else:
            self.entries_pane.pack_forget()
            self.crashes_pane.pack(fill="both", expand=True)
            self.stop_stream()
            self._status()
            self._slow_at = 0.0
        self.app.glitch.now(self.app.title)

    # — one entry —
    def selected(self) -> Optional[Entry]:
        sel = self.tree.selection()
        return self.by_iid.get(sel[0]) if sel else None

    def select_entry(self) -> None:
        e = self.selected()
        for b in (self.copy_button, self.only_button):
            b.set_enabled(e is not None)
        if e is None:
            put_text(self.detail, t('logs.pick'))
            return
        put_text(self.detail, journal.entry_text(e))

    def copy_entry(self) -> None:
        e = self.selected()
        if e is not None:
            self.copy(journal.entry_text(e))

    def only_this_app(self) -> None:
        e = self.selected()
        if e is not None:
            self.app_field.set(journal.source_name(e))
            self.app_field._fire()

    def copy(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self.app.set_status(t('logs.copied'))
        self.app.glitch.now(self.app.title)

    # — slow things on a thread: failed units, last boot, crashes —
    def _async(self, name: str, work: Callable[[], object]) -> None:
        if name in self._busy:
            return
        self._busy.add(name)

        def run():
            try:
                result = work()
            except Exception as exc:    # noqa: BLE001 - a thread must not die silently
                log.warning("logs: %s failed: %s", name, exc)
                result = None
            self._results.put((name, result))
        threading.Thread(target=run, daemon=True).start()

    def _crash_dir_mark(self) -> Optional[float]:
        try:
            return os.stat(self.app.src.path('var/lib/systemd/coredump')).st_mtime
        except OSError:
            return None

    def _slow_work(self) -> None:
        now = time.monotonic()
        mark = self._crash_dir_mark()
        changed = mark is not None and self._crash_mark is not None and mark != self._crash_mark
        if now - self._slow_at < SLOW_S and not changed:
            return
        first = self._slow_at == 0.0
        self._slow_at = now
        self._crash_mark = mark
        host = self.host
        self._async('crashes', lambda: journal.parse_crashes(
            host.run('coredumpctl.json', journal.crash_args())) if host.have('coredumpctl')
            else None)
        self._async('failed', lambda: self._failed_units())
        if first:
            self._async('shutdown', lambda: journal.boot_ended_cleanly(host.run(
                'journal-prev-tail.jsonl', ['journalctl', '-b', '-1', '-n', '300', '-o', 'json',
                                            '--no-pager', '--output-fields=MESSAGE'])))
            self._async('os', lambda: os_line(self.app.src, parse_ostree(host.run(
                'rpm-ostree.json', ['rpm-ostree', 'status', '--json'], 20)
                if host.have('rpm-ostree') else None)))

    def _failed_units(self) -> List[str]:
        host = self.host
        out: List[str] = []
        if host.have('systemctl'):
            out += journal.parse_failed(host.run('failed-system.txt', [
                'systemctl', '--failed', '--no-legend', '--plain', '--no-pager']))
            out += journal.parse_failed(host.run('failed-user.txt', [
                'systemctl', '--user', '--failed', '--no-legend', '--plain', '--no-pager']),
                user=True)
        return out

    def _pump_results(self) -> None:
        while True:
            try:
                name, result = self._results.get_nowait()
            except queue.Empty:
                return
            self._busy.discard(name)
            if name == 'crashes':
                self.got_crashes(result)
            elif name == 'failed':
                self.failed = result or []
                self._banner()
            elif name == 'shutdown':
                self.shutdown_state = result
                self._banner()
            elif name == 'os':
                self.os_text = result or ""
            elif name == 'info':
                key, text = result
                self.crash_info[key] = text
                if len(self.crash_info) > 20:
                    self.crash_info.pop(next(iter(self.crash_info)))
                self.select_crash()

    def _banner(self) -> None:
        lines: List[Tuple[str, str]] = []
        if self.failed:
            shown = ', '.join(self.failed[:4]) + (f" +{len(self.failed) - 4}"
                                                  if len(self.failed) > 4 else '')
            lines.append((t('logs.failed_units', n=len(self.failed), units=shown), T["pink"]))
        state = self.shutdown_state
        if state and state[0] is False:
            lines.append((t('logs.unclean', when=journal.when(state[1])), T["gold"]))
        for label in self.banner_rows:
            label.destroy()
        self.banner_rows = []
        for text, colour in lines:
            row = tk.Label(self.banner, text="● " + text, bg=T["panel"], fg=colour,
                           font=self.app.font(8), anchor="w", justify="left", padx=8, pady=4,
                           highlightthickness=1, highlightbackground=T["line"],
                           wraplength=self.app.px(940))
            row.pack(fill="x", pady=(0, 4))
            self.banner_rows.append(row)
        if lines:
            self.app.glitch.now(self.app.title)

    # — crashes —
    def got_crashes(self, crashes: Optional[List[Crash]]) -> None:
        tree = self.crash_tree
        if crashes is None:
            self.crashes = []
            tree.delete(*tree.get_children(''))
            tree.insert('', 'end', iid='none', values=("", t('crash.unavailable'), "", ""),
                        tags=('off',))
            return
        old = {(c.ts, c.pid) for c in self.crashes}
        new = [c for c in crashes if (c.ts, c.pid) not in old]
        if self.crashes_loaded and not new and len(crashes) == len(self.crashes):
            return
        first = not self.crashes_loaded
        self.crashes_loaded = True
        self.crashes = crashes
        fresh = {(n.ts, n.pid) for n in new} if not first else set()
        selected = tree.selection()
        tree.delete(*tree.get_children(''))
        for i, c in enumerate(crashes):
            tree.insert('', 'end', iid=str(i), values=(
                journal.when(c.ts), c.app, f"{c.signal_name}: {c.meaning}", self._size(c)),
                tags=('err',) if (c.ts, c.pid) in fresh else ())
        if not crashes:
            tree.insert('', 'end', iid='none', values=("", t('crash.none'), "", ""),
                        tags=('off',))
        if selected and tree.exists(selected[0]):
            tree.selection_set(selected[0])
        if fresh:                              # a crash appearing while the tab is open
            self.app.glitch.now(self.app.title, strong=True)
            self.app.set_status(t('crash.new', app=new[0].app.upper()), T["pink"], hold_ms=8000)

    @staticmethod
    def _size(c: Crash) -> str:
        from . import core
        return core.size(c.size, 1) if c.size else "—"

    def selected_crash(self) -> Optional[Crash]:
        sel = self.crash_tree.selection()
        if sel and sel[0].isdigit() and int(sel[0]) < len(self.crashes):
            return self.crashes[int(sel[0])]
        return None

    def select_crash(self) -> None:
        c = self.selected_crash()
        self.report_button.set_enabled(c is not None)
        if c is None:
            put_text(self.crash_detail, t('crash.pick'))
            return
        key = (c.ts, c.pid)
        head = '\n'.join((f"{t('detail.app')}: {c.app}", f"{t('detail.time')}: "
                          f"{journal.when(c.ts, True)}",
                          f"{t('crash.signal')}: {c.signal_name}: {c.meaning}",
                          f"{t('detail.pid')}: {c.pid}",
                          f"{t('detail.executable')}: {journal.scrub(c.exe)}"))
        info = self.crash_info.get(key)
        if info is None:
            put_text(self.crash_detail, head + '\n\n' + t('crash.loading'))
            host = self.host
            if host.have('coredumpctl'):
                self._async('info', lambda: (key, journal.scrub_info(host.run(
                    'coredumpctl-info.txt', journal.crash_args(c), 20) or t('crash.no_info'))))
            else:
                self.crash_info[key] = t('crash.no_info')
            return
        put_text(self.crash_detail, head + '\n\n' + info)

    def copy_report(self) -> None:
        c = self.selected_crash()
        if c is None:
            return
        self.copy(journal.crash_report(c, self.crash_info.get((c.ts, c.pid)), self.os_text))
