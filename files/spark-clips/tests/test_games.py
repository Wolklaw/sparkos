"""Game detection on made-up process trees: no real process is read."""

import os
import tempfile
import unittest

import testenv  # noqa: F401
from sparkclips import games
from sparkclips.games import Proc


def tree(*procs: Proc):
    return {p.pid: p for p in procs}


def no_names(_appid):
    return None


class Detect(unittest.TestCase):
    def test_nothing_running(self):
        self.assertIsNone(games.detect({}))
        busy = tree(Proc(1, 0, 'systemd', ['/usr/lib/systemd/systemd']),
                    Proc(100, 1, 'firefox', ['firefox']), Proc(101, 1, 'spark-terminal', ['spark-terminal']))
        self.assertIsNone(games.detect(busy, names=no_names))

    def test_spark_games_track(self):
        procs = tree(Proc(50, 1, 'python3', ['python3', '/usr/lib/spark-games/spark_games.py',
                                             '--track', '{"title": "Hollow Knight"}']))
        game = games.detect(procs)
        self.assertEqual((game.name, game.source), ('Hollow Knight', 'spark-games'))

    def test_spark_games_ignores_a_bad_spec(self):
        procs = tree(Proc(50, 1, 'python3', ['python3', 'spark_games.py', '--track', 'nope']))
        self.assertIsNone(games.detect(procs))

    def test_steam_game_uses_the_manifest_name(self):
        procs = tree(
            Proc(10, 1, 'reaper', ['reaper', 'SteamLaunch', 'AppId=1245620', '--', 'game']),
            Proc(11, 10, 'eldenring.exe', ['/x/eldenring.exe']))
        game = games.detect(procs, names=lambda appid: 'Elden Ring' if appid == '1245620' else None)
        self.assertEqual((game.name, game.source), ('Elden Ring', 'steam'))

    def test_steam_without_a_name_falls_back_to_the_id(self):
        procs = tree(Proc(10, 1, 'reaper', ['reaper', 'SteamLaunch', 'AppId=42']),
                     Proc(11, 10, 'x', ['x']))
        self.assertEqual(games.detect(procs, names=no_names).name, 'Steam 42')

    def test_steam_tools_and_a_launch_without_a_game_are_not_games(self):
        tool = tree(Proc(10, 1, 'reaper', ['reaper', 'SteamLaunch', 'AppId=1493710']),
                    Proc(11, 10, 'proton', ['proton']))
        self.assertIsNone(games.detect(tool, names=no_names))
        empty = tree(Proc(10, 1, 'reaper', ['reaper', 'SteamLaunch', 'AppId=620']))
        self.assertIsNone(games.detect(empty, names=no_names))

    def test_wine_exe(self):
        procs = tree(Proc(30, 1, 'wine64-preloader', ['Z:\\games\\Some_Game-x64.exe'],
                          '/usr/bin/wine64-preloader'))
        game = games.detect(procs)
        self.assertEqual((game.name, game.source), ('Some Game x64', 'wine'))

    def test_proton_through_umu(self):
        procs = tree(
            Proc(20, 1, 'umu-run', ['python3', '/usr/bin/umu-run', 'game.exe']),
            Proc(30, 20, 'wine64-preloader', ['C:\\Game\\Rogue.exe'], '/p/proton/wine64-preloader'))
        game = games.detect(procs)
        self.assertEqual((game.name, game.source), ('Rogue', 'proton'))

    def test_wine_helpers_are_not_games(self):
        for exe in ('explorer.exe', 'services.exe', 'winedevice.exe', 'EpicGamesLauncher.exe',
                    'UnityCrashHandler64.exe', 'vcredist_x64.exe', 'setup.exe'):
            procs = tree(Proc(30, 1, 'wine64-preloader', [exe], '/usr/bin/wine64-preloader'))
            self.assertIsNone(games.detect(procs), exe)

    def test_a_native_exe_name_alone_is_not_enough(self):
        procs = tree(Proc(30, 1, 'bash', ['/home/me/notes/report.exe'], '/usr/bin/bash'))
        self.assertIsNone(games.detect(procs))

    def test_gamemode_is_the_last_resort(self):
        procs = tree(Proc(70, 1, 'mygame', ['/opt/mygame/mygame'], '/opt/mygame/mygame'))
        game = games.detect(procs, gamemode_pids=[70])
        self.assertEqual((game.name, game.source), ('mygame', 'gamemode'))
        self.assertIsNone(games.detect(procs, gamemode_pids=[999]))

    def test_the_more_specific_rule_wins(self):
        procs = tree(
            Proc(10, 1, 'reaper', ['reaper', 'SteamLaunch', 'AppId=7']), Proc(11, 10, 'g', ['g']),
            Proc(70, 1, 'other', ['/opt/other'], '/opt/other'))
        self.assertEqual(games.detect(procs, gamemode_pids=[70], names=no_names).source, 'steam')

    def test_pretty_exe(self):
        self.assertEqual(games.pretty_exe('EldenRing.exe'), 'EldenRing')
        self.assertEqual(games.pretty_exe('my_game-x64.EXE'), 'my game x64')


class Steam(unittest.TestCase):
    def test_name_from_an_appmanifest_in_a_library_folder(self):
        with tempfile.TemporaryDirectory() as home:
            root = os.path.join(home, '.local/share/Steam/steamapps')
            os.makedirs(root)
            lib = os.path.join(home, 'Games', 'steamapps')
            os.makedirs(lib)
            with open(os.path.join(root, 'libraryfolders.vdf'), 'w') as f:
                f.write('"libraryfolders"\n{\n "0"\n {\n  "path"  "%s"\n }\n}\n' % os.path.dirname(lib))
            with open(os.path.join(lib, 'appmanifest_620.acf'), 'w') as f:
                f.write('"AppState"\n{\n\t"appid"\t"620"\n\t"name"\t"Portal 2"\n}\n')
            roots = games.steam_roots(home)
            self.assertIn(lib, roots)
            self.assertEqual(games.steam_name('620', roots), 'Portal 2')
            self.assertIsNone(games.steam_name('1', roots))

    def test_read_procs_reads_this_process(self):
        procs = games.read_procs()
        self.assertIn(os.getpid(), procs)


if __name__ == '__main__':
    unittest.main()
