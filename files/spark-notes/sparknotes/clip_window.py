"""The clipboard popup (Meta+V): a search box and the kept copies, newest first, pinned ones at
the top. Enter or a click copies an item again and closes the popup.

Keys: type to search (from anywhere), Down moves into the list, Enter copies, Delete removes the
selected item, Ctrl+P pins it, Esc clears the search and then closes.
"""

from typing import Callable, Tuple

import gi
from gi.repository import Gdk, GLib, Gtk

from . import core
from .core import History, Item
from .text import t


def _thumbnail(path: str):
    """(a small texture of at most 120 x 56, "W x H"), so a big screenshot doesn't fill the
    list. Falls back to the whole picture when GdkPixbuf isn't there."""
    try:
        gi.require_version('GdkPixbuf', '2.0')
        from gi.repository import GdkPixbuf
        info = GdkPixbuf.Pixbuf.get_file_info(path)
        dims = f"{info[1]} x {info[2]}" if info and info[0] else ''
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 120, 56, True)
        return Gdk.Texture.new_for_pixbuf(pixbuf), dims
    except (ImportError, ValueError):
        full = Gdk.Texture.new_from_filename(path)
        return full, f"{full.get_width()} x {full.get_height()}"


class ClipRow(Gtk.ListBoxRow):
    def __init__(self, item: Item, history: History, on_pin, on_delete):
        super().__init__()
        self.item = item
        if item.pinned:
            self.add_css_class('pinned')
        box = Gtk.Box(spacing=8)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(box, f'set_margin_{side}')(6)

        if item.kind == 'image':
            body = Gtk.Box(spacing=8, hexpand=True)
            try:
                path = history.image_path(item)
                texture, dims = _thumbnail(path)
                pic = Gtk.Picture.new_for_paintable(texture)
                pic.add_css_class('thumb')
                pic.set_can_shrink(True)
                pic.set_content_fit(Gtk.ContentFit.SCALE_DOWN)
                pic.set_halign(Gtk.Align.START)
                body.append(pic)
            except (GLib.Error, OSError):
                dims = ''
            label = Gtk.Label(label=f"{t('clip.image')}  {dims}".strip(), xalign=0,
                              valign=Gtk.Align.CENTER)
            label.add_css_class('micro')
            body.append(label)
        else:
            body = Gtk.Label(label=item.preview(), xalign=0, hexpand=True, wrap=True,
                             wrap_mode=2, lines=3, ellipsize=3, max_width_chars=48)
            body.add_css_class('preview')
        box.append(body)

        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3,
                       valign=Gtk.Align.CENTER)
        meta = Gtk.Label(label=f"{core.ago(item.time)}  {core.human_size(item.size)}", xalign=1)
        meta.add_css_class('meta')
        side.append(meta)
        buttons = Gtk.Box(spacing=3, halign=Gtk.Align.END)
        self.pin_button = Gtk.Button(label=t('clip.unpin' if item.pinned else 'clip.pin'))
        self.pin_button.add_css_class('mini')
        if item.pinned:
            self.pin_button.add_css_class('on')
        self.pin_button.set_tooltip_text(t('clip.pin_tip'))
        self.pin_button.set_focusable(False)
        self.pin_button.connect('clicked', lambda *_: on_pin(item))
        buttons.append(self.pin_button)
        self.delete_button = Gtk.Button(label=t('clip.delete'))
        self.delete_button.add_css_class('mini')
        self.delete_button.set_tooltip_text(t('clip.delete_tip'))
        self.delete_button.set_focusable(False)
        self.delete_button.connect('clicked', lambda *_: on_delete(item))
        buttons.append(self.delete_button)
        side.append(buttons)
        box.append(side)
        self.set_child(box)


class ClipWindow(Gtk.ApplicationWindow):

    def __init__(self, app, settings: dict, history: History,
                 on_copy: Callable[[Item], Tuple[bool, str]],
                 on_pause: Callable[[bool], None],
                 on_open_notes: Callable[[], None], glitch=None):
        super().__init__(application=app)
        self.add_css_class('spark-notes')
        self.add_css_class('popup')
        self.settings = settings
        self.history = history
        self.on_copy = on_copy
        self.on_pause = on_pause
        self.on_open_notes = on_open_notes
        self.glitch = glitch
        self.keep_open = False
        self.rows = []
        self.set_title("Spark Notes: " + t('clip.title').title())
        self.set_decorated(False)
        self.set_default_size(460, 520)
        self.set_resizable(False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(box, f'set_margin_{side}')(10)
        self.set_child(box)

        head = Gtk.Box(spacing=8)
        self.heading = Gtk.Label(label=t('clip.title'), xalign=0, hexpand=True)
        self.heading.add_css_class('heading')
        head.append(self.heading)
        self.count = Gtk.Label(label='', xalign=1)
        self.count.add_css_class('micro')
        head.append(self.count)
        box.append(head)

        self.entry = Gtk.SearchEntry()
        self.entry.add_css_class('search')
        self.entry.set_placeholder_text(t('clip.search'))
        self.entry.set_search_delay(60)
        self.entry.connect('search-changed', lambda *_: self.reload())
        self.entry.connect('activate', self._on_enter)
        self.entry.connect('stop-search', lambda *_: self.close_popup())
        self.entry.set_key_capture_widget(self)
        box.append(self.entry)

        self.scroll = Gtk.ScrolledWindow(vexpand=True)
        self.scroll.set_min_content_height(340)
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.list = Gtk.ListBox()
        self.list.add_css_class('rows')
        self.list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list.set_activate_on_single_click(True)
        self.list.connect('row-activated', lambda _l, row: self._copy(row.item))
        self.empty = Gtk.Label(label='', xalign=0, wrap=True)
        self.empty.add_css_class('empty')
        self.empty.set_margin_top(12)
        holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        holder.append(self.list)
        holder.append(self.empty)
        self.scroll.set_child(holder)
        box.append(self.scroll)

        footer = Gtk.Box(spacing=6)
        footer.add_css_class('footer')
        self.status = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)
        self.status.add_css_class('status')
        footer.append(self.status)
        self.pause_button = Gtk.Button()
        self.pause_button.add_css_class('action')
        self.pause_button.set_tooltip_text(t('clip.pause_tip'))
        self.pause_button.set_focusable(False)
        self.pause_button.connect('clicked', self._on_pause)
        footer.append(self.pause_button)
        clear = Gtk.Button(label=t('clip.clear'))
        clear.add_css_class('action')
        clear.set_tooltip_text(t('clip.clear_tip'))
        clear.set_focusable(False)
        clear.connect('clicked', self._on_clear)
        footer.append(clear)
        notes = Gtk.Button(label=t('clip.notes'))
        notes.add_css_class('action')
        notes.set_tooltip_text(t('clip.notes_tip'))
        notes.set_focusable(False)
        notes.connect('clicked', lambda *_: (self.close_popup(), self.on_open_notes()))
        footer.append(notes)
        box.append(footer)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self._on_key)
        self.add_controller(keys)
        self.connect('notify::is-active', self._on_active)
        self._refresh_pause()
        self.show_default()

    # --- showing and hiding ---

    def show_default(self) -> None:
        self.entry.set_text('')
        self.reload()
        self.set_status(t('clip.hint'))
        self.entry.grab_focus()

    def close_popup(self) -> None:
        self.set_visible(False)

    def _on_active(self, *_):
        if not self.is_active() and not self.keep_open and self.get_visible():
            GLib.timeout_add(180, self._maybe_close)

    def _maybe_close(self) -> bool:
        if not self.is_active() and not self.keep_open and self.get_visible():
            self.close_popup()
        return False

    def _on_key(self, _ctl, keyval, _code, state):
        if keyval == Gdk.KEY_Escape:
            if self.entry.get_text():
                self.entry.set_text('')
            else:
                self.close_popup()
            return True
        selected = self.list.get_selected_row()
        if keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down) and self.entry.has_focus() and self.rows:
            self.list.select_row(self.rows[0])
            self.rows[0].grab_focus()
            return True
        if keyval == Gdk.KEY_Delete and selected is not None:
            self.delete_item(selected.item)
            return True
        if keyval == Gdk.KEY_p and state & Gdk.ModifierType.CONTROL_MASK and selected is not None:
            self.toggle_pin(selected.item)
            return True
        return False

    # --- the list ---

    def reload(self) -> None:
        query = self.entry.get_text().strip()
        items = self.history.search(query)
        child = self.list.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.list.remove(child)
            child = nxt
        self.rows = []
        for item in items:
            row = ClipRow(item, self.history, self.toggle_pin, self.delete_item)
            self.list.append(row)
            self.rows.append(row)
        total = len(self.history.items())
        self.count.set_text(t('clip.count', n=total))
        if self.rows:
            self.empty.set_text('')
            self.empty.set_visible(False)
            if query:
                self.list.select_row(self.rows[0])
        else:
            self.empty.set_visible(True)
            if query:
                self.empty.set_text(t('clip.none', query=query))
            elif self.settings.get('paused'):
                self.empty.set_text(t('clip.paused_empty'))
            else:
                self.empty.set_text(t('clip.empty'))
        self.scroll.get_vadjustment().set_value(0)

    def _on_enter(self, _entry) -> None:
        row = self.list.get_selected_row() or (self.rows[0] if self.rows else None)
        if row is not None:
            self._copy(row.item)

    def _copy(self, item: Item) -> None:
        if self.glitch:
            self.glitch.now(self.heading)
        ok, why = self.on_copy(item)
        if ok:
            self.close_popup()
        else:
            self.set_status(t('clip.copy_failed', why=why), 'warn')
            if self.glitch:
                self.glitch.now(self.status)

    def toggle_pin(self, item: Item) -> None:
        self.history.set_pinned(item.id, not item.pinned)
        self.reload()

    def delete_item(self, item: Item) -> None:
        self.history.delete(item.id)
        self.reload()

    # --- footer ---

    def _on_clear(self, *_) -> None:
        n = self.history.clear(keep_pinned=True)
        self.reload()
        self.set_status(t('clip.cleared', n=n) if n else t('clip.cleared_none'),
                        'ok' if n else '')
        if self.glitch and n:
            self.glitch.now(self.heading)

    def _on_pause(self, *_) -> None:
        paused = not self.settings.get('paused')
        self.settings['paused'] = paused
        self.on_pause(paused)
        self._refresh_pause()
        self.set_status(t('clip.now_paused' if paused else 'clip.now_keeping'),
                        'warn' if paused else 'ok')
        if self.glitch:
            self.glitch.now(self.heading)
        self.reload()

    def _refresh_pause(self) -> None:
        paused = bool(self.settings.get('paused'))
        self.pause_button.set_label(t('clip.paused' if paused else 'clip.pause'))
        if paused:
            self.pause_button.add_css_class('paused')
        else:
            self.pause_button.remove_css_class('paused')

    def set_status(self, text: str, kind: str = '') -> None:
        self.status.set_text(text)
        for k in ('ok', 'warn'):
            self.status.remove_css_class(k)
        if kind:
            self.status.add_css_class(kind)

    def refresh(self) -> None:
        """Called when the popup opens again: new copies, current pause state."""
        self._refresh_pause()
        self.show_default()
