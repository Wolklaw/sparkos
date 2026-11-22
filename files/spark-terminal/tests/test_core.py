"""Profile settings, the command line, and the helpers that need no window."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sparkterminal import cli, core, text  # noqa: E402


class TempHome(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {
            'XDG_CONFIG_HOME': os.path.join(self.tmp.name, 'config'),
            'XDG_STATE_HOME': os.path.join(self.tmp.name, 'state'),
        })
        patcher.start()
        self.addCleanup(patcher.stop)


class SettingsTest(TempHome):
    def test_defaults_when_no_file(self):
        self.assertEqual(core.load_settings(), core.DEFAULTS)
        self.assertEqual(core.DEFAULTS['scrollback'], 10000)

    def test_save_and_load_round_trip(self):
        data = dict(core.DEFAULTS, shell='/bin/sh', font_size=14, copy_on_select=False,
                    cursor='ibeam', bell='off')
        self.assertTrue(core.save_settings(data))
        self.assertEqual(core.load_settings(), data)
        path = os.path.join(core.config_dir(), core.SETTINGS_FILE)
        self.assertFalse(os.path.exists(path + '.tmp'))

    def test_broken_file_gives_defaults(self):
        folder = core.config_dir()
        with open(os.path.join(folder, core.SETTINGS_FILE), 'w') as f:
            f.write('{not json')
        self.assertEqual(core.load_settings(), core.DEFAULTS)

    def test_bad_values_fall_back_or_clamp(self):
        cleaned = core.clean_settings({
            'font_size': 500, 'scrollback': -4, 'cursor': 'heart', 'bell': True,
            'copy_on_select': 'yes', 'shell': 42, 'font': '  ', 'glitch': False,
            'unknown': 1})
        self.assertEqual(cleaned['font_size'], core.FONT_SIZE_RANGE[1])
        self.assertEqual(cleaned['scrollback'], 0)
        self.assertEqual(cleaned['cursor'], 'block')
        self.assertEqual(cleaned['bell'], 'visual')
        self.assertTrue(cleaned['copy_on_select'])
        self.assertEqual(cleaned['shell'], '')
        self.assertEqual(cleaned['font'], core.DEFAULTS['font'])
        self.assertFalse(cleaned['glitch'])
        self.assertNotIn('unknown', cleaned)
        self.assertEqual(core.clean_settings(['a list']), core.DEFAULTS)
        self.assertEqual(core.clean_settings({'font_size': True})['font_size'], 11)

    def test_check_settings(self):
        self.assertEqual(core.check_settings(core.DEFAULTS), [])
        problems = core.check_settings(dict(core.DEFAULTS, shell='no-such-shell-xyz',
                                            start_dir='/no/such/folder'))
        self.assertEqual([k for k, _ in problems], ['shell', 'start_dir'])
        self.assertEqual(core.check_settings(dict(core.DEFAULTS, shell='sh', start_dir='~')), [])


class ShellAndFolderTest(TempHome):
    def test_shell_from_settings_or_login(self):
        self.assertEqual(core.shell_argv(dict(core.DEFAULTS, shell='sh')), [core.resolve_program('sh')])
        with mock.patch.dict(os.environ, {'SHELL': '/bin/sh'}):
            self.assertEqual(core.shell_argv(core.DEFAULTS), ['/bin/sh'])
            # a shell that doesn't exist falls back to the login shell
            self.assertEqual(core.shell_argv(dict(core.DEFAULTS, shell='nope-xyz')), ['/bin/sh'])

    def test_login_shell_skips_missing(self):
        with mock.patch.dict(os.environ, {'SHELL': '/no/such/shell'}):
            self.assertTrue(os.access(core.login_shell(), os.X_OK))

    def test_start_folder_order(self):
        a = os.path.join(self.tmp.name, 'a')
        b = os.path.join(self.tmp.name, 'b')
        os.makedirs(a)
        os.makedirs(b)
        s = dict(core.DEFAULTS, start_dir=b)
        self.assertEqual(core.start_folder(a, s, cwd='/'), a)                 # --workdir
        self.assertEqual(core.start_folder(None, s, cwd='/'), b)              # profile
        self.assertEqual(core.start_folder('/missing', s, cwd='/'), b)        # skipped
        self.assertEqual(core.start_folder(None, core.DEFAULTS, cwd=a), a)    # started from
        self.assertEqual(core.start_folder(None, core.DEFAULTS, cwd='/missing'),
                         os.path.expanduser('~'))

    def test_child_env(self):
        lines = core.child_env({'PATH': '/usr/bin', 'TERM': 'dumb', 'KONSOLE_VERSION': '1',
                                'COLUMNS': '80', 'HOME': '/h'})
        env = dict(line.split('=', 1) for line in lines)
        self.assertEqual(env['PATH'], '/usr/bin')
        self.assertEqual(env['HOME'], '/h')
        self.assertEqual(env['TERM_PROGRAM'], 'spark-terminal')
        for gone in ('TERM', 'KONSOLE_VERSION', 'COLUMNS'):
            self.assertNotIn(gone, env)


class LinksTest(unittest.TestCase):
    def test_path_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = os.path.join(tmp, 'main.c')
            open(f, 'w').close()
            self.assertEqual(core.path_target(f, None), f)
            self.assertEqual(core.path_target(f + ':12:4', None), f)
            self.assertEqual(core.path_target(f + ',', None), f)
            self.assertEqual(core.path_target('./main.c:3', tmp), f)
            self.assertIsNone(core.path_target('main.c', None))
            self.assertIsNone(core.path_target('/no/such/file', tmp))

    def test_uri_to_path(self):
        self.assertEqual(core.uri_to_path('file:///home/a/b%20c'), '/home/a/b c')
        self.assertEqual(core.uri_to_path('file://host/tmp'), '/tmp')
        self.assertIsNone(core.uri_to_path('https://x'))
        self.assertIsNone(core.uri_to_path(None))

    def test_patterns_are_valid_python_regex_too(self):
        import re
        url = re.compile(core.URL_PATTERN)
        self.assertEqual(url.search('see https://wolklaw.dev/a?b=1. next').group(0),
                         'https://wolklaw.dev/a?b=1')
        self.assertEqual(url.search('(https://x.org/y)').group(0), 'https://x.org/y')
        path = re.compile(core.PATH_PATTERN)
        self.assertEqual(path.search('error in /etc/os-release:3 here').group(0),
                         '/etc/os-release:3')
        self.assertEqual(path.search('cd ~/Projects/a').group(0), '~/Projects/a')
        self.assertEqual(path.search('src/main.c:10:2: warning').group(0), 'src/main.c:10:2')


class RunningTest(unittest.TestCase):
    def test_running_program(self):
        with tempfile.TemporaryDirectory() as proc:
            os.makedirs(os.path.join(proc, '200'))
            with open(os.path.join(proc, '200', 'comm'), 'w') as f:
                f.write('vim\n')
            self.assertIsNone(core.running_program(100, 100, proc))     # shell in front
            self.assertEqual(core.running_program(100, 200, proc), 'vim')
            self.assertEqual(core.running_program(100, 300, proc), '?')  # gone already
            self.assertIsNone(core.running_program(-1, 200, proc))

    def test_command_label(self):
        self.assertEqual(core.command_label(['/usr/bin/bash', '-l']), 'bash')
        self.assertEqual(core.command_label([]), '')


class CommandLineTest(unittest.TestCase):
    def test_konsole_style(self):
        o = cli.parse(['--hold', '--workdir', '/tmp', '-e', 'sparkos-claude', '/tmp'])
        self.assertTrue(o.hold)
        self.assertEqual(o.workdir, '/tmp')
        self.assertEqual(o.command, ['sparkos-claude', '/tmp'])

    def test_everything_after_e_belongs_to_the_command(self):
        o = cli.parse(['--nofork', '-e', 'bash', '-c', 'echo "$1" --hold', '_', 'x'])
        self.assertFalse(o.hold)
        self.assertEqual(o.command, ['bash', '-c', 'echo "$1" --hold', '_', 'x'])

    def test_single_string_is_split(self):
        self.assertEqual(cli.parse(['-e', 'ls -l /tmp']).command, ['ls', '-l', '/tmp'])
        self.assertEqual(cli.parse(['-x', 'htop']).command, ['htop'])
        self.assertEqual(cli.parse(['--', 'less', 'f']).command, ['less', 'f'])
        self.assertEqual(cli.parse(['-e', "echo 'unclosed"]).command, ["echo 'unclosed"])

    def test_single_string_naming_a_real_program_with_spaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            prog = os.path.join(tmp, 'my prog')
            open(prog, 'w').close()
            self.assertEqual(cli.parse(['-e', prog]).command, [prog])

    def test_value_option_named_like_a_flag(self):
        # the -e after --title is the title, not the start of the command
        self.assertEqual(cli.split_command(['--title', '-e', '-e', 'top']),
                         (['--title', '-e'], ['top']))
        o = cli.parse(['--title', 'My title', '-e', 'top'])
        self.assertEqual((o.title, o.command), ('My title', ['top']))

    def test_aliases_and_ignored(self):
        o = cli.parse(['--working-directory', '/tmp', '--noclose', '--new-tab', '-p', 'x',
                       '--separate'])
        self.assertEqual(o.workdir, '/tmp')
        self.assertTrue(o.hold)
        self.assertEqual(o.command, [])

    def test_unknown_option_fails(self):
        with mock.patch('sys.stderr'):
            with self.assertRaises(SystemExit):
                cli.parse(['--frobnicate'])

    def test_version_and_self_test_flags(self):
        self.assertTrue(cli.parse(['--version']).version)
        self.assertTrue(cli.parse(['--self-test']).self_test)
        self.assertIn('Spark Terminal', cli.version_line())


class TextTest(unittest.TestCase):
    def test_both_languages_have_the_same_keys(self):
        self.assertEqual(set(text.EN), set(text.FR))

    def test_placeholders_match(self):
        import string
        for key, en in text.EN.items():
            names = {f for _, f, _, _ in string.Formatter().parse(en) if f}
            fr = {f for _, f, _, _ in string.Formatter().parse(text.FR[key]) if f}
            self.assertEqual(names, fr, key)

    def test_shortcut_lists_line_up(self):
        en = text.EN['keys.list'].splitlines()
        fr = text.FR['keys.list'].splitlines()
        self.assertEqual(len(en), len(fr))
        for line in en + fr:
            self.assertEqual(line.count('\t'), 1, line)


class AppFilesTest(unittest.TestCase):
    HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def test_manifest_matches_package(self):
        from sparkterminal import APP_ID, VERSION
        with open(os.path.join(self.HERE, 'spark-app.json'), encoding='utf-8') as f:
            manifest = json.load(f)
        self.assertEqual(manifest['id'], APP_ID)
        self.assertEqual(manifest['version'], VERSION)

    def test_desktop_entry(self):
        from sparkterminal import APP_ID
        with open(os.path.join(self.HERE, f'{APP_ID}.desktop'), encoding='utf-8') as f:
            entry = f.read()
        self.assertIn('Exec=spark-terminal\n', entry)
        self.assertIn('TerminalEmulator;', entry)
        self.assertIn('X-ExecArg=-e', entry)

    def test_scheme_matches_konsole_copy(self):
        """core.SCHEME and the Konsole colour scheme in the image are the same colours."""
        path = os.path.join(self.HERE, '..', 'system', 'usr', 'share', 'konsole',
                            'SparkOS.colorscheme')
        if not os.path.exists(path):
            self.skipTest('not in the SparkOS repo')
        colours = {}
        section = None
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('['):
                    section = line[1:-1]
                elif line.startswith('Color=') and section:
                    r, g, b = (int(x) for x in line[6:].split(','))
                    colours[section] = f'#{r:02x}{g:02x}{b:02x}'
        self.assertEqual(core.SCHEME['background'], colours['Background'])
        self.assertEqual(core.SCHEME['foreground'], colours['Foreground'])
        for i in range(8):
            self.assertEqual(core.SCHEME['palette'][i], colours[f'Color{i}'], i)
            self.assertEqual(core.SCHEME['palette'][i + 8], colours[f'Color{i}Intense'], i)


if __name__ == '__main__':
    unittest.main()
