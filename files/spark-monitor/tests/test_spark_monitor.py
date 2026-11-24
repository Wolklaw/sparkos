"""Spark Monitor tests. Plain unittest:

    python -m unittest discover -s files/spark-monitor/tests -v

Parsers run against a fake /proc and /sys tree in fixtures/root (an AMD Ryzen with 16 threads,
an RX 6800 XT and the CPU's own graphics, an NVMe drive, Plasma 6 app scopes, a Flatpak Steam
running a game). They run anywhere, Windows included. End task tests start real processes
and need Linux. UI tests need a display (on CI: xvfb-run).
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
FIXTURE = os.path.join(HERE, 'fixtures', 'root')
sys.path.insert(0, APP_DIR)
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
    os.environ[var] = tempfile.mkdtemp(prefix=f'spark-monitor-{var.lower()}-')
os.environ['SPARK_MONITOR_REDUCED_MOTION'] = '1'
os.environ.pop('SPARK_MONITOR_ROOT', None)

from sparkmonitor import APP_ID, SHORTCUT, VERSION, core, startup  # noqa: E402
from sparkmonitor import system as sysm  # noqa: E402
from sparkmonitor.cli import self_test, shortcut_owner  # noqa: E402
from sparkmonitor.ender import ENDED, FAILED, FORCED, RUNNING, Ender  # noqa: E402
from sparkmonitor.procs import (APP, BACKGROUND, SYSTEM, ProcSampler, SteamLibrary,  # noqa: E402
                                classify, desktop_id_from_unit, parse_stat)
from sparkmonitor.desktop import DesktopIndex, find_icon, parse_desktop  # noqa: E402
from sparkmonitor.source import Source, read_int  # noqa: E402
from sparkmonitor.text import t  # noqa: E402

LINUX = sys.platform.startswith('linux')
PAGE = 4096
try:
    PAGE = os.sysconf('SC_PAGE_SIZE')
except (AttributeError, ValueError, OSError):
    pass


def rewrite(root, rel, fn):
    path = os.path.join(root, rel)
    with open(path, encoding='utf-8') as f:
        text = f.read()
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(fn(text))


def bump_stat(root, pid, ticks=0, start=None):
    """Add CPU ticks to a process (utime), or give its PID a new start time."""
    def fn(text):
        right = text.rfind(')')
        fields = text[right + 2:].split()
        fields[11] = str(int(fields[11]) + ticks)
        if start is not None:
            fields[19] = str(start)
        return text[:right + 2] + ' '.join(fields) + '\n'
    rewrite(root, f'proc/{pid}/stat', fn)


def bump_gpu(root, pid, fd, ns):
    def fn(text):
        lines = []
        for line in text.splitlines():
            if line.startswith('drm-engine-gfx:'):
                value = int(line.split()[1]) + ns
                line = f'drm-engine-gfx:\t{value} ns'
            lines.append(line)
        return '\n'.join(lines) + '\n'
    rewrite(root, f'proc/{pid}/fdinfo/{fd}', fn)


class FixtureCase(unittest.TestCase):
    """Each test gets its own copy of the fake tree, so it can change numbers between
    samples and write autostart overrides."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-monitor-test-')
        self.root = os.path.join(self.dir, 'root')
        shutil.copytree(FIXTURE, self.root)
        self.src = Source(self.root)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)


# ─── Whole-machine numbers ────────────────────────────────────

class SystemTests(FixtureCase):
    def test_read_int_hex(self):
        self.assertEqual(read_int(os.path.join(self.root, 'sys/class/drm/card1/device/vendor')),
                         0x1002)

    def test_cpu_percent_from_two_samples(self):
        s = sysm.SystemSampler(self.src)
        first = s.sample(0.0)
        self.assertIsNone(first.cpu)                 # one sample can't give a rate
        self.assertEqual(s.threads, 16)

        def fn(text):
            out = []
            for line in text.splitlines():
                parts = line.split()
                if parts and parts[0] == 'cpu':      # +800 busy (user), +800 idle
                    parts[1] = str(int(parts[1]) + 800)
                    parts[4] = str(int(parts[4]) + 800)
                elif parts and parts[0] == 'cpu0':   # fully busy
                    parts[1] = str(int(parts[1]) + 100)
                elif parts and parts[0] == 'cpu1':   # idle
                    parts[4] = str(int(parts[4]) + 100)
                out.append(' '.join(parts))
            return '\n'.join(out) + '\n'
        rewrite(self.root, 'proc/stat', fn)
        snap = s.sample(1.0)
        self.assertAlmostEqual(snap.cpu, 50.0)
        self.assertAlmostEqual(snap.threads[0], 100.0)
        self.assertAlmostEqual(snap.threads[1], 0.0)
        self.assertEqual(len(snap.threads), 16)

    def test_cpu_model_clock_and_temperature(self):
        s = sysm.SystemSampler(self.src)
        snap = s.sample(0.0, full=True)
        self.assertEqual(s.model, "AMD Ryzen 7 7800X3D 8-Core Processor")
        self.assertAlmostEqual(snap.cpu_mhz, 4475.0)
        self.assertAlmostEqual(s.cpu_max_mhz, 5050.0)
        self.assertAlmostEqual(snap.cpu_temp, 48.25)     # k10temp Tctl, not Tccd1

    def test_memory_and_zram(self):
        m = sysm.memory(self.src, ['zram0'])
        self.assertEqual(m.total, 32768000 * 1024)
        self.assertEqual(m.available, 20000000 * 1024)
        self.assertEqual(m.used, (32768000 - 20000000) * 1024)
        self.assertEqual(m.cached, (6000000 + 100000 + 300000) * 1024)
        self.assertEqual(m.swap_used, (8388604 - 7340028) * 1024)
        self.assertEqual(m.zram_data, 1073741824)
        self.assertEqual(m.zram_compressed, 285212672)

    def test_amd_gpus(self):
        s = sysm.SystemSampler(self.src)
        s.find_sensors()
        snap = s.sample(0.0, full=True)
        self.assertEqual([g.card for g in snap.gpus], ['card1', 'card0'])   # dedicated first
        g = snap.gpus[0]
        self.assertEqual(g.name, "AMD Radeon RX 6800 XT")
        self.assertEqual(g.busy, 37.0)
        self.assertEqual(g.vram_used, 4294967296)
        self.assertEqual(g.vram_total, 17163091968)
        self.assertEqual(g.gtt_total, 16777216000)
        self.assertAlmostEqual(g.clock_mhz, 2250.0)
        self.assertAlmostEqual(g.temp, 52.0)
        self.assertAlmostEqual(g.temp_hot, 61.0)
        self.assertAlmostEqual(g.power_w, 187.0)
        self.assertEqual(g.fan_rpm, 1450)
        igpu = snap.gpus[1]
        self.assertEqual(igpu.name, "AMD Raphael")
        self.assertAlmostEqual(igpu.power_w, 5.0)          # power1_input on newer kernels
        self.assertIsNone(igpu.fan_rpm)
        self.assertIsNone(igpu.temp_hot)

    def test_pci_lookup(self):
        with open(os.path.join(self.root, 'usr/share/hwdata/pci.ids'), 'rb') as f:
            data = f.read()
        self.assertEqual(sysm.pci_lookup(data, 0x1002, 0x73bf),
                         "AMD Radeon RX 6800/6800 XT / 6900 XT")
        self.assertEqual(sysm.pci_lookup(data, 0x1002, 0x73bf, 0x1043, 0x04f2),
                         "AMD ROG Strix RX 6800 XT")
        self.assertEqual(sysm.pci_lookup(data, 0x10de, 0x2684), "NVIDIA GeForce RTX 4090")
        self.assertIsNone(sysm.pci_lookup(data, 0x1002, 0xffff))

    def test_nvidia_says_what_it_cannot_read(self):
        folder = os.path.join(self.root, 'sys/class/drm/card2/device')
        os.makedirs(folder)
        for k, v in (('vendor', '0x10de'), ('device', '0x2684')):
            with open(os.path.join(folder, k), 'w') as f:
                f.write(v + '\n')
        gpus = sysm.find_gpus(self.src)
        nvidia = [g for g in gpus if g.vendor == 0x10de][0]
        self.assertIn("nvidia-smi", nvidia.note)
        sysm.read_gpu(nvidia, True)
        self.assertIsNone(nvidia.busy)

    def test_disks(self):
        s = sysm.SystemSampler(self.src)
        self.assertEqual([d.name for d in s.disks], ['nvme0n1', 'sda'])
        self.assertEqual(s.zram, ['zram0'])
        nvme, hdd = s.disks
        self.assertEqual((nvme.kind, hdd.kind), ("NVMe SSD", "HDD"))
        self.assertEqual(nvme.model, "Samsung SSD 990 PRO 2TB")
        self.assertEqual(nvme.size, 3907029168 * 512)
        s.sample(0.0, full=True)

        def fn(text):
            out = []
            for line in text.splitlines():
                parts = line.split()
                if parts[2] == 'nvme0n1':
                    parts[5] = str(int(parts[5]) + 2048)       # 1 MiB read
                    parts[9] = str(int(parts[9]) + 4096)       # 2 MiB written
                    parts[12] = str(int(parts[12]) + 500)      # busy half the second
                out.append(' '.join(parts))
            return '\n'.join(out) + '\n'
        rewrite(self.root, 'proc/diskstats', fn)
        s.sample(1.0, full=True)
        self.assertAlmostEqual(nvme.read_bps, 1024 * 1024)
        self.assertAlmostEqual(nvme.write_bps, 2 * 1024 * 1024)
        self.assertAlmostEqual(nvme.active, 50.0)
        self.assertAlmostEqual(nvme.temp, 41.85)
        self.assertIsNone(hdd.temp)
        # /boot, and the btrfs volume (mounted twice, behind LUKS on nvme0n1p3) once
        self.assertEqual([u[0] for u in nvme.usage], ['/boot', '/sysroot'])
        self.assertEqual([u[0] for u in hdd.usage], ['/var/mnt/games'])

    def test_network(self):
        s = sysm.SystemSampler(self.src)
        self.assertEqual([(n.name, n.kind) for n in s.nics],
                         [('enp14s0', 'Ethernet'), ('wlp15s0', 'Wi-Fi')])
        s.sample(0.0, full=True)

        def fn(text):
            out = []
            for line in text.splitlines():
                if line.startswith('enp14s0:'):
                    name, rest = line.split(':', 1)
                    parts = rest.split()
                    parts[0] = str(int(parts[0]) + 1_000_000)
                    parts[8] = str(int(parts[8]) + 250_000)
                    line = name + ': ' + ' '.join(parts)
                out.append(line)
            return '\n'.join(out) + '\n'
        rewrite(self.root, 'proc/net/dev', fn)
        snap = s.sample(2.0, full=True)
        enp = snap.nics[0]
        self.assertAlmostEqual(enp.rx_bps, 500_000)
        self.assertAlmostEqual(enp.tx_bps, 125_000)
        self.assertTrue(enp.up)
        self.assertEqual(enp.speed_mbps, 2500)
        self.assertFalse(snap.nics[1].up)


# ─── Processes and apps ───────────────────────────────────────

class ProcessTests(FixtureCase):
    def test_parse_stat_with_odd_names(self):
        line = b'4242 (Web (Content) 1) S 1 4242 4242 0 -1 4194560 1 0 0 0 70 30 0 0 20 5 ' \
               b'12 0 98765 1000 300' + b' 0' * 30
        comm, state, ppid, _flags, ticks, nice, threads, start = parse_stat(line)
        self.assertEqual(comm, 'Web (Content) 1')
        self.assertEqual((state, ppid, ticks, nice, threads, start), ('S', 1, 100, 5, 12, 98765))

    def test_desktop_id_from_unit(self):
        cases = {
            'app-org.kde.dolphin@0a1b2c3d.scope': 'org.kde.dolphin',
            'app-flatpak-com.valvesoftware.Steam-3000.scope': 'com.valvesoftware.Steam',
            'app-org.kde.kdeconnect.daemon@autostart.service': 'org.kde.kdeconnect.daemon',
            'app-gnome-org.gnome.Calculator-6100.scope': 'gnome-org.gnome.Calculator',
            'app-org.kde.kate-12345.scope': 'org.kde.kate',
            'app-steam\\x2dnative@1.scope': 'steam-native',
            'pipewire.service': None,
        }
        for unit, want in cases.items():
            self.assertEqual(desktop_id_from_unit(unit), want, unit)

    def test_classify(self):
        desktop = DesktopIndex(self.src)
        u = '/user.slice/user-1000.slice/user@1000.service'
        cases = [
            (u + '/app.slice/app-org.kde.dolphin@0a1b.scope', APP, 'Dolphin'),
            (u + '/app.slice/app-flatpak-com.valvesoftware.Steam-3000.scope', APP, 'Steam'),
            (u + '/app.slice/app-org.kde.konsole@9a8b.scope/tab(5000).scope', APP, 'Konsole'),
            (u + '/app.slice/app-gnome-org.gnome.Calculator-6100.scope', APP, 'Calculator'),
            (u + '/app.slice/app-org.kde.kdeconnect.daemon@autostart.service', BACKGROUND,
             'KDE Connect'),
            (u + '/background.slice/kde-baloo.service', BACKGROUND, 'kde-baloo'),
            (u + '/app.slice/app-unknown.thing@1.scope', BACKGROUND, 'unknown.thing'),
            (u + '/session.slice/plasma-plasmashell.service', SYSTEM, 'plasma-plasmashell'),
            (u + '/app.slice/xdg-desktop-portal-kde.service', SYSTEM, 'xdg-desktop-portal-kde'),
            (u + '/init.scope', SYSTEM, t('apps.session')),
            ('/user.slice/user-1000.slice/session-2.scope', SYSTEM, t('apps.login_session')),
            ('/system.slice/NetworkManager.service', SYSTEM, 'NetworkManager'),
            ('/init.scope', SYSTEM, 'systemd'),
        ]
        for cg, section, name in cases:
            key, sec, label, _did, _unit = classify(cg, desktop)
            self.assertEqual((sec, label), (section, name), cg)
            self.assertTrue(key)
        # Konsole's tab scope is grouped with Konsole itself
        self.assertEqual(classify(cases[2][0], desktop)[0],
                         u + '/app.slice/app-org.kde.konsole@9a8b.scope')
        self.assertEqual(classify('/', desktop)[0], '')        # not a systemd session

    def two_samples(self, change=None):
        p = ProcSampler(self.src, threads=16)
        p.sample(0.0)
        if change:
            change()
        p.sample(1.0)
        return p

    def groups_by_name(self, p):
        return {g.name: g for g in p.groups.values()}

    def test_grouping(self):
        p = self.two_samples()
        sections = {}
        for g in p.groups.values():
            sections.setdefault(g.section, set()).add(g.name)
        self.assertEqual(sections[APP], {'Calculator', 'Cyberpunk 2077', 'Dolphin', 'Firefox',
                                         'Konsole', 'Steam'})
        self.assertEqual(sections[BACKGROUND], {'KDE Connect', 'kde-baloo', 'python3'})
        self.assertEqual(sections[SYSTEM], {
            'systemd', 'NetworkManager', 'sddm', t('apps.login_session'), t('apps.session'),
            'plasma-kwin_wayland', 'plasma-plasmashell', 'pipewire',
            'xdg-desktop-portal-kde'})
        by = self.groups_by_name(p)
        self.assertEqual(sorted(by['Firefox'].pids), [2100, 2101, 2102])
        self.assertEqual(sorted(by['Konsole'].pids), [4900, 5000])
        self.assertEqual(sorted(by['Steam'].pids), [3000, 3010])
        self.assertEqual(sorted(by['Cyberpunk 2077'].pids), [3050, 3060])   # its own row
        self.assertEqual(by['Firefox'].icon, 'org.mozilla.firefox')
        self.assertEqual(p.totals(), (24, 9))
        self.assertNotIn(2, [pid for g in p.groups.values() for pid in g.pids])

    def test_cpu_memory_disk_per_app(self):
        def change():
            bump_stat(self.root, 2100, 160)          # 1.6 s of CPU in 1 s, 16 threads: 10%
            bump_stat(self.root, 2101, 80)           # 5%
            rewrite(self.root, 'proc/2100/io',
                    lambda t: t.replace(f'read_bytes: {2100 * 4096}',
                                        f'read_bytes: {2100 * 4096 + 3 * 1024 * 1024}'))
        p = self.two_samples(change)
        fx = self.groups_by_name(p)['Firefox']
        self.assertAlmostEqual(fx.cpu, 15.0)
        self.assertEqual(fx.mem, ((150000 - 50000) + (80000 - 30000) + (10000 - 8000)) * PAGE)
        self.assertAlmostEqual(fx.disk, 3 * 1024 * 1024)
        self.assertAlmostEqual(p.procs[2100].cpu, 10.0)

    def test_gpu_per_app(self):
        def change():
            bump_stat(self.root, 3060, 50)                  # only running processes are
            bump_stat(self.root, 2100, 10)                  # looked at for the GPU
            bump_gpu(self.root, 3060, 40, 500_000_000)     # half of the second
            bump_gpu(self.root, 2100, 30, 100_000_000)     # same client on fd 30 and 31
            bump_gpu(self.root, 2100, 31, 100_000_000)
        p = self.two_samples(change)
        p.sample(1.0)                         # fds are found on the second sample
        change()
        p.sample(2.0)
        by = self.groups_by_name(p)
        self.assertAlmostEqual(by['Cyberpunk 2077'].gpu, 50.0)
        self.assertAlmostEqual(by['Firefox'].gpu, 10.0)      # counted once, not twice
        self.assertIsNone(by['Dolphin'].gpu)                  # idle: never scanned
        self.assertEqual(p.procs[2000].gpu_scans, 0)
        self.assertTrue(p.gpu_readable)

    def test_idle_processes_are_read_less(self):
        def change():
            bump_stat(self.root, 2100, 10)
            for pid, value in ((2100, 160000), (2000, 60000)):
                rewrite(self.root, f'proc/{pid}/statm',
                        lambda t, v=value: ' '.join([t.split()[0], str(v)] + t.split()[2:]))
        p = ProcSampler(self.src, threads=16)
        p.ticks = 4                         # so that neither PID is due for its 10 s look
        p.sample(0.0)
        change()
        p.sample(1.0)
        self.assertEqual(p.procs[2100].mem, (160000 - 50000) * PAGE)   # ran: read again
        self.assertEqual(p.procs[2000].mem, (40000 - 25000) * PAGE)    # slept: kept

    def test_reused_pid_is_a_new_process(self):
        def change():
            bump_stat(self.root, 2000, 5000, start=999999)    # a different process now
        p = self.two_samples(change)
        self.assertEqual(p.procs[2000].cpu, 0.0)

    def test_children_and_protection(self):
        p = self.two_samples()
        self.assertEqual(p.children(2100)[-1], 2100)
        self.assertEqual(sorted(p.children(2100)), [2100, 2101, 2102])
        self.assertTrue(p.protected_pid(1300))         # kwin
        self.assertTrue(p.protected_pid(1))
        self.assertFalse(p.protected_pid(2100))

    def test_steam_library(self):
        lib = SteamLibrary(self.src)
        self.assertEqual(lib.name('1091500'), 'Cyberpunk 2077')
        self.assertEqual(lib.name('570'), 'Dota 2')          # second library folder
        self.assertEqual(lib.name('42'), 'Steam game 42')

    def test_desktop_entries_and_icons(self):
        d = DesktopIndex(self.src)
        self.assertEqual(d.lookup('com.valvesoftware.Steam').name, 'Steam')   # Flatpak export
        self.assertTrue(d.lookup('org.kde.kdeconnect.daemon').no_display)
        self.assertIsNone(d.lookup('nope.nothing'))
        self.assertTrue(find_icon(self.src, 'org.mozilla.firefox').endswith('.png'))
        self.assertTrue(find_icon(self.src, 'com.valvesoftware.Steam'))
        self.assertIsNone(find_icon(self.src, 'system-file-manager'))
        self.assertIsNone(find_icon(self.src, '../../etc/passwd'))
        keys = parse_desktop('[Desktop Entry]\nName=A\nName[fr]=B\n[Desktop Action x]\nName=C\n')
        self.assertEqual(keys, {'Name': 'A', 'Name[fr]': 'B'})


# ─── End task ─────────────────────────────────────────────────

class EndTaskTests(unittest.TestCase):
    def test_refuses_to_signal_a_fake_tree(self):
        # the PIDs in test data are real PIDs on this PC; they must never get a signal
        e = Ender(Source(FIXTURE), [1, 2100, os.getpid()])
        self.assertEqual(e.start(), FAILED)

    def run_ender(self, child, grace):
        e = Ender(Source('/'), [child.pid], grace=grace)
        result = e.start()
        deadline = time.time() + 15
        while result == RUNNING and time.time() < deadline:
            time.sleep(0.05)
            result = e.poll()
        child.wait(timeout=5)
        return result

    @unittest.skipUnless(LINUX, "needs Linux")
    def test_ends_with_sigterm(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
        self.assertEqual(self.run_ender(child, 5.0), ENDED)
        self.assertEqual(child.returncode, -15)

    @unittest.skipUnless(LINUX, "needs Linux")
    def test_forces_with_sigkill_after_the_grace_period(self):
        child = subprocess.Popen(
            [sys.executable, '-c', 'import signal, time\n'
             'signal.signal(signal.SIGTERM, signal.SIG_IGN)\n'
             'print("ready", flush=True)\ntime.sleep(60)'], stdout=subprocess.PIPE)
        self.assertEqual(child.stdout.readline().strip(), b'ready')
        started = time.time()
        self.assertEqual(self.run_ender(child, 0.6), FORCED)
        self.assertEqual(child.returncode, -9)
        self.assertGreaterEqual(time.time() - started, 0.5)
        child.stdout.close()

    @unittest.skipUnless(LINUX, "needs Linux")
    def test_never_signals_itself(self):
        e = Ender(Source('/'), [os.getpid()])
        self.assertEqual(e.pids, [])
        self.assertEqual(e.start(), ENDED)


# ─── Startup ──────────────────────────────────────────────────

class StartupTests(FixtureCase):
    def items(self):
        return {i.name: i for i in startup.all_items(self.src, [])}

    def test_lists_autostart_and_services(self):
        items = self.items()
        self.assertEqual(set(items), {'KDE Connect', 'Discover Update Notifier', 'Already Off',
                                      'Discord', 'syncthing', 'example-tray'})
        self.assertNotIn('GNOME Thing', items)                 # OnlyShowIn=GNOME
        self.assertFalse(items['Already Off'].enabled)
        self.assertEqual(items['Discord'].origin, 'user')
        self.assertEqual(items['KDE Connect'].origin, 'system')
        self.assertEqual(items['syncthing'].description,
                         'Syncthing - Open Source Continuous File Synchronization')
        self.assertTrue(items['syncthing'].can_toggle)
        self.assertFalse(items['example-tray'].can_toggle)     # set by the system for everyone

    def test_turning_off_a_system_entry_writes_an_override(self):
        etc = os.path.join(self.root, 'etc/xdg/autostart/org.kde.kdeconnect.daemon.desktop')
        with open(etc, 'rb') as f:
            before = f.read()
        item = self.items()['KDE Connect']
        startup.set_autostart(self.src, item, False)
        user = os.path.join(self.root, 'home/.config/autostart/org.kde.kdeconnect.daemon.desktop')
        with open(user, encoding="utf-8") as f:
            keys = parse_desktop(f.read())
        self.assertEqual(keys['Hidden'], 'true')
        self.assertEqual(keys['Name'], 'KDE Connect')
        self.assertEqual(keys[startup.MARK], 'true')
        with open(etc, 'rb') as f:
            self.assertEqual(f.read(), before)                 # /etc untouched
        self.assertFalse(self.items()['KDE Connect'].enabled)
        startup.set_autostart(self.src, self.items()['KDE Connect'], True)
        self.assertFalse(os.path.exists(user))                 # our override, removed
        self.assertTrue(self.items()['KDE Connect'].enabled)

    def test_turning_a_system_entry_on(self):
        startup.set_autostart(self.src, self.items()['Already Off'], True)
        self.assertTrue(self.items()['Already Off'].enabled)

    def test_switching_your_own_entry(self):
        startup.set_autostart(self.src, self.items()['Discord'], False)
        self.assertFalse(self.items()['Discord'].enabled)
        startup.set_autostart(self.src, self.items()['Discord'], True)
        item = self.items()['Discord']
        self.assertTrue(item.enabled)
        with open(item.path, encoding="utf-8") as f:
            self.assertIn("--start-minimized", f.read())

    def test_set_key(self):
        text = '[Desktop Entry]\nName=A\nHidden=false\n\n[Desktop Action x]\nHidden=keep\n'
        out = startup.set_key(text, 'Hidden', 'true')
        self.assertIn('[Desktop Entry]\nName=A\nHidden=true\n', out)
        self.assertIn('[Desktop Action x]\nHidden=keep', out)
        out = startup.set_key('[Desktop Entry]\nName=A\n[Other]\nX=1\n', 'Hidden', 'true')
        self.assertTrue(out.startswith('[Desktop Entry]\nName=A\nHidden=true\n[Other]'))
        self.assertNotIn('Hidden', startup.set_key(out, 'Hidden', None))

    def test_services_use_systemctl(self):
        calls = []

        def runner(cmd):
            calls.append(cmd)
            return 0, ''
        item = self.items()['syncthing']
        ok, _ = startup.set_service(item, False, runner)
        self.assertTrue(ok)
        self.assertEqual(calls, [['systemctl', '--user', 'disable', 'syncthing.service']])
        remembered = os.path.join(self.dir, 'startup.json')
        startup.remember_units(remembered, ['syncthing.service'])
        os.remove(os.path.join(self.root,
                               'home/.config/systemd/user/default.target.wants/syncthing.service'))
        items = {i.name: i for i in startup.all_items(self.src,
                                                      startup.remembered_units(remembered))}
        self.assertFalse(items['syncthing'].enabled)            # still listed, to turn back on


# ─── Command line, metadata ───────────────────────────────────

class MiscTests(FixtureCase):
    def test_self_test_on_fixture(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = self_test(self.src)
        text = out.getvalue()
        self.assertEqual(code, 0, text)
        self.assertIn('16 threads', text)
        self.assertIn('AMD Radeon RX 6800 XT', text)
        self.assertIn('self-test passed', text)

    def test_shortcut_conflict_check(self):
        self.assertIsNone(shortcut_owner(self.src))
        with open(os.path.join(self.root, 'home/.config/kglobalshortcutsrc'), 'a') as f:
            f.write('[org.example.other]\nOpen Thing=Shift+Ctrl+Escape\tMeta+T,none,Open\n')
        self.assertIn('org.example.other', shortcut_owner(self.src))

    def test_shortcut_registration_check(self):
        from sparkmonitor.cli import shortcut_claimants, shortcut_entry
        self.assertIsNone(shortcut_entry(self.src))
        self.assertEqual(shortcut_claimants(self.src), [])     # Konsole's Ctrl+Alt+T isn't it
        folder = os.path.join(self.root, 'usr/share/kglobalaccel')
        os.makedirs(folder)
        shutil.copy(os.path.join(APP_DIR, f'{APP_ID}.desktop'), folder)
        self.assertTrue(shortcut_entry(self.src).endswith(f'kglobalaccel{os.sep}{APP_ID}.desktop'))
        with open(os.path.join(self.root, 'usr/share/applications/other.desktop'), 'w') as f:
            f.write('[Desktop Entry]\nName=Other\nX-KDE-Shortcuts=Meta+X,Shift+Ctrl+Escape\n')
        self.assertEqual([os.path.basename(p) for p in shortcut_claimants(self.src)],
                         ['other.desktop'])
        out = io.StringIO()
        with redirect_stdout(out):
            self_test(self.src)
        self.assertIn('registered for Plasma by', out.getvalue())
        self.assertIn('also claimed by', out.getvalue())

    def test_metadata(self):
        with open(os.path.join(APP_DIR, 'spark-app.json'), encoding='utf-8') as f:
            meta = json.load(f)
        self.assertEqual(meta['id'], APP_ID)
        self.assertEqual(meta['version'], VERSION)
        self.assertFalse(meta['needs']['root'])
        source = sum(os.path.getsize(os.path.join(dp, n))
                     for dp, _dirs, names in os.walk(os.path.join(APP_DIR, 'sparkmonitor'))
                     for n in names if n.endswith('.py'))
        self.assertTrue(source / 1024 < meta['installed_size_kb'] < 4 * source / 1024)
        with open(os.path.join(APP_DIR, f'{APP_ID}.desktop'), encoding='utf-8') as f:
            keys = parse_desktop(f.read())
        self.assertEqual(keys['X-KDE-Shortcuts'], SHORTCUT)
        self.assertEqual(keys['Exec'], 'spark-monitor')
        self.assertEqual(keys['Icon'], APP_ID)

    def test_formatting(self):
        cases = [(core.size(512), "512 B", "512 o"), (core.size(1536), "1.5 KB", "1,5 Ko"),
                 (core.size(4294967296), "4.0 GB", "4,0 Go"),
                 (core.rate(3 * 1024 * 1024), "3.0 MB/s", "3,0 Mo/s"),
                 (core.rate(0), "0 MB/s", "0 Mo/s"), (core.bits(125_000), "1.0 Mbps", "1,0 Mbit/s"),
                 (core.mhz(4475), "4.47 GHz", "4,47 GHz"), (core.pct(12.34), "12.3%", "12,3 %"),
                 (core.pct(None), "—", "—")]
        for got, en, fr in cases:
            self.assertEqual(got, fr if t('tab.apps') != 'Apps' else en)

# ─── The window ───────────────────────────────────────────────

def said(key: str, shown: str) -> bool:
    """Does the status line show the sentence `key`, whatever the {name} in it? The status
    line shows it in capitals without the final full stop (App.end_finished)."""
    sample = t(key, name='@@').upper().rstrip('.')
    return all(part.strip() in shown for part in sample.split('@@') if part.strip())


def have_display() -> bool:
    if os.name == 'nt':
        return True
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


@unittest.skipUnless(have_display(), "needs a display")
class UITests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spark-monitor-ui-')
        self.root = os.path.join(self.dir, 'root')
        shutil.copytree(FIXTURE, self.root)
        self.apps = []

    def tearDown(self):
        for app in self.apps:
            try:
                app.close()
            except Exception:     # noqa: BLE001
                pass
        shutil.rmtree(self.dir, ignore_errors=True)

    def open(self, src, tab='apps'):
        from sparkmonitor.app import App
        app = App(src, tab=tab)
        self.apps.append(app)
        self.pump(app, 0.8)
        return app

    def pump(self, app, seconds=0.4):
        end = time.time() + seconds
        while time.time() < end:
            app.root.update()
            time.sleep(0.02)

    def test_every_tab_renders(self):
        app = self.open(Source(self.root))
        apps = app.views['apps']
        names = {apps.tree.item(i, 'text').split(' (')[0]
                 for s in apps.sections.values() for i in apps.tree.get_children(s)}
        self.assertIn('Firefox', names)
        self.assertIn('Cyberpunk 2077', names)
        for tab in ('performance', 'startup', 'details', 'apps'):
            app.show(tab)
            self.pump(app, 0.3)
            self.assertTrue(app.views[tab].winfo_ismapped(), tab)
        perf = app.views['performance']
        self.assertEqual(list(perf.items), ['cpu', 'mem', 'gpu0', 'gpu1', 'disk0', 'disk1',
                                            'net0', 'net1'])
        for key in perf.items:
            perf.select(key)
            self.pump(app, 0.1)
        self.assertEqual(len(perf.panes['cpu'].thread_graphs), 16)
        self.assertEqual(len(app.views['startup'].items), 6)
        self.assertEqual(len(app.views['details'].tree.get_children('')), 24)
        self.assertIn(t('status.test_data'), app.status.cget('text'))

    def test_sorting(self):
        app = self.open(Source(self.root))
        apps = app.views['apps']

        def order():
            return [apps.tree.item(i, 'text').split(' (')[0]
                    for i in apps.tree.get_children(apps.sections['app'])]
        self.assertEqual(order(), sorted(order(), key=str.lower))
        apps.sort_by('memory')
        self.assertEqual(order()[0], 'Cyberpunk 2077')
        self.assertIn('▼', apps.tree.heading('memory', 'text'))
        apps.sort_by('memory')
        self.assertEqual(order()[-1], 'Cyberpunk 2077')
        apps.sort_by('name')
        self.assertEqual(order()[0], 'Calculator')

    def test_open_group_lists_its_processes(self):
        app = self.open(Source(self.root))
        apps = app.views['apps']
        iid = apps.row_for([g.key for g in app.procs.groups.values() if g.name == 'Firefox'][0])
        apps.tree.item(iid, open=True)
        apps._opened()
        kids = apps.tree.get_children(iid)
        self.assertEqual(len(kids), 3)

    def test_system_rows_cannot_be_ended_here(self):
        app = self.open(Source(self.root))
        apps = app.views['apps']
        kwin = [g.key for g in app.procs.groups.values() if g.name == 'plasma-kwin_wayland'][0]
        apps.tree.item(apps.sections['system'], open=True)
        apps.tree.selection_set(apps.row_for(kwin))
        self.pump(app, 0.2)
        self.assertFalse(apps.end_button.enabled)
        self.assertEqual(apps.note.cget('text'), t('apps.system_note'))

    def test_end_task_on_test_data_sends_nothing(self):
        app = self.open(Source(self.root))
        apps = app.views['apps']
        fx = [g.key for g in app.procs.groups.values() if g.name == 'Firefox'][0]
        apps.tree.selection_set(apps.row_for(fx))
        self.pump(app, 0.2)
        apps.end_task()
        self.assertIsNone(app.ending)
        self.assertIn(t('end.test_data').upper(), app.status.cget('text').upper())

    def test_graph_moves_items_instead_of_making_new_ones(self):
        from sparkmonitor.ui import Graph
        app = self.open(Source(self.root), tab='performance')
        g = Graph(app.body, '#3de8c8', height=80, width=200, colour2='#ff4d8d',
                  label=lambda v: f"{v:.0f}%")
        g.pack()
        self.pump(app, 0.2)
        count = len(g.find_all())
        for i in range(120):
            g.set([float(j % 100) for j in range(i)], [50.0] * i)
        self.pump(app, 0.1)
        self.assertEqual(len(g.find_all()), count)

    def test_startup_switch(self):
        app = self.open(Source(self.root), tab='startup')
        view = app.views['startup']
        iid = 'autostart:org.kde.kdeconnect.daemon.desktop'
        view.tree.selection_set(iid)
        self.pump(app, 0.2)
        view.toggle()
        self.pump(app, 0.2)
        self.assertEqual(view.tree.item(iid, 'values')[0], t('startup.off'))
        self.assertTrue(os.path.exists(os.path.join(
            self.root, 'home/.config/autostart/org.kde.kdeconnect.daemon.desktop')))

    def test_sampling_stops_while_minimized(self):
        app = self.open(Source(self.root))
        app.root.iconify()
        self.pump(app, 0.6)
        if app.root.state() != 'iconic':
            self.skipTest("no window manager to minimize with")
        self.assertFalse(app.visible)
        samples = app.cost['samples']
        self.pump(app, 1.3)
        self.assertEqual(app.cost['samples'], samples)
        app.root.deiconify()
        self.pump(app, 0.6)
        self.assertTrue(app.visible)

    def test_unfocused_samples_slower_and_graphs_keep_one_point_a_second(self):
        from collections import deque
        from sparkmonitor.app import _Fill
        dq = deque([10.0], maxlen=60)
        _Fill(dq, 3).append(40.0)
        self.assertEqual(list(dq), [10.0, 20.0, 30.0, 40.0])
        gap = deque([5.0], maxlen=60)
        _Fill(gap, 3).append(None)
        self.assertEqual(list(gap), [5.0, None, None, None])
        app = self.open(Source(self.root))
        app.focused = False
        app.sample()
        before = len(app.hist['cpu'])
        app._last_sample -= 3.0
        app.sample()
        self.assertEqual(len(app.hist['cpu']), before + 3)
        self.pump(app, 1.3)               # the tick already waiting (1 s) runs and re-arms at 3 s
        app.focused = False               # (a real window manager may have focused it meanwhile)
        self.pump(app, 1.3)
        samples = app.cost['samples']
        self.pump(app, 2.0)               # unfocused: at most one sample in 2 s
        self.assertLessEqual(app.cost['samples'] - samples, 1)

    # — real processes, real /proc —
    def start_child(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
        threading.Thread(target=child.wait, daemon=True).start()   # reap it once it ends
        self.addCleanup(lambda: child.poll() is None and child.kill())
        return child

    def wait_for(self, app, test, seconds=10.0):
        end = time.time() + seconds
        while time.time() < end:
            app.sample()
            app.refresh()
            if test():
                return True
            self.pump(app, 0.2)
        return False

    @unittest.skipUnless(LINUX, "needs Linux")
    def test_details_end_process_removes_its_row(self):
        child = self.start_child()
        app = self.open(Source('/'), tab='details')
        view = app.views['details']
        self.assertTrue(self.wait_for(app, lambda: view.tree.exists(str(child.pid))))
        self.assertTrue(view.select_pid(child.pid))
        view.end(tree=False)
        self.assertTrue(self.wait_for(app, lambda: not view.tree.exists(str(child.pid))
                                      and app.ending is None))
        self.assertTrue(said('end.ended', app.status.cget('text')), app.status.cget('text'))

    @unittest.skipUnless(LINUX, "needs Linux")
    def test_apps_end_task_removes_its_row(self):
        child = self.start_child()
        app = self.open(Source('/'), tab='apps')
        apps = app.views['apps']
        self.assertTrue(self.wait_for(app, lambda: child.pid in app.procs.procs))
        key = app.procs.procs[child.pid].group
        group = app.procs.groups[key]
        if group.pids != [child.pid] or not group.endable:
            # on a desktop the child shares the test runner's app scope; ending that row
            # would end the terminal running these tests
            self.skipTest(f"the test process isn't alone in its row ({group.name})")
        row = apps.row_for(key)
        apps.tree.item(apps.sections['background'], open=True)
        apps.tree.selection_set(row)
        self.pump(app, 0.2)
        self.assertTrue(apps.end_button.enabled)
        apps.end_task()
        self.assertTrue(self.wait_for(app, lambda: not apps.tree.exists(row)
                                      and app.ending is None))
        self.assertTrue(said('end.ended', app.status.cget('text')), app.status.cget('text'))
        self.assertIsNotNone(child.poll())


if __name__ == '__main__':
    unittest.main()
