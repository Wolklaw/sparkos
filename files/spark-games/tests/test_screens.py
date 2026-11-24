"""screens.py: restarting an added launcher's Wine session after the screens change."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
    os.environ[var] = tempfile.mkdtemp(prefix=f'spark-games-{var.lower()}-')
os.environ['SPARK_LANG'] = 'en'

from sparkgames import launch, launchers, screens, strings  # noqa: E402
from sparkgames.core import Game  # noqa: E402


class FakeChild:
    """The launcher command (umu-run): runs until stopped or until it is told to end."""

    def __init__(self, ends_after=None):
        self.alive, self.polls, self.ends_after = True, 0, ends_after

    def poll(self):
        self.polls += 1
        if self.ends_after is not None and self.polls > self.ends_after:
            self.alive = False
        return None if self.alive else 0

    def wait(self, timeout=None):
        self.alive = False
        return 0


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


class ScreensCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='spark-games-screens-')
        self.drm = os.path.join(self.tmp, 'drm')
        self.proc = os.path.join(self.tmp, 'proc')
        self.prefix = os.path.join(self.tmp, 'prefixes', 'battlenet')
        os.makedirs(os.path.join(self.prefix, 'drive_c', 'Program Files (x86)', 'Battle.net'))
        os.symlink('.', os.path.join(self.prefix, 'pfx'))        # as umu-run makes it
        os.makedirs(self.proc)
        for name in ('card1-DP-1', 'card1-HDMI-A-1', 'card1-DP-3', 'card1-Writeback-1'):
            self.screen(name, 'disconnected' if 'Writeback' in name else 'connected')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def screen(self, name, status):
        os.makedirs(os.path.join(self.drm, name), exist_ok=True)
        with open(os.path.join(self.drm, name, 'status'), 'w') as f:
            f.write(status + '\n')

    def process(self, pid, arg0, prefix=None):
        path = os.path.join(self.proc, str(pid))
        os.makedirs(path, exist_ok=True)
        prefix = self.prefix if prefix is None else prefix
        with open(os.path.join(path, 'environ'), 'wb') as f:
            f.write(b'HOME=/home/x\0' + (b'WINEPREFIX=' + prefix.encode() + b'\0' if prefix else b''))
        with open(os.path.join(path, 'cmdline'), 'wb') as f:
            f.write(arg0.encode() + b'\0--flag\0')

    def launcher_running(self):
        pfx = os.path.join(self.prefix, 'pfx') + '/'
        self.process(10, '/usr/bin/python3', prefix=self.prefix)
        self.process(11, '/home/x/.local/share/Steam/compatibilitytools.d/P/files/bin/wineserver', pfx)
        self.process(12, 'C:\\windows\\system32\\explorer.exe', pfx)
        self.process(13, 'C:\\Program Files (x86)\\Battle.net\\Battle.net.exe', pfx)
        self.process(14, 'C:/ProgramData/Battle.net/Agent/Agent.9886/Agent.exe', pfx)
        self.process(15, '\\\\?\\X:\\.local\\share\\Steam\\compatibilitytools.d\\P\\xalia\\xalia.exe', pfx)
        self.process(16, 'C:\\Program Files\\Other\\Other.exe', '/somewhere/else')   # another prefix
        self.process(17, 'start.exe', pfx)                       # Wine's, by name alone

    def session(self):
        exe = os.path.join(self.prefix, 'drive_c', 'Program Files (x86)', 'Battle.net',
                           'Battle.net Launcher.exe')
        return launchers.session('battlenet', self.prefix, exe)


class DetectTests(ScreensCase):
    def test_connected_screens(self):
        self.assertEqual(screens.connected(self.drm),
                         {'card1-DP-1', 'card1-HDMI-A-1', 'card1-DP-3'})
        self.assertEqual(screens.connected(os.path.join(self.tmp, 'none')), frozenset())

    def test_session_folders(self):
        s = self.session()
        self.assertEqual(s['name'], 'Battle.net')
        self.assertEqual(s['homes'], ['c:\\program files (x86)\\battle.net\\',
                                      'c:\\programdata\\battle.net\\'])
        self.assertEqual(screens.windows_dir(self.prefix, '/elsewhere/dir'), '')

    def test_launcher_alone_is_not_a_game(self):
        self.launcher_running()
        self.assertFalse(screens.game_running(self.prefix, self.session()['homes'], self.proc))

    def test_game_outside_the_prefix_folders_is_a_game(self):
        self.launcher_running()
        self.process(20, 'Z:\\var\\mnt\\e\\Battle.Net\\World of Warcraft\\_forever_\\Wow.exe',
                     os.path.join(self.prefix, 'pfx') + '/')
        self.assertTrue(screens.game_running(self.prefix, self.session()['homes'], self.proc))

    def test_game_in_the_launchers_games_folder_is_a_game(self):
        # Ubisoft keeps games under its own folder, in games\
        home = 'c:\\program files (x86)\\ubisoft\\ubisoft game launcher\\'
        self.process(21, 'C:\\Program Files (x86)\\Ubisoft\\Ubisoft Game Launcher\\games\\X\\x.exe')
        self.assertTrue(screens.game_running(self.prefix, [home], self.proc))
        shutil.rmtree(os.path.join(self.proc, '21'))
        self.process(22, 'C:\\Program Files (x86)\\Ubisoft\\Ubisoft Game Launcher\\upc.exe')
        self.assertFalse(screens.game_running(self.prefix, [home], self.proc))

    def test_plan_carries_the_session(self):
        exe = os.path.join(self.prefix, 'drive_c', 'Program Files (x86)', 'Battle.net',
                           'Battle.net Launcher.exe')
        open(exe, 'w').close()
        game = Game(key='battlenet:launcher', title='Battle.net', source='battlenet',
                    install_dir=self.prefix, store_id='battlenet',
                    launch={'spark': True, 'store': 'battlenet', 'launcher': True, 'exe': exe,
                            'prefix': self.prefix})
        plan = launchers.plan(game, {}, lambda name: '/usr/bin/' + name)
        self.assertEqual(plan.session['prefix'], self.prefix)
        self.assertIn('c:\\programdata\\battle.net\\', plan.session['homes'])

    def test_words(self):
        self.assertIn('Battle.net', strings.tr('screens_restarted', name='Battle.net'))


class KeepTests(ScreensCase):
    def run_keep(self, script, child=None, limit=400):
        """script(t) runs before each look; returns (restarts, told, children started)."""
        clock = Clock()
        told, started = [], []
        child = child or FakeChild()
        stops = []
        original = screens.stop_session

        def stop(prefix, c, proc='/proc', **_):
            stops.append(clock())
            c.wait()

        def sleep(seconds):
            clock.sleep(seconds)
            script(clock())
            if clock() > limit:
                for c in [child] + started:
                    c.alive = False

        def start():
            c = FakeChild()
            started.append(c)
            return c

        screens.stop_session = stop
        try:
            n = screens.keep(child, start, self.session(), look=lambda: screens.connected(self.drm),
                             proc=self.proc,
                             clock=clock, sleep=sleep, tell=told.append)
        finally:
            screens.stop_session = original
        return n, told, started, stops

    def test_nothing_changes_nothing_restarts(self):
        self.launcher_running()
        n, told, started, _ = self.run_keep(lambda t: None)
        self.assertEqual((n, told, started), (0, [], []))

    def test_screen_blip_restarts_once_screens_settle(self):
        self.launcher_running()

        def script(t):
            if t == 50:
                self.screen('card1-DP-3', 'disconnected')        # a monitor sleeps...
            if t == 52:
                self.screen('card1-DP-3', 'connected')           # ...and wakes 2 s later
        n, told, started, stops = self.run_keep(script)
        self.assertEqual(n, 1)
        self.assertEqual(len(started), 1)
        self.assertGreaterEqual(stops[0], 52 + screens.SETTLE)
        self.assertEqual(told, [strings.tr('screens_restarted', name='Battle.net')])

    def test_waits_for_the_game_to_end(self):
        self.launcher_running()
        wow = os.path.join(self.proc, '20')

        def script(t):
            if t == 10:
                self.process(20, 'Z:\\games\\World of Warcraft\\_forever_\\Wow.exe',
                             os.path.join(self.prefix, 'pfx') + '/')
            if t == 50:
                self.screen('card1-DP-3', 'disconnected')
            if t == 300:
                shutil.rmtree(wow)                                 # the game ends
        n, told, started, stops = self.run_keep(script)
        self.assertEqual(n, 1)
        self.assertGreaterEqual(stops[0], 300)

    def test_ends_with_the_launcher(self):
        child = FakeChild(ends_after=3)
        n, told, started, _ = self.run_keep(lambda t: None, child=child)
        self.assertEqual((n, started), (0, []))

    def test_track_hands_a_launcher_to_keep(self):
        seen = {}
        original = screens.keep

        def keep(child, start, session, **_):
            seen['session'] = session
            child.wait()
            return 0
        screens.keep = keep
        try:
            spec = {'key': 'battlenet:launcher', 'argv': [sys.executable, '-c', 'pass'],
                    'session': {'prefix': self.prefix, 'homes': [], 'name': 'Battle.net'}}
            self.assertIsNone(launch.track(spec))
        finally:
            screens.keep = original
        self.assertEqual(seen['session']['name'], 'Battle.net')


class StopTests(ScreensCase):
    def test_stop_session_signals_only_this_prefix(self):
        real = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                                env=dict(os.environ, WINEPREFIX=os.path.join(self.prefix, 'pfx')))
        other = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                                 env=dict(os.environ, WINEPREFIX=os.path.join(self.tmp, 'other')))
        try:
            screens.stop_session(self.prefix, real, wait=10)
            self.assertIsNotNone(real.poll())
            self.assertIsNone(other.poll())
        finally:
            for p in (real, other):
                p.kill()
                p.wait()


if __name__ == '__main__':
    unittest.main()
