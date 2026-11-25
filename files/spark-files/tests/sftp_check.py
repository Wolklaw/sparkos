#!/usr/bin/env python3
"""The real stack, end to end, on this PC only: a throwaway sshd on 127.0.0.1, then Spark Files'
own code through kio-fuse and KIO's sftp worker: the host key check, connecting, listing,
copying a folder to the server and back, cancelling a big copy, and a server that is gone.

    python3 files/spark-files/tests/sftp_check.py

Needs sshd, ssh-keygen, kio-fuse and kio-extras. KIO's sftp worker reads the *passwd* home
(~/.ssh), not $HOME, so this runs itself inside `unshare -m -c` with a temporary folder bind
mounted over your home folder, inside that namespace only: nothing of yours is read or
written, and nothing outside /tmp is touched.
In a throwaway container that is already root, set SPARK_FILES_THROWAWAY=1 to use /root as is.
Not part of the unit tests (CI runs those); exits 0 when everything passes, 77 when the tools
are missing.
"""

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
MARK = 'SPARK_FILES_SFTP_INNER'
PORT = 2299


def need() -> bool:
    return all(shutil.which(x) for x in ('ssh-keygen', 'ssh-keyscan', 'dbus-run-session')) \
        and os.path.exists('/usr/sbin/sshd' if os.path.exists('/usr/sbin/sshd')
                           else '/usr/bin/sshd') and os.path.exists('/usr/libexec/kio-fuse')


def setup(tmp: str, ssh: str) -> subprocess.Popen:
    """A throwaway sshd on 127.0.0.1 serving tmp/srv, with a fresh key pair in `ssh`."""
    os.makedirs(ssh, mode=0o700, exist_ok=True)
    srv = os.path.join(tmp, 'srv')
    os.makedirs(os.path.join(srv, 'docs'))
    with open(os.path.join(srv, 'docs', 'hello.txt'), 'w') as f:
        f.write('hello from the server\n')
    host = os.path.join(tmp, 'hostkey')
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', host], check=True)
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f',
                    os.path.join(ssh, 'id_ed25519')], check=True)
    shutil.copy(os.path.join(ssh, 'id_ed25519.pub'), os.path.join(tmp, 'authorized_keys'))
    config = os.path.join(tmp, 'sshd_config')
    with open(config, 'w') as f:
        f.write(f"Port {PORT}\nListenAddress 127.0.0.1\nHostKey {host}\n"
                f"AuthorizedKeysFile {tmp}/authorized_keys\nPidFile {tmp}/sshd.pid\n"
                "PasswordAuthentication no\nStrictModes no\n"
                "Subsystem sftp /usr/libexec/openssh/sftp-server\n")
    sshd = '/usr/sbin/sshd' if os.path.exists('/usr/sbin/sshd') else '/usr/bin/sshd'
    daemon = subprocess.Popen([sshd, '-D', '-f', config, '-E', os.path.join(tmp, 'sshd.log')])
    time.sleep(1.5)
    return daemon


HELPERS = ('kio-fuse', 'kiod6', 'ksecretd', 'xdg-desktop-portal-kde')


def helper_pids() -> set:
    """Helpers the private session bus can start (they may outlive it)."""
    found = set()
    for name in HELPERS:
        out = subprocess.run(['pgrep', '-u', str(os.getuid()), '-x', name[:15]],
                             capture_output=True, text=True).stdout
        found |= {int(x) for x in out.split()}
    return found


def outer() -> int:
    if not need():
        print('skipped: sshd, ssh-keygen, dbus-run-session or kio-fuse missing')
        return 77
    tmp = tempfile.mkdtemp(prefix='spark-files-sftp-')
    daemon = None
    before = helper_pids()
    try:
        if os.geteuid() == 0:
            if os.environ.get('SPARK_FILES_THROWAWAY') != '1':
                print('refusing: running as root outside a throwaway container '
                      '(set SPARK_FILES_THROWAWAY=1 if it is one)')
                return 2
            daemon = setup(tmp, '/root/.ssh')
            return subprocess.call(
                ['dbus-run-session', '--', sys.executable, '-u', __file__],
                env=dict(os.environ, **{MARK: '1', 'SPARK_FILES_TMP': tmp,
                                        'SPARK_FILES_SSH_USER': 'root'}))
        import getpass
        import pwd
        home = os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir)
        runtime = os.path.join(tmp, 'run')
        os.makedirs(runtime, mode=0o700)
        daemon = setup(tmp, os.path.join(tmp, 'home', '.ssh'))
        script = (f'mount --bind {shlex.quote(tmp)}/home {shlex.quote(home)} && '
                  f'export HOME={shlex.quote(home)} XDG_RUNTIME_DIR={shlex.quote(runtime)} '
                  f'{MARK}=1 SPARK_FILES_TMP={shlex.quote(tmp)} && '
                  f'exec dbus-run-session -- {shlex.quote(sys.executable)} -u '
                  f'{shlex.quote(os.path.abspath(__file__))}')
        return subprocess.call(['unshare', '-m', '-c', '--keep-caps', 'bash', '-c', script],
                               env=dict(os.environ, SPARK_FILES_SSH_USER=getpass.getuser()))
    finally:
        if daemon is not None and daemon.poll() is None:
            daemon.terminate()
        for pid in helper_pids() - before:        # what this run started, nothing older
            try:
                os.kill(pid, 15)
            except OSError:
                pass
        try:
            with open(os.path.join(tmp, 'sshd.log')) as f:
                print('--- sshd.log', ''.join(f.readlines()[-12:]), sep='\n')
        except OSError:
            pass
        shutil.rmtree(tmp, ignore_errors=True)


def inner() -> int:
    tmp = os.environ['SPARK_FILES_TMP']
    for var in ('XDG_STATE_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME'):
        os.environ[var] = os.path.join(tmp, var.lower())
    from sparkfiles import network, ops
    srv = os.path.join(tmp, 'srv')
    results = []

    def check(name, ok, detail=''):
        results.append(ok)
        print(('ok    ' if ok else 'FAIL  ') + name + (f'  {detail}' if detail and not ok
                                                       else ''))
    user = os.environ['SPARK_FILES_SSH_USER']
    if True:
        server, _ = network.parse_address(f'sftp://127.0.0.1:{PORT}{srv}', user=user)

        check('the host is new', network.host_key_known(server) is False)
        line, fp = network.scan_host_key(server)
        check('scan reads a fingerprint', fp.startswith('SHA256:'), fp)
        network.accept_host_key(line)
        check('the host is known after accepting', network.host_key_known(server) is True)

        path = network.connect_blocking(server, None, timeout=45)
        check('connect returns a folder', os.path.isdir(path), path)
        check('it is a network place', network.is_remote(path), path)
        remote = network.split_remote(path)
        check('its label is the address', bool(remote) and remote[1].startswith('sftp://'),
              str(remote))
        check('it lists the server folder', os.listdir(path) == ['docs'], str(os.listdir(path)))

        local = os.path.join(tmp, 'local')
        os.makedirs(os.path.join(local, 'photos'))
        with open(os.path.join(local, 'photos', 'a.bin'), 'wb') as f:
            f.write(os.urandom(300_000))
        job = ops.Job('copy', [os.path.join(local, 'photos')], os.path.join(path, 'docs'))
        job.start()
        job.thread.join(60)
        up = os.path.join(srv, 'docs', 'photos', 'a.bin')
        check('copy to the server finishes', job.state == 'done' and not job.errors, f'{job.state} {job.errors}')
        src = os.path.join(local, 'photos', 'a.bin')
        check('the file arrived intact', os.path.exists(up) and
              open(up, 'rb').read() == open(src, 'rb').read(),
              f'{up}: {os.path.getsize(up) if os.path.exists(up) else None} bytes, want '
              f'{os.path.getsize(src)}; tree {sorted(os.listdir(os.path.join(srv, "docs")))}')

        back = os.path.join(tmp, 'back')
        os.makedirs(back)
        job = ops.Job('copy', [os.path.join(path, 'docs', 'hello.txt')], back)
        job.start()
        job.thread.join(60)
        got = os.path.join(back, 'hello.txt')
        check('copy from the server finishes', job.state == 'done', f'{job.state} {job.errors}')
        check('the file came back intact', os.path.exists(got) and
              open(got).read() == 'hello from the server\n',
              f'{os.path.exists(got)} {open(got).read()!r} {job.errors}' if os.path.exists(got)
              else f'missing; {job.errors}')

        big = os.path.join(local, 'big.bin')
        with open(big, 'wb') as f:
            f.write(os.urandom(1024 * 1024) * 400)
        job = ops.Job('copy', [big], os.path.join(path, 'docs'))
        job.start()
        end = time.monotonic() + 30
        while job.done_bytes == 0 and job.active and time.monotonic() < end:
            time.sleep(0.001)
        job.cancel()
        job.thread.join(30)
        check('a big copy can be cancelled', job.state == 'cancelled', job.state)

        with open(os.path.join(tmp, 'sshd.pid')) as f:
            os.kill(int(f.read()), 15)
        time.sleep(1)
        began = time.monotonic()
        try:
            network.connect_blocking(
                network.parse_address(f'sftp://127.0.0.1:{PORT}/x', user=user)[0], None,
                timeout=15)
            check('a stopped server is an error', False)
        except network.NetworkError as err:
            check('a stopped server is an error, not a hang',
                  time.monotonic() - began < 20, f'{err.code} {err.detail}')
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(inner() if os.environ.get(MARK) else outer())
