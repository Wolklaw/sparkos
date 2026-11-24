"""The App updates page: reading what Spark Apps installed, and the window's rows and buttons.
The units that install things are never started here (liveapps.start is replaced)."""

import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-update-{var.lower()}-'))
os.environ['SPARK_UPDATE_REDUCED_MOTION'] = '1'

from sparkupdate import liveapps                      # noqa: E402
from sparkupdate.core import Env                      # noqa: E402
from sparkupdate.text import t                        # noqa: E402
from test_language import have_display                # noqa: E402
from test_spark_update import make_root, write        # noqa: E402
from langcheck import clipped                         # noqa: E402


def record(slug, version, name, live=True):
    data = {'slug': slug, 'name': name, 'version': version, 'system_api': 1}
    if live:
        data['live_update'] = True
    return json.dumps(data)


def machine(state=None, extra_records=()):
    root = make_root()
    write(root, '/usr/share/spark-apps/spark-calc.json', record('spark-calc', '1.0.0', 'Spark Calc'))
    write(root, '/usr/share/spark-apps/spark-edit.json', record('spark-edit', '2.0.0', 'Spark Edit'))
    write(root, '/usr/share/spark-apps/spark-snip.json',
          record('spark-snip', '1.0.0', 'Spark Snip', live=False))
    for slug, version, name in extra_records:
        write(root, f'/usr/share/spark-apps/{slug}.json', record(slug, version, name))
    if state is not None:
        write(root, '/var/lib/spark-apps/state.json', json.dumps(state))
    return root


class Reading(unittest.TestCase):
    def test_nothing_installed(self):
        summary = liveapps.read(Env(machine()))
        self.assertEqual([r.slug for r in summary.rows], ['spark-calc', 'spark-edit'])
        self.assertTrue(summary.installed)
        self.assertEqual(summary.rows[0].running, '1.0.0')
        self.assertFalse(summary.rows[0].on_live)

    def test_a_live_copy(self):
        state = {'last_check': 1000, 'last_result': 'ok',
                 'apps': {'spark-calc': {'active': '1.0.2', 'use': 'live', 'latest': '1.0.3'},
                          'spark-edit': {'latest': '3.0.0', 'waiting': 'needs-os'}}}
        rows = {r.slug: r for r in liveapps.read(Env(machine(state))).rows}
        calc, edit = rows['spark-calc'], rows['spark-edit']
        self.assertEqual((calc.running, calc.on_live, calc.newer), ('1.0.2', True, True))
        self.assertEqual((edit.running, edit.waiting, edit.newer), ('2.0.0', True, False))

    def test_use_builtin_runs_the_builtin_one(self):
        state = {'apps': {'spark-calc': {'active': '1.0.2', 'use': 'builtin', 'latest': '1.0.3'}}}
        calc = liveapps.read(Env(machine(state))).rows[0]
        self.assertEqual((calc.running, calc.on_live, calc.newer), ('1.0.0', False, False))

    def test_live_copy_older_than_the_image(self):
        state = {'apps': {'spark-calc': {'active': '0.9.0', 'use': 'live'}}}
        self.assertEqual(liveapps.read(Env(machine(state))).rows[0].running, '1.0.0')

    def test_garbage_is_ignored(self):
        for text in ('', '{', '[]', '{"apps": 5}', '{"apps": {"spark-calc": {"active": "x"}}}'):
            root = machine()
            write(root, '/var/lib/spark-apps/state.json', text)
            self.assertEqual(liveapps.read(Env(root)).rows[0].running, '1.0.0', text)

    def test_not_in_this_image(self):
        summary = liveapps.read(Env(make_root()))
        self.assertEqual((summary.rows, summary.installed), ([], False))

    def test_start_only_runs_known_actions(self):
        calls = []
        with mock.patch.object(liveapps, 'run', lambda cmd, timeout=0: calls.append(cmd) or (0, '', '')):
            self.assertEqual(liveapps.start('update')[0], 0)
            self.assertEqual(liveapps.start('use-builtin', 'spark-calc')[0], 0)
            self.assertEqual(liveapps.start('use-builtin', '../x')[0], 2)
            self.assertEqual(liveapps.start('rm', 'spark-calc')[0], 2)
            self.assertEqual(liveapps.start('use-live')[0], 2)
        self.assertEqual(calls, [['systemctl', 'start', 'spark-apps-now@update.service'],
                                 ['systemctl', 'start',
                                  'spark-apps-now@use-builtin:spark-calc.service']])


@unittest.skipUnless(have_display(), "needs a display")
class Window(unittest.TestCase):
    def open(self, state, extra=()):
        import gc
        from sparkupdate.app import App
        app = App(Env(machine(state, extra)), view='apps')

        def close():
            while app.pending:
                app.root.update()
                time.sleep(0.01)
            app.root.destroy()
            app.__dict__.clear()
            gc.collect()
        self.addCleanup(close)
        app.root.geometry('%dx%d' % app.root.minsize())
        for _ in range(5):
            app.root.update()
            time.sleep(0.02)
        return app

    def pump(self, app, seconds=0.3):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.root.update()
            time.sleep(0.01)

    def test_rows_and_text_fit_at_the_smallest_size(self):
        state = {'last_check': time.time() - 7200, 'last_result': 'ok', 'apps': {
            'spark-calc': {'active': '1.0.2', 'use': 'live', 'latest': '1.0.3'},
            'spark-edit': {'latest': '3.0.0', 'waiting': 'needs-os'},
            'spark-notes': {'use': 'builtin', 'active': '1.1.0'},
            'spark-clock': {'last_error': 'the bundle has no spark-app.json'}}}
        app = self.open(state, [('spark-notes', '1.0.0', 'Spark Notes'),
                                ('spark-clock', '1.0.0', 'Spark Clock')])
        self.assertEqual([r[0] for r in app.app_rows],
                         ['spark-calc', 'spark-clock', 'spark-edit', 'spark-notes'])
        self.assertEqual(clipped(app.root), [])
        by = {r[0]: r for r in app.app_rows}
        self.assertEqual(by['spark-calc'][1], '1.0.2')
        self.assertEqual(by['spark-calc'][2], t('apps.state.newer', version='1.0.3'))
        self.assertEqual(by['spark-edit'][2], t('apps.state.needs_os', version='3.0.0'))
        self.assertEqual(by['spark-notes'][2], t('apps.state.held'))

    def test_update_now_and_per_app_switch(self):
        state = {'apps': {'spark-calc': {'active': '1.0.2', 'use': 'live'}}}
        app = self.open(state)
        app.env = Env(app.env.root)
        started = []

        def fake(verb, slug=None):
            started.append((verb, slug))
            return 0, ''
        with mock.patch('sparkupdate.liveapps.start', fake), \
                mock.patch.object(Env, 'fake', False):
            app.on_apps_now()
            self.pump(app)
            app.on_app_switch(app.apps_summary.rows[0], 'use-builtin')
            self.pump(app)
        self.assertEqual(started, [('update', None), ('use-builtin', 'spark-calc')])
        self.assertIn(t('which.builtin'), app.message.cget('text'))

    def test_failure_is_said(self):
        app = self.open(None)
        with mock.patch('sparkupdate.liveapps.start', lambda *a: (1, 'no route')), \
                mock.patch.object(Env, 'fake', False):
            app.on_apps_now()
            self.pump(app)
        self.assertIn('no route', app.message.cget('text'))
        self.assertFalse(app.busy)


if __name__ == '__main__':
    unittest.main()
