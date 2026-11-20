"""CI only: screenshots of the windows under Xvfb, to look at the interface without a desktop.
Uses invented files. Writes PNGs to the folder given (default: screenshots/). Run with
SPARK_LANG=fr for the French interface.

    xvfb-run -a -s "-screen 0 1280x800x24" python3 tests/screenshots.py OUT
"""

import os
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from PIL import ImageGrab  # noqa: E402


def grab(root, path):
    root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    w, h = root.winfo_width(), root.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h), xdisplay=os.environ.get('DISPLAY')).save(path)
    print("wrote", path)


def settle(root, ms):
    import time
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        root.update()
        time.sleep(0.01)


def main():
    out = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else 'screenshots')
    os.makedirs(out, exist_ok=True)
    tmp = tempfile.mkdtemp()
    os.environ['XDG_CACHE_HOME'] = os.path.join(tmp, 'cache')
    os.environ['SPARK_ARCHIVE_REDUCED_MOTION'] = '1'          # still frames, no tear mid-shot
    arc = os.path.join(tmp, 'holiday-photos.zip')
    with zipfile.ZipFile(arc, 'w') as zf:
        for i in range(1, 13):
            zf.writestr(f'holiday-photos/day {i:02d}/IMG_{1000 + i}.jpg', os.urandom(4000 * i))
        zf.writestr('holiday-photos/notes.txt', 'Train at 9:40.\n')
        zf.writestr('holiday-photos/map.pdf', os.urandom(90000))
        zf.writestr('../outside.txt', 'x')

    from sparkarchive.app import App
    app = App(arc)
    app.root.geometry('900x600+0+0')
    settle(app.root, 1500)
    for iid in ('holiday-photos', 'holiday-photos/day 01'):
        app._expand_iid(iid)
        app.table.item(iid, open=True)
    app.table.selection_set(['holiday-photos/day 01/IMG_1001.jpg'])
    app._update_buttons()
    settle(app.root, 300)
    grab(app.root, os.path.join(out, 'window.png'))

    # the overwrite question over the window
    app.root.after(400, lambda: [grab(w, os.path.join(out, 'overwrite.png')) or w.destroy()
                                 for w in app.root.winfo_children()
                                 if w.winfo_class() == 'Toplevel'])
    app.ask_overwrite({'name': 'IMG_1001.jpg', 'path': 'holiday-photos/day 01/IMG_1001.jpg',
                       'new_size': 4000, 'old_size': 3800, 'new_mtime': 1700000000,
                       'old_mtime': 1690000000})
    app.root.after(400, lambda: [grab(w, os.path.join(out, 'password.png')) or w.destroy()
                                 for w in app.root.winfo_children()
                                 if w.winfo_class() == 'Toplevel'])
    app.ask_password('holiday-photos.7z', True)
    app.root.after(400, lambda: [grab(w, os.path.join(out, 'compress.png')) or w.destroy()
                                 for w in app.root.winfo_children()
                                 if w.winfo_class() == 'Toplevel'])
    app.ask_compress(3, '7z', with_password=True)
    app.extract_all()
    settle(app.root, 1500)
    grab(app.root, os.path.join(out, 'extracted.png'))
    app.root.destroy()

    empty = App(None)
    empty.root.geometry('900x600+0+0')
    settle(empty.root, 800)
    grab(empty.root, os.path.join(out, 'empty.png'))
    empty.root.destroy()

    # the Dolphin progress window, held on its progress panel
    from sparkarchive.jobwindow import JobWindow
    from sparkarchive import jobs
    import time
    real_add = jobs.Job._add_bytes

    def slow_add(self, n):                     # screenshots only: a slow disk
        time.sleep(0.03)
        real_add(self, n)
    jobs.Job._add_bytes = slow_add
    big = os.path.join(tmp, 'big.zip')
    with zipfile.ZipFile(big, 'w', zipfile.ZIP_STORED) as zf:
        for i in range(40):
            zf.writestr(f'big/part{i:02d}.bin', os.urandom(3 << 20))
    win = JobWindow('extract-here', [big])
    win.root.geometry('+0+0')
    settle(win.root, 1500)
    if win.job is not None:
        grab(win.root, os.path.join(out, 'progress.png'))
        win.cancel()
    settle(win.root, 1500)
    try:
        grab(win.root, os.path.join(out, 'cancelled.png'))
        win.root.destroy()
    except Exception as exc:                       # it may have closed itself
        print("progress window closed:", exc)


if __name__ == '__main__':
    main()
