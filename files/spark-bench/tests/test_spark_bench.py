"""Spark Bench tests. Everything runs in a temporary HOME with fake flatpak and systemctl, so
nothing here touches the real MangoHud config, the Steam folder, Flatpak overrides or systemd.
The window tests need a display (CI uses Xvfb)."""

import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, 'fixtures')
sys.path.insert(0, os.path.dirname(HERE))

_HOME = tempfile.mkdtemp(prefix='spark-bench-home-')
os.environ['HOME'] = _HOME
for var, sub in (('XDG_CONFIG_HOME', '.config'), ('XDG_DATA_HOME', '.local/share'),
                 ('XDG_STATE_HOME', '.local/state'), ('XDG_CACHE_HOME', '.cache'),
                 ('XDG_RUNTIME_DIR', 'run')):
    os.environ[var] = os.path.join(_HOME, sub)
    os.makedirs(os.environ[var], exist_ok=True)
os.environ['SPARK_BENCH_REDUCED_MOTION'] = '1'
os.environ['SPARK_BENCH_SCALE'] = '1'

from sparkbench import core, frames, library, mangohud, watch  # noqa: E402

MH = os.path.join(FIXTURES, 'mangohud')
PM = os.path.join(FIXTURES, 'presentmon')
MH_RUNS = ('Spider-Man2_2026-11-22_05-03-31.csv', 'Spider-Man2_2026-11-22_05-08-33.csv')
PM_RUNS = ('spiderman2_2026-11-21_21-20-55-1.csv', 'spiderman2_2026-11-21_21-20-55-2.csv',
           'expedition33_2026-11-21_21-28-09-1.csv')


def assert_in_home(test, path):
    test.assertTrue(os.path.abspath(path).startswith(_HOME + os.sep), path)


def fresh_home():
    """Empty the temporary HOME between tests (it never is the real one)."""
    assert core.home() == _HOME and _HOME.startswith(tempfile.gettempdir())
    for name in os.listdir(_HOME):
        path = os.path.join(_HOME, name)
        shutil.rmtree(path) if os.path.isdir(path) else os.unlink(path)
    for var in ('XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_CACHE_HOME',
                'XDG_RUNTIME_DIR'):
        os.makedirs(os.environ[var], exist_ok=True)


class FakeFlatpak:
    """Stands in for the flatpak command. The override it writes goes to the temp HOME."""

    def __init__(self, steam=True, branch='25.08', layers=('25.08',), flatpak=True):
        self.steam, self.branch, self.layers, self.flatpak = steam, branch, list(layers), flatpak
        self.calls = []

    def __call__(self, argv, timeout=20):
        self.calls.append(list(argv))
        if not self.flatpak:
            return 127, 'not found'
        if argv[:2] == ['flatpak', '--version']:
            return 0, 'Flatpak 1.16.1'
        if argv[:3] == ['flatpak', 'info', '--show-runtime']:
            return (0, f'org.freedesktop.Platform/x86_64/{self.branch}\n') if self.steam \
                else (1, 'error: not installed')
        if argv[:3] == ['flatpak', 'list', '--runtime']:
            return 0, ''.join(f'{mangohud.LAYER}\t{b}\n' for b in self.layers) + \
                'org.freedesktop.Platform\t25.08\n'
        if argv[:3] == ['flatpak', 'override', '--user']:
            path = mangohud.user_override()
            assert_in_home(unittest.TestCase(), path)
            text = mangohud.read_text(path) or ''
            env = [a.split('=', 1)[1] for a in argv if a.startswith('--env=')]
            fs = [a.split('=', 1)[1] for a in argv if a.startswith('--filesystem=')]
            lines = text.splitlines()
            if fs:
                lines = ['[Context]', 'filesystems=' + ';'.join(fs) + ';'] + lines
            if env:
                lines += ['', '[Environment]'] + env
            core.write_text(path, '\n'.join(lines) + '\n')
            return 0, ''
        if argv[:2] == ['flatpak', 'install']:
            self.layers.append(argv[-1].rsplit('//', 1)[-1])
            return 0, 'Installing…'
        if argv[:2] == ['flatpak', 'uninstall']:
            return 0, ''
        return 1, 'unexpected: ' + ' '.join(argv)


class FakeSystemctl:
    def __init__(self):
        self.calls, self.enabled = [], False

    def __call__(self, *args):
        self.calls.append(args)
        if args[0] == 'enable':
            self.enabled = True
        elif args[0] == 'disable':
            self.enabled = False
        elif args[0] == 'is-enabled':
            return (0 if self.enabled else 1), 'enabled' if self.enabled else 'disabled'
        return 0, ''


# ─── The numbers ──────────────────────────────────────────────

class Math(unittest.TestCase):
    def test_flat_60(self):
        s = frames.compute([1000 / 60] * 600)
        self.assertAlmostEqual(s.avg_fps, 60.0, places=6)
        self.assertAlmostEqual(s.low1, 60.0, places=6)
        self.assertAlmostEqual(s.seconds, 10.0, places=6)
        self.assertEqual(len(s.per_second), 10)

    def test_lows_average_the_slowest(self):
        ft = [10.0] * 990 + [40.0] * 10          # 1000 frames, the slowest 1% at 40 ms
        s = frames.compute(ft)
        self.assertAlmostEqual(s.low1, 25.0)
        self.assertAlmostEqual(s.low01, 25.0)
        self.assertAlmostEqual(s.worst_ms, 40.0)
        self.assertAlmostEqual(s.avg_fps, 1000 / (sum(ft) / len(ft)))
        ft = [10.0] * 980 + [20.0] * 10 + [40.0] * 10
        self.assertAlmostEqual(frames.low(ft, 0.01), 25.0)
        self.assertAlmostEqual(frames.low(ft, 0.02), 1000 / 30)

    def test_trim(self):
        ft = [100.0] * 50 + [10.0] * 100 + [100.0] * 50       # 5 s slow, 1 s fast, 5 s slow
        s = frames.compute(ft, trim_start=5, trim_end=5)
        self.assertEqual(s.frames, 100)
        self.assertAlmostEqual(s.avg_fps, 100.0)
        self.assertAlmostEqual(s.total_seconds, 11.0)
        with self.assertRaises(ValueError):
            frames.compute(ft, trim_start=6, trim_end=6)

    def test_game_key(self):
        self.assertEqual(frames.game_key('Spider-Man2'), 'spiderman2')
        self.assertEqual(frames.game_key('Spider-Man2.exe'), 'spiderman2')
        self.assertEqual(frames.program_from_name('Spider-Man2_2026-11-22_05-03-31.csv'),
                         'Spider-Man2')


class Fixtures(unittest.TestCase):
    def test_mangohud(self):
        path = os.path.join(MH, MH_RUNS[0])
        self.assertEqual(frames.sniff(path), frames.MANGOHUD)
        rec = frames.read(path)
        self.assertEqual(rec.program, 'Spider-Man2')
        self.assertEqual(len(rec.frametimes), 300)
        s = frames.compute(rec.frametimes)
        self.assertAlmostEqual(s.avg_fps, 136.1, delta=0.1)
        self.assertAlmostEqual(s.low1, 94.3, delta=0.1)
        self.assertAlmostEqual(s.avg_fps, s.frames / s.seconds, delta=0.01)

    def test_summary_is_not_a_recording(self):
        path = os.path.join(MH, MH_RUNS[0].replace('.csv', '_summary.csv'))
        self.assertIsNone(frames.sniff(path))

    def test_presentmon(self):
        path = os.path.join(PM, PM_RUNS[0])
        self.assertEqual(frames.sniff(path), frames.PRESENTMON)
        rec = frames.read(path)
        self.assertEqual(rec.program, 'Spider-Man2.exe')
        s = frames.compute(rec.frametimes)
        self.assertAlmostEqual(s.avg_fps, 97.0, delta=0.1)
        rec = frames.read(os.path.join(PM, PM_RUNS[2]))
        self.assertEqual(frames.game_key(rec.program), 'sandfallwin64shipping')

    def test_not_a_recording(self):
        path = os.path.join(_HOME, 'notes.csv')
        with open(path, 'w') as f:
            f.write('a,b\n1,2\n')
        self.assertIsNone(frames.sniff(path))
        with self.assertRaises(frames.FormatError):
            frames.read(path)


# ─── The library ──────────────────────────────────────────────

def stage(folder=None):
    """Copy the fixtures: MangoHud's into an output folder, PresentMon's imported."""
    folder = folder or os.path.join(_HOME, 'bench')
    os.makedirs(folder, exist_ok=True)
    for name in os.listdir(MH):
        shutil.copy2(os.path.join(MH, name), folder)
    old = time.time() - 3600
    for name in os.listdir(folder):
        os.utime(os.path.join(folder, name), (old, old))
    return folder


class Library(unittest.TestCase):
    def setUp(self):
        fresh_home()
        self.settings = core.load_settings()
        self.folder = stage()
        self.lib = library.Library(self.settings, self.folder)

    def test_scan_and_import(self):
        runs = self.lib.scan()
        self.assertEqual([r.id for r in runs], list(MH_RUNS))
        self.assertTrue(all(r.system == 'SparkOS' for r in runs))
        copied, refused = self.lib.import_files([os.path.join(PM, n) for n in PM_RUNS] +
                                                [os.path.join(MH, MH_RUNS[0].replace(
                                                    '.csv', '_summary.csv'))])
        self.assertEqual(copied, 3)
        self.assertEqual(len(refused), 1)
        runs = self.lib.scan()
        self.assertEqual(len(runs), 5)
        self.assertEqual(self.lib.systems(), ['Windows', 'SparkOS'])
        names = [g for g, _ in self.lib.groups()]
        self.assertIn('Spider-Man2', names)
        self.assertIn('SandFall-Win64-Shipping', names)

    def test_duplicates_count_once(self):
        self.lib.add_folder(MH)                 # the same files in a second folder
        self.assertEqual(len(self.lib.scan()), 2)

    def test_still_recording(self):
        path = os.path.join(self.folder, 'Spider-Man2_2026-11-22_06-00-00.csv')
        shutil.copy(os.path.join(MH, MH_RUNS[0]), path)
        runs = {r.id: r for r in self.lib.scan()}
        self.assertTrue(runs[os.path.basename(path)].recording_now)
        self.assertFalse(runs[MH_RUNS[0]].recording_now)

    def test_marks_rename_and_compare(self):
        self.lib.import_files([os.path.join(PM, n) for n in PM_RUNS])
        runs = self.lib.scan()
        stats = {r.id: self.lib.stats(r) for r in runs}
        table = dict(library.comparison(self.lib, stats))
        spider = table['Spider-Man2']
        self.assertEqual(spider['SparkOS'].runs, 2)
        self.assertEqual(spider['Windows'].runs, 2)
        self.assertAlmostEqual(spider['SparkOS'].avg_fps, (136.14 + 124.36) / 2, delta=0.05)

        self.lib.set_mark(MH_RUNS[1], excluded=True)
        table = dict(library.comparison(self.lib, stats))
        self.assertEqual(table['Spider-Man2']['SparkOS'].runs, 1)
        reread = library.Library(self.settings, self.folder)
        self.assertTrue(reread.mark(MH_RUNS[1])['excluded'])
        self.lib.set_mark(MH_RUNS[1], excluded=False)
        self.assertNotIn(MH_RUNS[1], self.lib.marks)

        self.lib.set_mark(MH_RUNS[0], trim_start=1)
        trimmed = self.lib.stats(runs[[r.id for r in runs].index(MH_RUNS[0])])
        self.assertLess(trimmed.frames, 300)

        self.lib.rename_game('sandfallwin64shipping', 'Expedition 33')
        self.lib.rename_game('spiderman2', 'Expedition 33')
        self.assertEqual([g for g, _ in self.lib.groups()], ['Expedition 33'])
        self.lib.rename_game('spiderman2', '')
        self.assertEqual(len(self.lib.groups()), 2)

        text = library.summary_csv(self.lib, stats, 'Windows')
        lines = text.strip().splitlines()
        self.assertTrue(lines[0].startswith('Game,System,Recording'))
        self.assertEqual(sum(1 for line in lines if 'AVERAGE OF' in line), 3)
        sparkos_avg = next(line for line in lines if line.startswith('Spider-Man2,SparkOS,AVERAGE'))
        self.assertRegex(sparkos_avg, r',\+\d+\.\d,')
        self.assertAlmostEqual(library.difference(110, 100), 10.0)
        self.assertIsNone(library.difference(110, 0))


# ─── MangoHud setup, fix and undo ─────────────────────────────

class Setup(unittest.TestCase):
    def setUp(self):
        fresh_home()
        self.settings = core.load_settings()
        self.no_system = os.path.join(_HOME, 'no-system-override')

    def inspect(self, runner):
        return mangohud.inspect(self.settings, runner, system_override=self.no_system)

    def test_paths_are_in_the_temp_home(self):
        for path in (mangohud.steam_config(), mangohud.host_config(), mangohud.user_override(),
                     mangohud.undo_path(), watch.unit_path(), core.settings_path()):
            assert_in_home(self, path)

    def test_edit_keeps_other_lines(self):
        text = "# mine\nfps_limit=60\ntoggle_logging=Shift_L+F2\nlog_duration=30\n" \
               "toggle_logging=F3\n"
        want = mangohud.wanted('Control_L+F11', 90, '/x/bench')
        new, changed = mangohud.edit(text, want)
        values = mangohud.parse(new)
        self.assertEqual(values['toggle_logging'], 'Control_L+F11')
        self.assertEqual(values['log_duration'], '90')
        self.assertEqual(values['output_folder'], '/x/bench')
        self.assertIn('no_display', values)
        self.assertIn('fps_limit=60', new)
        self.assertIn('# mine', new)
        self.assertEqual(new.count('toggle_logging'), 1)
        self.assertTrue(changed)
        again, changed = mangohud.edit(new, want)
        self.assertEqual(again, new)
        self.assertEqual(changed, [])

    def test_fresh_system_fix_and_undo(self):
        runner = FakeFlatpak()
        r = self.inspect(runner)
        self.assertTrue(r.steam_flatpak)
        self.assertEqual(r.steam_branch, '25.08')
        self.assertTrue(r.layer_ok)
        self.assertFalse(r.env_enabled)
        self.assertFalse(r.ready)
        self.assertTrue(r.fixable)
        self.assertEqual(r.output_folder, os.path.join(mangohud.steam_dir(), 'benchmark'))
        changes = mangohud.plan(r, self.settings)
        kinds = sorted(c.kind for c in changes)
        self.assertIn('override', kinds)
        self.assertIn('folder', kinds)
        override = next(c for c in changes if c.kind == 'override')
        self.assertNotIn('--filesystem', ' '.join(override.argv))   # inside Steam's folder
        self.assertEqual(mangohud.apply(changes, runner), [])
        r = self.inspect(runner)
        self.assertTrue(r.ready, r)
        self.assertFalse(r.fixable)
        self.assertTrue(r.undo_available)
        self.assertTrue(os.path.isdir(r.output_folder))
        self.assertTrue(mangohud.undo_summary())

        self.assertEqual(mangohud.undo(runner), [])
        for path in (mangohud.steam_config(), mangohud.host_config(), mangohud.user_override()):
            self.assertFalse(os.path.exists(path), path)
        self.assertFalse(os.path.exists(os.path.join(mangohud.steam_dir(), 'benchmark')))
        self.assertFalse(self.inspect(runner).undo_available)

    def test_undo_restores_exact_bytes(self):
        runner = FakeFlatpak()
        original = "fps_limit=144\r\nposition=top-right\ntoggle_logging=Shift_L+F2\n"
        core.write_text(mangohud.steam_config(), original)
        core.write_text(mangohud.user_override(), "[Context]\nshared=network;\n")
        before_override = mangohud.read_text(mangohud.user_override())
        mangohud.apply(mangohud.plan(self.inspect(runner), self.settings), runner)
        self.assertNotEqual(mangohud.read_text(mangohud.steam_config()), original)
        # a second fix after a settings change keeps the first "before"
        self.settings['duration'] = 60
        mangohud.apply(mangohud.plan(self.inspect(runner), self.settings), runner)
        self.assertEqual(mangohud.undo(runner), [])
        with open(mangohud.steam_config(), newline='') as f:
            self.assertEqual(f.read(), original)
        self.assertEqual(mangohud.read_text(mangohud.user_override()), before_override)

    def test_their_folder_is_kept(self):
        runner = FakeFlatpak()
        theirs = os.path.join(_HOME, 'my-logs')
        core.write_text(mangohud.steam_config(), f"output_folder={theirs}\n")
        r = self.inspect(runner)
        self.assertEqual(r.output_folder, theirs)
        changes = mangohud.plan(r, self.settings)
        steam = next(c for c in changes if c.path == mangohud.steam_config())
        self.assertNotIn(f'output_folder={theirs}', steam.lines)
        override = next(c for c in changes if c.kind == 'override')
        self.assertIn(f'--filesystem={theirs}', override.argv)

    def test_wrong_layer_branch(self):
        runner = FakeFlatpak(branch='25.08', layers=('24.08',))
        r = self.inspect(runner)
        self.assertFalse(r.layer_ok)
        self.assertEqual(mangohud.layer_ref(r), f'{mangohud.LAYER}//25.08')
        ok, _ = mangohud.install_layer(r, runner)
        self.assertTrue(ok)
        self.assertIn(['flatpak', 'install', '--user', '-y', '--noninteractive', 'flathub',
                       f'{mangohud.LAYER}//25.08'], runner.calls)
        self.assertTrue(self.inspect(runner).layer_ok)
        mangohud.undo(runner)
        self.assertEqual(runner.calls[-1][:2], ['flatpak', 'uninstall'])

    def test_no_flatpak(self):
        r = self.inspect(FakeFlatpak(flatpak=False))
        self.assertFalse(r.steam_flatpak)
        self.assertTrue(r.layer_ok)

    def test_system_override_counts(self):
        path = os.path.join(_HOME, 'system-override')
        core.write_text(path, "[Environment]\nMANGOHUD=1\n")
        r = mangohud.inspect(self.settings, FakeFlatpak(), system_override=path)
        self.assertTrue(r.env_enabled)
        self.assertEqual(r.env_where, 'system')

    def test_pretty_key(self):
        self.assertEqual(mangohud.pretty_key('Control_L+F11'), 'Ctrl+F11')


# ─── Alerts ───────────────────────────────────────────────────

class Alerts(unittest.TestCase):
    def setUp(self):
        fresh_home()

    def test_watcher(self):
        folder = os.path.join(_HOME, 'out')
        os.makedirs(folder)
        open(os.path.join(folder, 'old.csv'), 'w').close()
        w = watch.FolderWatcher([folder])
        self.assertEqual(w.poll(), [])
        open(os.path.join(folder, 'Game_2026-11-22_10-00-00.csv'), 'w').close()
        self.assertEqual([k for k, _ in w.poll()], [watch.STARTED])
        open(os.path.join(folder, 'Game_2026-11-22_10-00-00_summary.csv'), 'w').close()
        self.assertEqual([k for k, _ in w.poll()], [watch.STOPPED])
        self.assertEqual(w.poll(), [])

    def test_lock_is_held_once(self):
        a, b = watch.AlertLock(), watch.AlertLock()
        assert_in_home(self, a.path)
        self.assertTrue(a.try_take())
        self.assertFalse(b.try_take())
        a.release()
        self.assertTrue(b.try_take())
        b.release()

    def test_messages(self):
        title, body = watch.message(watch.STARTED, 90)
        self.assertIn('90', body)
        self.assertTrue(watch.message(watch.STOPPED, 90)[0])

    def test_background_service(self):
        sc = FakeSystemctl()
        ok, _ = watch.enable_background(sc)
        self.assertTrue(ok)
        path = watch.unit_path()
        with open(path) as f:
            text = f.read()
        self.assertTrue(text.startswith(watch.UNIT_MARK))
        self.assertIn('--watch', text)
        self.assertTrue(watch.background_on(sc))
        ok, _ = watch.disable_background(sc)
        self.assertTrue(ok)
        self.assertFalse(os.path.exists(path))

    def test_their_unit_is_left_alone(self):
        path = watch.unit_path()
        core.write_text(path, "[Service]\nExecStart=/bin/true\n")
        watch.disable_background(FakeSystemctl())
        self.assertTrue(os.path.exists(path))


# ─── The window ───────────────────────────────────────────────

def have_display() -> bool:
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


def make_app(test, tab='recordings', runner=None):
    from sparkbench.app import App
    alerts = []
    app = App(tab=tab, runner=runner or FakeFlatpak(), systemctl=FakeSystemctl(),
              alerter=lambda kind, title, body: alerts.append((kind, title, body)), auto=False)
    test.addCleanup(app.close)
    app.alerts = alerts
    app.wait_idle()
    app.wait_idle()
    return app


@unittest.skipUnless(have_display(), "needs a display")
class Window(unittest.TestCase):
    def setUp(self):
        fresh_home()
        from sparkbench import views
        self.views = views

    def test_recordings_and_compare(self):
        folder = os.path.join(mangohud.steam_dir(), 'benchmark')
        stage(folder)
        lib = library.Library(core.load_settings(), folder)
        lib.import_files([os.path.join(PM, n) for n in PM_RUNS])
        app = make_app(self)
        self.assertEqual(len(app.library.runs), 5)
        from sparkbench.frames import Stats
        self.assertEqual(sum(isinstance(s, Stats) for s in app.stats.values()), 5)
        view = app.views['recordings']
        self.assertEqual(len(view.items), 5)
        iid = next(i for i, r in view.items.items() if r.id == MH_RUNS[0])
        view.tree.selection_set(iid)
        app.root.update()
        self.assertEqual(view.selected, MH_RUNS[0])
        view._count(view.items[iid], False)
        self.assertTrue(app.library.mark(MH_RUNS[0])['excluded'])
        view.trim_start.set('1')
        view._trim(view.items[iid])
        app.wait_idle()
        self.assertEqual(app.library.mark(MH_RUNS[0])['trim_start'], 1.0)
        app.show('compare')
        app.root.update()
        cmp = app.views['compare']
        self.assertEqual(cmp.baseline(), 'Windows')
        self.assertTrue(cmp.scroll.inner.winfo_children())
        app.show('setup')
        app.root.update()

    def test_watch_alerts(self):
        app = make_app(self)
        folder = app.report.output_folder
        os.makedirs(folder, exist_ok=True)
        app.watcher.set_folders([folder])
        shutil.copy(os.path.join(MH, MH_RUNS[0]), os.path.join(folder, 'Game_2026-11-22_10-00-00.csv'))
        app.poll()
        self.assertEqual([a[0] for a in app.alerts], [watch.STARTED])
        self.assertIsNotNone(app.live)
        open(os.path.join(folder, 'Game_2026-11-22_10-00-00_summary.csv'), 'w').close()
        app.poll()
        self.assertEqual([a[0] for a in app.alerts], [watch.STARTED, watch.STOPPED])
        self.assertIsNone(app.live)

    def test_quiet_while_the_background_watcher_alerts(self):
        other = watch.AlertLock()
        self.assertTrue(other.try_take())
        self.addCleanup(other.release)
        app = make_app(self)
        app.on_event(watch.STARTED, '/nowhere/x.csv')
        self.assertEqual(app.alerts, [])

    def test_fix_from_the_window(self):
        runner = FakeFlatpak()
        app = make_app(self, tab='setup', runner=runner)
        self.assertFalse(app.report.ready)
        original = self.views.dialogs.askokcancel
        self.views.dialogs.askokcancel = lambda *a, **k: True
        self.addCleanup(setattr, self.views.dialogs, 'askokcancel', original)
        app.views['setup'].fix()
        app.wait_idle()
        app.wait_idle()
        self.assertTrue(app.report.ready)
        app.views['setup'].undo()
        app.wait_idle()
        app.wait_idle()
        self.assertFalse(app.report.ready)
        self.assertFalse(os.path.exists(mangohud.steam_config()))

    def test_background_toggle(self):
        app = make_app(self, tab='setup')
        app.views['setup']._background(True)
        app.wait_idle()
        self.assertTrue(os.path.exists(watch.unit_path()))
        self.assertTrue(app.views['setup'].background.value)
        app.views['setup']._background(False)
        app.wait_idle()
        self.assertFalse(os.path.exists(watch.unit_path()))


class CommandLine(unittest.TestCase):
    def test_version_and_self_test(self):
        import io
        from contextlib import redirect_stdout
        from sparkbench import cli
        with self.assertRaises(SystemExit) as ctx, redirect_stdout(io.StringIO()) as out:
            cli.main(['--version'])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn('Spark Bench', out.getvalue())
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(['--self-test']), 0)
        self.assertIn('tkinter', out.getvalue())


if __name__ == '__main__':
    unittest.main()
