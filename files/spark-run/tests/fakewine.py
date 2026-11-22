"""A stand-in for Wine in the unit tests: `wine` and `wineserver` scripts that act out what
Spark Run asks of them (wineboot makes a prefix, a fake installer installs a fake program with
Start Menu shortcuts, programs write where they ran), so the install flow can be tested
without Wine, a display or a network. The real thing is tested in CI (tests/ci_wine.sh).

    fakewine.make(folder) -> a Wine root to put in SPARK_RUN_WINE

Installers are recognised by name: fake-setup*.exe installs "Fake App"; fake-multi-setup*.exe
also installs "Fake Tool"; fake-empty-setup*.exe installs nothing; fake-fail-setup*.exe exits 2.
Programs named fake-crash*.exe and fake-dll*.exe fail the way Wine prints those failures.
Any other program appends "ran <path> <args>" to $FAKEWINE_OUT.
"""

import os
import stat
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def make(folder: str) -> str:
    bindir = os.path.join(folder, 'bin')
    os.makedirs(bindir, exist_ok=True)
    for name in ('wine', 'wineserver'):
        path = os.path.join(bindir, name)
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(f'#!/bin/sh\nexec "{sys.executable}" "{os.path.abspath(__file__)}" '
                    f'{name} "$@"\n')
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.makedirs(os.path.join(folder, 'share', 'wine', 'mono', 'wine-mono-11.3.0'),
                exist_ok=True)
    return folder


def _prefix() -> str:
    return os.environ['WINEPREFIX']


def _drive_c() -> str:
    return os.path.join(_prefix(), 'drive_c')


def _write(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


def wineboot() -> int:
    drive_c = _drive_c()
    user = os.environ.get('USER') or 'user'
    for sub in ('windows/system32', 'windows/syswow64', 'Program Files/Internet Explorer',
                'ProgramData/Microsoft/Windows/Start Menu/Programs',
                f'users/{user}/AppData/Roaming/Microsoft/Windows/Start Menu/Programs'):
        os.makedirs(os.path.join(drive_c, sub), exist_ok=True)
    _write(os.path.join(drive_c, 'Program Files/Internet Explorer/iexplore.exe'),
           forge.pe(strings={'ProductName': 'Wine Internet Explorer'}))
    real_desktop = os.path.join(_prefix(), 'fake-home-desktop')
    os.makedirs(real_desktop, exist_ok=True)
    desktop = os.path.join(drive_c, 'users', user, 'Desktop')
    if not os.path.lexists(desktop):
        os.symlink(real_desktop, desktop)
    dosdevices = os.path.join(_prefix(), 'dosdevices')
    os.makedirs(dosdevices, exist_ok=True)
    if not os.path.lexists(os.path.join(dosdevices, 'c:')):
        os.symlink('../drive_c', os.path.join(dosdevices, 'c:'))
    _write(os.path.join(_prefix(), 'system.reg'), b'WINE REGISTRY Version 2\n')
    return 0


def install(path: str) -> int:
    name = path.replace(chr(92), '/').rsplit('/', 1)[-1].lower()     # C:\... or /...
    if name.startswith('fake-fail-setup'):
        print("installer: something went wrong", file=sys.stderr)
        return 2
    if name.startswith('fake-empty-setup'):
        return 0
    drive_c = _drive_c()
    menu = os.path.join(drive_c, 'ProgramData/Microsoft/Windows/Start Menu/Programs')
    programs = [('Fake App', 'fakeapp.exe', 'Fake App')]
    if name.startswith('fake-multi-setup'):
        programs.append(('Fake App', 'faketool.exe', 'Fake Tool'))
    for folder, exe, title in programs:
        target = f'C:\\Program Files\\{folder}\\{exe}'
        _write(os.path.join(drive_c, 'Program Files', folder, exe),
               forge.pe(strings={'ProductName': title, 'CompanyName': 'Fake Co',
                                 'FileDescription': title, 'ProductVersion': '1.2.3'}))
        _write(os.path.join(menu, 'Fake App', title + '.lnk'), forge.lnk(target, title))
    _write(os.path.join(drive_c, 'Program Files/Fake App/uninstall.exe'), forge.pe())
    _write(os.path.join(menu, 'Fake App', 'Uninstall Fake App.lnk'),
           forge.lnk('C:\\Program Files\\Fake App\\uninstall.exe', 'Uninstall'))
    _write(os.path.join(drive_c, 'users', os.environ.get('USER') or 'user', 'Desktop',
                        'Fake App.lnk'),
           forge.lnk('C:\\Program Files\\Fake App\\fakeapp.exe', 'Fake App'))
    return 0


def run(path: str, args) -> int:
    name = os.path.basename(path).lower()
    if name.startswith('fake-crash'):
        print("wine: Unhandled page fault on read access to 00000000 at address 0040100A")
        return 1
    if name.startswith('fake-dll'):
        print("0024:err:module:import_dll Library MSVCP140.dll (which is needed by "
              f"L\"{path}\") not found")
        return 53
    if 'setup' in name:
        return install(path)
    out = os.environ.get('FAKEWINE_OUT')
    if out:
        with open(out, 'a', encoding='utf-8') as f:
            f.write(' '.join(['ran', path] + list(args)) + '\n')
    return 0


def main(argv) -> int:
    tool, args = argv[0], argv[1:]
    log = os.environ.get('FAKEWINE_LOG')
    if log:
        with open(log, 'a', encoding='utf-8') as f:
            f.write(' '.join([tool] + args) + f'  [{os.environ.get("WINEPREFIX")}]'
                    f'  [{os.environ.get("WINEDLLOVERRIDES")}]\n')
    if tool == 'wineserver':
        return 0
    if not args:
        return 1
    if args[0] == '--version':
        print('wine-11.22 (fake)')
        return 0
    if args[0] == 'wineboot':
        return wineboot()
    if args[0] == 'reg':
        if args[1:2] == ['query']:
            print('    Version    REG_SZ    win10')
        return 0
    if args[0] == 'msiexec':
        return install(args[2])
    return run(args[0], args[1:])


if __name__ == '__main__':
    sys.path.insert(0, HERE)
    import forge  # noqa: E402
    sys.exit(main(sys.argv[1:]))
