"""Screenshots of Spark Run's windows for the README and the PR, taken in CI under Xvfb.
The apps in them are invented (made-up names, plain colour icons); the windows are real.

    DISPLAY=:99 python3 tests/screenshots.py OUT_DIR
"""

import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else 'shots')
TMP = tempfile.mkdtemp(prefix='spark-run-shots-')
for key in ('XDG_DATA_HOME', 'XDG_CONFIG_HOME', 'XDG_STATE_HOME', 'XDG_CACHE_HOME'):
    os.environ[key] = os.path.join(TMP, key)
os.environ['SPARK_RUN_REDUCED_MOTION'] = '1'
os.environ.pop('SPARK_RUN_WINE', None)

import forge  # noqa: E402
from PIL import Image, ImageGrab  # noqa: E402
from sparkrun import apps, ui  # noqa: E402
from sparkrun.errors import Problem  # noqa: E402


def make_app(slug, name, windows, colour):
    app = apps.App(slug=slug, name=name, program='C:/Program Files/x/x.exe', windows=windows,
                   added='2026-11-20')
    os.makedirs(app.prefix, exist_ok=True)
    app.save()
    Image.new('RGBA', (64, 64), colour).save(os.path.join(app.prefix, 'icon.png'))


def grab(widget, name):
    widget.lift()
    for _ in range(40):
        widget.update()
        time.sleep(0.02)
    x, y = widget.winfo_rootx(), widget.winfo_rooty()
    box = (x, y, x + widget.winfo_width(), y + widget.winfo_height())
    ImageGrab.grab(box, xdisplay=os.environ.get('DISPLAY')).save(os.path.join(OUT, name))
    print('wrote', name)


def main():
    os.makedirs(OUT, exist_ok=True)
    make_app('text-editor', 'Text Editor Pro', 'win10', (140, 200, 90, 255))
    make_app('photo-viewer', 'Photo Viewer 64', 'win7', (220, 90, 70, 255))
    make_app('music-tagger', 'Music Tagger', 'win10', (70, 130, 220, 255))

    w = ui.Window()
    grab(w.root, '1-list.png')
    w.root.destroy()

    exe = os.path.join(TMP, 'texteditor-8.6-setup-x64.exe')
    with open(exe, 'wb') as f:
        f.write(forge.pe(strings={'ProductName': 'Text Editor Pro', 'CompanyName': 'Example Co',
                                  'ProductVersion': '8.6.2'},
                         manifest=b'Nullsoft.NSIS.exehead'))
    w = ui.Window(file=exe)
    grab(w.root, '2-chooser.png')
    w._progress_view()
    w.on_report('setup', size=0, names='')
    w.on_report('progress.wine.download', done=40 << 20, total=94 << 20)
    grab(w.root, '3-downloading.png')
    w.root.destroy()

    w = ui.Window(error=('setup.exe', Problem('error.vc_runtime', {'dll': 'MSVCP140.dll'}), '',
                         False))
    grab(w.root, '4-error.png')
    w.root.destroy()

    w = ui.Window()
    dialog = ui.OptionsDialog(w, w.apps[0])
    grab(dialog, '5-options.png')
    w.root.destroy()


if __name__ == '__main__':
    main()
