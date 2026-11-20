#!/usr/bin/env python3
"""Start an installed Spark Link service and check it from outside, the way CI does it:

    python3 smoke.py /usr/bin/spark-link [--mdns] [--cpu SECONDS]

It must not listen with nothing paired; it must listen (and with --mdns, be announced through
Avahi with the right TXT records) once pairing starts; and it must use next to no CPU while
idle. Talks to the control socket directly, without importing the app."""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time


def request(path, req):
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(5)
        s.connect(path)
        s.sendall((json.dumps(req) + '\n').encode())
        buf = b''
        while not buf.endswith(b'\n'):
            data = s.recv(65536)
            if not data:
                break
            buf += data
    return json.loads(buf)


def cpu_ticks(pid):
    with open(f'/proc/{pid}/stat') as f:
        fields = f.read().rsplit(')', 1)[1].split()
    return int(fields[11]) + int(fields[12])


def main():
    exe = sys.argv[1]
    mdns = '--mdns' in sys.argv
    cpu_secs = 10
    if '--cpu' in sys.argv:
        cpu_secs = int(sys.argv[sys.argv.index('--cpu') + 1])
    env = dict(os.environ)
    if not env.get('XDG_RUNTIME_DIR'):
        env['XDG_RUNTIME_DIR'] = tempfile.mkdtemp()
    os.chmod(env['XDG_RUNTIME_DIR'], 0o700)
    sock = os.path.join(env['XDG_RUNTIME_DIR'], 'spark-link', 'control.sock')
    cmd = [exe, '--service'] + ([] if mdns else ['--no-mdns'])
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for _ in range(100):
            try:
                st = request(sock, {'cmd': 'status', 'peek': True})
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise SystemExit('the service did not open its control socket')
        assert not st['listening'], 'listening with nothing paired'
        print(f"pc {st['pc']['name']} id {st['pc']['id']} key {st['pc']['key']}")
        if mdns and shutil.which('avahi-browse'):
            time.sleep(1)
            out = subprocess.run(['avahi-browse', '-rtp', '_sparklink._tcp'],
                                 stdout=subprocess.PIPE, timeout=20).stdout.decode()
            assert '=' not in [line[:1] for line in out.splitlines()], 'announced too early'
        st = request(sock, {'cmd': 'pair.start'})
        assert st['listening'] and st['pairing']['active'], st
        print(f"pairing: {st['pairing']['link']}")
        if mdns:
            time.sleep(2)
            st = request(sock, {'cmd': 'status', 'peek': True})
            print(f"mdns: {st['mdns'] or 'not announced'}")
            assert st['mdns'], 'not announced over mDNS'
            out = subprocess.run(['avahi-browse', '-rtp', '_sparklink._tcp'],
                                 stdout=subprocess.PIPE, timeout=20).stdout.decode()
            print(out)
            found = [line for line in out.splitlines() if line.startswith('=')]
            assert found, 'avahi-browse found nothing'
            line = found[0]
            assert f";{st['port']};" in line, line
            assert '"v=1"' in line and f'"id={st["pc"]["id"]}"' in line, line
            assert re.search(r'"name=[^"]+"', line), line
        before = cpu_ticks(proc.pid)
        time.sleep(cpu_secs)
        used = cpu_ticks(proc.pid) - before
        hz = os.sysconf('SC_CLK_TCK')
        print(f"cpu: {used} ticks ({used / hz:.2f} s) in {cpu_secs} s idle while pairing")
        assert used <= max(5, cpu_secs // 2), 'too busy while idle'
        request(sock, {'cmd': 'pair.cancel'})
        st = request(sock, {'cmd': 'status', 'peek': True})
        assert not st['listening'], 'still listening after pairing stopped'
        request(sock, {'cmd': 'stop'})
        proc.wait(10)
        print('smoke test passed')
    finally:
        if proc.poll() is None:
            proc.kill()
        out = proc.stdout.read().decode('utf-8', 'replace')
        if out.strip():
            print('--- service log\n' + out)


if __name__ == '__main__':
    main()
