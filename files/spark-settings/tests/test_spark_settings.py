"""Spark Settings tests. Every tool is a fake from tests/fixtures/bin that logs its arguments;
nothing here touches the machine's real settings. Run: python3 -m unittest discover -s tests -v
(the window tests need a display: Xvfb in CI, skipped without one)."""

import ast
import glob
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIX = os.path.join(HERE, 'fixtures')
sys.path.insert(0, ROOT)

# the fake tools must be executable even where a checkout dropped the mode bit
for _f in glob.glob(os.path.join(FIX, 'bin', '*')):
    os.chmod(_f, 0o755)

_tmp = tempfile.mkdtemp(prefix='spark-settings-test-')
LOG = os.path.join(_tmp, 'calls.log')
os.environ.update({
    'HOME': _tmp, 'XDG_CONFIG_HOME': os.path.join(_tmp, 'config'),
    'XDG_STATE_HOME': os.path.join(_tmp, 'state'), 'XDG_DATA_HOME': os.path.join(_tmp, 'data'),
    'PATH': os.path.join(FIX, 'bin') + os.pathsep + os.environ['PATH'],
    'FAKE_LOG': LOG, 'SPARK_SETTINGS_APPDIRS': os.path.join(FIX, 'apps'),
    'SPARK_SETTINGS_OS_RELEASE': os.path.join(FIX, 'os-release'),
    'SPARK_SETTINGS_AUTOSTART_DIRS': os.path.join(_tmp, 'autostart'),
    'SPARK_SETTINGS_TEST_PAGE': os.path.join(FIX, 'os-release'),
    # no test may reach the real system or session bus (logind, timedated ...);
    # test_dbus.py swaps in private fake buses for its own classes
    'DBUS_SYSTEM_BUS_ADDRESS': 'unix:path=/nonexistent/system',
    'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/nonexistent/session',
})
os.environ.pop('DBUS_STARTER_ADDRESS', None)
# Windows only open on CI's Xvfb, never on the desktop someone is using
os.environ.pop('WAYLAND_DISPLAY', None)
if not os.environ.get('CI'):
    os.environ.pop('DISPLAY', None)

from sparksettings import (bluetooth, clock, core, defaults, displays, network,  # noqa: E402
                           power, printers, sound, startup, sysinfo)


def calls():
    try:
        return open(LOG).read().splitlines()
    except FileNotFoundError:
        return []


def reset_calls():
    open(LOG, 'w').close()


def have_display():
    try:
        import tkinter
        r = tkinter.Tk()
        r.destroy()
        return True
    except Exception:
        return False


class Parsers(unittest.TestCase):
    def test_displays(self):
        outs = displays.parse(open(os.path.join(FIX, 'displays.json')).read())
        self.assertEqual([o.name for o in outs], ['DP-1', 'DP-2', 'HDMI-A-1'])
        a = outs[0]
        self.assertEqual(a.mode.res, '2560x1440')
        self.assertEqual(a.mode.rate, '143.91')
        self.assertEqual(a.vrr, 'always')
        self.assertEqual(outs[1].vrr, 'never')
        self.assertEqual(a.label, 'DP-1: Acme Panel One')
        self.assertEqual(a.rates('1920x1080')[0].hz, 119.98)
        self.assertEqual(displays.parse('not json'), [])

    def test_display_commands(self):
        o = displays.parse(open(os.path.join(FIX, 'displays.json')).read())[1]
        self.assertEqual(displays.a_mode(o, '1920x1080@60.000'), 'output.DP-2.mode.1920x1080@60.000')
        self.assertEqual(displays.a_scale(o, 1.25), 'output.DP-2.scale.1.25')
        self.assertEqual(displays.a_rotation(o, 'left'), 'output.DP-2.rotation.left')
        self.assertEqual(displays.a_hdr(o, True), 'output.DP-2.hdr.enable')
        self.assertEqual(displays.a_position(o, 10, 20), 'output.DP-2.position.10,20')

    def test_restore(self):
        outs = displays.parse(open(os.path.join(FIX, 'displays.json')).read())
        args = displays.restore_args(outs, ['DP-1'])
        self.assertIn('output.DP-1.mode.2560x1440@143.910', args)
        self.assertIn('output.DP-1.position.0,0', args)
        self.assertIn('output.DP-1.vrrpolicy.always', args)
        self.assertFalse([a for a in args if 'DP-2' in a])

    def test_hdr_goes_to_outputs_conf(self):
        conf = displays._conf_path()
        if os.path.exists(conf):
            os.remove(conf)
        o = displays.load()[0]
        reset_calls()
        self.assertTrue(displays.apply([displays.a_hdr(o, True)]))
        self.assertEqual(calls(), ['wlr-randr --json'])
        text = open(conf).read()
        self.assertIn('output DP-1 mode=2560x1440@143.910 scale=1 transform=normal pos=0,0 vrr=on hdr=on', text)
        self.assertTrue(displays.load()[0].hdr)
        self.assertFalse(displays.load()[1].hdr)
        displays.apply([displays.a_hdr(o, False)])
        self.assertNotIn('hdr=on', open(conf).read())

    def test_sound(self):
        st = sound.parse_status(open(os.path.join(FIX, 'wpctl-status.txt')).read())
        self.assertEqual([(s.id, s.default, s.muted) for s in st.sinks], [(52, True, False), (53, False, True)])
        self.assertIn('FiiO', st.sinks[0].name)
        self.assertEqual(st.sinks[0].volume, 0.40)
        self.assertEqual([s.id for s in st.sources], [54])
        self.assertIn('QuadCast', st.sources[0].name)
        self.assertEqual([s.id for s in st.streams], [60])

    def test_sound_commands(self):
        reset_calls()
        sound.set_default(53)
        sound.set_volume(52, 0.5)
        sound.set_mute(52, True)
        self.assertEqual(calls(), ['wpctl set-default 53', 'wpctl set-volume 52 0.50', 'wpctl set-mute 52 1'])

    STREAM0 = '''FiiO USB DAC-E10 at usb-0000:0e:00.0-1, full : USB Audio

Playback:
  Status: Running
  Interface 1
    Altset 1
    Format: S32_LE
    Endpoint: 0x01 (1 OUT) (ASYNC)
    Rates: 44100, 48000, 88200, 96000
  Interface 1
    Altset 2
    Format: S16_LE
    Endpoint: 0x01 (1 OUT) (ASYNC)
    Rates: 44100, 48000, 88200, 96000

Capture:
  Status: Stop
  Interface 2
    Altset 1
    Endpoint: 0x82 (2 IN) (ASYNC)
    Rates: 16000
'''

    def test_sample_rates_parse(self):
        name, rates = sound.parse_stream(self.STREAM0)
        self.assertIn('FiiO', name)
        self.assertEqual(rates, [44100, 48000, 88200, 96000])      # no capture rate
        self.assertEqual(sound.parse_stream('Cam\n\nCapture:\n    Rates: 16000\n')[1], [])
        self.assertEqual(sound.parse_stream('Dac\n\nPlayback:\n    Rates: 44100 - 192000 (continuous)\n')[1],
                         [44100, 48000, 88200, 96000, 176400, 192000])
        self.assertEqual(sound.parse_stream('')[1], [])
        self.assertEqual([sound.rate_label(r) for r in (44100, 48000, 96000, 192000)],
                         ['44.1 kHz', '48 kHz', '96 kHz', '192 kHz'])

    def test_sample_rates_per_device(self):
        root = tempfile.mkdtemp()
        for n, text in ((0, self.STREAM0),
                        (3, 'Kingston HyperX Quadcast at usb-1, full speed : USB Audio\n\n'
                            'Playback:\n    Rates: 44100, 48000\n')):
            os.makedirs(os.path.join(root, f'card{n}'))
            open(os.path.join(root, f'card{n}', 'stream0'), 'w').write(text)
        self.assertEqual(sound.device_rates('FiiO USB DAC-E10 Analog Stereo', root),
                         [44100, 48000, 88200, 96000])
        self.assertEqual(sound.device_rates('HyperX Quadcast Analog Stereo', root), [44100, 48000])
        self.assertEqual(sound.device_rates('Built-in Audio HDMI', root), sound.FALLBACK_RATES)
        self.assertEqual(sound.device_rates('FiiO', os.path.join(root, 'nothing')),
                         [44100, 48000, 96000, 192000])

    def test_sample_rate_file(self):
        home = tempfile.mkdtemp()
        old = os.environ['XDG_CONFIG_HOME']
        os.environ['XDG_CONFIG_HOME'] = os.path.join(home, '.config')
        try:
            path = sound.rate_file()
            self.assertEqual(path, os.path.join(home, '.config', 'pipewire', 'pipewire.conf.d',
                                                '50-sample-rates.conf'))
            self.assertEqual(sound.read_rate(), 0)                 # no file: follow the track
            self.assertTrue(sound.write_rate(0))                   # removing nothing is fine
            self.assertTrue(sound.write_rate(96000))
            text = open(path).read()
            self.assertTrue(text.startswith('# Written by Spark Settings'))
            self.assertIn('context.properties = {\n    default.clock.rate = 96000\n'
                          '    default.clock.allowed-rates = [ 96000 ]\n}\n', text)
            self.assertEqual(sound.read_rate(), 96000)
            self.assertTrue(sound.write_rate(192000))
            self.assertEqual(sound.read_rate(), 192000)
            self.assertEqual(open(path).read().count('default.clock.rate = '), 1)
            self.assertFalse(os.path.exists(path + '.tmp'))
            self.assertTrue(sound.write_rate(0))
            self.assertFalse(os.path.exists(path))
            self.assertEqual(sound.read_rate(), 0)
            # the user's existing file, written by hand, is read as it is
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, 'w').write('context.properties = {\n    default.clock.rate          = 96000\n'
                                  '    default.clock.allowed-rates = [ 96000 ]\n}\n')
            self.assertEqual(sound.read_rate(), 96000)
        finally:
            os.environ['XDG_CONFIG_HOME'] = old

    def test_sample_rate_apply(self):
        reset_calls()
        self.assertTrue(sound.apply_rate(96000))
        self.assertTrue(sound.apply_rate(0))
        self.assertEqual(calls(), ['pw-metadata -n settings 0 clock.force-rate 96000',
                                   'pw-metadata -n settings 0 clock.force-rate 0'])

    def test_network(self):
        self.assertEqual(network.split_terse(r'no:Neighbour\:5G:45:WPA2'), ['no', 'Neighbour:5G', '45', 'WPA2'])
        nets = network.wifi_list()
        self.assertEqual(nets[0].ssid, 'HomeNet')
        self.assertTrue(any(n.ssid == 'Neighbour:5G' for n in nets))
        self.assertTrue(network.wifi_enabled())
        self.assertEqual([v for v in network.vpns()][0].name, 'Work VPN')

    def test_bluetooth(self):
        self.assertTrue(bluetooth.powered())
        devs = bluetooth.devices()
        self.assertEqual([d.name for d in devs], ['Headphones', 'Controller'])
        self.assertTrue(devs[0].connected)
        self.assertFalse(devs[1].connected)
        reset_calls()
        bluetooth.connect('77:88:99:AA:BB:CC')
        self.assertTrue(any(c.startswith('bluetoothctl connect 77:88') for c in calls()))

    def test_power(self):
        self.assertEqual(sorted(power.profiles()), ['balanced', 'performance', 'power-saver'])
        self.assertEqual(power.current(), 'balanced')
        reset_calls()
        power.set_profile('performance')
        self.assertEqual(calls(), ['powerprofilesctl set performance'])
        # without powerprofilesctl (Fedora's tuned-ppd) it goes over D-Bus with busctl
        real, power.have = power.have, lambda t: t != 'powerprofilesctl'
        try:
            self.assertEqual(sorted(power.profiles()), ['balanced', 'performance', 'power-saver'])
            self.assertEqual(power.current(), 'balanced')
            reset_calls()
            power.set_profile('power-saver')
            self.assertEqual(calls(), ['busctl --system set-property net.hadess.PowerProfiles '
                                       '/net/hadess/PowerProfiles net.hadess.PowerProfiles '
                                       'ActiveProfile s power-saver'])
        finally:
            power.have = real

    def test_default_apps(self):
        apps = defaults.installed_apps()
        self.assertEqual(sorted(a.name for a in apps.values()), ['Test Browser', 'Test Player'])
        cat = [c for c in defaults.CATEGORIES if c[0] == 'browser'][0]
        names = [a.name for a in defaults.candidates(cat[2], apps)]
        self.assertEqual(names, ['Test Browser'])
        reset_calls()
        defaults.set_default('browser.desktop', cat[2])
        self.assertTrue(calls()[0].startswith('xdg-mime default browser.desktop '))
        self.assertIn('text/html', calls()[0])
        self.assertIn('x-scheme-handler/https', calls()[0])

    def test_clock(self):
        self.assertIsNone(clock.zone())      # no bus here; tests/test_dbus.py has the fake timedated
        self.assertIn('Europe/Paris', clock.zones())

    def test_printers(self):
        ps = printers.printers()
        self.assertEqual(ps[0].name, 'Canon_TR4700')
        self.assertTrue(ps[0].default)
        found = printers.discover()
        self.assertTrue(any('Canon' in f.name for f in found))
        reset_calls()
        printers.make_default('Canon_TR4700')
        self.assertEqual(calls(), ['lpadmin -d Canon_TR4700'])

    def test_startup_off_is_a_user_copy(self):
        sysdir = os.path.join(_tmp, 'autostart')
        os.makedirs(sysdir, exist_ok=True)
        with open(os.path.join(sysdir, 'thing.desktop'), 'w') as f:
            f.write("[Desktop Entry]\nType=Application\nName=Thing\nExec=thing\n")
        items = startup.items()
        self.assertTrue(any(i.name == 'Thing' for i in items))

    def test_sysinfo(self):
        self.assertEqual(sysinfo.os_release()['PRETTY_NAME'], 'SparkOS 43 (Test)')
        self.assertIn('SparkOS', sysinfo.report([('OS', 'SparkOS')], '1'))

class Backends(unittest.TestCase):
    """The pieces that write settings, against files in the throwaway HOME."""

    def test_spark_json_merges(self):
        self.assertTrue(core.spark_save('t1', a=1))
        self.assertTrue(core.spark_save('t1', b=2))
        self.assertEqual(core.spark_load('t1'), {'a': 1, 'b': 2})
        self.assertTrue(core.spark_file('t1').startswith(os.path.join(_tmp, 'config', 'spark')))
        self.assertEqual(core.spark_load('missing'), {})

    def test_shortcut_keys(self):
        from sparksettings import shortcuts
        self.assertEqual(shortcuts.key_text('Super+Ctrl+e'), 'Super+Ctrl+E')
        self.assertEqual(shortcuts.key_text(''), '')
        self.assertEqual(shortcuts.key_code('e', 0x4 | 0x40), 'Super+Ctrl+e')
        self.assertIsNone(shortcuts.key_code('Shift_L', 0))
        self.assertEqual(shortcuts.key_code('Escape', 0), 'Escape')

    def test_lsblk(self):
        from sparksettings import storage
        text = json.dumps({'blockdevices': [{'name': 'sda', 'rm': False, 'children': [
            {'name': 'sda1', 'label': 'Games', 'fstype': 'ext4', 'mountpoint': '/var/mnt/games',
             'size': 1000, 'fsavail': 400, 'rm': False},
            {'name': 'sda2', 'fstype': 'vfat', 'mountpoint': '/boot/efi', 'size': 5, 'rm': False}]},
            {'name': 'sdb', 'rm': True, 'children': [
                {'name': 'sdb1', 'fstype': 'exfat', 'mountpoint': '/run/media/u/USB', 'size': 9,
                 'fsavail': 3, 'rm': True}]}]})
        vols = storage.parse_lsblk(text)
        self.assertEqual([(v.title, v.free) for v in vols], [('Games', 400)])
        self.assertEqual(storage.parse_lsblk('nope'), [])

    def test_notifications_and_power_are_saved_for_spark(self):
        from sparksettings import notifications
        self.assertEqual(notifications.get(), {'seconds': 5, 'position': 'TopRight'})
        self.assertTrue(notifications.save(seconds=8, position='BottomLeft'))
        self.assertEqual(notifications.get(), {'seconds': 8, 'position': 'BottomLeft'})
        self.assertEqual(core.spark_load('notifications'), {'seconds': 8, 'position': 'BottomLeft'})
        self.assertTrue(power.set_timers(10, 30))
        self.assertEqual(power.timers(), {'screen_off': 10, 'sleep': 30})
        self.assertTrue(power.lock_set(True, 5, False))
        self.assertEqual(power.lock_get(), {'autolock': True, 'minutes': 5, 'on_resume': False})
        conf = open(os.path.join(_tmp, 'config', 'spark', 'compositor', 'compositor.conf')).read()
        self.assertIn('idle lock=300 screen_off=600 suspend=1800', conf)

    def test_reduced_motion_follows_the_animations_setting(self):
        from sparksettings import appearance
        os.environ.pop('SPARK_SETTINGS_REDUCED_MOTION', None)
        try:
            self.assertFalse(core.reduced_motion())
            self.assertTrue(appearance.set_animations(False))
            self.assertTrue(core.reduced_motion())
            self.assertFalse(appearance.get()['animations'])
            os.environ['SPARK_SETTINGS_REDUCED_MOTION'] = '1'
            self.assertTrue(core.reduced_motion())
        finally:
            os.environ.pop('SPARK_SETTINGS_REDUCED_MOTION', None)
            appearance.set_animations(True)

    def test_default_terminal_goes_to_xdg_terminals_list(self):
        self.assertTrue(defaults.terminal_set('dev.wolklaw.SparkTerminal.desktop'))
        self.assertEqual(defaults.terminal_get(), 'dev.wolklaw.SparkTerminal.desktop')

    def test_appearance_lists_and_writes(self):
        from sparksettings import appearance
        share = os.path.join(_tmp, 'share')
        pic = os.path.join(share, 'wallpapers', 'Dusk', 'contents', 'images')
        os.makedirs(pic, exist_ok=True)
        for n in ('1280x720.png', '2560x1440.png'):
            open(os.path.join(pic, n), 'w').close()
        os.environ['SPARK_SETTINGS_SHARE_DIRS'] = share
        try:
            self.assertEqual(appearance.wallpapers(), [('Dusk', os.path.join(pic, '2560x1440.png'))])
            self.assertTrue(appearance.set_wallpaper(os.path.join(pic, '2560x1440.png')))
            self.assertEqual(core.spark_load('shell')['wallpaper'], os.path.join(pic, '2560x1440.png'))
        finally:
            del os.environ['SPARK_SETTINGS_SHARE_DIRS']

    def test_startup_add_and_remove(self):
        from sparksettings import startup
        os.makedirs(os.path.join(_tmp, 'autostart'), exist_ok=True)
        self.assertFalse(startup.add_app('nothing.desktop'))
        self.assertTrue(startup.add_app('player.desktop'))
        item = next(i for i in startup.items() if i.file == 'player.desktop')
        self.assertTrue(startup.is_mine(item))
        self.assertTrue(startup.remove(item))
        self.assertFalse(any(i.file == 'player.desktop' for i in startup.items()))

    def test_user_names(self):
        from sparksettings import accounts
        self.assertTrue(accounts.valid_name('anna_2'))
        self.assertFalse(accounts.valid_name('Anna'))


class TaskbarOptions(unittest.TestCase):
    """The Spark Connect widget key and the workspace count, in the throwaway HOME."""

    def setUp(self):
        from sparksettings import taskbar
        self.taskbar = taskbar
        # a compositor pid file must never be found, so no test can signal a real one
        self._rt = os.environ.get('XDG_RUNTIME_DIR')
        os.environ['XDG_RUNTIME_DIR'] = tempfile.mkdtemp(prefix='spark-rt-')
        self._conf = os.path.join(os.environ['XDG_CONFIG_HOME'], 'spark', 'compositor',
                                  'compositor.conf')
        for path in (self._conf, core.spark_file('shell'), core.spark_file('appearance')):
            if os.path.exists(path):
                os.remove(path)

    def tearDown(self):
        if self._rt is None:
            os.environ.pop('XDG_RUNTIME_DIR', None)
        else:
            os.environ['XDG_RUNTIME_DIR'] = self._rt

    def test_connect_defaults_and_merge(self):
        self.assertEqual(self.taskbar.connect_get(), {'enabled': False, 'monitor': ''})
        core.spark_save('shell', wallpaper='a.png', pinned=['x.desktop'])
        self.assertTrue(self.taskbar.connect_set(enabled=True))
        self.assertTrue(self.taskbar.connect_set(monitor=' DP-1 '))
        self.assertEqual(self.taskbar.connect_get(), {'enabled': True, 'monitor': 'DP-1'})
        saved = core.spark_load('shell')
        self.assertEqual(saved['wallpaper'], 'a.png')
        self.assertEqual(saved['pinned'], ['x.desktop'])
        self.taskbar.connect_set(enabled=False)
        self.assertEqual(self.taskbar.connect_get(), {'enabled': False, 'monitor': 'DP-1'})
        self.taskbar.connect_set(monitor='')
        self.assertEqual(self.taskbar.connect_get()['monitor'], '')

    def test_connect_ignores_junk(self):
        core.spark_save('shell', connect_widget='yes')
        self.assertEqual(self.taskbar.connect_get(), {'enabled': False, 'monitor': ''})
        core.spark_save('shell', connect_widget={'enabled': 1, 'monitor': 5})
        self.assertEqual(self.taskbar.connect_get(), {'enabled': False, 'monitor': ''})

    def test_screens_come_from_the_fake_wlr_randr(self):
        self.assertIn('DP-1', [c for c, _l in self.taskbar.screens()])

    def test_clamp(self):
        for raw, want in ((0, 1), (1, 1), (4, 4), (9, 9), (12, 9), ('6', 6), ('x', 4), (None, 4)):
            self.assertEqual(self.taskbar.clamp_workspaces(raw), want, raw)

    def test_workspaces_line_keeps_the_rest(self):
        os.makedirs(os.path.dirname(self._conf), exist_ok=True)
        with open(self._conf, 'w') as f:
            f.write('output DP-1 scale=1\nworkspaces count=2\n')
        self.assertEqual(self.taskbar.workspaces_get(), 4)
        self.assertTrue(self.taskbar.workspaces_set(6))
        text = open(self._conf).read()
        self.assertIn('output DP-1 scale=1', text)
        self.assertEqual(text.count('workspaces count='), 1)
        self.assertIn('workspaces count=6', text)
        self.assertEqual(self.taskbar.workspaces_get(), 6)
        self.assertTrue(self.taskbar.workspaces_set(99))
        self.assertIn('workspaces count=9', open(self._conf).read())

    def test_no_workspaces_line_until_set(self):
        from sparksettings import inputdev
        self.assertTrue(inputdev._compositor_write())
        self.assertNotIn('workspaces', open(self._conf).read())


class French(unittest.TestCase):
    def test_every_string_has_french(self):
        from sparksettings.fr import FR
        found = set()
        for f in glob.glob(os.path.join(ROOT, 'sparksettings', '*.py')):
            if os.path.basename(f) in ('fr.py', 'lang.py', 'widgets.py'):
                continue
            for n in ast.walk(ast.parse(open(f, encoding='utf-8').read())):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == '_' \
                        and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                    found.add(n.args[0].value)
        for _k, label, _m in defaults.CATEGORIES:
            found.add(label)
        missing = sorted(s for s in found if s not in FR and s.strip() and any(c.isalpha() for c in s))
        self.assertEqual(missing, [])

    def test_placeholders_match(self):
        import re
        from sparksettings.fr import FR
        for en, fr in FR.items():
            self.assertEqual(sorted(re.findall(r'\{\w*\}', en)), sorted(re.findall(r'\{\w*\}', fr)), en)


class SelfTest(unittest.TestCase):
    def test_runs(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'spark_settings.py'), '--self-test'],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('self-test passed', r.stdout)


@unittest.skipUnless(have_display(), 'no display')
class Window(unittest.TestCase):
    app = None

    @classmethod
    def setUpClass(cls):
        from sparksettings.app import App
        cls.app = App()

    @classmethod
    def tearDownClass(cls):
        cls.app.root.destroy()

    def test_every_page_opens(self):
        from sparksettings.pages import SIDEBAR
        for key in SIDEBAR:
            self.app.open_page(key)
            self.app.idle(3)
            self.assertIs(self.app.current, self.app.pages[key])

    def test_sound_page_shows_the_saved_rate(self):
        """The rate in the user's own file is the one selected; with none, follow the track."""
        from sparksettings.ui import Choice
        old = os.environ['XDG_CONFIG_HOME']
        os.environ['XDG_CONFIG_HOME'] = tempfile.mkdtemp()
        try:
            self.app.open_page('sound')
            self.app.idle(3)
            page = self.app.pages['sound']
            st = sound.parse_status(open(os.path.join(FIX, 'wpctl-status.txt')).read())

            def rate_choice():
                page.sig = None
                page.render(st)
                found = []

                def walk(w):
                    if isinstance(w, Choice) and w.options[0][1] == '0':
                        found.append(w)
                    for c in w.winfo_children():
                        walk(c)
                walk(page.holder)
                self.assertEqual(len(found), 1)
                return found[0]

            self.assertEqual(rate_choice().value, '0')
            sound.write_rate(96000)
            choice = rate_choice()
            self.assertEqual(choice.value, '96000')
            self.assertIn(('96 kHz', '96000'), choice.options)
            self.assertIn('96 kHz', choice.label.cget('text'))
        finally:
            os.environ['XDG_CONFIG_HOME'] = old

    def test_new_pages_show_their_sections(self):
        for key in ('appearance', 'input', 'shortcuts', 'notifications', 'users', 'storage',
                    'power', 'startup', 'datetime'):
            self.app.open_page(key)
            self.app.idle(3)
            self.assertIs(self.app.current, self.app.pages[key], key)

    def test_search_finds_refresh_rate_on_displays(self):
        hits = self.app.find('refresh')
        self.assertIn('displays', [t for _s, t in hits])
        self.assertIn('sound', [t for _s, t in self.app.find('fiio dac')] + ['sound'])
        self.assertIn('displays', [t for _s, t in self.app.find('taux')] + ['displays'])

    def test_display_change_reverts_after_the_countdown(self):
        self.app.open_page('displays')
        page = self.app.pages['displays']
        self.app.idle(3)
        o = page.outputs[1]
        reset_calls()
        page.change([o.name], [displays.a_scale(o, 1.5)])
        self.app.idle(3)
        self.assertEqual(calls()[0], 'wlr-randr --output DP-2 --scale 1.5')
        self.assertIsNotNone(page.pending)
        reset_calls()
        for _ in range(page.REVERT_SECONDS):
            page.tick()
        self.app.idle(3)
        self.assertIsNone(page.pending)
        back = [c for c in calls() if c.startswith('wlr-randr --output')]
        self.assertTrue(back and '--scale 1 ' in back[0] and '--mode 1920x1080@119.980Hz' in back[0], back)
        self.assertNotIn('DP-1', back[0])

    def test_display_change_kept(self):
        self.app.open_page('displays')
        page = self.app.pages['displays']
        self.app.idle(3)
        o = page.outputs[2]
        page.change([o.name], [displays.a_rotation(o, 'left')])
        self.app.idle(3)
        reset_calls()
        page.keep()
        page.tick()
        self.app.idle(2)
        self.assertEqual(calls(), [])
        self.assertIsNone(page.pending)


if __name__ == '__main__':
    unittest.main()
