"""File dialogs with tkinter.filedialog's names and arguments, answered by spark-pick (Spark Files'
picker, through the desktop portal) when it is installed, and by Tk's own dialog otherwise or
when there is no portal to ask. Use it as: from . import pickdialog as filedialog"""

import os
import shutil
import subprocess
from typing import List, Optional, Sequence, Tuple

CANCELLED, NO_PORTAL = 1, 2


def _filter(filetypes: Sequence[Tuple[str, str]]) -> str:
    """Tk filetypes -> spark-pick's one-filter-per-line text; the catch-all "*" entry is dropped."""
    lines = []
    for label, patterns in filetypes or ():
        globs = patterns.split() if isinstance(patterns, str) else list(patterns)
        if globs and globs != ['*']:
            lines.append(f"{' '.join(globs)}|{label}")
    return '\n'.join(lines)


def _ask(args: List[str], title: str) -> Optional[List[str]]:
    """Paths picked with spark-pick, [] if cancelled, None if it can't be asked (use Tk)."""
    exe = shutil.which('spark-pick')
    if not exe or os.name == 'nt':
        return None
    try:
        res = subprocess.run([exe, *args, '--title', title or 'Open'],
                             capture_output=True, text=True)
    except OSError:
        return None
    if res.returncode == NO_PORTAL:
        return None
    return [line for line in res.stdout.splitlines() if line.strip()]


def _start(kw: dict) -> str:
    return os.path.expanduser(kw.get('initialdir') or '~')


def askopenfilename(**kw) -> str:
    args = ['--getopenfilename', _start(kw)]
    flt = _filter(kw.get('filetypes', ()))
    if flt:
        args.append(flt)
    got = _ask(args, kw.get('title', ''))
    if got is None:
        from tkinter import filedialog
        return filedialog.askopenfilename(**kw)
    return got[0] if got else ''


def askopenfilenames(**kw) -> Tuple[str, ...]:
    args = ['--getopenfilename', _start(kw)]
    flt = _filter(kw.get('filetypes', ()))
    if flt:
        args.append(flt)
    got = _ask(args + ['--multiple', '--separate-output'], kw.get('title', ''))
    if got is None:
        from tkinter import filedialog
        return tuple(filedialog.askopenfilenames(**kw))
    return tuple(got)


def askdirectory(**kw) -> str:
    got = _ask(['--getexistingdirectory', _start(kw)], kw.get('title', ''))
    if got is None:
        from tkinter import filedialog
        return filedialog.askdirectory(**kw)
    return got[0] if got else ''


def asksaveasfilename(**kw) -> str:
    name = kw.get('initialfile') or ''
    args = ['--getsavefilename', os.path.join(_start(kw), name)]
    flt = _filter(kw.get('filetypes', ()))
    if flt:
        args.append(flt)
    got = _ask(args, kw.get('title', ''))
    if got is None:
        from tkinter import filedialog
        return filedialog.asksaveasfilename(**kw)
    path = got[0] if got else ''
    ext = kw.get('defaultextension') or ''
    if path and ext and not os.path.splitext(path)[1]:
        path += ext
    return path
