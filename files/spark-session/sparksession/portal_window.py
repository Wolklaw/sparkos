"""The dialogs of spark-portal (GTK4, house style): one window built from a plain `spec` dict.

  kind, title, subtitle, body        the words ('kind' is access, account, launcher or print)
  grant, deny                        button labels
  choices   [{id, label, options: [[id, label]], initial}]   a check box or a menu each
  name      {value, editable}        a field for the launcher's name
  printers  [{name, label}], default_printer, copies          the print dialog
  icon      a serialized GIcon (Variant) or None

show(spec, done) calls done(accepted, values) once; values is {choices: {id: value}, name,
printer, copies}. It returns an object with close(), which ends the dialog as a refusal.

Tests set SPARK_PORTAL_TEST_DIALOG to a JSON answer, {"accept": true, "values": {...}} or one
per kind ({"access": {...}, "*": {...}}; a list gives one answer per request), and no window is shown. SPARK_PORTAL_TEST_LOG is
a file that gets every spec as a JSON line. "delay_ms" holds the answer back."""

import json
import os

from .strings import t


def _json_default(value):
    return str(value)


def test_answers(environ=None):
    """The parsed SPARK_PORTAL_TEST_DIALOG, or None when it is not set."""
    env = os.environ if environ is None else environ
    raw = env.get('SPARK_PORTAL_TEST_DIALOG')
    if not raw:
        return None
    return json.loads(raw)


_used = {}


class _Handle:
    def __init__(self, close):
        self.close = close


def show(spec: dict, done) -> _Handle:
    answers = test_answers()
    if answers is not None:
        return _show_test(spec, done, answers)
    return _show_window(spec, done)


def _show_test(spec, done, answers) -> _Handle:
    from gi.repository import GLib
    log_path = os.environ.get('SPARK_PORTAL_TEST_LOG')
    if log_path:
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(spec, default=_json_default) + '\n')
    answer = answers.get(spec['kind']) or answers.get('*') or answers
    if isinstance(answer, list):                  # one answer per request, the last repeats
        used = _used.get(spec['kind'], 0)
        _used[spec['kind']] = used + 1
        answer = answer[min(used, len(answer) - 1)]
    state = {'done': False, 'source': 0}

    def finish(accepted, values):
        if state['done']:
            return False
        state['done'] = True
        done(accepted, values)
        return False

    state['source'] = GLib.timeout_add(int(answer.get('delay_ms', 0)), finish,
                                       bool(answer.get('accept', True)),
                                       dict(answer.get('values') or {}))

    def close():
        if not state['done']:
            state['done'] = True
            GLib.source_remove(state['source'])
    return _Handle(close)


def _show_window(spec, done) -> _Handle:
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gio, Gtk
    from . import style
    if not Gtk.init_check():
        done(False, {})
        return _Handle(lambda: None)
    style.install()
    state = {'done': False}
    win = Gtk.Window()
    win.add_css_class('spark-sec')
    win.set_title(spec.get('title') or '')
    win.set_default_size(460, -1)
    win.set_resizable(False)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    for side in ('top', 'bottom', 'start', 'end'):
        getattr(box, f'set_margin_{side}')(20)
    box.add_css_class('panel')
    win.set_child(box)

    def label(text, css, selectable=False):
        w = Gtk.Label(label=text, xalign=0, wrap=True, max_width_chars=60, selectable=selectable)
        w.add_css_class(css)
        return w

    box.append(label((spec.get('title') or '').upper(), 'heading'))
    if spec.get('subtitle'):
        box.append(label(spec['subtitle'], 'micro'))
    icon = None
    if spec.get('icon') is not None:
        try:
            icon = Gio.Icon.deserialize(spec['icon'])
        except Exception:                                   # noqa: BLE001
            icon = None
    if icon is not None:
        image = Gtk.Image.new_from_gicon(icon)
        image.set_pixel_size(64)
        image.set_halign(Gtk.Align.START)
        box.append(image)
    if spec.get('body'):
        body = label(spec['body'], 'message')
        body.set_margin_top(6)
        body.set_margin_bottom(6)
        box.append(body)

    widgets = {'choices': {}}
    for choice in spec.get('choices') or []:
        if choice['options']:
            box.append(label(choice['label'].upper(), 'micro'))
            ids = [o[0] for o in choice['options']]
            drop = Gtk.DropDown.new_from_strings([o[1] for o in choice['options']])
            if choice.get('initial') in ids:
                drop.set_selected(ids.index(choice['initial']))
            widgets['choices'][choice['id']] = ('menu', drop, ids)
            box.append(drop)
        else:
            check = Gtk.CheckButton(label=choice['label'], active=choice.get('initial') == 'true')
            widgets['choices'][choice['id']] = ('check', check, None)
            box.append(check)
    if spec.get('name') is not None:
        box.append(label(t('portal.launcher.name'), 'micro'))
        entry = Gtk.Entry(text=spec['name'].get('value', ''),
                          editable=bool(spec['name'].get('editable', True)))
        entry.set_activates_default(True)
        widgets['name'] = entry
        box.append(entry)
    printers = spec.get('printers')
    if printers is not None:
        if not printers:
            box.append(label(t('portal.print.none'), 'status warn'))
        else:
            box.append(label(t('portal.print.printer'), 'micro'))
            drop = Gtk.DropDown.new_from_strings([p['label'] for p in printers])
            names = [p['name'] for p in printers]
            if spec.get('default_printer') in names:
                drop.set_selected(names.index(spec['default_printer']))
            widgets['printer'] = (drop, names)
            box.append(drop)
            box.append(label(t('portal.print.copies'), 'micro'))
            spin = Gtk.SpinButton.new_with_range(1, 99, 1)
            spin.set_value(int(spec.get('copies') or 1))
            widgets['copies'] = spin
            box.append(spin)

    def values():
        out = {'choices': {}}
        for cid, (kind, widget, ids) in widgets['choices'].items():
            out['choices'][cid] = (('true' if widget.get_active() else 'false') if kind == 'check'
                                   else ids[widget.get_selected()])
        if 'name' in widgets:
            out['name'] = widgets['name'].get_text()
        if 'printer' in widgets:
            drop, names = widgets['printer']
            out['printer'] = names[drop.get_selected()]
            out['copies'] = int(widgets['copies'].get_value())
        return out

    def finish(accepted):
        if state['done']:
            return
        state['done'] = True
        got = values() if accepted else {}
        win.destroy()
        done(accepted, got)

    row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
    row.set_margin_top(8)
    deny = Gtk.Button(label=spec.get('deny') or t('portal.deny'))
    deny.connect('clicked', lambda *_: finish(False))
    grant = Gtk.Button(label=spec.get('grant') or t('portal.allow'))
    grant.add_css_class('primary')
    grant.connect('clicked', lambda *_: finish(True))
    grant.set_sensitive(printers is None or bool(printers))
    row.append(deny)
    row.append(grant)
    box.append(row)
    win.set_default_widget(grant)
    win.connect('close-request', lambda *_: finish(False) or False)
    win.present()

    def close():
        if not state['done']:
            state['done'] = True
            win.destroy()
    return _Handle(close)
