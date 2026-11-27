"""spark-foreground-booster against a fake /proc, a fake cgroup tree and a fake compositor
socket. Nothing here touches the real /sys/fs/cgroup or a real session."""

import importlib.machinery
import importlib.util
import os
import shutil
import socket
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, '..', '..', '..', 'files', 'system', 'usr', 'libexec',
                      'spark-foreground-booster')
loader = importlib.machinery.SourceFileLoader('booster', SCRIPT)
spec = importlib.util.spec_from_loader('booster', loader)
booster = importlib.util.module_from_spec(spec)
loader.exec_module(booster)

UID = 1000
APP = f'user.slice/user-{UID}.slice/user@{UID}.service/app.slice'
VRAM = 17163091968


class Fake(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, 'cg')
        self.proc = os.path.join(self.tmp, 'proc')
        os.makedirs(self.root)
        os.makedirs(self.proc)
        self.write(os.path.join(self.root, 'dmem.capacity'),
                   f'drm/0000:03:00.0/vram {VRAM}\ndrm/0000:03:00.0/stolen 0\n')
        self.messages = []
        booster.log = lambda *a: self.messages.append(' '.join(map(str, a)))
        self.b = booster.Booster(self.root, self.proc, UID)

    def write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(text)

    def read(self, rel, name):
        # a real cgroup file is replaced by a write; the fake one is overwritten in place, so the
        # newest value is the last line
        with open(os.path.join(self.root, rel, name)) as f:
            lines = f.read().strip().splitlines()
        return lines[-1] if lines else ''

    def unit(self, pid, unit, below='', with_files=True):
        """A process whose cgroup is app.slice/<below>/<unit>, with its dmem.low and cpu.weight."""
        rel = f'{APP}/{below}/{unit}'.replace('//', '/') if below else f'{APP}/{unit}'
        self.write(os.path.join(self.proc, str(pid), 'cgroup'), f'0::/{rel}\n')
        if with_files:
            d = os.path.join(self.root, f'{APP}/{below}/{unit}'.replace('//', '/')
                             if below else f'{APP}/{unit}')
            self.write(os.path.join(d, 'dmem.low'), '')
            self.write(os.path.join(d, 'cpu.weight'), '100\n')
        return rel

    def cgroup(self, pid, path):
        self.write(os.path.join(self.proc, str(pid), 'cgroup'), f'0::{path}\n')


class Boosting(Fake):
    def test_focus_boosts_and_undoes_the_previous_app(self):
        game = self.unit(10, 'app-steam-game-10.scope')
        browser = self.unit(11, 'app-firefox-11.scope')
        self.b.focus(10, 'game')
        self.assertEqual(self.read(game, 'dmem.low'), f'drm/0000:03:00.0/stolen 0')
        # each region was written on its own; the last write wins in a plain file, so look at
        # the writes themselves
        writes = []
        real = self.b._write
        self.b._write = lambda rel, name, text: writes.append((os.path.basename(rel), name, text)) \
            or real(rel, name, text)
        self.b.focus(11, 'firefox')
        self.assertEqual(writes, [
            ('app-steam-game-10.scope', 'dmem.low', 'drm/0000:03:00.0/vram 0'),
            ('app-steam-game-10.scope', 'dmem.low', 'drm/0000:03:00.0/stolen 0'),
            ('app-steam-game-10.scope', 'cpu.weight', '100'),
            ('app-firefox-11.scope', 'dmem.low', f'drm/0000:03:00.0/vram {VRAM}'),
            ('app-firefox-11.scope', 'dmem.low', 'drm/0000:03:00.0/stolen 0'),
            ('app-firefox-11.scope', 'cpu.weight', '10000')])
        self.assertEqual(self.read(game, 'cpu.weight'), '100')
        self.assertEqual(self.read(browser, 'cpu.weight'), '10000')

    def test_values_on_the_leaf_only(self):
        game = self.unit(10, 'app-game-10.scope')
        self.b.focus(10, 'game')
        self.assertEqual(self.read(game, 'cpu.weight'), '10000')
        for parent in (APP, os.path.dirname(APP), os.path.dirname(os.path.dirname(APP))):
            self.assertFalse(os.path.exists(os.path.join(self.root, parent, 'cpu.weight')))
            self.assertFalse(os.path.exists(os.path.join(self.root, parent, 'dmem.low')))

    def test_same_app_again_changes_nothing(self):
        self.unit(10, 'app-game-10.scope')
        self.b.focus(10, 'game')
        self.b.focus(10, 'game')
        self.assertEqual(len([m for m in self.messages if m.startswith('boosting')]), 1)

    def test_child_cgroup_of_a_unit_boosts_the_unit(self):
        rel = f'{APP}/app-flatpak-x-5.scope'
        self.write(os.path.join(self.proc, '5', 'cgroup'), f'0::/{rel}/sandbox/leaf\n')
        self.write(os.path.join(self.root, rel, 'cpu.weight'), '100\n')
        self.b.focus(5, 'x')
        self.assertEqual(self.read(rel, 'cpu.weight'), '10000')

    def test_unit_inside_an_app_slice_and_a_service(self):
        scope = self.unit(7, 'app-gnome-y-7.scope', below='app-gnome.slice')
        svc = self.unit(8, 'app-z@autostart.service')
        self.b.focus(7, 'y')
        self.assertEqual(self.read(scope.rsplit('/', 0)[0], 'cpu.weight'), '10000')
        self.b.focus(8, 'z')
        self.assertEqual(self.read(svc, 'cpu.weight'), '10000')
        self.assertEqual(self.read(scope, 'cpu.weight'), '100')

    def test_custom_weight(self):
        b = booster.Booster(self.root, self.proc, UID, cpu_weight=500)
        game = self.unit(10, 'app-game-10.scope')
        b.focus(10, 'game')
        self.assertEqual(self.read(game, 'cpu.weight'), '500')

    def test_release_undoes(self):
        game = self.unit(10, 'app-game-10.scope')
        self.b.focus(10, 'game')
        self.b.release()
        self.assertEqual(self.read(game, 'cpu.weight'), '100')
        self.assertIsNone(self.b.current)


class Skipping(Fake):
    def test_session_pieces_and_other_cgroups_are_skipped(self):
        self.cgroup(20, f'/user.slice/user-{UID}.slice/session-5.scope')
        self.cgroup(21, f'/user.slice/user-{UID}.slice/user@{UID}.service/background.slice/x.service')
        self.cgroup(22, f'/user.slice/user-{UID + 1}.slice/user@{UID + 1}.service/app.slice/app-a.scope')
        self.cgroup(23, f'/system.slice/foo.service')
        self.cgroup(24, f'/{APP}/spark-shell.service')
        self.cgroup(25, f'/{APP}/spark-compositor.service')
        self.cgroup(26, f'/{APP}/app.slice')                 # a bare slice, no unit
        self.cgroup(27, f'/{APP}/app-spark-foreground-booster.service')
        for pid in range(20, 28):
            for d in (f'{APP}/spark-shell.service', f'{APP}/spark-compositor.service',
                      f'{APP}/app-spark-foreground-booster.service'):
                self.write(os.path.join(self.root, d, 'cpu.weight'), '100\n')
            self.b.focus(pid, f'app{pid}')
        self.assertIsNone(self.b.current)
        for d in os.listdir(os.path.join(self.root, APP)):
            self.assertEqual(self.read(f'{APP}/{d}', 'cpu.weight'), '100')
        # every skip is said once, with the reason
        self.assertTrue(any('part of the Spark session' in m for m in self.messages))
        before = len(self.messages)
        self.b.focus(24, 'app24')
        self.assertEqual(len(self.messages), before)

    def test_focus_on_a_skipped_app_keeps_the_boost(self):
        game = self.unit(10, 'app-game-10.scope')
        self.cgroup(30, f'/user.slice/user-{UID}.slice/session-5.scope')
        self.b.focus(10, 'game')
        self.b.focus(30, 'shell')
        self.b.focus(0, '')
        self.assertEqual(self.read(game, 'cpu.weight'), '10000')

    def test_dead_pid(self):
        self.b.focus(999, 'gone')
        self.assertIsNone(self.b.current)


class NoDmem(Fake):
    def test_no_dmem_files_is_quiet(self):
        os.remove(os.path.join(self.root, 'dmem.capacity'))
        game = self.unit(10, 'app-game-10.scope', with_files=False)
        os.makedirs(os.path.join(self.root, game))
        self.b.focus(10, 'game')
        self.assertEqual(os.listdir(os.path.join(self.root, game)), [])
        self.assertEqual([m for m in self.messages if 'cannot write' in m], [])

    def test_dmem_without_cpu_controller(self):
        game = self.unit(10, 'app-game-10.scope', with_files=False)
        self.write(os.path.join(self.root, game, 'dmem.low'), '')
        self.b.focus(10, 'game')
        self.assertFalse(os.path.exists(os.path.join(self.root, game, 'cpu.weight')))

    def test_permission_error_is_said_once(self):
        game = self.unit(10, 'app-game-10.scope')
        os.chmod(os.path.join(self.root, game, 'cpu.weight'), 0o444)
        if os.access(os.path.join(self.root, game, 'cpu.weight'), os.W_OK):
            self.skipTest('running as root')
        self.b.focus(10, 'game')
        self.b.release()
        self.b.focus(10, 'game')
        self.assertEqual(len([m for m in self.messages if 'cannot write' in m]), 1)


class FakeCtl:
    """A control socket: answers "watch" with "ok" and then sends the lines it is given."""
    def __init__(self, path):
        self.path = path
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(path)
        self.server.listen(1)
        self.conn = None
        self.got = b''

    def accept(self, timeout=5):
        self.server.settimeout(timeout)
        self.conn, _ = self.server.accept()
        self.conn.settimeout(timeout)
        while b'\n' not in self.got:
            self.got += self.conn.recv(100)

    def send(self, text):
        self.conn.sendall(text.encode())

    def close(self):
        for s in (self.conn, self.server):
            if s:
                s.close()


class Socket(Fake):
    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.tmp, 'ctl')
        self.stop = threading.Event()
        self.addCleanup(self.stop.set)

    def start(self, **kw):
        thread = threading.Thread(target=self.b.run, args=(self.path, self.stop.is_set),
                                  kwargs=kw, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(self.stop.set)
        return thread

    def until(self, check, timeout=5):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if check():
                return True
            time.sleep(0.02)
        return check()

    def test_watch_focus_lines(self):
        game = self.unit(10, 'app-game-10.scope')
        browser = self.unit(11, 'app-ff-11.scope')
        ctl = FakeCtl(self.path)
        self.addCleanup(ctl.close)
        self.start()
        ctl.accept()
        self.assertEqual(ctl.got, b'watch\n')
        ctl.send('ok\nworkspace 2\ntiling on\nfocus 10 game\n')
        self.assertTrue(self.until(lambda: self.read(game, 'cpu.weight') == '10000'))
        ctl.send('focus 11 fire')          # a line split over two sends
        time.sleep(0.1)
        ctl.send('fox\ntiling off\n')
        self.assertTrue(self.until(lambda: self.read(browser, 'cpu.weight') == '10000'))
        self.assertEqual(self.read(game, 'cpu.weight'), '100')
        ctl.send('focus 0 \n')
        time.sleep(0.2)
        self.assertEqual(self.read(browser, 'cpu.weight'), '10000')

    def test_waits_for_the_socket_logs_once_and_connects_later(self):
        game = self.unit(10, 'app-game-10.scope')
        sleeps = []
        self.start(backoff=(0.1, 0.2), sleep=lambda s: (sleeps.append(s), time.sleep(s)))
        time.sleep(0.8)
        self.assertEqual(len([m for m in self.messages if m.startswith('waiting')]), 1)
        ctl = FakeCtl(self.path)
        self.addCleanup(ctl.close)
        ctl.accept()
        ctl.send('ok\nfocus 10 game\n')
        self.assertTrue(self.until(lambda: self.read(game, 'cpu.weight') == '10000'))
        self.assertTrue(any('connected' in m for m in self.messages))

    def test_compositor_going_away_releases_and_reconnects(self):
        game = self.unit(10, 'app-game-10.scope')
        ctl = FakeCtl(self.path)
        self.start(backoff=(0.1,))
        ctl.accept()
        ctl.send('ok\nfocus 10 game\n')
        self.assertTrue(self.until(lambda: self.read(game, 'cpu.weight') == '10000'))
        ctl.close()
        os.remove(self.path)
        self.assertTrue(self.until(lambda: self.read(game, 'cpu.weight') == '100'))
        ctl2 = FakeCtl(self.path)
        self.addCleanup(ctl2.close)
        ctl2.accept()
        ctl2.send('ok\nfocus 10 game\n')
        self.assertTrue(self.until(lambda: self.read(game, 'cpu.weight') == '10000'))


if __name__ == '__main__':
    unittest.main()
