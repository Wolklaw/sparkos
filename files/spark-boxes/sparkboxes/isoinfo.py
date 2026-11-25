"""Read an ISO 9660 image's volume label (the primary volume descriptor, sector 16) and guess
which kind of system it installs. Pure Python; no isoinfo."""

import os
from typing import Optional

PVD_OFFSET = 16 * 2048
LABEL_AT, LABEL_LEN = PVD_OFFSET + 40, 32          # byte 32808, 32 bytes
PRESETS = ('win11', 'win10', 'linux', 'other')

# Microsoft's own media labels say little ("CCCOMA_X64FRE_EN-US_DV9"), so the label is only a
# hint: the window lets the person change the preset.
LINUX_WORDS = ('fedora', 'ubuntu', 'debian', 'arch', 'linux', 'mint', 'opensuse', 'suse',
               'manjaro', 'kinoite', 'silverblue', 'bazzite', 'nixos', 'alpine', 'gentoo',
               'pop_os', 'pop-os', 'endeavour', 'rocky', 'almalinux', 'centos', 'rhel',
               'kali', 'tails', 'elementary', 'zorin', 'sparkos', 'void', 'slackware',
               'knoppix', 'parrot', 'sysresccd', 'gparted', 'clonezilla')
MICROSOFT_LABELS = ('CCCOMA', 'CCSA', 'CENA', 'CPBA', 'CCSNA', 'CCCOMA')


def volume_label(path: str) -> Optional[str]:
    """The ISO's volume label, or None when the file is not an ISO 9660 image."""
    try:
        with open(path, 'rb') as f:
            f.seek(PVD_OFFSET)
            if f.read(7) != b'\x01CD001\x01':
                return None
            f.seek(LABEL_AT)
            raw = f.read(LABEL_LEN)
    except OSError:
        return None
    return raw.decode('ascii', 'replace').strip()


def guess_preset(label: Optional[str], filename: str = '') -> str:
    """'win11', 'win10', 'linux' or 'other' from the volume label and the file name."""
    text = f"{label or ''} {os.path.basename(filename)}".lower()
    squashed = text.replace('_', '').replace('-', '').replace(' ', '')
    if 'win11' in squashed or 'windows11' in squashed:
        return 'win11'
    if 'win10' in squashed or 'windows10' in squashed:
        return 'win10'
    if (label or '').upper().startswith(MICROSOFT_LABELS) or 'windows' in text:
        # the label does not say 10 or 11: offer the newer one; Windows 10 is one click away
        return 'win11'
    if any(word in text for word in LINUX_WORDS):
        return 'linux'
    return 'other'
