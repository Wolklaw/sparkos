"""Another app for the drag and drop tests: a separate process with its own Tk and X
connection, speaking XDND through Spark Files' own xdnd module (which is what any X app does).

    python3 xdnd_peer.py target X Y          prints READY, then DROP <paths> when files land
    python3 xdnd_peer.py source X Y PATH     drags PATH to the screen point TX, TY; prints
                                             ACCEPTED/REFUSED and FINISHED
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk  # noqa: E402

from sparkfiles.xdnd import XDnd  # noqa: E402


def main() -> int:
    mode = sys.argv[1]
    root = tk.Tk()
    root.title(f'xdnd peer ({mode})')
    if mode == 'target':
        x, y = int(sys.argv[2]), int(sys.argv[3])
        root.geometry(f'300x300+{x}+{y}')
        root.update()

        def dropped(paths, action, _x, _y):
            print('DROP', action, *paths, flush=True)
            root.after(300, root.destroy)
        d = XDnd(root, lambda *_a: True, lambda: None, dropped)
        if not d.ok:
            print('NO-XDND', flush=True)
            return 1
        d.register(root)
        print('READY', flush=True)
        root.after(20000, root.destroy)
        root.mainloop()
        return 0
    tx, ty, path = int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    root.geometry('100x100+1400+700')            # well away from the target
    root.update()
    d = XDnd(root, lambda *_a: False, lambda: None, lambda *_a: None)
    if not d.ok or not d.drag_start(root, [path]):
        print('NO-XDND', flush=True)
        return 1
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not d.drag_accepted:
        d.drag_motion(tx, ty, 'copy')
        root.update()
        time.sleep(0.05)
    print('ACCEPTED' if d.drag_accepted else 'REFUSED', flush=True)
    d.drag_drop()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and d.drag_paths:
        root.update()                    # answers the target's request for the file list
        time.sleep(0.02)
    print('FINISHED' if not d.drag_paths else 'NO-FINISH', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
