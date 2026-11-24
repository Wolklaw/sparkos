"""Spark Connect tests. Plain unittest:

    python -m unittest discover -s files/spark-connect/tests -v

The probe's JSON and ssh's failures come from fixtures/ (made-up machines: a main server and a
standby laptop). Nothing here connects to a real machine. The probe itself runs on this PC
(Linux only), and the website check against a local HTTP server. UI tests need a display (on
CI: xvfb-run). The SSH end-to-end test is e2e_ssh.py, run by CI against a throwaway container.
"""

import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(HERE)
FIX = os.path.join(HERE, 'fixtures')
EXAMPLE = os.path.join(APP_DIR, 'machines.example.toml')
sys.path.insert(0, APP_DIR)
for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'APPDATA', 'LOCALAPPDATA'):
    os.environ[var] = tempfile.mkdtemp(prefix=f'spark-connect-{var.lower()}-')
os.environ['SPARK_CONNECT_REDUCED_MOTION'] = '1'

from sparkconnect import VERSION, actions, alerts, config, probe, report, sites  # noqa: E402
from sparkconnect.cli import self_test  # noqa: E402
from sparkconnect.probe import (AUTH, BAD, DOWN, HOSTKEY_CHANGED, HOSTKEY_UNKNOWN, OK,  # noqa
                                TIMEOUT, WARN, Result, classify_ssh_failure, level, parse_probe,
                                problems)
from sparkconnect.text import t, verdict_text  # noqa: E402
from sparkconnect.transport import (DONE, NEEDS_PASSWORD, ActionResult, SshTransport,  # noqa
                                    probe_script, result_from_ssh)

LINUX = sys.platform.startswith('linux')


def fixture(name: str) -> str:
    with open(os.path.join(FIX, name), encoding='utf-8') as f:
        return f.read()


def example():
    return config.load(EXAMPLE)


MAIN = 0
STANDBY = 1


def machine(i=MAIN):
    return example().machines[i]


def result_for(name, m=None, at=None):
    """A Result for a fixture: .json is probe output, .stderr an ssh failure."""
    m = m or machine(STANDBY if name.startswith('standby') else MAIN)
    if name.endswith('.json'):
        r = result_from_ssh(m.name, 0, fixture(name), '')
    else:
        r = result_from_ssh(m.name, 255, '', fixture(name))
    if at is not None:
        r.at = at
    return r


def verdict_of(name):
    m = machine(STANDBY if name.startswith('standby') else MAIN)
    found = problems(m, result_for(name, m))
    return found, (verdict_text(found[0]) if found else t('verdict.ok'))


# ─── The probe's JSON ─────────────────────────────────────────

class ParseProbe(unittest.TestCase):
    def test_all_fine(self):
        d = parse_probe(fixture('all-fine.json'))
        self.assertEqual(d['hostname'], 'main-server')
        self.assertEqual(d['load'], [0.42, 0.38, 0.35])
        self.assertEqual([u['state'] for u in d['units']], ['running'] * 3)
        self.assertEqual(d['tunnel']['connections'], 4)
        self.assertAlmostEqual(d['disks'][0]['pct'], 100 * 80 / 237, places=3)
        found, text = verdict_of('all-fine.json')
        self.assertEqual(found, [])
        self.assertEqual(text, t('verdict.ok'))

    def test_failed_unit(self):
        d = parse_probe(fixture('failed-unit.json'))
        portal = d['units'][1]
        self.assertEqual((portal['state'], portal['restarts']), ('failed', 3))
        self.assertEqual(len(portal['log']), 3)
        found, text = verdict_of('failed-unit.json')
        self.assertEqual(level(found), BAD)
        self.assertEqual(text, t('verdict.unit_failed', unit='example-portal'))
        # old-backup is known-failed in the example config; the watched one isn't counted twice
        self.assertEqual(len(found), 1)

    def test_other_failed_unit_counts(self):
        m = machine()
        m.known_failed = []
        found = problems(m, result_for('failed-unit.json', m))
        self.assertEqual([p.args.get('unit') for p in found], ['example-portal', 'old-backup'])

    def test_full_disk(self):
        found, text = verdict_of('disk-full.json')
        self.assertEqual(found[0].level, WARN)      # 90-95% full; 95% and up is BAD
        self.assertIn('94', text)
        self.assertIn('(/)', text)

    def test_cloudflared_reconnecting(self):
        found, text = verdict_of('cloudflared-reconnecting.json')
        self.assertEqual(level(found), BAD)
        self.assertEqual(text, t('verdict.tunnel_reconnecting', unit='cloudflared'))

    def test_cloudflared_restarting(self):
        raw = json.loads(fixture('all-fine.json'))
        raw['units'][2].update(active='activating', sub='auto-restart')
        raw['tunnel']['active'] = 'activating'
        found = problems(machine(), result_from_ssh('Main server', 0, json.dumps(raw), ''))
        self.assertEqual(verdict_text(found[0]), t('verdict.unit_restarting', unit='cloudflared'))
        self.assertEqual(len(found), 1)

    def test_standby_standing_by_is_calm(self):
        found, text = verdict_of('standby-ok.json')
        self.assertEqual(found, [])       # its stopped tunnel is the normal state

    def test_standby_after_takeover(self):
        found, text = verdict_of('standby-takeover.json')
        self.assertEqual(level(found), BAD)
        self.assertEqual(text, t('verdict.taken_over'))
        self.assertTrue(probe.is_taken_over(result_for('standby-takeover.json').data))

    def test_timeout(self):
        r = result_for('ssh-timeout.stderr', at=1795000000)
        self.assertFalse(r.ok)
        self.assertEqual(r.problem, TIMEOUT)
        found = problems(machine(), r, down_since=1795000000)
        self.assertEqual(level(found), DOWN)
        self.assertEqual(verdict_text(found[0]),
                         t('verdict.unreachable', since=time.strftime(
                             '%H:%M', time.localtime(1795000000))))

    def test_changed_host_key(self):
        r = result_for('ssh-hostkey-changed.stderr')
        self.assertEqual(r.problem, HOSTKEY_CHANGED)
        self.assertEqual(r.fingerprint, 'SHA256:Zm9vYmFyYmF6cXV4ZXhhbXBsZWZpbmdlcnByaW50MDE.'
                         .rstrip('.'))
        found = problems(machine(), r)
        self.assertEqual(verdict_text(found[0]), t('verdict.hostkey_changed'))

    def test_unknown_host_key(self):
        r = result_for('ssh-hostkey-unknown.stderr')
        self.assertEqual(r.problem, HOSTKEY_UNKNOWN)
        self.assertIn('No ED25519 host key is known', r.message)

    def test_auth(self):
        self.assertEqual(result_for('ssh-auth.stderr').problem, AUTH)

    def test_other_failures(self):
        for text, want in (("ssh: connect to host x port 22: Connection refused", 'unreachable'),
                           ("ssh: Could not resolve hostname x: Name or service not known",
                            'unreachable'),
                           ("ssh: connect to host x port 22: No route to host", 'unreachable')):
            self.assertEqual(classify_ssh_failure(255, text)[0], want)
        self.assertEqual(classify_ssh_failure(None, '', timed_out=True)[0], TIMEOUT)

    def test_banner_before_json_and_garbage(self):
        r = result_from_ssh('m', 0, "Welcome!\n" + fixture('all-fine.json'), '')
        self.assertTrue(r.ok)
        r = result_from_ssh('m', 0, "sh: 1: syntax error", '')
        self.assertEqual((r.ok, r.problem), (False, probe.BAD_OUTPUT))
        with self.assertRaises(probe.ProbeError):
            parse_probe('{"probe": 99}')

    def test_missing_keys_are_tolerated(self):
        d = parse_probe('{"probe":1,"units":[{"name":"x","active":"active","sub":"running"}],'
                        '"disks":[{"mount":"/","size":0}]}')
        self.assertEqual(d['units'][0]['state'], 'running')
        self.assertEqual(d['disks'], [])
        self.assertEqual(d['load'], [None, None, None])

    def test_hot_and_low_memory(self):
        raw = json.loads(fixture('all-fine.json'))
        raw['temps'].append({'name': 'nvme Composite', 'c': 91.0})
        raw['memory']['available'] = 300000000
        found = problems(machine(), result_from_ssh('m', 0, json.dumps(raw), ''))
        self.assertEqual({p.key for p in found}, {'hot', 'memory_low'})
        self.assertEqual(level(found), WARN)

    def test_impossible_temperature_is_ignored(self):
        raw = json.loads(fixture('all-fine.json'))
        raw['temps'].append({'name': 'dell_smm', 'c': 126.0})
        r = result_from_ssh('m', 0, json.dumps(raw), '')
        self.assertNotIn(126.0, [x['c'] for x in r.data['temps']])
        self.assertEqual(problems(machine(), r), [])

    def test_tunnel_count_unknown_is_not_reconnecting(self):
        raw = json.loads(fixture('all-fine.json'))
        raw['tunnel']['connections'] = None
        found = problems(machine(), result_from_ssh('m', 0, json.dumps(raw), ''))
        self.assertNotIn('tunnel_reconnecting', {p.key for p in found})

    def test_reboot_needed(self):
        raw = json.loads(fixture('all-fine.json'))
        raw['packages'] = {'manager': 'apt', 'updates': 23, 'security': 0,
                           'reboot': {'since': 1794552446,
                                      'pkgs': ['libc6', 'linux-image-7.0.0-43-generic']}}
        r = result_from_ssh('m', 0, json.dumps(raw), '')
        self.assertEqual(r.data['packages']['updates'], 23)
        found = problems(machine(), r)
        self.assertEqual([p.key for p in found], ['reboot_kernel'])
        self.assertEqual(level(found), WARN)
        self.assertIn(time.strftime('%Y-%m-%d', time.localtime(1794552446)),
                      verdict_text(found[0]))
        # the same wait reads the same on the next refresh, so it doesn't flash as new
        r.at += 600
        self.assertEqual(problems(machine(), r), found)
        raw['packages']['reboot']['pkgs'] = ['libc6']
        found = problems(machine(), result_from_ssh('m', 0, json.dumps(raw), ''))
        self.assertIn('libc6', verdict_text(found[0]))

    def test_no_packages_section_is_calm(self):
        r = result_from_ssh('m', 0, fixture('all-fine.json'), '')
        self.assertEqual(r.data['packages'], {'manager': '', 'reboot': None, 'updates': None,
                                              'security': None})
        self.assertEqual(problems(machine(), r), [])

    def test_silence_after_our_reboot_is_not_down(self):
        r = result_for('ssh-timeout.stderr')
        found = problems(machine(), r, rebooting_since=r.at - 30)
        self.assertEqual((found[0].key, found[0].level), ('rebooting', WARN))
        found = problems(machine(), r, rebooting_since=r.at - probe.REBOOT_GRACE_S - 1)
        self.assertEqual(found[0].level, DOWN)

    def test_local_check_failure(self):
        raw = json.loads(fixture('all-fine.json'))
        raw['local_checks'][0].update(status=503)
        found = problems(machine(), result_from_ssh('m', 0, json.dumps(raw), ''))
        self.assertEqual(verdict_text(found[0]), t('verdict.check_failed', name='api',
                                                   why='HTTP 503'))


# ─── The probe script ─────────────────────────────────────────

class ProbeScript(unittest.TestCase):
    def test_settings_are_quoted(self):
        m = machine()
        m.failover = config.Failover("~/it's here", ('user', 'x'), 'a.log', '')
        script = probe_script(m)
        head = script.split('# Spark Connect probe', 1)[0]
        self.assertIn("SC_UNITS='caddy example-portal'\n", head)
        self.assertIn("SC_TUNNEL=user:cloudflared\n", head)
        self.assertIn("SC_FAILOVER_DIR=''\"'\"'", head.replace("~/it", ""))
        self.assertIn("SC_LOCAL_URLS=api=http://127.0.0.1:8000/health\n", head)

    @unittest.skipUnless(LINUX and shutil.which('sh'), "needs Linux and sh")
    def test_runs_here_and_prints_json(self):
        """The real probe on this PC (it only reads), with every setting filled in."""
        m = config.Machine('here', 'localhost', units=['no-such-unit-sc'],
                           user_units=['no-such-unit-sc'], tunnel=('user', 'no-such-unit-sc'),
                           local_checks=[('nothing', 'http://127.0.0.1:9/')],
                           failover=config.Failover(tempfile.mkdtemp(),
                                                    ('user', 'no-such-unit-sc'), 'x.log', ''))
        done = subprocess.run(['sh', '-s'], input=probe_script(m), capture_output=True,
                              text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        raw = json.loads(done.stdout)
        for key in ('probe', 'time', 'hostname', 'systemd', 'uptime_s', 'load', 'memory',
                    'disks', 'temps', 'net', 'units', 'failed', 'tunnel', 'failover',
                    'local_checks', 'packages'):
            self.assertIn(key, raw)
        d = parse_probe(done.stdout)
        self.assertGreater(d['memory']['total'], 0)
        self.assertEqual(d['local_checks'][0]['status'], None)
        if d['systemd']:
            self.assertEqual({u['state'] for u in d['units']}, {'missing'})

    def test_probe_reads_no_secrets(self):
        """The probe opens only /proc, /sys, /etc/os-release and the failover folder's
        incidents and monitor log; no key or credential file is named in it."""
        text = probe.__dict__['PROBE_FILE']
        with open(text, encoding='utf-8') as f:
            body = '\n'.join(ln for ln in f.read().splitlines()
                             if not ln.lstrip().startswith('#'))
        for word in ('.key', 'credentials', '.pem', 'id_rsa', 'id_ed25519', '.json"'):
            self.assertNotIn(word, body.lower())
        import re
        self.assertIsNone(re.search(r'systemctl (--user )?(re)?(start|stop|enable|disable|'
                                    r'kill|mask)', body))
        for cmd in ('rm ', 'mv ', 'tee ', 'chmod', ' > /', '>>', 'sudo'):
            self.assertNotIn(cmd, body)


# ─── The config ───────────────────────────────────────────────

class Config(unittest.TestCase):
    def write(self, text):
        path = os.path.join(tempfile.mkdtemp(), 'machines.toml')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        return path

    def test_example(self):
        cfg = example()
        self.assertTrue(cfg.found)
        main, standby, desk, gd = cfg.machines
        self.assertTrue(desk.desktop)
        self.assertTrue(gd.console and not gd.desktop)
        self.assertFalse(main.desktop or standby.desktop or main.console)
        self.assertEqual(main.restartable, [('system', 'example-portal'), ('user', 'cloudflared')])
        self.assertTrue(main.can_restart('user', 'cloudflared'))
        self.assertFalse(main.can_restart('system', 'caddy'))
        self.assertTrue(main.is_tunnel('user', 'cloudflared'))
        self.assertTrue(main.is_known_failed('old-backup.service'))
        self.assertEqual(standby.failover.active_unit, ('user', 'cloudflared'))
        self.assertEqual(standby.failover.watches, 'Main server')
        self.assertEqual((main.allow, standby.allow), (['update', 'reboot'], []))
        self.assertEqual(len(cfg.sites), 2)

    def test_missing_file_is_empty(self):
        cfg = config.load(os.path.join(tempfile.mkdtemp(), 'machines.toml'))
        self.assertEqual((cfg.found, cfg.machines, cfg.sites), (False, [], []))

    def test_errors(self):
        bad = {
            '[[machine]]\nname = "a"\n': 'host',
            '[[machine]]\nname = "a"\nhost = "-oProxyCommand=x"\n': 'host',
            '[[machine]]\nname = "a"\nhost = "a"\nunits = ["x; rm -rf /"]\n': 'unit name',
            '[[machine]]\nname = "a"\nhost = "a"\nrestartable = ["caddy"]\n': 'not in units',
            '[[machine]]\nname = "a"\nhost = "a"\nkind = "tablet"\n': "isn't supported",
            '[[machine]]\nname = "a"\nhost = "a"\ntransport = "hub"\n': "isn't supported",
            '[[machine]]\nname = "a"\nhost = "a"\nlocal_checks = { x = "https://example.org/" }'
            '\n': '127.0.0.1',
            '[[machine]]\nname = "a"\nhost = "a"\npasword = 1\n': 'unknown setting',
            '[[machine]]\nname = "a"\nhost = "a"\n[[machine]]\nname = "a"\nhost = "b"\n': 'two',
            '[[site]]\nurl = "ftp://x"\n': 'url',
            'machine = 3\n': 'write machines',
            '[[machine]\n': 'machines.toml',
            '[[machine]]\nname = "a"\nhost = "a"\nallow = ["shutdown"]\n': 'one of',
            '[[machine]]\nname = "a"\nhost = "a"\n[machine.failover]\ndir = "x"\n'
            'watches = "b"\n': "isn't in the list",
        }
        for text, words in bad.items():
            with self.subTest(text=text):
                with self.assertRaises(config.ConfigError) as cm:
                    config.load(self.write(text))
                self.assertIn(words, str(cm.exception))


# ─── Actions ──────────────────────────────────────────────────

class Confirmations(unittest.TestCase):
    def test_restart_cloudflared_names_every_hostname(self):
        c = actions.confirm_restart(machine(), 'user', 'cloudflared')
        for host in ('example.org', 'www.example.org', 'app.example.org'):
            self.assertIn(host, c.detail)
        self.assertIn('ssh main-server systemctl --user restart cloudflared', c.detail)
        self.assertIn('cloudflared', c.title)

    def test_restart_tunnel_without_hostnames_says_so(self):
        m = machine()
        m.tunnel_hostnames = []
        c = actions.confirm_restart(m, 'user', 'cloudflared')
        self.assertIn('tunnel_hostnames', c.detail)

    def test_restart_system_unit(self):
        c = actions.confirm_restart(machine(), 'system', 'example-portal')
        self.assertIn('sudo -n systemctl restart example-portal', c.detail)
        self.assertIn(t('confirm.touches_unit', unit='example-portal'), c.detail)
        self.assertIn(t('confirm.sudo'), c.detail)
        self.assertNotIn('example.org', c.detail)

    def test_terminal_and_failback(self):
        c = actions.confirm_terminal(machine())
        self.assertIn('ssh main-server', c.detail)
        c = actions.confirm_failback(machine(STANDBY))
        self.assertIn('~/failover/hand-back.sh', c.detail)
        self.assertIn('ssh standby', c.detail)

    def test_failback_is_typed_not_run(self):
        remote = actions.typed_not_run("~/failover/hand-back.sh --now")
        self.assertTrue(remote.startswith('bash -c '))
        self.assertIn('read -e -i', remote)
        self.assertIn('hand-back.sh --now', remote)

    @unittest.skipUnless(LINUX and shutil.which('bash'), "needs bash")
    def test_typed_line_runs_only_on_enter(self):
        """Feed the remote line an empty answer (Ctrl+D): the command must not run."""
        marker = os.path.join(tempfile.mkdtemp(), 'ran')
        remote = actions.typed_not_run(f"touch {marker}")
        inner = remote[len('bash -c '):]
        script = subprocess.run(['sh', '-c', f'printf %s {inner}'], capture_output=True,
                                text=True).stdout.replace('exec bash -l', 'true')
        subprocess.run(['bash', '-c', script], stdin=subprocess.DEVNULL, capture_output=True,
                       timeout=10)
        self.assertFalse(os.path.exists(marker))

    def test_terminal_argv(self):
        argv = actions.terminal_argv(machine(), actions.typed_not_run('x'), ssh='ssh')
        if not argv:
            self.skipTest("no terminal program here")
        self.assertIn('-t', argv)
        self.assertEqual(argv[-2], 'main-server')


class MachineActions(unittest.TestCase):
    def test_reboot_names_sites_and_standby(self):
        c = actions.confirm_reboot(machine(), ['Standby laptop'])
        for host in ('example.org', 'www.example.org', 'app.example.org', 'Standby laptop',
                     'sudo -n systemctl reboot', 'ssh main-server'):
            self.assertIn(host, c.detail)
        self.assertEqual(c.button, t('action.reboot'))

    def test_update_runs_in_a_terminal(self):
        self.assertIsNone(actions.update_command(''))
        cmd = actions.update_command('apt')
        self.assertEqual(cmd, "sudo apt update && sudo apt full-upgrade")
        self.assertNotIn(' -y', cmd)                   # apt still asks before it changes
        remote = actions.update_remote(cmd)
        self.assertTrue(remote.startswith('bash -c '))
        self.assertIn('exec bash -l', remote)
        c = actions.confirm_update(machine(), 'apt', 23, 1)
        self.assertIn(cmd, c.detail)
        self.assertIn('23', c.detail)

    @unittest.skipUnless(LINUX, "the stand-in ssh is a shell script")
    def test_reboot_outcomes(self):
        folder = tempfile.mkdtemp()
        fake = os.path.join(folder, 'ssh')

        def answer(script):
            with open(fake, 'w') as f:
                f.write('#!/bin/sh\n' + script)
            os.chmod(fake, 0o755)
            return SshTransport(ssh=fake, multiplex=False).reboot(machine())

        self.assertEqual(answer('exit 0\n').outcome, DONE)
        self.assertEqual(answer('echo "Connection to x closed by remote host." >&2; exit 255\n')
                         .outcome, DONE)
        self.assertEqual(answer('echo "sudo: a password is required" >&2; exit 1\n').outcome,
                         NEEDS_PASSWORD)
        self.assertEqual(answer('echo "ssh: connect to host x port 22: No route to host" >&2;'
                                ' exit 255\n').outcome, 'failed')
        self.assertEqual(SshTransport(ssh=fake).reboot(machine(STANDBY)).outcome, 'refused')


class Restart(unittest.TestCase):
    """The restart command, with a stand-in ssh that records what it was asked and answers
    like sudo would."""

    @unittest.skipUnless(LINUX, "the stand-in ssh is a shell script")
    def test_commands_and_password_refusal(self):
        folder = tempfile.mkdtemp()
        record = os.path.join(folder, 'args')
        fake = os.path.join(folder, 'ssh')
        with open(fake, 'w') as f:
            f.write('#!/bin/sh\nprintf "%s\\n" "$@" > ' + record + '\n'
                    'case "$*" in *sudo*) echo "sudo: a password is required" >&2; exit 1;; '
                    'esac\nexit 0\n')
        os.chmod(fake, 0o755)
        tr = SshTransport(ssh=fake, multiplex=False)
        m = machine()
        self.assertEqual(tr.restart(m, 'user', 'cloudflared').outcome, DONE)
        with open(record) as f:
            args = f.read().split('\n')
        self.assertIn('BatchMode=yes', args)
        self.assertIn('StrictHostKeyChecking=yes', args)
        self.assertTrue(any(a.endswith('systemctl --user restart -- cloudflared') for a in args), args)
        self.assertEqual(tr.restart(m, 'system', 'example-portal').outcome, NEEDS_PASSWORD)
        self.assertEqual(tr.restart(m, 'system', 'caddy').outcome, 'refused')


# ─── Alerts, report, websites, self-test ──────────────────────

class Alerting(unittest.TestCase):
    def test_once_down_once_back(self):
        a = alerts.Alerts()
        key = ('machine', 'm', 'down')
        self.assertEqual(a.update({key: 'x'}, scope=('machine', 'm')), [('bad', key, 'x')])
        self.assertEqual(a.update({key: 'x'}, scope=('machine', 'm')), [])
        self.assertEqual(a.update({('site', 's'): 'y'}, scope=('site', 's'))[0][0], 'bad')
        self.assertEqual(a.update({}, scope=('machine', 'm')), [('recovered', key, 'x')])
        self.assertEqual(a.update({}, scope=('machine', 'm')), [])
        self.assertIn(('site', 's'), a.active)


class Report(unittest.TestCase):
    def test_report(self):
        m = machine()
        text = report.build(m, result_for('failed-unit.json', m), now=1795000000)
        self.assertIn('Main server (main-server)', text)
        self.assertIn(t('verdict.unit_failed', unit='example-portal'), text)
        self.assertIn('system:example-portal: failed', text)
        self.assertIn("ImportError", text)
        self.assertIn('Disk /:', text)
        text = report.build(m, result_for('ssh-hostkey-changed.stderr', m))
        self.assertIn('SHA256:', text)


class Handler(http.server.BaseHTTPRequestHandler):
    agents = []

    def do_GET(self):
        Handler.agents.append(self.headers.get('User-Agent'))
        self.send_response(500 if self.path == '/broken' else 200)
        self.end_headers()
        self.wfile.write(b'ok')

    def log_message(self, *_a):
        pass


class Websites(unittest.TestCase):
    def test_check(self):
        server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            good = sites.check(config.Site('ok', base + '/'))
            bad = sites.check(config.Site('bad', base + '/broken'))
        finally:
            server.shutdown()
        self.assertEqual((good.status, good.ok), (200, True))
        self.assertEqual((bad.status, bad.ok), (500, False))
        self.assertEqual(Handler.agents[0], f"SparkConnect/{VERSION}")
        gone = sites.check(config.Site('gone', 'http://127.0.0.1:9/'), timeout=2)
        self.assertFalse(gone.ok)
        self.assertTrue(gone.error)


class SelfTest(unittest.TestCase):
    def test_self_test(self):
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out):
            code = self_test(EXAMPLE)
        text = out.getvalue()
        self.assertIn('4 machines, 2 websites', text)
        self.assertIn('probe:', text)
        if shutil.which('ssh'):
            self.assertEqual(code, 0, text)
        broken = os.path.join(tempfile.mkdtemp(), 'machines.toml')
        with open(broken, 'w') as f:
            f.write('[[machine]]\nname = "x"\n')
        with redirect_stdout(io.StringIO()):
            self.assertEqual(self_test(broken), 1)


# ─── The window ───────────────────────────────────────────────

def have_display() -> bool:
    if os.name == 'nt':
        return True
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


class FakeTransport:
    """Answers from fixtures and records every call. restart() must never be reached when a
    confirmation is cancelled."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def fetch(self, m):
        self.calls.append(('fetch', m.name))
        return result_for(self.answers.get(m.name, 'desktop-in-use.json'), m)

    def restart(self, m, scope, unit):
        self.calls.append(('restart', m.name, scope, unit))
        return ActionResult(DONE)

    def reboot(self, m):
        self.calls.append(('reboot', m.name))
        return ActionResult(DONE)

    def tail(self, m, scope, unit, on_line, lines=200):
        self.calls.append(('tail', m.name, scope, unit))

        class Tail:
            def stop(self):
                pass
        on_line("2026-11-20T09:00:00-05:00 main-server caddy[1]: serving")
        on_line("2026-11-20T09:00:01-05:00 main-server caddy[1]: something else")
        return Tail()


def fake_site(site):
    if site.name == 'app.example.org':
        return sites.SiteResult(site.name, site.url, status=502, ms=80.0)
    return sites.SiteResult(site.name, site.url, status=200, ms=120.0)


# ─── --status, what the Plasma widget shows ───────────────────

class WidgetStatus(unittest.TestCase):
    def setUp(self):
        from sparkconnect import status
        self.status = status
        self.cfg = example()
        self.names = [m.name for m in self.cfg.machines]

    def collect(self, answers):
        return self.status.collect(self.cfg, FakeTransport(answers), check_site=fake_site)

    def test_every_machine_and_site(self):
        out = self.collect({self.names[MAIN]: 'all-fine.json'})
        self.assertEqual([m['name'] for m in out['machines']], self.names)
        main = out['machines'][MAIN]
        self.assertEqual((main['level'], main['state'], main['verdict'], main['up']),
                         (OK, t('card.up'), t('verdict.ok'), True))
        for key in ('uptime', 'load', 'memory', 'disk', 'temp'):
            self.assertNotEqual(main[key], '—', key)
        bad = [s for s in out['sites'] if not s['ok']]
        self.assertEqual([(s['name'], s['status'], s['level']) for s in bad],
                         [('app.example.org', 'HTTP 502', DOWN)])
        self.assertEqual(out['level'], DOWN)         # the worst of everything
        self.assertEqual(out['summary'], t('widget.trouble', n=1))
        json.dumps(out)                              # all of it is plain JSON

    def test_down_machine_and_its_words(self):
        out = self.collect({self.names[MAIN]: 'ssh-timeout.stderr'})
        main = out['machines'][MAIN]
        self.assertEqual((main['level'], main['state'], main['up'], main['uptime']),
                         (DOWN, t('card.down'), False, '—'))
        self.assertTrue(main['verdict'].startswith(t('verdict.unreachable', since='')), main['verdict'])

    def test_down_since_is_kept_between_runs(self):
        path = os.path.join(tempfile.mkdtemp(), 'down.json')
        first = result_for('ssh-timeout.stderr', at=1000.0)
        self.assertEqual(self.status.remember_down({'a': first}, path), {'a': 1000.0})
        later = result_for('ssh-timeout.stderr', at=1060.0)
        self.assertEqual(self.status.remember_down({'a': later}, path), {'a': 1000.0})
        back = result_for('all-fine.json', at=1120.0)
        self.assertEqual(self.status.remember_down({'a': back}, path), {})
        again = result_for('ssh-timeout.stderr', at=1180.0)
        self.assertEqual(self.status.remember_down({'a': again}, path), {'a': 1180.0})
        with open(path, 'w') as f:
            f.write('not json')
        self.assertEqual(self.status.remember_down({'a': later}, path), {'a': 1060.0})

    def test_no_machine_list_and_a_broken_one(self):
        missing = os.path.join(tempfile.mkdtemp(), 'machines.toml')
        out = self.status.report(missing)
        self.assertTrue(out['empty'])
        self.assertEqual((out['level'], out['machines'], out['summary']),
                         (OK, [], t('status.no_config')))
        with open(missing, 'w') as f:
            f.write('[[machine]]\nname = "x"\n')
        out = self.status.report(missing)
        self.assertEqual(out['level'], DOWN)
        self.assertTrue(out['error'])
        self.assertIn('widget.open', out['labels'])

    def test_command_line(self):
        missing = os.path.join(tempfile.mkdtemp(), 'machines.toml')
        done = subprocess.run([sys.executable, os.path.join(APP_DIR, 'spark_connect.py'),
                               '--status', '--config', missing],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)
        self.assertEqual((out['format'], out['version']), (1, VERSION))


@unittest.skipUnless(have_display(), "needs a display")
class UITests(unittest.TestCase):
    def make(self, answers, path=EXAMPLE):
        from sparkconnect.app import App
        self.transport = FakeTransport(answers)
        self.notes = []
        app = App(config_path=path, transport=self.transport, site_checker=fake_site,
                  auto_refresh=False, notifier=lambda a, b: self.notes.append((a, b)) or True)
        self.addCleanup(app.close)
        return app

    def settle(self, app, until, timeout=10.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            app.root.update()
            if until():
                return
            time.sleep(0.02)
        self.fail("timed out waiting")

    def load_all(self, app):
        for m in app.config.machines:
            app.start(('machine', m.name))
        for s in app.config.sites:
            app.start(('site', s.name))
        count = len(app.config.machines)
        self.settle(app, lambda: not app.pending and len(app.results) == count
                    and len(app.site_results) == 2)

    def test_overview_renders_calm(self):
        app = self.make({'Main server': 'all-fine.json', 'Standby laptop': 'standby-ok.json'})
        self.load_all(app)
        ov = app.overview
        self.assertEqual(ov.order, ['Main server', 'Standby laptop', 'Living-room PC', 'GD host'])
        card = ov.cards['Main server']
        self.assertEqual(card.verdict.cget('text'), t('verdict.ok'))
        self.assertFalse(card.slipped)
        self.assertFalse(ov.cards['Standby laptop'].slipped)
        self.assertEqual(card.values['load'].cget('text'), '0.42')
        # the broken site sorts first and slips; the calm one doesn't
        self.assertEqual(ov.site_order, ['app.example.org', 'example.org'])
        self.assertTrue(ov.sites['app.example.org'].slipped)
        self.assertFalse(ov.sites['example.org'].slipped)
        self.assertEqual([n[1] for n in self.notes], ['HTTP 502'])

    def test_failed_machine_sorts_to_top(self):
        app = self.make({'Main server': 'all-fine.json',
                         'Standby laptop': 'ssh-timeout.stderr'})
        self.load_all(app)
        self.assertEqual(app.overview.order, ['Standby laptop', 'Main server', 'Living-room PC', 'GD host'])
        card = app.overview.cards['Standby laptop']
        self.assertTrue(card.slipped)
        self.assertIn(t('card.down'), card.state.cget('text'))
        self.assertTrue(card.verdict.cget('text').startswith(
            t('verdict.unreachable', since='')[:5]))
        self.assertIn(('Spark Connect: Standby laptop'), [n[0] for n in self.notes])
        # it answers again: one recovery note, and it sorts back down
        self.transport.answers['Standby laptop'] = 'standby-ok.json'
        app.start(('machine', 'Standby laptop'))
        self.settle(app, lambda: not app.pending)
        self.assertEqual(app.overview.order, ['Main server', 'Standby laptop', 'Living-room PC', 'GD host'])
        self.assertTrue(self.notes[-1][1].startswith(t('alert.back', text='')[:4]))

    def test_restart_confirmation_cancel_runs_nothing(self):
        import tkinter as tk
        app = self.make({'Main server': 'cloudflared-reconnecting.json',
                         'Standby laptop': 'standby-ok.json'})
        self.load_all(app)
        app.open_machine('Main server')
        app.root.update()
        seen = {}

        def answer():
            tops = [w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel)]
            if not tops:
                app.root.after(50, answer)
                return
            texts = []

            def walk(w):
                for c in w.winfo_children():
                    try:
                        texts.append(str(c.cget('text')))
                    except tk.TclError:
                        pass
                    walk(c)
            walk(tops[0])
            seen['text'] = '\n'.join(texts)
            tops[0].event_generate('<Escape>')

        app.root.after(100, answer)
        m = app.machine('Main server')
        app.ask_restart(m, 'user', 'cloudflared')
        app.root.update()
        self.assertIn('www.example.org', seen['text'])
        self.assertIn('app.example.org', seen['text'])
        self.assertIn(t('action.restart').upper(), seen['text'])
        self.assertFalse(any(c[0] == 'restart' for c in self.transport.calls))

        # confirmed this time: the restart runs once, then the machine refreshes
        app.confirm = lambda c: True
        before = sum(1 for c in self.transport.calls if c[0] == 'fetch')
        app.ask_restart(m, 'user', 'cloudflared')
        self.settle(app, lambda: not app.pending and
                    sum(1 for c in self.transport.calls if c[0] == 'fetch') > before)
        self.assertEqual([c for c in self.transport.calls if c[0] == 'restart'],
                         [('restart', 'Main server', 'user', 'cloudflared')])

    def test_reboot_cancel_runs_nothing_then_quiet_while_down(self):
        app = self.make({'Main server': 'all-fine.json', 'Standby laptop': 'standby-ok.json'})
        self.load_all(app)
        m = app.machine('Main server')
        seen = []
        app.confirm = lambda c: seen.append(c) or False
        app.ask_reboot(m)
        self.assertIn('Standby laptop', seen[0].detail)
        self.assertFalse(any(c[0] == 'reboot' for c in self.transport.calls))
        app.confirm = lambda c: True
        app.ask_reboot(m)
        self.settle(app, lambda: not app.pending and 'Main server' in app.rebooting)
        self.assertEqual([c for c in self.transport.calls if c[0] == 'reboot'],
                         [('reboot', 'Main server')])
        # it goes quiet: shown as rebooting, no "unreachable" notification
        notes = len(self.notes)
        self.transport.answers['Main server'] = 'ssh-timeout.stderr'
        app.start(('machine', 'Main server'))
        self.settle(app, lambda: not app.pending)
        self.assertEqual(app.problems_of(m)[0].key, 'rebooting')
        self.assertEqual(len(self.notes), notes)
        # the standby can't reboot: no button, and the call does nothing
        app.ask_reboot(app.machine('Standby laptop'))
        self.assertEqual(len([c for c in self.transport.calls if c[0] == 'reboot']), 1)

    def test_machine_view_every_tab(self):
        for main, standby in (('failed-unit.json', 'standby-takeover.json'),
                              ('disk-full.json', 'ssh-hostkey-changed.stderr')):
            app = self.make({'Main server': main, 'Standby laptop': standby})
            self.load_all(app)
            for name in ('Main server', 'Standby laptop'):
                app.open_machine(name)
                view = app.machine_view
                for tab in view.tabbar.labels:
                    view.show(tab)
                    app.root.update()
                if name == 'Standby laptop' and standby == 'standby-takeover.json':
                    self.assertTrue(view.failback.winfo_ismapped())
                app.show_overview()
            app.close()

    def test_logs_follow_and_filter(self):
        app = self.make({'Main server': 'all-fine.json', 'Standby laptop': 'standby-ok.json'})
        self.load_all(app)
        app.open_machine('Main server')
        view = app.machine_view
        view.open_logs('system', 'caddy')
        self.settle(app, lambda: 'serving' in view.logs.text.get('1.0', 'end'))
        view.logs.filter.set('else')
        app.root.update()
        shown = view.logs.text.get('1.0', 'end')
        self.assertNotIn('serving', shown)
        self.assertIn('something else', shown)

    def test_no_machine_list(self):
        app = self.make({}, path=os.path.join(tempfile.mkdtemp(), 'machines.toml'))
        app.root.update()
        self.assertFalse(app.overview.cards)
        self.assertIn('machines.toml', str(app.overview.message_panel.inner.winfo_children()[0]
                                           .winfo_children()[1].cget('text')))

    def test_copy_report(self):
        app = self.make({'Main server': 'failed-unit.json', 'Standby laptop': 'standby-ok.json'})
        self.load_all(app)
        app.copy_report(app.machine('Main server'))
        self.assertIn('example-portal', app.root.clipboard_get())


if __name__ == '__main__':
    unittest.main()
