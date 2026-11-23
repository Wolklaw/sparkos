"""About: the SparkOS version and image, the hardware, and the text for bug reports."""

import os
import platform
import re
from typing import Dict, List, Tuple

from .core import out, run


def os_release() -> Dict[str, str]:
    info: Dict[str, str] = {}
    path = os.environ.get('SPARK_SETTINGS_OS_RELEASE', '/etc/os-release')
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    k, v = line.strip().split('=', 1)
                    info[k] = v.strip('"')
    except OSError:
        pass
    return info


def image() -> str:
    """The image this PC booted: rpm-ostree's origin, e.g. ostree-image-signed:docker://ghcr.io/..."""
    text = out(['rpm-ostree', 'status', '--booted'], timeout=15)
    m = re.search(r'^\s*(?:●\s*)?(ostree[^\s]*:\S+|\S*ghcr\.io\S+)', text, re.M)
    return m.group(1) if m else ''


def cpu() -> str:
    try:
        with open('/proc/cpuinfo', encoding='utf-8', errors='replace') as f:
            m = re.search(r'^model name\s*:\s*(.+)$', f.read(), re.M)
        return re.sub(r'\s+', ' ', m.group(1)) if m else platform.processor()
    except OSError:
        return platform.processor()


def memory() -> str:
    try:
        with open('/proc/meminfo', encoding='utf-8') as f:
            kb = int(re.search(r'MemTotal:\s*(\d+)', f.read()).group(1))
        return f"{kb / 1048576:.1f} GB"
    except (OSError, AttributeError, ValueError):
        return ''


def gpus() -> List[str]:
    text = out(['lspci', '-mm'], timeout=10)
    names = []
    for line in text.splitlines():
        if re.search(r'"(VGA compatible controller|3D controller|Display controller)"', line):
            parts = re.findall(r'"([^"]*)"', line)
            if len(parts) >= 4:
                names.append(f"{parts[2]} {parts[3]}")
    return names


def rows() -> List[Tuple[str, str]]:
    rel = os_release()
    data = [("SparkOS", rel.get('PRETTY_NAME') or rel.get('NAME', 'SparkOS')),
            ("Version", rel.get('VERSION_ID', '')),
            ("Kernel", platform.release()),
            ("Image", image()),
            ("Processor", cpu()),
            ("Memory", memory())]
    for i, g in enumerate(gpus()):
        data.append(("Graphics" if i == 0 else "Graphics " + str(i + 1), g))
    return [(k, v) for k, v in data if v]


def report(rows_: List[Tuple[str, str]], version: str) -> str:
    lines = [f"Spark Settings {version}"] + [f"{k}: {v}" for k, v in rows_]
    return '\n'.join(lines) + '\n'
