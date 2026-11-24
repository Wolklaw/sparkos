"""The picker window: a search box, category tabs, a grid of characters, and a status line.

Keys: type to search (from anywhere), Enter picks the first result, Down moves into the grid,
arrows move around it, Enter picks, Esc closes. Right-click a hand or person for skin tones.
"""

from typing import Callable, List, Optional, Tuple

from gi.repository import GLib, Gtk

from . import core
from .core import Entry
from .text import t

TAB_GLYPHS = [          # (id, glyph, what it holds)
    ('recent', '\U0001F552', None),
    ('smileys', '\U0001F600', None), ('people', '\U0001F44B', None),
    ('nature', '\U0001F43B', None), ('food', '\U0001F354', None),
    ('travel', '\U0001F697', None), ('activities', '⚽', None),
    ('objects', '\U0001F4A1', None), ('symbols', '\U0001F523', None),
    ('flags', '\U0001F3C1', None), ('math', 'Ω', None),     # math = all the text symbols
]
COLUMNS = 9
TONE_HANDS = '✋'


class Cell(Gtk.FlowBoxChild):
    def __init__(self, entry: Entry, char: str, name: str):
        super().__init__()
        self.entry = entry
        self.char = char
        self.name = name
        label = Gtk.Label(label=char)
        label.add_css_class('cell')
        if entry is not None and entry.kind == 'symbol':
            label.add_css_class('symbolcell')
        self.set_child(label)
        self.set_tooltip_text(name)
        self.add_css_class('cellbox')


class PickerWindow(Gtk.ApplicationWindow):

    def __init__(self, app, settings: dict, on_pick: Callable[[str, Optional[Entry]], None],
                 on_enable_paste: Optional[Callable[[], None]] = None,
                 on_tone: Optional[Callable[[int], None]] = None, glitch=None):
        super().__init__(application=app)
        self.add_css_class('spark-emoji')
        self.settings = settings
        self.on_pick = on_pick
        self.on_enable_paste = on_enable_paste
        self.on_tone = on_tone
        self.glitch = glitch
        self.keep_open = False        # true while the desktop asks a question
        self.current = 'smileys'
        self.cells: List[Cell] = []
        self.set_title("Spark Emoji")
        self.set_decorated(False)
        self.set_default_size(440, 470)
        self.set_resizable(False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(box, f'set_margin_{side}')(10)
        self.set_child(box)

        self.entry = Gtk.SearchEntry()
        self.entry.add_css_class('search')
        self.entry.set_placeholder_text(t('search.placeholder'))
        self.entry.set_search_delay(60)
        self.entry.connect('search-changed', self._on_search)
        self.entry.connect('activate', self._on_enter)
        self.entry.connect('stop-search', lambda *_: self.close_picker())
        self.entry.set_key_capture_widget(self)
        box.append(self.entry)

        self.tabs = Gtk.Box(spacing=2)
        self.tabs.add_css_class('tabs')
        self.tab_buttons = {}
        first = None
        for tab_id, glyph, _ in TAB_GLYPHS:
            b = Gtk.ToggleButton(label=glyph)
            b.add_css_class('tab')
            b.set_focus_on_click(False)
            b.set_tooltip_text(self._tab_title(tab_id))
            if first is None:
                first = b
            else:
                b.set_group(first)
            b.connect('toggled', self._on_tab, tab_id)
            self.tabs.append(b)
            self.tab_buttons[tab_id] = b
        box.append(self.tabs)

        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_vexpand(True)
        self.scroll.set_min_content_height(300)
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.scroll.set_child(self.content)
        box.append(self.scroll)

        footer = Gtk.Box(spacing=6)
        footer.add_css_class('footer')
        self.status = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)
        self.status.add_css_class('status')
        footer.append(self.status)
        self.paste_button = Gtk.Button(label=t('paste.enable'))
        self.paste_button.add_css_class('link')
        self.paste_button.set_tooltip_text(t('paste.enable_tip'))
        self.paste_button.connect('clicked', lambda *_: self.on_enable_paste and
                                  self.on_enable_paste())
        footer.append(self.paste_button)
        self.tone_button = Gtk.MenuButton()
        self.tone_button.add_css_class('tab')
        self.tone_button.set_tooltip_text(t('tip.tone'))
        self.tone_button.set_popover(self._tone_popover())
        footer.append(self.tone_button)
        box.append(footer)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self._on_key)
        self.add_controller(keys)
        self.connect('notify::is-active', self._on_active)
        self._refresh_tone_label()
        self.show_default()

    # --- showing and hiding ---

    def show_default(self) -> None:
        self.entry.set_text('')
        recents = core.load_recents()
        self._select_tab('recent' if recents else 'smileys')
        self.set_status(t('hint.idle'))
        self.entry.grab_focus()

    def close_picker(self) -> None:
        self.set_visible(False)

    def _on_active(self, *_):
        if not self.is_active() and not self.keep_open and self.get_visible():
            GLib.timeout_add(180, self._maybe_close)

    def _maybe_close(self) -> bool:
        if not self.is_active() and not self.keep_open and self.get_visible():
            self.close_picker()
        return False

    def _on_key(self, _ctl, keyval, _code, _state):
        from gi.repository import Gdk
        if keyval == Gdk.KEY_Escape:
            if self.entry.get_text():
                self.entry.set_text('')
            else:
                self.close_picker()
            return True
        if keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down) and self.entry.has_focus() and self.cells:
            self.cells[0].grab_focus()
            return True
        return False

    # --- tabs and the grid ---

    @staticmethod
    def _tab_title(tab_id: str) -> str:
        if tab_id == 'recent':
            return t('group.recent')
        if tab_id == 'math':
            return t('about.symbols')
        for g in core.groups():
            if g.id == tab_id and g.kind == 'emoji':
                return g.title()
        return tab_id

    def _on_tab(self, button, tab_id):
        if button.get_active() and not self.entry.get_text().strip():
            self._show_tab(tab_id)

    def _select_tab(self, tab_id: str) -> None:
        button = self.tab_buttons[tab_id]
        button.set_active(True)
        self._show_tab(tab_id)

    def _show_tab(self, tab_id: str) -> None:
        self.current = tab_id
        tone = self.settings.get('tone', -1)
        if tab_id == 'recent':
            entries = [(c, core.find_entry(c)) for c in core.load_recents()]
            sections = [(t('group.recent'), [self._cell_for(c, e, tone, raw=True)
                                             for c, e in entries])]
        elif tab_id == 'math':
            sections = [(g.title(), [self._cell_for(e.char, e, tone) for e in g.entries])
                        for g in core.groups() if g.kind == 'symbol']
        else:
            sections = [(g.title(), [self._cell_for(e.char, e, tone) for e in g.entries])
                        for g in core.groups() if g.id == tab_id and g.kind == 'emoji']
        self._fill(sections, empty=t('recent.empty') if tab_id == 'recent' else '')

    def _cell_for(self, char: str, entry: Optional[Entry], tone: int, raw: bool = False) -> Cell:
        shown = char if raw or entry is None else entry.with_tone(tone)
        return Cell(entry, shown, entry.name() if entry else char)

    def _fill(self, sections: List[Tuple[str, List[Cell]]], empty: str = '') -> None:
        child = self.content.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.content.remove(child)
            child = nxt
        self.cells = []
        shown = False
        for title, cells in sections:
            if not cells:
                continue
            shown = True
            heading = Gtk.Label(label=title.upper(), xalign=0)
            heading.add_css_class('group-title')
            heading.set_margin_top(4)
            self.content.append(heading)
            flow = Gtk.FlowBox()
            flow.set_selection_mode(Gtk.SelectionMode.NONE)
            flow.set_min_children_per_line(COLUMNS)
            flow.set_max_children_per_line(COLUMNS)
            flow.set_homogeneous(True)
            flow.set_activate_on_single_click(True)
            flow.connect('child-activated', self._on_activated)
            for cell in cells:
                self._wire(cell)
                flow.append(cell)
            self.content.append(flow)
            self.cells.extend(cells)
        if not shown:
            label = Gtk.Label(label=empty, xalign=0, wrap=True)
            label.add_css_class('empty')
            label.set_margin_top(12)
            self.content.append(label)
        if self.cells and self.entry.get_text().strip():
            self.cells[0].get_child().add_css_class('first')
        vadj = self.scroll.get_vadjustment()
        vadj.set_value(0)

    def _wire(self, cell: Cell) -> None:
        motion = Gtk.EventControllerMotion()
        motion.connect('enter', lambda *_: self.set_status(self._describe(cell)))
        cell.add_controller(motion)
        right = Gtk.GestureClick()
        right.set_button(3)
        right.connect('pressed', lambda g, n, x, y: self._tone_menu(cell))
        cell.add_controller(right)

    @staticmethod
    def _describe(cell: Cell) -> str:
        return f"{cell.char}  {cell.name}"

    # --- search ---

    def _on_search(self, entry) -> None:
        query = entry.get_text().strip()
        if not query:
            self._select_tab(self.current)
            self.set_status(t('hint.idle'))
            return
        tone = self.settings.get('tone', -1)
        found = core.search(query)
        cells = [self._cell_for(e.char, e, tone) for e in found]
        self._fill([(f"{len(found)}", cells)] if cells else [],
                   empty=t('search.none', query=query))

    def _on_enter(self, _entry) -> None:
        if self.cells:
            self._pick(self.cells[0])

    def _on_activated(self, _flow, cell) -> None:
        self._pick(cell)

    def _pick(self, cell: Cell) -> None:
        if self.glitch:
            self.glitch.now(cell.get_child())
        self.on_pick(cell.char, cell.entry)

    # --- skin tones ---

    def _tone_menu(self, cell: Cell) -> None:
        entry = cell.entry
        if entry is None or not entry.tones:
            return
        pop = Gtk.Popover()
        row = Gtk.Box(spacing=2)
        for char in (entry.char,) + entry.tones:
            b = Gtk.Button(label=char)
            b.add_css_class('cell')
            b.connect('clicked', lambda _b, c=char, p=pop: (p.popdown(), self.on_pick(c, entry)))
            row.append(b)
        pop.set_child(row)
        pop.set_parent(cell)
        pop.connect('closed', lambda p: GLib.idle_add(p.unparent))
        pop.popup()

    def _tone_popover(self) -> Gtk.Popover:
        pop = Gtk.Popover()
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for tone in range(-1, 5):
            hand = TONE_HANDS + (core.TONES[tone] if tone >= 0 else '')
            name = t('tone.default') if tone < 0 else t(f'tone.{tone}')
            b = Gtk.Button(label=f"{hand}  {name}")
            b.add_css_class('link')
            b.connect('clicked', lambda _b, n=tone, p=pop: (p.popdown(), self.set_tone(n)))
            col.append(b)
        pop.set_child(col)
        return pop

    def set_tone(self, tone: int) -> None:
        self.settings['tone'] = tone
        self._refresh_tone_label()
        if self.on_tone:
            self.on_tone(tone)
        if self.entry.get_text().strip():
            self._on_search(self.entry)
        else:
            self._show_tab(self.current)

    def _refresh_tone_label(self) -> None:
        tone = self.settings.get('tone', -1)
        self.tone_button.set_label(TONE_HANDS + (core.TONES[tone] if tone >= 0 else ''))

    # --- status ---

    def set_status(self, text: str, kind: str = '') -> None:
        self.status.set_text(text)
        for k in ('ok', 'warn'):
            self.status.remove_css_class(k)
        if kind:
            self.status.add_css_class(kind)

    def show_paste_button(self, visible: bool) -> None:
        self.paste_button.set_visible(visible)
