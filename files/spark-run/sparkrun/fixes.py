"""Known-app fixes: small files an app needs that Wine doesn't give it.

Each fix is keyed on the end of the installed program's Windows path (case ignored), and
creates files next to that program when they are missing. Add an entry to FIXES to fix
another app. They run after an install and before every start, and never overwrite a file.
"""

import os
from typing import Dict, List, NamedTuple, Optional

from . import lnk
from .core import log


class Fix(NamedTuple):
    name: str
    exe: str                       # the end of the program's Windows path, lower case
    files: Dict[str, str]          # file name next to the program -> its content


FIXES = (
    # Amazon Music stops with "No update.ini file found" unless an empty one is there
    Fix('Amazon Music', '\\amazon music\\amazon music.exe', {'update.ini': ''}),
)


def matching(program: str) -> List[Fix]:
    low = program.replace('/', '\\').lower()
    return [fix for fix in FIXES if low.endswith(fix.exe)]


def apply(prefix: str, program: str, unix_program: Optional[str] = None) -> List[str]:
    """Create the missing files for `program` (a Windows path in `prefix`). Returns the
    paths created."""
    found = matching(program)
    if not found:
        return []
    exe = unix_program or lnk.windows_to_unix(prefix, program)
    if not exe:
        return []
    folder = os.path.dirname(exe)
    if not os.path.isdir(folder):
        return []
    made = []
    for fix in found:
        for name, content in fix.files.items():
            path = os.path.join(folder, name)
            if os.path.lexists(path):
                continue
            try:
                with open(path, 'w', encoding='utf-8', newline='') as f:
                    f.write(content)
            except OSError as exc:
                log.warning("fix for %s: could not write %s: %s", fix.name, path, exc)
                continue
            log.info("fix for %s: made %s", fix.name, path)
            made.append(path)
    return made
