"""Settings, autostart, the command line and the two languages. Everything runs in a throwaway
HOME; no display is needed and no real session file is read or written."""

import os
import subprocess
import sys
import tempfile
import unittest

import harness  # noqa: F401

from sparktray import autostart, core, text   # noqa: E402

APP = harness.APP


def run_cli(home, *args, lang='en'):
    env = {k: v for k, v in os.environ.items()
           if k not in ('DISPLAY', 'WAYLAND_DISPLAY', 'XDG_CONFIG_HOME', 'XDG_STATE_HOME',
                        'XDG_CURRENT_DESKTOP')}
    env.update(HOME=home, SPARK_LANG=lang)
    return subprocess.run([sys.executable, os.path.join(APP, 'spark_tray.py'), *args],
                          capture_output=True, text=True, env=env, timeout=60)


class Home(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = self.tmp.name
        saved = {k: os.environ.get(k) for k in ('HOME', 'XDG_CONFIG_HOME', 'XDG_STATE_HOME')}
        os.environ.update(HOME=self.home, XDG_CONFIG_HOME=os.path.join(self.home, 'c'),
                          XDG_STATE_HOME=os.path.join(self.home, 's'))

        def restore():
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.addCleanup(restore)


class ConfigTest(Home):
    def test_defaults_everything_on_power_hidden_without_battery(self):
        cfg = core.load_config()
        self.assertTrue(all(cfg['items'].values()))
        self.assertEqual(set(cfg['items']), set(core.ITEMS))
        self.assertFalse(cfg['power_show_without_battery'])

    def test_turning_one_item_off_is_saved(self):
        core.set_item_enabled('printers', False)
        cfg = core.load_config()
        self.assertFalse(cfg['items']['printers'])
        self.assertTrue(cfg['items']['network'])

    def test_a_broken_file_gives_the_defaults(self):
        with open(os.path.join(core.config_dir(), 'config.json'), 'w') as f:
            f.write('{nope')
        self.assertEqual(core.load_config(), core.DEFAULTS)

    def test_wrong_types_are_ignored(self):
        with open(os.path.join(core.config_dir(), 'config.json'), 'w') as f:
            f.write('{"items": {"network": "no"}, "popup_corner": "middle"}')
        cfg = core.load_config()
        self.assertTrue(cfg['items']['network'])
        self.assertEqual(cfg['popup_corner'], 'bottom-right')


class AutostartTest(Home):
    def test_enable_writes_a_file_without_only_show_in(self):
        autostart.enable()
        body = open(autostart.user_file(), encoding='utf-8').read()
        self.assertIn('Type=Application', body)
        self.assertNotIn('OnlyShowIn', body)
        self.assertNotIn('Hidden=true', body)
        self.assertEqual(autostart.status()['mode'], 'on')
        self.assertTrue(autostart.status()['effective'])

    def test_disable_hides_the_system_entry(self):
        autostart.disable()
        self.assertIn('Hidden=true', open(autostart.user_file(), encoding='utf-8').read())
        self.assertEqual(autostart.status()['mode'], 'off')
        self.assertFalse(autostart.status()['effective'])

    def test_reset_removes_the_file(self):
        autostart.enable()
        autostart.reset()
        self.assertFalse(os.path.exists(autostart.user_file()))
        autostart.reset()          # nothing to remove is fine
        self.assertEqual(autostart.status()['mode'], 'default')

    def test_the_spark_session_is_recognised(self):
        self.assertTrue(autostart.in_spark_session({'XDG_CURRENT_DESKTOP': 'Spark'}))
        self.assertTrue(autostart.in_spark_session({'XDG_CURRENT_DESKTOP': 'X-Foo:spark'}))
        self.assertFalse(autostart.in_spark_session({'XDG_CURRENT_DESKTOP': 'KDE'}))
        self.assertFalse(autostart.in_spark_session({}))

    def test_a_path_with_spaces_is_quoted(self):
        self.assertIn('Exec="/a b/spark-tray"', autostart.desktop_text('/a b/spark-tray'))
        self.assertIn('OnlyShowIn=Spark;', autostart.desktop_text('x', only_show_in='Spark'))


class CliTest(Home):
    def test_version(self):
        r = run_cli(self.home, '--version')
        self.assertEqual(r.returncode, 0)
        self.assertIn('Spark Tray', r.stdout)

    def test_item_off_and_status(self):
        r = run_cli(self.home, '--item', 'bluetooth', 'off')
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_cli(self.home, '--status')
        self.assertIn('bluetooth: off', r.stdout)
        self.assertIn('network: on', r.stdout)
        self.assertIn('autostart: default', r.stdout)

    def test_unknown_item_is_refused(self):
        r = run_cli(self.home, '--item', 'toaster', 'on')
        self.assertEqual(r.returncode, 2)
        self.assertIn('unknown item', r.stderr)

    def test_enable_disable_reset_through_the_command(self):
        self.assertEqual(run_cli(self.home, '--enable').returncode, 0)
        self.assertIn('autostart: on', run_cli(self.home, '--status').stdout)
        self.assertEqual(run_cli(self.home, '--disable').returncode, 0)
        self.assertIn('autostart: off', run_cli(self.home, '--status').stdout)
        self.assertEqual(run_cli(self.home, '--reset').returncode, 0)
        self.assertIn('autostart: default', run_cli(self.home, '--status').stdout)

    def test_power_without_battery(self):
        run_cli(self.home, '--power-without-battery', 'on')
        self.assertIn('power icon without a battery: on', run_cli(self.home, '--status').stdout)

    def test_no_display_means_a_clear_exit(self):
        r = run_cli(self.home)
        self.assertEqual(r.returncode, 1)
        self.assertIn('graphical session', r.stderr)

    def test_self_test_passes_without_a_display(self):
        r = run_cli(self.home, '--self-test')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('self-test passed', r.stdout)


class LanguageTest(unittest.TestCase):
    def test_the_two_tables_match(self):
        self.assertEqual(text.check_tables(), [])

    def test_french_has_real_translations(self):
        same = [k for k in text.EN if text.EN[k] == text.FR[k] and len(text.EN[k]) > 12]
        self.assertEqual(same, [], "sentences left in English in the French table")

    def test_a_missing_key_shows_the_key_not_a_crash(self):
        self.assertEqual(text.t('no.such.key'), 'no.such.key')

    def test_the_language_follows_spark_lang(self):
        for lang, word in (('en', 'Disconnect'), ('fr', 'Déconnecter')):
            code = ("import sys; sys.path.insert(0, %r); from sparktray.text import t; "
                    "print(t('net.disconnect'))" % APP)
            env = dict(os.environ, SPARK_LANG=lang)
            out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                                 env=env).stdout.strip()
            self.assertEqual(out, word)


if __name__ == '__main__':
    unittest.main()
