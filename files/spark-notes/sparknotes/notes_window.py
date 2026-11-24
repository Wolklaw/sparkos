"""The notes window: a list of notes on the left (search, pinned first), the selected note on
the right. A note is a plain text file; it saves half a second after you stop typing, when you
switch notes and when you close the window.

Markdown-light: lines starting with #, ##, ### are headings, **bold** and `code` are styled,
- [ ] and - [x] are checkboxes (Ctrl+Enter ticks the line you are on). The text stays plain.
"""

import re
from typing import Callable, List, Optional

from gi.repository import Gdk, GLib, Gtk, Pango

from . import core
from .core import CHROME as C
from .core import Note, NoteStore
from .text import t

SAVE_DELAY_MS = 500
MAX_STYLED_CHARS = 200_000
HEADING = re.compile(r'^(#{1,3})\s')
BOLD = re.compile(r'\*\*[^*\n]+\*\*')
CODE = re.compile(r'`[^`\n]+`')
TASK = re.compile(r'^(\s*[-*] )\[( |x|X)\]')


class NoteRow(Gtk.ListBoxRow):
    def __init__(self, note: Note, draft: bool):
        super().__init__()
        self.note = note
        if note.pinned:
            self.add_css_class('pinned')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(box, f'set_margin_{side}')(6)
        title = Gtk.Label(label=note.title or t('notes.untitled'), xalign=0, ellipsize=3)
        title.add_css_class('title')
        box.append(title)
        if not draft:
            sub = Gtk.Label(label=f"{core.ago(note.updated)}  {note.snippet(40)}".strip(),
                            xalign=0, ellipsize=3)
            sub.add_css_class('snippet')
            box.append(sub)
        self.set_child(box)


class NotesWindow(Gtk.ApplicationWindow):

    def __init__(self, app, store: NoteStore, settings: dict,
                 on_open_clipboard: Optional[Callable[[], None]] = None, glitch=None):
        super().__init__(application=app)
        self.add_css_class('spark-notes')
        self.store = store
        self.settings = settings
        self.on_open_clipboard = on_open_clipboard
        self.glitch = glitch
        self.current_id: Optional[str] = None
        self.loading = False
        self.dirty = False
        self.save_id = 0
        self.undo_id: Optional[str] = None
        self.rows: List[NoteRow] = []
        self.set_title(t('notes.title'))
        self.set_default_size(820, 560)

        root = Gtk.Box()
        self.set_child(root)

        # left: search, new, the list
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left.add_css_class('side')
        left.set_size_request(280, -1)
        for side in ('top', 'bottom', 'start'):
            getattr(left, f'set_margin_{side}')(10)
        left.set_margin_end(10)
        head = Gtk.Box(spacing=8)
        self.heading = Gtk.Label(label="NOTES", xalign=0, hexpand=True)
        self.heading.add_css_class('heading')
        head.append(self.heading)
        self.count = Gtk.Label(label='', xalign=1)
        self.count.add_css_class('micro')
        head.append(self.count)
        left.append(head)
        top = Gtk.Box(spacing=6)
        self.search = Gtk.SearchEntry(hexpand=True)
        self.search.add_css_class('search')
        self.search.set_placeholder_text(t('notes.search'))
        self.search.set_search_delay(80)
        self.search.connect('search-changed', lambda *_: self.refresh_list())
        top.append(self.search)
        new = Gtk.Button(label=t('notes.new'))
        new.add_css_class('action')
        new.add_css_class('primary')
        new.set_tooltip_text(t('notes.new_tip'))
        new.connect('clicked', lambda *_: self.new_note())
        top.append(new)
        left.append(top)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.list = Gtk.ListBox()
        self.list.add_css_class('rows')
        self.list.connect('row-selected', self._on_row_selected)
        self.empty = Gtk.Label(label='', xalign=0, wrap=True)
        self.empty.add_css_class('empty')
        holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        holder.append(self.list)
        holder.append(self.empty)
        scroll.set_child(holder)
        left.append(scroll)
        clip = Gtk.Button(label=t('notes.clipboard'))
        clip.add_css_class('action')
        clip.set_tooltip_text(t('notes.clipboard_tip'))
        clip.connect('clicked', lambda *_: self.on_open_clipboard and self.on_open_clipboard())
        left.append(clip)
        root.append(left)

        # right: the note
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True)
        for side in ('top', 'bottom', 'end'):
            getattr(right, f'set_margin_{side}')(10)
        right.set_margin_start(10)
        bar = Gtk.Box(spacing=6)
        self.status = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)
        self.status.add_css_class('status')
        bar.append(self.status)
        self.undo_button = Gtk.Button(label=t('notes.undo'))
        self.undo_button.add_css_class('action')
        self.undo_button.set_visible(False)
        self.undo_button.connect('clicked', lambda *_: self.undo_delete())
        bar.append(self.undo_button)
        self.pin_button = Gtk.Button(label=t('notes.pin'))
        self.pin_button.add_css_class('mini')
        self.pin_button.connect('clicked', lambda *_: self.toggle_pin())
        bar.append(self.pin_button)
        self.delete_button = Gtk.Button(label=t('notes.delete'))
        self.delete_button.add_css_class('mini')
        self.delete_button.connect('clicked', lambda *_: self.delete_current())
        bar.append(self.delete_button)
        right.append(bar)

        self.buffer = Gtk.TextBuffer()
        self._make_tags()
        self.buffer.connect('changed', self._on_changed)
        self.view = Gtk.TextView(buffer=self.buffer)
        self.view.add_css_class('editor')
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_monospace(True)
        for side in ('top', 'bottom', 'left', 'right'):
            getattr(self.view, f'set_{side}_margin')(10)
        editor = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        editor.add_css_class('editorbox')
        editor.set_child(self.view)
        right.append(editor)
        foot = Gtk.Label(label=t('notes.footer', path=self.store.notes_dir), xalign=0,
                         ellipsize=3)
        foot.add_css_class('micro')
        right.append(foot)
        root.append(right)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self._on_key)
        self.add_controller(keys)
        self.connect('close-request', self._on_close)

        self.refresh_list()
        if self.rows:
            self.open_note(self.rows[0].note.id)
        else:
            self.new_note()

    # --- tags: the Markdown-light look ---

    def _make_tags(self) -> None:
        b = self.buffer
        b.create_tag('h1', weight=Pango.Weight.BOLD, scale=1.5, foreground=C['accent'])
        b.create_tag('h2', weight=Pango.Weight.BOLD, scale=1.25, foreground=C['accent'])
        b.create_tag('h3', weight=Pango.Weight.BOLD, scale=1.1, foreground=C['accent'])
        b.create_tag('bold', weight=Pango.Weight.BOLD)
        b.create_tag('code', foreground=C['gold'], background=C['panel2'])
        b.create_tag('task', foreground=C['muted'])
        b.create_tag('done', foreground=C['dim'], strikethrough=True)

    def restyle(self) -> None:
        b = self.buffer
        start, end = b.get_bounds()
        b.remove_all_tags(start, end)
        if b.get_char_count() > MAX_STYLED_CHARS:
            return
        text = b.get_text(start, end, False)
        offset = 0
        for line in text.split('\n'):
            m = HEADING.match(line)
            if m:
                self._tag(f'h{len(m.group(1))}', offset, offset + len(line))
            task = TASK.match(line)
            if task:
                lo = offset + len(task.group(1))
                self._tag('task', lo, lo + 3)
                if task.group(2) in 'xX':
                    self._tag('done', offset + task.end(), offset + len(line))
            for m in BOLD.finditer(line):
                self._tag('bold', offset + m.start(), offset + m.end())
            for m in CODE.finditer(line):
                self._tag('code', offset + m.start(), offset + m.end())
            offset += len(line) + 1

    def _tag(self, name: str, lo: int, hi: int) -> None:
        b = self.buffer
        b.apply_tag_by_name(name, b.get_iter_at_offset(lo), b.get_iter_at_offset(hi))

    # --- the list ---

    def refresh_list(self, select: Optional[str] = None) -> None:
        keep = select or self.current_id
        query = self.search.get_text().strip()
        notes = self.store.list(query)
        drafts = set()
        if self.current_id and not any(n.id == self.current_id for n in notes) and not query:
            notes.insert(0, Note(self.current_id, core.note_title(self._text()), self._text(),
                                 False, 0.0))
            drafts.add(self.current_id)
        total = len(self.store.list()) if query else len(notes) - len(drafts)
        self.loading = True
        try:
            child = self.list.get_first_child()
            while child is not None:
                nxt = child.get_next_sibling()
                self.list.remove(child)
                child = nxt
            self.rows = []
            for note in notes:
                row = NoteRow(note, note.id in drafts)
                self.list.append(row)
                self.rows.append(row)
                if note.id == keep:
                    self.list.select_row(row)
        finally:
            self.loading = False
        self.count.set_text(t('notes.count', n=total))
        if not notes:
            self.empty.set_text(t('notes.none', query=query) if query else t('notes.empty_list'))
        else:
            self.empty.set_text('')
        self.empty.set_visible(not notes)
        self._refresh_pin()

    def _on_row_selected(self, _list, row) -> None:
        if self.loading or row is None or row.note.id == self.current_id:
            return
        self.open_note(row.note.id)

    # --- opening, creating, saving ---

    def _text(self) -> str:
        start, end = self.buffer.get_bounds()
        return self.buffer.get_text(start, end, False)

    def open_note(self, note_id: str) -> None:
        self.flush()
        note = self.store.load(note_id)
        self.current_id = note_id
        self.loading = True
        self.buffer.set_text(note.body if note else '')
        self.loading = False
        self.restyle()
        self.dirty = False
        self.set_status(t('notes.saved'), 'ok')
        self._select_row(note_id)
        self._refresh_pin()

    def new_note(self) -> None:
        self.flush()
        self.current_id = self.store.new_id()
        self.loading = True
        self.buffer.set_text('')
        self.loading = False
        self.dirty = False
        self.set_status(t('notes.saved'), 'ok')
        self.refresh_list(self.current_id)
        self.view.grab_focus()

    def _select_row(self, note_id: str) -> None:
        for row in self.rows:
            if row.note.id == note_id:
                self.loading = True
                self.list.select_row(row)
                self.loading = False
                return

    def _on_changed(self, _buffer) -> None:
        if self.loading:
            return
        self.dirty = True
        self.restyle()
        self.set_status(t('notes.saving'))
        if self.save_id:
            GLib.source_remove(self.save_id)
        self.save_id = GLib.timeout_add(SAVE_DELAY_MS, self._autosave)

    def _autosave(self) -> bool:
        self.save_id = 0
        self.flush()
        self.refresh_list()
        return False

    def flush(self) -> bool:
        """Write the open note now if it changed."""
        if self.save_id:
            GLib.source_remove(self.save_id)
            self.save_id = 0
        if not self.dirty or not self.current_id:
            return True
        ok = self.store.save(self.current_id, self._text())
        if ok:
            self.dirty = False
            self.set_status(t('notes.saved'), 'ok')
        else:
            self.set_status(t('notes.save_failed'), 'warn')
            if self.glitch:
                self.glitch.now(self.status, self.view.get_parent())
        return ok

    def _on_close(self, *_) -> bool:
        self.flush()
        return False

    # --- pin, delete, undo ---

    def _current_note(self) -> Optional[Note]:
        return self.store.load(self.current_id) if self.current_id else None

    def _refresh_pin(self) -> None:
        note = self._current_note()
        on = bool(note and note.pinned)
        self.pin_button.set_label(t('notes.unpin' if on else 'notes.pin'))
        if on:
            self.pin_button.add_css_class('on')
        else:
            self.pin_button.remove_css_class('on')
        self.pin_button.set_sensitive(note is not None)
        self.delete_button.set_sensitive(note is not None)

    def toggle_pin(self) -> None:
        self.flush()
        note = self._current_note()
        if note is None:
            return
        self.store.set_pinned(note.id, not note.pinned)
        self.refresh_list()

    def delete_current(self) -> None:
        self.flush()
        note = self._current_note()
        if note is None:
            return
        if self.store.delete(note.id):
            self.undo_id = note.id
            self.undo_button.set_visible(True)
            self.current_id = None
            self.refresh_list()
            self.loading = True
            self.buffer.set_text('')
            self.loading = False
            nxt = self.rows[0].note.id if self.rows else None
            if nxt:
                self.open_note(nxt)
            else:
                self.new_note()
            self.set_status(t('notes.deleted'), 'warn')
            if self.glitch:
                self.glitch.now(self.status)

    def undo_delete(self) -> None:
        if self.undo_id and self.store.restore(self.undo_id):
            restored = self.undo_id
            self.undo_id = None
            self.undo_button.set_visible(False)
            self.refresh_list()
            self.open_note(restored)
            self.set_status(t('notes.restored'), 'ok')

    # --- keys and status ---

    def _on_key(self, _ctl, keyval, _code, state):
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        if ctrl and keyval in (Gdk.KEY_n, Gdk.KEY_N):
            self.new_note()
            return True
        if ctrl and keyval in (Gdk.KEY_f, Gdk.KEY_F):
            self.search.grab_focus()
            return True
        if ctrl and keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.toggle_task()
            return True
        if keyval == Gdk.KEY_Escape and self.search.get_text():
            self.search.set_text('')
            return True
        return False

    def toggle_task(self) -> None:
        b = self.buffer
        it = b.get_iter_at_mark(b.get_insert())
        line = it.get_line()
        found = b.get_iter_at_line(line)
        start = found[1] if isinstance(found, tuple) else found     # GTK 4 returns (ok, iter)
        end = start.copy()
        if not end.ends_line():
            end.forward_to_line_end()
        text = b.get_text(start, end, False)
        m = TASK.match(text)
        if not m:
            return
        box = b.get_iter_at_offset(start.get_offset() + len(m.group(1)) + 1)
        box_end = b.get_iter_at_offset(box.get_offset() + 1)
        at = start.get_offset() + len(m.group(1)) + 1
        self.loading = True          # the delete alone must not restyle or save a half edit
        try:
            b.delete(box, box_end)
        finally:
            self.loading = False
        b.insert(b.get_iter_at_offset(at), ' ' if m.group(2) in 'xX' else 'x')

    def set_status(self, text: str, kind: str = '') -> None:
        self.status.set_text(text)
        for k in ('ok', 'warn'):
            self.status.remove_css_class(k)
        if kind:
            self.status.add_css_class(kind)
