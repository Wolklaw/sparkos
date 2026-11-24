"""Running commands. Everything that talks to btrfs, rsync, mount or lsblk goes through a
Runner, so the tests can swap in a fake one and never touch a disk."""

import subprocess
import tempfile
from typing import NamedTuple, Optional, Sequence, Tuple


class Result(NamedTuple):
    code: int
    out: str = ""
    err: str = ""

    @property
    def ok(self) -> bool:
        return self.code == 0

    def message(self) -> str:
        lines = [x for x in (self.err or self.out).strip().splitlines() if x.strip()]
        return lines[-1] if lines else f"exit {self.code}"


class Runner:
    def run(self, argv: Sequence[str], input: Optional[str] = None,
            timeout: Optional[float] = None) -> Result:
        try:
            done = subprocess.run(list(argv), input=input, capture_output=True, text=True,
                                  errors="replace", timeout=timeout)
            return Result(done.returncode, done.stdout, done.stderr)
        except FileNotFoundError:
            return Result(127, "", f"{argv[0]}: not found")
        except subprocess.TimeoutExpired:
            return Result(124, "", f"{argv[0]}: timed out")
        except OSError as exc:
            return Result(126, "", f"{argv[0]}: {exc}")

    def pipe(self, first: Sequence[str], second: Sequence[str]) -> Tuple[Result, Result]:
        """first | second (btrfs send into btrfs receive). Stderr goes to temporary files so a
        chatty command can never fill a pipe and stall the other one."""
        with tempfile.TemporaryFile() as err1, tempfile.TemporaryFile() as err2:
            try:
                p1 = subprocess.Popen(list(first), stdout=subprocess.PIPE, stderr=err1)
            except OSError as exc:
                return Result(127, "", f"{first[0]}: {exc}"), Result(1, "", "not started")
            try:
                p2 = subprocess.Popen(list(second), stdin=p1.stdout, stdout=subprocess.PIPE,
                                      stderr=err2)
            except OSError as exc:
                p1.kill()
                p1.wait()
                return Result(1, "", "not started"), Result(127, "", f"{second[0]}: {exc}")
            assert p1.stdout is not None
            p1.stdout.close()
            out2 = p2.communicate()[0]
            p1.wait()
            err1.seek(0)
            err2.seek(0)
            return (Result(p1.returncode, "", err1.read().decode("utf-8", "replace")),
                    Result(p2.returncode, out2.decode("utf-8", "replace"),
                           err2.read().decode("utf-8", "replace")))
