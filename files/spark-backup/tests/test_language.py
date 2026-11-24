"""The French interface, text that fits, and the three tabs opening. The whole suite runs twice
in CI, with SPARK_LANG=en and fr. The window tests need a display (Xvfb in CI)."""

import json
import os
import re
import shutil
import tempfile
import time
import unittest
from unittest import mock

import support
from langcheck import clipped, fields, table_problems
from sparkbackup import text
from sparkbackup.btrfs import Btrfs
from sparkbackup.lang import ui_language

PKG = os.path.join(os.path.dirname(support.HERE), 'sparkbackup')


class Tables(unittest.TestCase):
    def test_french_is_complete(self):
        self.assertEqual(table_problems(text.EN, text.FR), [])

    def test_every_sentence_fills_in(self):
        for key, value in text.EN.items():
            filled = text.t(key, **{name: 'X' for name in fields(value)})
            self.assertNotIn('{', filled.replace('{{', ''), key)

    def test_every_key_used_in_the_code_exists(self):
        used = set()
        for name in os.listdir(PKG):
            if name.endswith('.py') and name != 'text.py':
                with open(os.path.join(PKG, name), encoding='utf-8') as f:
                    used.update(re.findall(r"\bt\(\s*['\"]([a-z0-9_.]+)['\"]", f.read()))
        self.assertEqual(sorted(k for k in used if k not in text.EN), [])

    def test_the_keys_built_at_run_time_exist(self):
        keys = [f'tab.{k}' for k in ('backups', 'browse', 'settings')]
        keys += [f'tile.{k}' for k in ('last', 'next', 'drive', 'count')]
        keys += [f'status.{k}' for k in ('snapshot', 'copy', 'prune', 'working')]
        keys += [f'day.{d}' for d in ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')]
        keys += ['settings.method_btrfs', 'settings.method_rsync', 'refuse.fat',
                 'refuse.system', 'refuse.other']
        self.assertEqual([k for k in keys if k not in text.EN], [])


class PickTheLanguage(unittest.TestCase):
    def test_from_the_locale(self):
        cases = [({'LANG': 'fr_CA.UTF-8'}, 'fr'), ({'LANG': 'en_CA.UTF-8'}, 'en'),
                 ({}, 'en'), ({'LANG': 'fr_CA.UTF-8', 'SPARK_LANG': 'en'}, 'en')]
        for env, want in cases:
            with self.subTest(env=env):
                self.assertEqual(ui_language(env), want)

    def test_spark_lang_picks_the_table(self):
        want = os.environ.get('SPARK_LANG')
        if want in ('en', 'fr'):
            self.assertEqual(text.LANG, want)


try:
    import tkinter as tk
    tk.Tk().destroy()
    DISPLAY = bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))
except Exception:  # noqa: BLE001 - no display, or no Tk at all
    DISPLAY = False


@unittest.skipUnless(DISPLAY, "needs a display")
class Window(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-backup-window-')
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.home = support.make_home(self.dir)
        snaps = os.path.join(self.home, '.spark-backup', 'snapshots')
        for name in ('2026-11-21_020000', '2026-11-22_020000', '2026-11-23_020000'):
            shutil.copytree(os.path.join(self.home, 'alex'), os.path.join(snaps, name, 'alex'))
        env = {'XDG_CONFIG_HOME': os.path.join(self.dir, 'config'),
               'SPARK_BACKUP_CONFIG': os.path.join(self.dir, 'config.json'),
               'SPARK_BACKUP_RUN_DIR': os.path.join(self.dir, 'run'),
               'SPARK_BACKUP_STATE_DIR': os.path.join(self.dir, 'state'),
               'SPARK_BACKUP_DIRECT': '1', 'SPARK_BACKUP_REDUCED_MOTION': '1'}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        fake = mock.patch.object(Btrfs, 'is_subvolume', support.FakeBtrfs.is_subvolume)
        fake.start()
        self.addCleanup(fake.stop)
        self.drives = [support.drive(uuid='AAAA-1111', mountpoint=os.path.join(self.dir, 'usb')),
                       support.drive(uuid='BBBB-2222', fstype='vfat', method='',
                                     reason='refuse.fat', label='Camera card')]

    def pump(self, app, seconds):
        end = time.time() + seconds
        while time.time() < end:
            app.root.update()
            time.sleep(0.02)

    def open(self, tab):
        from sparkbackup.app import App
        return App(tab=tab, drives=self.drives, source=self.home)

    def test_every_tab_opens_and_its_text_fits(self):
        for tab in ('backups', 'browse', 'settings'):
            app = self.open(tab)
            try:
                self.pump(app, 0.6)
                app.root.geometry('%dx%d' % app.root.minsize())
                self.pump(app, 0.3)
                with self.subTest(tab=tab):
                    self.assertEqual(clipped(app.root), [])
            finally:
                app.close()

    def test_the_backups_tab_lists_the_snapshots(self):
        app = self.open('backups')
        try:
            self.pump(app, 0.3)
            view = app.views['backups']
            self.assertEqual(list(view.tree.get_children()),
                             ['2026-11-23_020000', '2026-11-22_020000', '2026-11-21_020000'])
            self.assertEqual(app.model.layout, True)
        finally:
            app.close()

    def test_browse_opens_a_snapshot_and_restores_beside(self):
        app = self.open('backups')
        try:
            self.pump(app, 0.3)
            app.show('browse')
            view = app.views['browse']
            view.open('2026-11-22_020000')
            self.pump(app, 0.3)
            self.assertEqual([i.name for i in view.items], ['alex'])
            view.tree.selection_set('0')
            view._enter()
            self.assertEqual(view.rel, 'alex')
            names = [i.name for i in view.items]
            view.tree.selection_set(str(names.index('top.txt')))
            view.restore_here()
            self.pump(app, 0.8)
            restored = os.path.join(self.home, 'alex', 'top (restored 2026-11-22 02:00).txt')
            self.assertTrue(os.path.exists(restored))
            with open(os.path.join(self.home, 'alex', 'top.txt')) as f:
                self.assertEqual(f.read(), 'top')
        finally:
            app.close()

    def test_saving_settings_goes_through_the_helper(self):
        calls = []
        app = self.open('settings')
        try:
            self.pump(app, 0.3)
            view = app.views['settings']
            from sparkbackup import helper
            with mock.patch.object(helper, '_systemctl', lambda *a: calls.append(a) or 0), \
                    mock.patch.object(helper, 'dropin_path',
                                      lambda: os.path.join(self.dir, 'schedule.conf')):
                view.tree.selection_set('AAAA-1111')
                view.every.set('weekly', fire=True)
                view.time.delete(0, 'end')
                view.time.insert(0, '03:15')
                view.save()
                self.pump(app, 1.0)
            with open(os.environ['SPARK_BACKUP_CONFIG']) as f:
                saved = json.load(f)
            self.assertTrue(saved['enabled'])
            self.assertEqual(saved['target']['uuid'], 'AAAA-1111')
            self.assertEqual(saved['schedule']['every'], 'weekly')
            self.assertEqual(saved['schedule']['time'], '03:15')
            self.assertTrue(any('enable' in c for c in calls))
        finally:
            app.close()

    def test_a_bad_time_is_not_sent(self):
        app = self.open('settings')
        try:
            self.pump(app, 0.3)
            view = app.views['settings']
            view.time.delete(0, 'end')
            view.time.insert(0, '99:99')
            view.save()
            self.pump(app, 0.3)
            self.assertFalse(os.path.exists(os.environ['SPARK_BACKUP_CONFIG']))
        finally:
            app.close()

    def test_a_drive_that_cannot_hold_backups_is_not_sent(self):
        app = self.open('settings')
        try:
            self.pump(app, 0.3)
            view = app.views['settings']
            view.tree.selection_set('BBBB-2222')
            view.save()
            self.pump(app, 0.3)
            self.assertFalse(os.path.exists(os.environ['SPARK_BACKUP_CONFIG']))
        finally:
            app.close()


if __name__ == '__main__':
    unittest.main()
