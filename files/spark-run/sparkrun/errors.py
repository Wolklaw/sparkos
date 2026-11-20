"""Turn what Wine printed into one plain sentence. Never a stack trace: the details stay in
the log (~/.local/state/spark-run/<app>.log) for whoever wants them."""

import re
from dataclasses import dataclass, field
from typing import Dict, Optional

from .pe import PEInfo

MISSING_DLL = re.compile(
    r'(?:err:module:import_dll (?:Library|Loading library) |'
    r'err:module:find_forwarded_export .*? |'
    r'cannot find |could not load )'
    r'L?"?([\w.+-]+\.dll)', re.I)
VC_RUNTIME = re.compile(r'(?i)^(msvcp\d+|vcruntime\d+|msvcr\d+|concrt\d+|mfc\d+u?|'
                        r'vcomp\d+|ucrtbased|api-ms-win-crt-.*)\.dll$')
DOTNET = re.compile(r'(?i)^(mscoree|mscorlib|clr|coreclr|hostfxr)\.dll$')


@dataclass
class Problem:
    key: str                      # a text.py key: 'error.<kind>'
    values: Dict[str, str] = field(default_factory=dict)


def before_running(info: PEInfo) -> Optional[Problem]:
    """Problems known from the file alone, said before Wine is even started."""
    if info.kind == 'dos':
        return Problem('error.dos')
    if info.kind == 'other':
        return Problem('error.not_windows')
    if info.kind == 'pe' and info.machine in ('arm', 'arm64'):
        return Problem('error.arm')
    if info.kind == 'pe' and info.machine not in ('x86', 'x64'):
        return Problem('error.not_windows')
    return None


def after_exit(code: Optional[int], output: str, has_mono: bool = True) -> Optional[Problem]:
    """A problem if the program ended in a way that needs explaining. code None: still
    running (only the output is looked at)."""
    text = output[-200_000:]
    if 'Bad EXE format' in text or 'is not a valid Win32 application' in text:
        return Problem('error.not_windows')
    match = MISSING_DLL.search(text)
    if match and (code not in (None, 0) or 'import_dll' in match.group(0)):
        dll = match.group(1)
        if VC_RUNTIME.match(dll):
            return Problem('error.vc_runtime', {'dll': dll})
        if DOTNET.match(dll):
            return Problem('error.dotnet' if has_mono else 'error.no_mono', {'dll': dll})
        return Problem('error.missing_dll', {'dll': dll})
    if re.search(r'(?i)wine: cannot find|file not found|could not find the file', text) and \
            code not in (None, 0):
        return Problem('error.not_found')
    if re.search(r'wine: Unhandled (page fault|exception)|Unhandled exception: ', text):
        return Problem('error.crashed')
    if re.search(r'(?i)(failed to|could not) (open|connect to) (the )?display|'
                 r'no driver could be loaded', text) and code not in (None, 0):
        return Problem('error.display')
    if re.search(r'(?i)libvulkan|vkCreateInstance failed|vulkan.*not supported', text) and \
            code not in (None, 0):
        return Problem('error.vulkan')
    if code not in (None, 0) and code < 0:
        return Problem('error.killed', {'code': str(code)})
    return None
