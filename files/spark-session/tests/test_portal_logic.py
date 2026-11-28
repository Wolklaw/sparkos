"""spark-portal's plain parts: no bus, no window."""

import json
import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from gi.repository import GLib  # noqa: E402

from sparksession import portal_backend as backend  # noqa: E402
from sparksession import portal_logic as logic  # noqa: E402
from sparksession import strings  # noqa: E402


def vardict(**kw):
    return GLib.Variant('a{sv}', kw)


class Settings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {'XDG_CONFIG_HOME': self.tmp.name, 'HOME': self.tmp.name}
        os.makedirs(os.path.join(self.tmp.name, 'spark'))

    def tearDown(self):
        self.tmp.cleanup()

    def test_appearance(self):
        v = logic.appearance_values(self.env)
        self.assertEqual(v['color-scheme'].unpack(), 1)
        self.assertEqual(v['contrast'].unpack(), 0)
        self.assertEqual(v['reduced-motion'].unpack(), 0)
        self.assertEqual(v['accent-color'].get_type_string(), '(ddd)')
        r, g, b = v['accent-color'].unpack()
        self.assertEqual((round(r * 255), round(g * 255), round(b * 255)), (0x3d, 0xe8, 0xc8))

    def test_reduced_motion(self):
        path = logic.appearance_file(self.env)
        for text, want in (('{"animations": false}', 1), ('{"animations": true}', 0),
                           ('{}', 0), ('not json', 0), ('[]', 0)):
            with open(path, 'w') as f:
                f.write(text)
            self.assertEqual(logic.reduced_motion(self.env), want, text)

    def test_namespace_globs(self):
        m = logic.namespace_matches
        self.assertTrue(m('org.gnome.desktop.interface', []))
        self.assertTrue(m('org.gnome.desktop.interface', ['org.gnome.*']))
        self.assertTrue(m('org.freedesktop.appearance', ['org.freedesktop.appearance']))
        self.assertTrue(m('anything', ['*']))
        self.assertFalse(m('org.gnome.desktop.interface', ['org.gnome']))
        self.assertFalse(m('org.freedesktop.appearance', ['org.gnome.*']))

    def test_store_read(self):
        store = logic.SettingsStore(environ=self.env)
        self.assertEqual(store.read('org.freedesktop.appearance', 'color-scheme').unpack(), 1)
        self.assertIsNone(store.read('org.freedesktop.appearance', 'nothing'))
        self.assertIsNone(store.read('no.such.namespace', 'color-scheme'))
        got = store.read_all(['org.freedesktop.*'])
        self.assertEqual(list(got), ['org.freedesktop.appearance'])


class Inhibit(unittest.TestCase):
    def test_flags(self):
        self.assertEqual(logic.inhibit_kinds(0), [])
        self.assertEqual(logic.inhibit_kinds(15), ['logout', 'user-switch', 'suspend', 'idle'])
        self.assertEqual(logic.logind_what(logic.INHIBIT_SUSPEND), 'sleep')
        self.assertEqual(logic.logind_what(logic.INHIBIT_LOGOUT), 'shutdown')
        self.assertEqual(logic.logind_what(logic.INHIBIT_USER_SWITCH), 'shutdown')
        self.assertEqual(logic.logind_what(logic.INHIBIT_IDLE), '')

    def test_registry(self):
        with tempfile.TemporaryDirectory() as d:
            path = logic.inhibit_registry_path({'XDG_RUNTIME_DIR': d})
            self.assertEqual(path, os.path.join(d, 'spark-wl', 'portal-inhibit.json'))
            logic.write_inhibit_registry(path, [{'app_id': 'a', 'reason': 'r', 'flags': 1}])
            with open(path) as f:
                self.assertEqual(json.load(f)[0]['app_id'], 'a')


class Notification(unittest.TestCase):
    def test_parse(self):
        n = logic.parse_notification('org.x.App', 'id1', vardict(
            title=GLib.Variant('s', 'Hello'), body=GLib.Variant('s', 'plain'),
            priority=GLib.Variant('s', 'urgent'),
            icon=GLib.Variant('(sv)', ('themed', GLib.Variant('as', ['mail-unread']))),
            **{'default-action': GLib.Variant('s', 'app.open'),
               'default-action-target': GLib.Variant('s', 'inbox'),
               'buttons': GLib.Variant('aa{sv}', [
                   {'label': GLib.Variant('s', 'Reply'), 'action': GLib.Variant('s', 'app.reply')}])}))
        self.assertEqual(n['summary'], 'Hello')
        self.assertEqual(n['body'], 'plain')
        self.assertEqual(n['icon'], 'mail-unread')
        self.assertEqual(n['hints']['urgency'].unpack(), 2)
        self.assertEqual(n['hints']['desktop-entry'].unpack(), 'org.x.App')
        self.assertEqual(n['actions'], ['default', '', '0:app.reply', 'Reply'])
        self.assertEqual(n['targets']['default'][0], 'app.open')
        self.assertEqual(n['targets']['default'][1].unpack(), 'inbox')
        self.assertEqual(n['targets']['0:app.reply'][0], 'app.reply')
        self.assertIsNone(n['targets']['0:app.reply'][1])

    def test_markup_body_wins_and_file_icon(self):
        n = logic.parse_notification('a', 'i', vardict(
            title=GLib.Variant('s', 'T'), body=GLib.Variant('s', 'x'),
            **{'markup-body': GLib.Variant('s', '<b>x</b>')},
            icon=GLib.Variant('(sv)', ('file', GLib.Variant('s', '/tmp/i.png')))))
        self.assertEqual(n['body'], '<b>x</b>')
        self.assertEqual(n['icon'], '/tmp/i.png')

    def test_empty(self):
        n = logic.parse_notification('a', 'i', vardict())
        self.assertEqual((n['summary'], n['body'], n['icon'], n['actions']), ('', '', '', []))
        self.assertEqual(n['hints']['urgency'].unpack(), 1)


class Email(unittest.TestCase):
    def test_mailto(self):
        self.assertEqual(logic.mailto_uri({'addresses': ['a@b.c', 'd@e.f'], 'subject': 'Hi there',
                                           'body': 'a&b'}),
                         'mailto:a@b.c,d@e.f?subject=Hi%20there&body=a%26b')
        self.assertEqual(logic.mailto_uri({'address': 'a@b.c', 'cc': ['x@y.z']}),
                         'mailto:a@b.c?cc=x@y.z')
        self.assertEqual(logic.mailto_uri({}), 'mailto:')


class Account(unittest.TestCase):
    def test_user_information(self):
        with tempfile.TemporaryDirectory() as home:
            entry = types.SimpleNamespace(pw_name='wolk', pw_gecos='Wolk Law,,,', pw_dir=home)
            info = logic.user_information(home, entry)
            self.assertEqual((info['id'], info['name'], info['image']), ('wolk', 'Wolk Law', ''))
            open(os.path.join(home, '.face'), 'w').close()
            self.assertEqual(logic.user_information(home, entry)['image'], 'file://' + home + '/.face')
            entry.pw_gecos = ''
            self.assertEqual(logic.user_information(home, entry)['name'], 'wolk')


class Printing(unittest.TestCase):
    def test_lpstat(self):
        text = ('printer Office is idle.  enabled since Mon\n'
                'printer Lab now printing Lab-4.  enabled since Mon\n'
                'printer Old disabled since Mon -\n'
                'system default destination: Office\n')
        self.assertEqual(logic.parse_lpstat(text), (
            [('Office', 'idle'), ('Lab', 'printing'), ('Old', 'disabled')], 'Office'))
        self.assertEqual(logic.parse_lpstat(''), ([], ''))

    def test_lp_command(self):
        self.assertEqual(logic.lp_command('Office', 2, 'Doc'), ['lp', '-d', 'Office', '-n', '2', '-t', 'Doc'])
        self.assertEqual(logic.lp_command('', 0, ''), ['lp', '-n', '1'])

    def test_trusted(self):
        self.assertTrue(logic.trusted_launcher_app('dev.wolklaw.SparkStore'))
        self.assertFalse(logic.trusted_launcher_app('org.mozilla.firefox'))


class Specs(unittest.TestCase):
    def test_access_spec_keeps_choices(self):
        spec = backend.access_spec('T', 'S', 'B', {
            'grant_label': 'Yes', 'choices': [('c', 'Remember', [], 'false'),
                                              ('m', 'Mode', [('a', 'A'), ('b', 'B')], 'a')]}, 'x.y')
        self.assertEqual((spec['grant'], spec['deny']), ('Yes', strings.t('portal.deny')))
        self.assertEqual([c['id'] for c in spec['choices']], ['c', 'm'])
        self.assertEqual(spec['choices'][1]['options'], [['a', 'A'], ['b', 'B']])
        json.dumps(spec)

    def test_print_spec_labels(self):
        spec = backend.print_spec('Doc', [('A', 'idle'), ('B', 'disabled')], 'A', 1)
        self.assertEqual([p['label'] for p in spec['printers']], ['A', 'B (disabled)'])

    def test_strings_have_both_languages(self):
        for key in ('portal.allow', 'portal.deny', 'portal.cancel', 'portal.app',
                    'portal.account.title', 'portal.launcher.title', 'portal.print.title',
                    'portal.print.go', 'portal.print.none'):
            self.assertNotEqual(strings.t(key, language='en'), strings.t(key, language='fr'), key)

    def test_self_test(self):
        self.assertEqual(backend.self_test(), 0)


if __name__ == '__main__':
    unittest.main()
