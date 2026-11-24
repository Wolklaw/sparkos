"""The Logs and System tabs: parsing, plain-language headlines, scrubbing, and both tabs on the
fake root. The commands (journalctl, coredumpctl, rpm-ostree, ...) are fixture files under
fixtures/root/commands, so these never read the real journal. Everything in the fixtures is
invented."""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, 'fixtures', 'root')
sys.path.insert(0, os.path.dirname(HERE))
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-monitor-{var.lower()}-'))
os.environ['SPARK_MONITOR_REDUCED_MOTION'] = '1'

from sparkmonitor import journal, sysinfo  # noqa: E402
from sparkmonitor.host import Host  # noqa: E402
from sparkmonitor.source import Source  # noqa: E402
from sparkmonitor.system import SystemSampler  # noqa: E402
from sparkmonitor.text import t  # noqa: E402


def read(name: str) -> str:
    with open(os.path.join(FIXTURE, 'commands', name), encoding='utf-8') as f:
        return f.read()


def entries(name: str):
    return [journal.parse_entry(line) for line in read(name).splitlines()]


class Entries(unittest.TestCase):
    def test_parse_and_filter(self):
        got = entries('journal-this-warning.jsonl')
        self.assertEqual(len(got), 5)
        self.assertEqual([e.prio for e in got], [4, 3, 3, 4, 3])
        self.assertIsNone(journal.parse_entry('not json'))
        self.assertIsNone(journal.parse_entry('[1, 2]'))
        self.assertTrue(journal.matches(got[0], 'kwin', ''))
        self.assertTrue(journal.matches(got[0], '', 'INPUT METHOD'))
        self.assertFalse(journal.matches(got[0], 'blender', ''))

    def test_binary_and_huge_fields_are_safe(self):
        line = json.dumps({'MESSAGE': list(b'caf\xc3\xa9'), 'PRIORITY': '3',
                           '__REALTIME_TIMESTAMP': '1'})
        self.assertEqual(journal.parse_entry(line).message, 'café')
        big = json.dumps({'MESSAGE': 'x' * 100000, 'PRIORITY': '6'})
        self.assertLessEqual(len(journal.parse_entry(big).message), journal.MESSAGE_MAX + 1)
        self.assertEqual(journal.parse_entry(json.dumps({'MESSAGE': None})).message, '')

    def test_arguments(self):
        args = journal.journal_args(-1, 'err', False)
        self.assertEqual(args[:2], ['journalctl', '-o'])
        self.assertIn('-1', args)
        self.assertEqual(args[args.index('-p') + 1], '3')
        self.assertNotIn('-f', args)
        self.assertIn('-f', journal.journal_args(0, 'warning', True))

    def test_headlines_say_it_plainly(self):
        got = entries('journal-this-warning.jsonl')
        self.assertIn('blender', journal.headline(got[1]))
        self.assertNotIn('total-vm', journal.headline(got[1]))
        self.assertIn('Example Sync Daemon', journal.headline(got[2]))
        self.assertEqual(journal.headline(got[3]), t('head.gpu_reset'))
        self.assertEqual(journal.headline(got[0]), got[0].message)     # no rule: as written

    def test_home_is_scrubbed_from_copies(self):
        e = entries('journal-this-warning.jsonl')[4]
        text = journal.entry_text(e)
        self.assertNotIn('fixtureuser', text)
        self.assertIn('~/Documents/a.txt', text)
        self.assertEqual(journal.source_name(e), 'fixture-app')

    def test_unclean_shutdown_is_a_guess_from_the_log(self):
        clean, last = journal.boot_ended_cleanly(read('journal-prev-tail.jsonl'))
        self.assertFalse(clean)
        self.assertGreater(last, 0)
        done = json.dumps({'MESSAGE': 'Reached target Shutdown.', '__REALTIME_TIMESTAMP': '5',
                           'PRIORITY': '6'})
        self.assertTrue(journal.boot_ended_cleanly(done)[0])
        self.assertEqual(journal.boot_ended_cleanly(''), (None, 0))
        self.assertEqual(journal.boot_ended_cleanly(None), (None, 0))


class Crashes(unittest.TestCase):
    def test_list_newest_first(self):
        crashes = journal.parse_crashes(read('coredumpctl.json'))
        self.assertEqual([c.app for c in crashes], ['fixture-viewer', 'fixture-tool'])
        self.assertEqual(crashes[0].signal_name, 'SIGSEGV')
        self.assertTrue(crashes[0].stored)
        self.assertFalse(crashes[1].stored)
        self.assertEqual(journal.parse_crashes(''), [])
        self.assertEqual(journal.parse_crashes('{bad'), [])

    def test_report_leaves_out_what_identifies_the_pc(self):
        crashes = journal.parse_crashes(read('coredumpctl.json'))
        info = journal.scrub_info(read('coredumpctl-info.txt'))
        report = journal.crash_report(crashes[0], info, 'SparkOS 45')
        for private in ('Machine ID', 'Boot ID', 'Hostname', 'fixtureuser', 'fixture-host'):
            self.assertNotIn(private, report)
        self.assertIn('fixture-viewer', report)
        self.assertIn('SIGSEGV', report)
        self.assertIn('SparkOS 45', report)

    def test_failed_units(self):
        self.assertEqual(journal.parse_failed(read('failed-system.txt')),
                         ['fixture-broken.service'])
        self.assertEqual(journal.parse_failed(read('failed-user.txt'), user=True), [])
        self.assertEqual(journal.parse_failed('  UNIT LOAD\n0 loaded units listed.'), [])


class System(unittest.TestCase):
    def setUp(self):
        self.src = Source(FIXTURE)
        self.sampler = SystemSampler(self.src)
        self.sampler.sample(time.monotonic())
        self.cmds = sysinfo.fetch(Host(self.src))

    def rows(self, sections=None):
        out = {}
        for s in sections or sysinfo.build(self.src, self.sampler, self.cmds):
            for r in s.rows:
                out[f'{s.key}/{r.label}'] = r
        return out

    def test_fetch_reads_every_command(self):
        self.assertEqual(set(self.cmds), {'ostree', 'udev', 'vulkan', 'glx', 'kscreen'})
        self.assertTrue(self.cmds['ostree'])

    def test_parsers(self):
        ost = sysinfo.parse_ostree(self.cmds['ostree'])
        self.assertEqual(ost['version'], '45.20260301.0')
        self.assertEqual(ost['staged'], '45.20260302.0')
        self.assertEqual(sysinfo.parse_ostree('nope'), {})
        mods = sysinfo.parse_udev_memory(self.cmds['udev'])
        self.assertEqual(len(mods), 2)
        devices = sysinfo.parse_vulkan(self.cmds['vulkan'])
        self.assertEqual(len(devices), 2)
        self.assertIn('Mesa 26', sysinfo.vulkan_for(devices, 0x1002, 0x73bf)['driverInfo'])
        self.assertIsNone(sysinfo.vulkan_for(devices, 0x10de, 0x1))
        self.assertEqual(sysinfo.parse_kscreen(self.cmds['kscreen'])['DP-1']['hz'], '144')
        self.assertEqual(sysinfo.parse_glx('OpenGL version string: 4.6 (Core) Mesa 26.0'),
                         '4.6 (Core) Mesa 26.0')

    def test_sections(self):
        sections = sysinfo.build(self.src, self.sampler, self.cmds)
        keys = [s.key for s in sections]
        for key in ('os', 'cpu', 'memory', 'board', 'disks', 'displays', 'uptime'):
            self.assertIn(key, keys)
        self.assertEqual(sum(1 for k in keys if k.startswith('gpu')), 2)
        rows = self.rows(sections)
        text = ' '.join(r.value for r in rows.values())
        self.assertIn('45.20260301.0', text)
        self.assertIn('FixtureRAM', text)
        self.assertIn('6000 MT/s', text)
        self.assertIn('FX-X1 WIFI', text)

    def test_two_modules_get_two_names(self):
        labels = [r.label for s in sysinfo.build(self.src, self.sampler, self.cmds)
                  if s.key == 'memory' for r in s.rows if not r.secret and 'FixtureRAM' in r.value]
        self.assertEqual(len(labels), 2)
        self.assertEqual(len(set(labels)), 2)

    def test_serials_stay_out_unless_asked(self):
        sections = sysinfo.build(self.src, self.sampler, self.cmds)
        plain = sysinfo.report(sections, False, '2026-03-02 09:00 EST')
        full = sysinfo.report(sections, True, '2026-03-02 09:00 EST')
        for serial in ('BOARDSERIAL-0001', 'PRODSERIAL-0001', 'RAMSERIAL-0001'):
            self.assertNotIn(serial, plain)
            self.assertIn(serial, full)

    def test_missing_pieces_do_not_break_it(self):
        sections = sysinfo.build(self.src, self.sampler, {})
        self.assertTrue(sections)
        self.assertIn('Spark Monitor', sysinfo.report(sections, False, 'now'))

    def test_uptime_text(self):
        self.assertEqual(sysinfo.uptime_text(59 * 60), t('sys.uptime_m', m=59))
        self.assertEqual(sysinfo.uptime_text(26 * 3600 + 5 * 60),
                         t('sys.uptime_d', d=1, h=2, m=5))


def have_display() -> bool:
    return os.name == 'nt' or bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


@unittest.skipUnless(have_display(), "needs a display")
class Tabs(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-monitor-logs-')
        self.root = os.path.join(self.dir, 'root')
        shutil.copytree(FIXTURE, self.root)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def open(self, tab):
        from sparkmonitor.app import App
        app = App(Source(self.root), tab=tab)
        self.addCleanup(app.close)
        self.pump(app, 1.2)
        return app

    @staticmethod
    def pump(app, seconds):
        end = time.time() + seconds
        while time.time() < end:
            app.root.update()
            time.sleep(0.02)

    def test_logs_tab(self):
        app = self.open('logs')
        view = app.views['logs']
        self.assertEqual(len(view.tree.get_children()), 5)
        first = view.tree.get_children()[0]
        view.tree.selection_set(first)
        view.select_entry()
        self.assertTrue(view.selected())
        view.set_level('err')
        self.pump(app, 0.8)
        self.assertEqual(len(view.tree.get_children()), 3)
        view.set_level('warning')
        self.pump(app, 0.8)
        view.set_boot('-1')
        self.pump(app, 0.8)
        self.assertEqual(len(view.tree.get_children()), 1)
        self.assertIsNone(view.stream and view.stream.process)     # nothing real was started

    def test_logs_crashes_and_banner(self):
        app = self.open('logs')
        view = app.views['logs']
        view.set_mode('crashes')
        self.pump(app, 1.5)
        rows = view.crash_tree.get_children()
        self.assertEqual(len(rows), 2)
        view.crash_tree.selection_set(rows[0])
        view.select_crash()
        self.pump(app, 1.0)
        shown = view.crash_detail.get('1.0', 'end')
        self.assertIn('fixture-viewer', shown)
        self.assertNotIn('fixtureuser', shown)
        self.assertEqual(view.failed, ['fixture-broken.service'])

    def test_leaving_the_tab_stops_the_stream(self):
        app = self.open('logs')
        view = app.views['logs']
        app.show('apps')
        self.pump(app, 0.3)
        self.assertIsNone(view.stream)
        app.show('logs')
        self.pump(app, 0.5)
        self.assertIsNotNone(view.stream)

    def test_system_tab(self):
        app = self.open('system')
        view = app.views['system']
        self.pump(app, 1.5)
        self.assertTrue(view.ready)
        shown = []
        stack = [view.inner]
        while stack:
            w = stack.pop()
            stack.extend(w.winfo_children())
            if w.winfo_class() == 'Label' and w.cget('text'):
                shown.append(w.cget('text'))
        text = '\n'.join(shown)
        self.assertIn('FX-X1 WIFI', text)
        self.assertNotIn('BOARDSERIAL-0001', text)
        view.set_serials(True)
        self.pump(app, 0.3)
        again = []
        stack = [view.inner]
        while stack:
            w = stack.pop()
            stack.extend(w.winfo_children())
            if w.winfo_class() == 'Label' and w.cget('text'):
                again.append(w.cget('text'))
        self.assertIn('BOARDSERIAL-0001', '\n'.join(again))
        view.copy_all()
        self.assertIn('Spark Monitor', app.root.clipboard_get())

    def test_keys_reach_the_new_tabs(self):
        app = self.open('apps')
        for key, tab in (('5', 'logs'), ('6', 'system')):
            event = type('E', (), {'keysym': key, 'state': 0x4})()
            app._key(event)
            self.pump(app, 0.3)
            self.assertEqual(app.tab, tab)


if __name__ == '__main__':
    unittest.main()
