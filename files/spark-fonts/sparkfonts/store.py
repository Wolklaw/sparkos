"""Installing and removing fonts for you.

Install copies a file into ~/.local/share/fonts/<Family>/ (never moves your original), after
checking by its content that it is a font Pillow can open. A zip is unpacked safely first.
Remove sends the file to the trash. fc-cache runs on the folder afterwards.

No window code here."""

import hashlib
import os
import re
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from . import core, fcdata, fontfile, trash
from .core import log, run

MAX_ENTRIES = 5000                  # entries in a zip
MAX_FILE = 160 * 1024 * 1024        # one font out of a zip (a big CJK font is about 100 MB)
MAX_TOTAL = 600 * 1024 * 1024       # everything one zip may write
MAX_FOLDER_FILES = 5000


class StoreError(Exception):
    pass


# ─── Zip files ───────────────────────────────────────────────

def _unsafe_name(name: str) -> Optional[str]:
    """The reason an entry's name is refused, or None."""
    if not name or '\x00' in name:
        return 'bad_name'
    flat = name.replace('\\', '/')
    if flat.startswith('/') or re.match(r'^[A-Za-z]:', flat):
        return 'absolute'
    if '..' in flat.split('/'):
        return 'dotdot'
    return None


def extract_zip(path: str, dest: str) -> Tuple[List[str], List[Tuple[str, str]]]:
    """Unpack the fonts of a zip into dest (flat, only files whose first bytes say font).
    Returns (files written, [(entry name, reason)]). Refuses absolute paths, '..', links,
    devices and encrypted entries, and stops at the size limits. Never writes anything that
    isn't a font, and never outside dest."""
    written: List[str] = []
    skipped: List[Tuple[str, str]] = []
    total = 0
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError, NotImplementedError) as exc:
        raise StoreError('bad_zip') from exc
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ENTRIES:
            raise StoreError('too_many')
        for info in infos:
            name = info.filename
            if info.is_dir():
                continue
            reason = _unsafe_name(name)
            mode = info.external_attr >> 16
            if reason is None and info.create_system == 3 and mode:
                kind = stat.S_IFMT(mode)
                if kind not in (0, stat.S_IFREG):
                    reason = 'link' if kind == stat.S_IFLNK else 'special'
            if reason is None and info.flag_bits & 0x1:
                reason = 'encrypted'
            if reason is None and info.file_size > MAX_FILE:
                reason = 'too_big'
            if reason is not None:
                skipped.append((name, reason))
                continue
            try:
                src = zf.open(info)
            except (RuntimeError, NotImplementedError, zipfile.BadZipFile):
                skipped.append((name, 'unreadable'))
                continue
            with src:
                head = src.read(4)
                if fontfile.MAGIC.get(head) is None:
                    skipped.append((name, 'not_font'))
                    continue
                base = re.sub(r'[\x00-\x1f/\\]', '_', os.path.basename(name.replace('\\', '/')))
                target = _free_name(dest, base)
                size = len(head)
                try:
                    with open(target, 'wb') as out:
                        out.write(head)
                        while True:
                            chunk = src.read(1024 * 1024)
                            if not chunk:
                                break
                            size += len(chunk)
                            total += len(chunk)
                            # the header can lie about the size, so count what really comes out
                            if size > MAX_FILE or total > MAX_TOTAL:
                                raise StoreError('too_big')
                            out.write(chunk)
                except (zipfile.BadZipFile, OSError, EOFError, zlib_error()) as exc:
                    log.info("zip entry %s unreadable: %s", name, exc)
                    _unlink(target)
                    skipped.append((name, 'unreadable'))
                    continue
                except StoreError:
                    _unlink(target)
                    raise
            written.append(target)
    return written, skipped


def zlib_error():
    import zlib
    return zlib.error


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _free_name(folder: str, base: str) -> str:
    base = base.lstrip('.') or 'font'
    stem, ext = os.path.splitext(base)
    target, n = os.path.join(folder, base), 1
    while os.path.lexists(target):
        n += 1
        target = os.path.join(folder, f"{stem}-{n}{ext}")
    return target


# ─── What a file holds ───────────────────────────────────────

def identity(path: str) -> List[Tuple[str, str]]:
    """[(family, style)] for each face in a font file, read from the file's own name table
    (the same names fontconfig lists first), or from fc-query when it can't be read."""
    out: List[Tuple[str, str]] = []
    try:
        first = fontfile.read_details(path)
        for i in range(min(first.faces, 128)):
            d = first if i == 0 else fontfile.read_details(path, i)
            if d.family:
                out.append((d.family, d.style or 'Regular'))
    except fontfile.FontError:
        pass
    if not out:
        out = [(f.family, f.style) for f in fcdata.query_file(path) if f.family]
    return out


def folder_name(family: str) -> str:
    name = re.sub(r'[\x00-\x1f/\\:*?"<>|]', '_', family).strip().strip('.')
    return name[:80] or 'Fonts'


def file_digest(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


# ─── Candidates: what an install would do ────────────────────

NEW, SAME, DUPLICATE, SYSTEM, REFUSED = 'new', 'same', 'duplicate', 'system', 'refused'


@dataclass
class Candidate:
    src: str
    name: str                                  # shown: the file's name
    status: str = NEW
    reason: str = ''                           # why REFUSED: not_font, web_font, unreadable...
    family: str = ''
    styles: List[str] = field(default_factory=list)
    kind: str = ''
    replaces: List[str] = field(default_factory=list)    # your files with the same family and style

    @property
    def installable(self) -> bool:
        return self.status in (NEW, DUPLICATE)


def examine(src: str, installed: Sequence[fcdata.Face], name: Optional[str] = None) -> Candidate:
    """Decide what installing one file would do."""
    cand = Candidate(src=src, name=name or os.path.basename(src))
    try:
        cand.kind, _faces = fontfile.check_installable(src)
    except fontfile.FontError as exc:
        text = str(exc)
        cand.status = REFUSED
        cand.reason = text if text in ('not_font', 'web_font') else 'unreadable'
        return cand
    ids = identity(src)
    if not ids:
        cand.status, cand.reason = REFUSED, 'unreadable'
        return cand
    cand.family = ids[0][0]
    cand.styles = [s for _f, s in ids]
    have: Dict[Tuple[str, str], List[fcdata.Face]] = {}
    for face in installed:
        have.setdefault(face.key, []).append(face)
    hits = [face for fam, style in ids for face in have.get((fam.lower(), style.lower()), [])]
    if not hits:
        return cand
    mine = sorted({f.path for f in hits if fcdata.is_user_font(f.path)})
    if not mine:
        cand.status = SYSTEM
        return cand
    try:
        digest = file_digest(src)
        if all(os.path.isfile(p) and file_digest(p) == digest for p in mine) \
                and len(mine) == 1 and len(hits) >= len(ids):
            cand.status = SAME
            return cand
    except OSError:
        pass
    cand.status, cand.replaces = DUPLICATE, mine
    return cand


def gather(paths: Iterable[str], work: str) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    """Every file to look at for the dropped or chosen paths: files as they are, zips
    unpacked into work, folders walked. Returns ([(path, shown name)], [(name, reason)])."""
    files: List[Tuple[str, str]] = []
    problems: List[Tuple[str, str]] = []
    for path in paths:
        path = os.path.abspath(path)
        base = os.path.basename(path)
        if os.path.isdir(path):
            n = 0
            for root, dirs, names in os.walk(path, followlinks=False):
                dirs.sort()
                for name in sorted(names):
                    full = os.path.join(root, name)
                    if os.path.islink(full):
                        continue
                    if name.lower().endswith(fontfile.FONT_EXTENSIONS) or fontfile.sniff(full):
                        n += 1
                        if n > MAX_FOLDER_FILES:
                            problems.append((base, 'too_many'))
                            break
                        files.append((full, name))
            continue
        if not os.path.isfile(path):
            problems.append((base, 'unreadable'))
            continue
        if zipfile.is_zipfile(path):
            folder = tempfile.mkdtemp(prefix='zip-', dir=work)
            try:
                got, skipped = extract_zip(path, folder)
            except StoreError as exc:
                problems.append((base, str(exc)))
                continue
            files += [(p, os.path.basename(p)) for p in got]
            problems += [(f"{base}: {n}", r) for n, r in skipped if r != 'not_font']
            if not got:
                problems.append((base, 'no_fonts'))
            continue
        files.append((path, base))
    return files, problems


def plan(paths: Iterable[str], work: str,
         installed: Optional[Sequence[fcdata.Face]] = None
         ) -> Tuple[List[Candidate], List[Tuple[str, str]]]:
    """What installing these paths would do: a Candidate per font file, and the problems
    (name, reason) for anything that couldn't even be looked at."""
    files, problems = gather(paths, work)
    have = list(installed) if installed is not None else fcdata.list_faces()
    return [examine(path, have, name) for path, name in files], problems


# ─── Install ─────────────────────────────────────────────────

@dataclass
class Outcome:
    installed: List[str] = field(default_factory=list)      # paths written
    replaced: int = 0
    failed: List[Tuple[str, str]] = field(default_factory=list)
    trashed_old: List[str] = field(default_factory=list)


def refresh_cache(folder: Optional[str] = None) -> bool:
    """fc-cache on the folder so every app sees the change. Forced: fontconfig trusts a cache
    made in the same second as the change, and a font installed right after would be missed."""
    code, _out, err = run(['fc-cache', '-f', folder or core.fonts_dir()], timeout=120)
    if code != 0:
        log.warning("fc-cache failed (%s): %s", code, err.strip())
    return code == 0


def install(cands: Sequence[Candidate], replace: bool = False) -> Outcome:
    """Copy each installable candidate into your fonts folder. A DUPLICATE is only taken when
    replace is True (its old files go to the trash first). Refreshes the cache once."""
    out = Outcome()
    root = core.fonts_dir()
    for cand in cands:
        if not cand.installable or (cand.status == DUPLICATE and not replace):
            continue
        try:
            for old in cand.replaces:
                try:
                    trash.trash(old)
                    out.trashed_old.append(old)
                except (trash.NoTrash, OSError) as exc:
                    raise StoreError(f"couldn't trash the old copy: {exc}") from exc
            folder = os.path.join(root, folder_name(cand.family))
            os.makedirs(folder, exist_ok=True)
            base = re.sub(r'[\x00-\x1f/\\]', '_', os.path.basename(cand.src)).lstrip('.')
            target = os.path.join(folder, base or 'font')
            if os.path.lexists(target):
                target = _free_name(folder, os.path.basename(target))
            tmp = target + '.part'
            shutil.copyfile(cand.src, tmp)
            os.chmod(tmp, 0o644)
            os.replace(tmp, target)
            out.installed.append(target)
            if cand.status == DUPLICATE:
                out.replaced += 1
            log.info("installed %s as %s", cand.src, target)
        except (OSError, StoreError) as exc:
            log.warning("install %s failed: %s", cand.src, exc)
            out.failed.append((cand.name, str(exc)))
    if out.installed or out.trashed_old:
        refresh_cache(root)
    return out


# ─── Remove ──────────────────────────────────────────────────

def remove(paths: Iterable[str]) -> Tuple[List[str], List[Tuple[str, str]]]:
    """Trash your font files. Returns (trashed, [(path, reason)]). System fonts are refused
    here too, whatever the window allows."""
    done: List[str] = []
    failed: List[Tuple[str, str]] = []
    for path in sorted(set(paths)):
        reason = fcdata.removal_refusal(path)
        if reason:
            failed.append((path, reason))
            continue
        try:
            trash.trash(path)
            done.append(path)
        except FileNotFoundError:
            done.append(path)
        except (trash.NoTrash, OSError) as exc:
            failed.append((path, str(exc)))
    # empty family folders go too (the trash keeps the font; an empty folder is just clutter)
    for root in core.user_font_roots():
        for base, dirs, _names in os.walk(root, topdown=False):
            if base != root and not os.listdir(base):
                try:
                    os.rmdir(base)
                except OSError:
                    pass
    if done:
        refresh_cache(core.fonts_dir())
    return done, failed
