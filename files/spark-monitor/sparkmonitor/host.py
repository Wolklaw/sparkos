"""The few programs the Logs and System tabs ask: journalctl, coredumpctl, systemctl,
rpm-ostree, udevadm, vulkaninfo. Everything else comes from /proc and /sys.

Each call has a key. On this PC the key is ignored and the program runs; with test data
(--root) the answer is the file `commands/<key>` under the fake root, so the tests and the
interface work never touch the real journal.

Nothing here runs until a tab that needs it is opened."""

import os
import queue
import shutil
import subprocess
import threading
from typing import Iterator, List, Optional

from .core import log
from .source import Source


class Stream:
    """Lines from a program that keeps running (journalctl -f), read on a thread into a
    bounded queue, so a busy journal can't use more than the queue's size in memory: the
    thread waits when the queue is full, and the program waits on its pipe."""

    def __init__(self, lines: Iterator[str], process: Optional[subprocess.Popen] = None,
                 limit: int = 4000):
        self.queue: "queue.Queue[str]" = queue.Queue(maxsize=limit)
        self.process = process
        self.done = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._read, args=(lines,), daemon=True)
        self._thread.start()

    def _read(self, lines: Iterator[str]) -> None:
        try:
            for line in lines:
                while not self._stop.is_set():
                    try:
                        self.queue.put(line, timeout=0.25)
                        break
                    except queue.Full:
                        continue
                if self._stop.is_set():
                    return
        except (OSError, ValueError):
            pass
        finally:
            self.done = True

    def drain(self, limit: int = 400) -> List[str]:
        out: List[str] = []
        while len(out) < limit:
            try:
                out.append(self.queue.get_nowait())
            except queue.Empty:
                break
        return out

    @property
    def idle(self) -> bool:
        return self.done and self.queue.empty()

    def stop(self) -> None:
        self._stop.set()
        proc = self.process
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except (OSError, subprocess.SubprocessError):
                try:
                    proc.kill()
                except OSError:
                    pass
        if proc is not None and proc.stdout is not None:
            try:
                proc.stdout.close()
            except (OSError, ValueError):
                pass


def _file_lines(path: str) -> Iterator[str]:
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            for line in f:
                yield line
    except OSError:
        return


class Host:
    def __init__(self, src: Source):
        self.src = src

    def _fixture(self, key: str) -> str:
        return os.path.join(self.src.root, 'commands', key)

    def have(self, program: str) -> bool:
        if self.src.fake:
            return True
        return shutil.which(program) is not None

    def run(self, key: str, argv: List[str], timeout: float = 10.0) -> Optional[str]:
        """The program's output, or None if it isn't there, failed with nothing to show, or
        took too long. Output is returned even when the exit code is not 0 (coredumpctl and
        systemctl use codes for 'nothing found')."""
        if self.src.fake:
            try:
                with open(self._fixture(key), encoding='utf-8', errors='replace') as f:
                    return f.read()
            except OSError:
                return None
        try:
            done = subprocess.run(argv, capture_output=True, timeout=timeout, check=False,
                                  stdin=subprocess.DEVNULL,
                                  env={**os.environ, 'LC_ALL': 'C.UTF-8', 'SYSTEMD_COLORS': '0',
                                       'SYSTEMD_PAGER': ''})
        except (OSError, subprocess.SubprocessError) as exc:
            log.info("%s: not run: %s", argv[0], exc)
            return None
        text = done.stdout.decode('utf-8', 'replace')
        if done.returncode != 0 and not text.strip():
            return None
        return text

    def stream(self, key: str, argv: List[str]) -> Optional[Stream]:
        if self.src.fake:
            return Stream(_file_lines(self._fixture(key)))
        if shutil.which(argv[0]) is None:
            return None
        try:
            proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    stdin=subprocess.DEVNULL, text=True, encoding='utf-8',
                                    errors='replace', bufsize=1,
                                    env={**os.environ, 'LC_ALL': 'C.UTF-8',
                                         'SYSTEMD_COLORS': '0', 'SYSTEMD_PAGER': ''})
        except OSError as exc:
            log.info("%s: not started: %s", argv[0], exc)
            return None
        return Stream(iter(proc.stdout.readline, ''), proc)
