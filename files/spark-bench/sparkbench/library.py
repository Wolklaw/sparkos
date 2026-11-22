"""The recordings: where they are, which game and system each belongs to, what the owner marked
on them (left out, seconds trimmed), the averages per system, and the summary CSV.

Recordings are found in MangoHud's output folder and in any folder added in the app. Windows
PresentMon CSVs are imported by copying them into ~/.local/share/spark-bench/imported/, so they
stay when the drive they came from is gone. The same file found twice (same name and size) is
listed once."""

import csv
import io
import os
import shutil
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from . import core, frames
from .frames import MANGOHUD, PRESENTMON, Recording, Stats

SYSTEM_FOR = {MANGOHUD: 'SparkOS', PRESENTMON: 'Windows'}
STILL_WRITING_S = 5          # a MangoHud CSV with no summary changed this recently is recording
MAX_DEPTH = 3                # how deep added folders are searched


@dataclass
class Run:
    id: str                  # the file name; marks are kept under it
    path: str
    kind: str
    system: str
    program: str
    key: str                 # game key (frames.game_key)
    when: float              # when it was recorded (epoch)
    size: int
    mtime: float
    recording_now: bool = False


def _when(path: str, mtime: float) -> float:
    stamp = frames.stamp_from_name(os.path.basename(path))
    if stamp:
        try:
            return time.mktime(time.strptime(stamp, '%Y-%m-%d %H:%M:%S'))
        except (ValueError, OverflowError):
            pass
    return mtime


def _first_program(path: str) -> str:
    """The Application of the first data row of a PresentMon CSV, without reading it all."""
    try:
        with open(path, encoding='utf-8-sig', errors='replace') as f:
            header = None
            for _ in range(frames.HEADER_LINES):
                line = f.readline()
                if not line:
                    return ''
                cells = [c.strip().strip('"') for c in line.split(',')]
                if header is None and 'MsBetweenPresents' in cells:
                    header = cells
                    break
            if not header or 'Application' not in header:
                return ''
            col = header.index('Application')
            for _ in range(50):
                cells = f.readline().split(',')
                if len(cells) > col and cells[col].strip():
                    return cells[col].strip().strip('"')
    except OSError:
        pass
    return ''


def probe(path: str, system: str = '', now: Optional[float] = None) -> Optional[Run]:
    """A Run for one CSV, from its first lines only; None if it isn't a recording."""
    name = os.path.basename(path)
    if not name.lower().endswith('.csv') or name.endswith('_summary.csv'):
        return None
    kind = frames.sniff(path)
    if kind is None:
        return None
    try:
        st = os.stat(path)
    except OSError:
        return None
    if kind == PRESENTMON:
        program = _first_program(path) or frames.program_from_name(name)
    else:
        program = frames.program_from_name(name)
    summary = path[:-4] + '_summary.csv'
    now = time.time() if now is None else now
    writing = (kind == MANGOHUD and not os.path.exists(summary)
               and now - st.st_mtime < STILL_WRITING_S)
    if program.lower().endswith('.exe'):
        program = program[:-4]
    return Run(id=name, path=path, kind=kind, system=system or SYSTEM_FOR[kind],
               program=program, key=frames.game_key(program), when=_when(path, st.st_mtime),
               size=st.st_size, mtime=st.st_mtime, recording_now=writing)


def _csvs(folder: str, depth: int = MAX_DEPTH):
    try:
        entries = sorted(os.scandir(folder), key=lambda e: e.name)
    except OSError:
        return
    for entry in entries:
        try:
            if entry.is_dir(follow_symlinks=False) and depth > 0:
                yield from _csvs(entry.path, depth - 1)
            elif entry.is_file() and entry.name.lower().endswith('.csv'):
                yield entry.path
        except OSError:
            continue


class Library:
    """Finds the recordings and keeps what the owner marked on them in runs.json."""

    def __init__(self, settings: Dict, output_folder: str):
        self.settings = settings
        self.output_folder = output_folder
        self.extra_watched: List[str] = []      # other output folders MangoHud configs name
        self.runs: List[Run] = []
        self.marks: Dict[str, Dict] = core.read_json(self.marks_path(), {})
        self._cache: Dict[str, Tuple[Tuple, Recording]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def marks_path() -> str:
        return os.path.join(core.config_dir(), 'runs.json')

    def sources(self) -> List[Tuple[str, str]]:
        """(folder, system); an empty system means 'from the file's format'."""
        out = [(self.output_folder, '')] + [(f, '') for f in self.extra_watched]
        out.append((core.imported_dir(), ''))
        for item in self.settings.get('folders', []):
            if isinstance(item, dict) and item.get('path'):
                out.append((item['path'], str(item.get('system') or '')))
        return out

    def scan(self) -> List[Run]:
        """List every recording. Reads only the first lines of each file."""
        seen, runs = set(), []
        for folder, system in self.sources():
            if not folder or not os.path.isdir(folder):
                continue
            depth = 0 if folder == self.output_folder or folder in self.extra_watched \
                else MAX_DEPTH
            for path in _csvs(folder, depth):
                run = probe(path, system)
                if run is None or (run.id, run.size) in seen:
                    continue
                seen.add((run.id, run.size))
                runs.append(run)
        runs.sort(key=lambda r: (r.when, r.id))
        self.runs = runs
        return runs

    # — reading frames (worker threads) —
    def recording(self, run: Run) -> Recording:
        stamp = (run.size, run.mtime)
        with self._lock:
            cached = self._cache.get(run.path)
        if cached and cached[0] == stamp:
            return cached[1]
        rec = frames.read(run.path)
        with self._lock:
            self._cache[run.path] = (stamp, rec)
        return rec

    def stats(self, run: Run) -> Optional[Stats]:
        mark = self.mark(run.id)
        return frames.compute(self.recording(run).frametimes, mark['trim_start'],
                              mark['trim_end'])

    # — marks —
    def mark(self, run_id: str) -> Dict:
        m = self.marks.get(run_id) or {}
        return {'excluded': bool(m.get('excluded', False)),
                'trim_start': float(m.get('trim_start', 0) or 0),
                'trim_end': float(m.get('trim_end', 0) or 0)}

    def set_mark(self, run_id: str, **changes) -> None:
        m = self.mark(run_id)
        m.update(changes)
        if m == {'excluded': False, 'trim_start': 0.0, 'trim_end': 0.0}:
            self.marks.pop(run_id, None)
        else:
            self.marks[run_id] = m
        core.write_json(self.marks_path(), self.marks)

    # — games —
    def game_name(self, key: str) -> str:
        names = self.settings.get('games', {})
        if key in names and names[key].strip():
            return names[key].strip()
        programs = [r.program for r in self.runs if r.key == key]
        # the most readable spelling: the one with capitals or punctuation, if any
        programs.sort(key=lambda p: (p == p.lower(), -len(p)))
        return programs[0] if programs else key

    def rename_game(self, key: str, name: str) -> None:
        """Two games given the same name become one (Windows and Linux can name a game's
        program differently)."""
        names = dict(self.settings.get('games', {}))
        if name.strip():
            names[key] = name.strip()
        else:
            names.pop(key, None)
        self.settings['games'] = names
        core.save_settings(self.settings)

    def groups(self) -> List[Tuple[str, List[Run]]]:
        """(game name, runs) sorted by name; runs oldest first."""
        out: Dict[str, List[Run]] = {}
        for run in self.runs:
            out.setdefault(self.game_name(run.key), []).append(run)
        return sorted(out.items(), key=lambda kv: kv[0].lower())

    def systems(self) -> List[str]:
        found = []
        for run in self.runs:
            if run.system not in found:
                found.append(run.system)
        return found

    # — importing —
    def import_files(self, paths: List[str], system: str = '') -> Tuple[int, List[str]]:
        """Copy recordings into the imported folder. Returns (copied, refused file names)."""
        refused, copied = [], 0
        for path in paths:
            if frames.sniff(path) is None:
                refused.append(os.path.basename(path))
                continue
            sub = core.imported_dir()
            if system:
                sub = os.path.join(sub, _safe(system))
            os.makedirs(sub, exist_ok=True)
            target = os.path.join(sub, os.path.basename(path))
            if os.path.abspath(target) != os.path.abspath(path):
                shutil.copyfile(path, target)
            copied += 1
        if system:
            self.add_folder_label(os.path.join(core.imported_dir(), _safe(system)), system)
        return copied, refused

    def add_folder_label(self, path: str, system: str) -> None:
        folders = [f for f in self.settings.get('folders', [])
                   if isinstance(f, dict) and f.get('path') != path]
        folders.append({'path': path, 'system': system})
        self.settings['folders'] = folders
        core.save_settings(self.settings)

    def add_folder(self, path: str, system: str = '') -> None:
        self.add_folder_label(path, system)

    def remove_folder(self, path: str) -> None:
        self.settings['folders'] = [f for f in self.settings.get('folders', [])
                                    if isinstance(f, dict) and f.get('path') != path]
        core.save_settings(self.settings)


def _safe(name: str) -> str:
    return ''.join(c if c.isalnum() or c in '-_ ' else '_' for c in name).strip() or 'other'


# ─── Comparing systems ────────────────────────────────────────

@dataclass
class Average:
    runs: int
    avg_fps: float
    low1: float
    low01: float


METRICS = ('avg_fps', 'low1', 'low01')


def average(stats: List[Stats]) -> Optional[Average]:
    if not stats:
        return None
    n = len(stats)
    return Average(runs=n, avg_fps=sum(s.avg_fps for s in stats) / n,
                   low1=sum(s.low1 for s in stats) / n, low01=sum(s.low01 for s in stats) / n)


def difference(value: Optional[float], base: Optional[float]) -> Optional[float]:
    """Percent above (+) or below (-) the baseline."""
    if value is None or not base:
        return None
    return (value - base) / base * 100.0


def comparison(lib: Library, stats: Dict[str, Optional[Stats]]
               ) -> List[Tuple[str, Dict[str, Average]]]:
    """Per game, the average of the counted runs of each system. stats: run id -> Stats."""
    out = []
    for game, runs in lib.groups():
        per: Dict[str, List[Stats]] = {}
        for run in runs:
            s = stats.get(run.id)
            if s is None or lib.mark(run.id)['excluded'] or run.recording_now:
                continue
            per.setdefault(run.system, []).append(s)
        averages = {system: average(lst) for system, lst in per.items() if lst}
        if averages:
            out.append((game, averages))
    return out


def summary_csv(lib: Library, stats: Dict[str, Optional[Stats]], baseline: str) -> str:
    """Every run, then each system's average per game with the difference from the baseline.
    Numbers use a decimal point, whatever the PC's language, so spreadsheets read them."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(['Game', 'System', 'Recording', 'Counted', 'TrimStartS', 'TrimEndS', 'Seconds',
                'Frames', 'AvgFPS', 'Low1pctFPS', 'Low01pctFPS', 'WorstFrameMs',
                f'AvgFPSvs{baseline}Pct', f'Low1pctvs{baseline}Pct', f'Low01pctvs{baseline}Pct'])
    for game, runs in lib.groups():
        for run in runs:
            s = stats.get(run.id)
            if s is None:
                continue
            m = lib.mark(run.id)
            w.writerow([game, run.system, run.id, 'no' if m['excluded'] else 'yes',
                        f"{m['trim_start']:g}", f"{m['trim_end']:g}", f"{s.seconds:.1f}",
                        s.frames, f"{s.avg_fps:.1f}", f"{s.low1:.1f}", f"{s.low01:.1f}",
                        f"{s.worst_ms:.1f}", '', '', ''])
    for game, averages in comparison(lib, stats):
        base = averages.get(baseline)
        for system, a in averages.items():
            diffs = ['' if system == baseline or base is None else
                     f"{difference(getattr(a, k), getattr(base, k)):+.1f}" for k in METRICS]
            w.writerow([game, system, f'AVERAGE OF {a.runs}', 'yes', '', '', '', '',
                        f"{a.avg_fps:.1f}", f"{a.low1:.1f}", f"{a.low01:.1f}", ''] + diffs)
    return buf.getvalue()
