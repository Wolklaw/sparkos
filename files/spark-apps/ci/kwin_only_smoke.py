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
import os
import shutil
import subprocess
import sys
import tempfile

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


@check("spark-files: FUSE mount with rclone works without plasmashell")
def _():
    need('rclone')
    need('fusermount3')
    from sparkfiles import network
    folder = tempfile.mkdtemp(prefix='kwin-only-share-')
    point = tempfile.mkdtemp(prefix='kwin-only-mount-')
    try:
        with open(os.path.join(folder, 'a.txt'), 'w') as f:
            f.write('hi')
        rc = network.Rclone(conf=os.path.join(folder, 'rclone.conf'))
        done = subprocess.run(rc.argv(':local:' + folder, point, 20), capture_output=True,
                              text=True, timeout=30, stdin=subprocess.DEVNULL)
        assert done.returncode == 0, done.stderr[-300:]
        assert os.path.isfile(os.path.join(point, 'a.txt')), os.listdir(point)
        return "rclone mounted a folder (smb and Google Drive use the same mount)"
    finally:
        subprocess.run(['fusermount3', '-u', '-z', point], capture_output=True)
        shutil.rmtree(folder, ignore_errors=True)
        os.rmdir(point) if os.path.isdir(point) and not os.listdir(point) else None


@check("spark-files: sftp goes to sshfs, smb and Google Drive to rclone (no KIO)")
def _():
    from sparkfiles import network
    assert isinstance(network.choose_backend(network.Server('sftp', 'h')), network.SshFs)
    assert isinstance(network.choose_backend(network.Server('smb', 'h')), network.Rclone)
    assert isinstance(network.choose_backend(network.RawUrl(network.GDRIVE_URL)), network.Rclone)
    assert not hasattr(network, 'KioFuse')


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
