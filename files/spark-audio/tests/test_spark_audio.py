"""Spark Audio tests. No PipeWire, no sound card and no Scarlett needed: everything runs on the
saved data in tests/fixtures (a sanitized pw-dump of a real PC, and a made-up Scarlett 2i2).
The window tests need a display (Xvfb in CI) and skip without one."""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURES = os.path.join(HERE, 'fixtures')
sys.path.insert(0, ROOT)
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
    os.environ.setdefault(var, tempfile.mkdtemp(prefix=f'spark-audio-{var.lower()}-'))

from sparkaudio import eq, model  # noqa: E402
from sparkaudio.backend import FakeBackend  # noqa: E402
from sparkaudio.core import gain_to_volume, volume_to_gain  # noqa: E402
from sparkaudio.scarlett import (Interface, classify, fake_runner, find_interfaces,  # noqa: E402
                                 parse_contents)


def read(name):
    with open(os.path.join(FIXTURES, name), encoding='utf-8') as f:
        return f.read()


class Volume(unittest.TestCase):
    def test_round_trip(self):
        for v in (0.0, 0.25, 0.5, 0.8, 1.0, 1.3):
            self.assertAlmostEqual(gain_to_volume(volume_to_gain(v)), v, places=6)

    def test_cube(self):
        self.assertAlmostEqual(volume_to_gain(0.5), 0.125)


class Devices(unittest.TestCase):
    def setUp(self):
        self.state = FakeBackend(FIXTURES).state()

    def titles(self, nodes):
        return [n.title for n in nodes]

    def test_the_owners_devices_have_sensible_names(self):
        sinks = ' | '.join(self.titles(self.state.sinks))
        sources = ' | '.join(self.titles(self.state.sources))
        self.assertIn('FiiO USB DAC-E10', sinks)
        self.assertIn('Onboard audio (ALC897)', sinks)
        self.assertIn('HyperX QuadCast', sources)
        self.assertIn('Logitech C920', sources)
        self.assertIn('Onboard audio (ALC897)', sources)

    def test_no_raw_alsa_names(self):
        for n in self.state.sinks + self.state.sources:
            self.assertNotIn('alsa_', n.title)
            self.assertNotIn('Analog Stereo', n.title)

    def test_defaults_are_found(self):
        self.assertIsNotNone(self.state.sink_by_id(self.state.default_sink))
        self.assertIsNotNone(self.state.source_by_id(self.state.default_source))

    def test_monitors_are_not_inputs(self):
        for n in self.state.sources:
            self.assertNotIn('Monitor', n.kind)
            self.assertFalse(n.name.endswith('.monitor'))

    def test_cards_have_profiles(self):
        self.assertTrue(self.state.cards)
        self.assertTrue(any(c.profiles for c in self.state.cards))

    def test_streams_are_listed(self):
        self.assertTrue(self.state.playing)
        for s in self.state.playing:
            self.assertFalse(s.name.startswith('spark-audio-'))


class Graph(unittest.TestCase):
    def test_removal_and_update(self):
        text = read('pw-dump.json')
        graph = model.Graph()
        batches = model.parse_dump(text)
        for b in batches:
            graph.apply(b)
        before = graph.state()
        sink = before.sinks[0]
        graph.apply([{'id': sink.id, 'type': 'PipeWire:Interface:Node', 'info': None}])
        after = graph.state()
        self.assertEqual(len(after.sinks), len(before.sinks) - 1)

    def test_garbage_is_ignored(self):
        self.assertEqual(model.parse_dump(''), [])
        self.assertEqual(model.parse_dump('not json'), [])


class FakeControls(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend(FIXTURES)
        self.state = self.backend.state()

    def test_volume(self):
        node = self.state.sinks[0]
        self.backend._apply_volume(node, 0.5)
        again = self.backend.state().sink_by_id(node.id)
        self.assertAlmostEqual(again.volume, 0.5, places=2)

    def test_mute(self):
        node = self.state.sinks[0]
        self.backend.set_mute(node, True)
        self.assertTrue(self.backend.state().sink_by_id(node.id).mute)
        self.backend.set_mute(node, False)
        self.assertFalse(self.backend.state().sink_by_id(node.id).mute)

    def test_default(self):
        other = [n for n in self.state.sinks if n.id != self.state.default_sink][0]
        self.backend.set_default(other)
        self.assertEqual(self.backend.state().default_sink, other.id)


class Equalizer(unittest.TestCase):
    def test_presets_have_one_gain_per_band(self):
        for name, gains in eq.PRESETS.items():
            self.assertEqual(len(gains), len(eq.BANDS), name)

    def test_preset_name(self):
        for name, gains in eq.PRESETS.items():
            self.assertEqual(eq.preset_name(gains), name)
        self.assertEqual(eq.preset_name([1.3, 0, 0, 0, 0]), 'custom')

    def test_clamp(self):
        out = eq.clamp_gains([99, -99, 1])
        self.assertEqual(len(out), len(eq.BANDS))
        self.assertEqual(out[0], eq.GAIN_MAX)
        self.assertEqual(out[1], eq.GAIN_MIN)
        self.assertEqual(out[3], 0.0)

    def test_preamp_never_boosts(self):
        self.assertLessEqual(eq.preamp_gain([6, 6, 6, 6, 6]), 1.0)
        self.assertEqual(eq.preamp_gain([0] * 5), 1.0)

    def test_config_names_the_sink_and_the_bands(self):
        conf = eq.chain_config('alsa_output.usb-FiiO', 'FiiO USB DAC-E10', [0, 0, 5.5, 0, 0])
        self.assertIn('spark_eq.alsa_output.usb-FiiO', conf)
        self.assertIn('FiiO USB DAC-E10 (EQ)', conf)
        self.assertIn('eq_band_3', conf)
        self.assertIn('5.5', conf)
        self.assertIn('alsa_output.usb-FiiO', conf)

    def test_full_config_has_one_chain_per_output(self):
        conf = eq.full_config({'a': {'enabled': True, 'gains': [0] * 5, 'title': 'A'},
                               'b': {'enabled': True, 'gains': [0] * 5, 'title': 'B'},
                               'c': {'enabled': False, 'gains': [0] * 5, 'title': 'C'}})
        self.assertEqual(conf.count('spark_eq.a'), conf.count('spark_eq.b'))
        self.assertNotIn('spark_eq.c', conf)


class EqFiles(unittest.TestCase):
    """The real manager writing into a temp folder, with a fake systemctl."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-audio-eq-')
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.log = os.path.join(self.dir, 'calls')
        ctl = os.path.join(self.dir, 'ctl')
        with open(ctl, 'w') as f:
            f.write(f'#!/bin/sh\necho "$@" >> "{self.log}"\n')
        os.chmod(ctl, 0o755)
        os.environ['XDG_CONFIG_HOME'] = self.dir
        self.addCleanup(os.environ.pop, 'XDG_CONFIG_HOME', None)
        self.manager = eq.EqManager(conf_path=os.path.join(self.dir, 'eq.conf'),
                                    unit_dir=os.path.join(self.dir, 'units'), systemctl=[ctl])

    def calls(self):
        try:
            with open(self.log) as f:
                return f.read()
        except OSError:
            return ''

    def test_enable_writes_and_starts(self):
        self.manager.enable('out.a', 'Speaker', [0, 0, 3, 0, 0])
        self.assertTrue(os.path.exists(self.manager.unit_path))
        self.assertTrue(os.path.exists(self.manager.conf_path))
        self.assertIn('restart', self.calls())
        self.assertTrue(self.manager.get('out.a').enabled)

    def test_remove_leaves_nothing(self):
        self.manager.enable('out.a', 'Speaker', [0] * 5)
        self.manager.remove('out.a')
        self.assertFalse(os.path.exists(self.manager.unit_path))
        self.assertFalse(os.path.exists(self.manager.conf_path))
        self.assertIn('disable --now', self.calls())
        self.assertFalse(self.manager.installed())

    def test_two_outputs_keep_the_service_until_both_go(self):
        self.manager.enable('out.a', 'A', [0] * 5)
        self.manager.enable('out.b', 'B', [0] * 5)
        self.manager.remove('out.a')
        self.assertTrue(os.path.exists(self.manager.unit_path))
        self.manager.disable('out.b')
        self.assertFalse(os.path.exists(self.manager.unit_path))

    def test_remove_all(self):
        self.manager.enable('out.a', 'A', [0] * 5)
        self.manager.remove_all()
        self.assertFalse(self.manager.installed())


class Scarlett(unittest.TestCase):
    def test_parse(self):
        controls = parse_contents(read('amixer-contents.txt'))
        self.assertGreater(len(controls), 20)
        kinds = {c.kind for c in controls}
        self.assertTrue({'BOOLEAN', 'ENUMERATED', 'INTEGER'} <= kinds)
        enum = [c for c in controls if c.kind == 'ENUMERATED'][0]
        self.assertTrue(enum.items)

    def test_classify(self):
        page = classify(parse_contents(read('amixer-contents.txt')))
        self.assertTrue(page.inputs)
        self.assertTrue(page.phantom)
        self.assertTrue(page.monitor)
        self.assertTrue(page.outputs)
        self.assertTrue(page.mix)

    def test_finds_only_a_scarlett(self):
        runner = fake_runner(FIXTURES)
        found = find_interfaces(runner, read('proc-asound-cards.txt'))
        self.assertEqual([i.card for i in found], [1])

    def test_nothing_without_the_tool(self):
        self.assertEqual(find_interfaces(lambda argv: (1, 'no amixer'), read('proc-asound-cards.txt')), [])

    def test_write_and_read_back(self):
        iface = Interface(1, 'Scarlett', fake_runner(FIXTURES))
        controls = iface.read()
        switch = [c for c in controls if c.kind == 'BOOLEAN' and c.writable][0]
        self.assertTrue(iface.set(switch, not switch.on))
        again = [c for c in iface.read() if c.numid == switch.numid][0]
        self.assertEqual(again.on, not switch.on)


class Command(unittest.TestCase):
    def run_cli(self, *args):
        env = dict(os.environ, SPARK_LANG='en')
        return subprocess.run([sys.executable, os.path.join(ROOT, 'spark_audio.py'), *args],
                              capture_output=True, text=True, timeout=60, env=env)

    def test_version(self):
        r = self.run_cli('--version')
        self.assertEqual(r.returncode, 0)
        self.assertIn('Spark Audio', r.stdout)

    def test_self_test_on_the_fixtures(self):
        r = self.run_cli('--self-test', '--fake', FIXTURES)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('FiiO USB DAC-E10', r.stdout)
        self.assertIn('scarlett:  card 1', r.stdout)
        self.assertIn('self-test passed', r.stdout)


def have_display() -> bool:
    try:
        import tkinter as tk
        probe = tk.Tk()
        probe.destroy()
        return True
    except Exception:  # noqa: BLE001
        return False


@unittest.skipUnless(have_display(), "needs a display")
class Window(unittest.TestCase):
    def pump(self, app, seconds):
        end = time.time() + seconds
        while time.time() < end:
            app.root.update()
            time.sleep(0.02)

    def make(self, tab='outputs'):
        from sparkaudio.app import App
        os.environ['SPARK_AUDIO_SCALE'] = '1'
        app = App(FIXTURES, tab)
        self.addCleanup(app.close)
        self.pump(app, 0.6)
        return app

    def test_every_tab_builds(self):
        app = self.make()
        for tab in ('inputs', 'apps', 'eq', 'scarlett', 'outputs'):
            app.show(tab)
            self.pump(app, 0.3)
            self.assertEqual(app.tab, tab)
            self.assertEqual(app.views[tab].winfo_manager(), 'pack')

    def test_scarlett_tab_only_with_a_scarlett(self):
        app = self.make()
        self.assertIn('scarlett', [k for k, _ in app._tab_list()])
        self.assertTrue(app.scarlett)

    def test_mute_button_mutes(self):
        app = self.make()
        node = app.backend.state().sinks[0]
        app.backend.set_mute(node, True)
        self.pump(app, 0.4)
        self.assertTrue(app.backend.state().sink_by_id(node.id).mute)

    def test_set_default_updates_the_list(self):
        app = self.make()
        state = app.backend.state()
        other = [n for n in state.sinks if n.id != state.default_sink][0]
        app.backend.set_default(other)
        self.pump(app, 0.4)
        self.assertEqual(app.backend.state().default_sink, other.id)

    def test_meters_stop_when_hidden(self):
        app = self.make()
        app._pause()
        self.assertFalse(app.visible)
        self.assertEqual(app.meters.meters, {})


if __name__ == '__main__':
    unittest.main()
