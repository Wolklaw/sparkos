"""Write a copy of a font from this system under another family name, so it is a font the system
doesn't have (CI installs it as a real user, checks fc-list, then removes it).

    python3 make_test_font.py OUT.ttf     prints the new family name"""

import os
import sys

# fontkit points HOME at a temporary folder; this only reads the system's fonts
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fontkit  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    src = fontkit.pick_font()
    if not src:
        print("no TrueType or OpenType font on this system", file=sys.stderr)
        return 1
    print(fontkit.rename_family(src, sys.argv[1], 'Zq' + 'x' * 30))
    return 0


if __name__ == '__main__':
    sys.exit(main())
