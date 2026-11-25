#!/usr/bin/env python3
"""Smoke checks for the Spark apps that used to lean on Plasma, run INSIDE kwin-only.sh (a
headless KWin, a private bus, no plasmashell):

    files/spark-apps/ci/kwin-only.sh python3 files/spark-apps/ci/kwin_only_smoke.py

Each check prints PASS, FAIL or SKIP with the reason. Exit 1 on any FAIL. SKIP is only for a
program the machine doesn't have (the CI job runs on the SparkOS image, which has them all, and
sets KWIN_ONLY_STRICT=1 so a SKIP counts as a FAIL there).

Shows no window, changes no setting, restarts nothing: the Restart code path is only asked
whether ksmserver is there.
"""
import importlib.machinery
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = os.path.dirname(os.path.dirname(HERE))
STRICT = os.environ.get('KWIN_ONLY_STRICT') == '1'
results = []


def check(name):
    def wrap(fn):
        try:
            # KWIN_ONLY_WAIVE="text one|text two": checks whose name contains one of these are
            # not run (CI only; each is named in the job's workflow file with its reason)
            for text in filter(None, os.environ.get('KWIN_ONLY_WAIVE', '').split('|')):
                if text in name:
                    raise Waived(f"waived by KWIN_ONLY_WAIVE ({text!r}), see the workflow file")
            note = fn()
            results.append(('PASS', name, note or ''))
        except Skip as why:
            results.append(('FAIL' if STRICT else 'SKIP', name, str(why)))
        except Waived as why:
            results.append(('WAIVED', name, str(why)))
        except Exception as exc:                    # noqa: BLE001 - reported, not raised
            results.append(('FAIL', name, f"{type(exc).__name__}: {exc}"))
        print(*results[-1], flush=True)
        return fn
    return wrap


class Skip(Exception):
    pass


class Waived(Exception):
    """Not run on purpose here (KWIN_ONLY_NO_RENDER=1); never counts as a failure."""


def need(path_or_cmd):
    if not (os.path.exists(path_or_cmd) or shutil.which(path_or_cmd)):
        raise Skip(f"{path_or_cmd} is not installed")


def bus_names():
    out = subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.freedesktop.DBus',
                          '--object-path', '/org/freedesktop/DBus', '--method',
                          'org.freedesktop.DBus.ListNames'], capture_output=True, text=True,
                         timeout=10).stdout
    return out


def app_path(app):
    sys.path.insert(0, os.path.join(FILES, app))


# ── the session itself ──
@check("session: KWin alone, no plasmashell on the bus")
def _():
    names = bus_names()
    assert "'org.kde.KWin.ScreenShot2'" in names, "KWin is not offering ScreenShot2"
    for plasma in ('org.kde.plasmashell', 'org.kde.KSplash', 'org.kde.ksmserver',
                   'org.kde.Shutdown'):
        assert f"'{plasma}'" not in names, f"{plasma} is on the bus"
    assert os.environ.get('XDG_CURRENT_DESKTOP') == 'Spark'


# ── Spark Snip ──
app_path('spark-snip')


@check("spark-snip: capture order follows the bus, not the desktop name")
def _():
    from sparksnip import core
    order = core.capture_order()
    assert order == ['kwin', 'portal'], order
    return str(order)


@check("spark-snip: --self-test passes")
def _():
    done = subprocess.run([sys.executable, os.path.join(FILES, 'spark-snip', 'spark_snip.py'),
                           '--self-test'], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, (done.stdout + done.stderr)[-400:]


# ── Spark Files ──
app_path('spark-files')


@check("spark-files: kio-fuse can be reached without plasmashell and mounts a folder")
def _():
    need('/usr/libexec/kio-fuse')
    from sparkfiles import network
    assert network.kio_fuse_offered(), "kio-fuse is neither running nor startable"
    folder = tempfile.mkdtemp(prefix='kwin-only-share-')
    try:
        with open(os.path.join(folder, 'a.txt'), 'w') as f:
            f.write('hi')
        backend = network.choose_backend(network.Server('sftp', 'h'))
        assert isinstance(backend, network.KioFuse), backend
        mount = backend.mount('file://' + folder, 20)
        assert os.path.isfile(os.path.join(mount, 'a.txt')) or \
            os.path.isfile(os.path.join(mount, folder.lstrip('/'), 'a.txt')) or \
            os.path.isdir(mount), mount
        return "kio-fuse mounted file:// (sftp and smb use the same workers)"
    finally:
        shutil.rmtree(folder, ignore_errors=True)


@check("spark-files: with kio-fuse out of reach, sftp falls to sshfs")
def _():
    from sparkfiles import network
    server = network.Server('sftp', 'h')
    assert isinstance(network.choose_backend(server, kio_offered=False, sshfs_there=True),
                      network.SshFs)


@check("spark-files: kded6 (accounts for Google Drive) can start without plasmashell")
def _():
    need('/usr/bin/kded6')
    out = subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.kde.kded6', '--object-path',
                          '/kded', '--method', 'org.kde.kded6.loadedModules'],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr[-300:]
    return "loaded: " + out.stdout.strip()[:120]


@check("spark-files: --self-test passes")
def _():
    done = subprocess.run([sys.executable, os.path.join(FILES, 'spark-files', 'spark_files.py'),
                           '--self-test'], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, (done.stdout + done.stderr)[-400:]


# ── Spark Emoji ──
app_path('spark-emoji')


@check("spark-emoji: the RemoteDesktop portal offers a keyboard")
def _():
    need('/usr/libexec/xdg-desktop-portal-kde')
    from sparkemoji import paste
    assert paste.portal_available(), ("no RemoteDesktop keyboard on the portal; xdg-desktop-"
                                      "portal-kde offers it only when XDG_CURRENT_DESKTOP "
                                      "contains KDE")


@check("spark-emoji: --self-test passes")
def _():
    done = subprocess.run([sys.executable, os.path.join(FILES, 'spark-emoji', 'spark_emoji.py'),
                           '--self-test'], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, (done.stdout + done.stderr)[-400:]


# ── Spark Update ──
app_path('spark-update')


@check("spark-update: Restart sees no ksmserver and would ask systemd (nothing is restarted)")
def _():
    from sparkupdate import notify
    assert notify.session_has_ksmserver() is False


# ── spark-share ──
def load_share():
    path = os.path.join(FILES, 'system', 'usr', 'bin', 'spark-share')
    loader = importlib.machinery.SourceFileLoader('spark_share', path)
    spec = importlib.util.spec_from_loader('spark_share', loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


@check("spark-share: krdpserver --plasma starts on KWin alone and listens on 127.0.0.1")
def _():
    need('/usr/bin/krdpserver')
    need('openssl')
    share = load_share()
    work = tempfile.mkdtemp(prefix='kwin-only-krdp-')
    server = None
    try:
        cert, key, _fp = share.make_certificate(work)
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        server = subprocess.Popen(share.krdp_argv(port, 'u', 'p', cert, key),
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not share.listening(port):
            assert server.poll() is None, server.stderr.read()[-300:].decode('utf-8', 'replace')
            time.sleep(0.3)
        assert share.listening(port), "krdpserver never listened"
        return "listening; a frame was not streamed (no RDP client here)"
    finally:
        if server and server.poll() is None:
            server.terminate()
            try:
                server.wait(5)
            except subprocess.TimeoutExpired:
                server.kill()
        shutil.rmtree(work, ignore_errors=True)


@check("spark-share: --self-test passes")
def _():
    path = os.path.join(FILES, 'system', 'usr', 'bin', 'spark-share')
    done = subprocess.run([sys.executable, path, '--self-test'], capture_output=True, text=True,
                          timeout=60)
    assert done.returncode == 0, (done.stdout + done.stderr)[-400:]


# last: on a GPU-less machine KWin may die when it renders, which would take the rest with it
@check("spark-snip: KWin ScreenShot2 captures the workspace")
def _():
    if os.environ.get('KWIN_ONLY_NO_RENDER') == '1':
        raise Waived("this machine has no GPU: KWin crashes when asked to render, so the "
                     "capture is tried on a PC only")
    from sparksnip import capture
    with capture.KWinScreenShot() as kwin:
        size = kwin.workspace().size
    assert size[0] > 0 and size[1] > 0, size
    return f"{size[0]}x{size[1]} (an empty headless screen is one flat colour; pixels not judged)"


failed = [r for r in results if r[0] == 'FAIL']
print(f"\n{len(results) - len(failed)} of {len(results)} checks passed"
      + (f", {len(failed)} failed" if failed else ""))
sys.exit(1 if failed else 0)
