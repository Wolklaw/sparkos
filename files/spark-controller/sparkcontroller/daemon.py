"""spark-controller-daemon: applies fan curves.

Runs as a system service (root, because writing pwm needs it). Every two seconds it reads the
temperatures, works out each enabled fan's duty with the smoothing in curve.py, and writes it.

Safety, in order of importance:
  - A fan only gets controlled when its entry in the configuration is enabled. By default the
    daemon touches nothing.
  - Before the first write to a fan it saves the mode that fan was in (pwmN_enable) in
    /run/spark-controller/originals.json. When the daemon stops, for any reason, that mode is
    written back. systemd runs `spark-controller-daemon --release` after the service stops, so
    this also happens after a crash or a kill, and the next start releases leftovers too.
  - A temperature that can't be read sends the fan to its fail-safe speed, never holds a guess.
  - A broken configuration file keeps the last good one in use.
"""

import json
import os
import signal
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from . import APP_NAME, RUN_DIR, VERSION, config
from .curve import FanController
from .hwmon import MANUAL, Hwmon
from .liquid import LiquidHub
from .log import log, setup_logging

INTERVAL_S = 2.0
RESCAN_S = 60.0           # look for fans that appeared (a USB device plugged in)
MAX_DT = 10.0             # after a suspend, don't pretend that much time passed


class Daemon:
    def __init__(self, hwmon: Hwmon, hub: Optional[LiquidHub] = None, config_file: str = "",
                 run_dir: str = RUN_DIR, clock: Callable[[], float] = time.monotonic):
        self.hwmon, self.hub = hwmon, hub
        self.config_file = config_file or config.config_path()
        self.run_dir = run_dir
        self.clock = clock
        self.config: Dict[str, Any] = config.empty()
        self.config_stamp: Optional[tuple] = None
        self.fans: Dict[str, Any] = {}
        self.controllers: Dict[str, FanController] = {}
        self.entries: Dict[str, Dict[str, Any]] = {}
        self.originals: Dict[str, Optional[int]] = {}
        self.failed: Dict[str, str] = {}
        self.last: Optional[float] = None
        self.last_scan = -RESCAN_S
        self.stop = False
        self._wake = threading.Event()    # set by request_stop(); run() sleeps on it

    # — files —
    @property
    def originals_path(self) -> str:
        return os.path.join(self.run_dir, "originals.json")

    @property
    def state_path(self) -> str:
        return os.path.join(self.run_dir, "state.json")

    def _write_json(self, path: str, data: Dict[str, Any]) -> None:
        try:
            os.makedirs(self.run_dir, exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.chmod(tmp, 0o644)
            os.replace(tmp, path)
        except OSError as exc:
            log.warning("can't write %s: %s", path, exc)

    def _stamp(self) -> Optional[tuple]:
        try:
            st = os.stat(self.config_file)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def reload(self, force: bool = False) -> bool:
        stamp = self._stamp()
        if not force and stamp == self.config_stamp:
            return False
        self.config_stamp = stamp
        try:
            self.config = config.load(self.config_file)
            log.info("configuration loaded: %d fan(s) set", len(self.config["fans"]))
        except (config.ConfigError, OSError) as exc:
            log.error("configuration not used (%s); keeping the last good one", exc)
        return True

    def scan(self, now: float) -> None:
        if now - self.last_scan < RESCAN_S and self.fans:
            return
        self.last_scan = now
        fans: Dict[str, Any] = {f.key: f for f in self.hwmon.fans() if f.controllable}
        if self.hub is not None:
            for fan in self.hub.fans():
                fans[fan.key] = fan
        # keep the objects we already hold (a liquidctl fan owns an open handle)
        for key, fan in fans.items():
            if key not in self.fans or fan.kind == "hwmon":
                self.fans[key] = fan
        for key in list(self.fans):
            if key not in fans:
                self.originals.pop(key, None)
                del self.fans[key]

    # — taking over and handing back —
    def _take(self, fan: Any) -> bool:
        try:
            original = fan.takeover()
            if fan.key not in self.originals:
                self.originals[fan.key] = original
                self._write_json(self.originals_path, self.originals)
            return True
        except Exception as exc:
            self._fail(fan.key, f"can't take over: {exc}")
            return False

    def _fail(self, key: str, message: str) -> None:
        if self.failed.get(key) != message:
            log.error("%s: %s", key, message)
        self.failed[key] = message

    def _give_back(self, key: str) -> None:
        fan = self.fans.get(key)
        if key in self.originals and fan is not None:
            try:
                fan.release(self.originals[key])
                log.info("%s: handed back", key)
            except Exception as exc:
                log.error("%s: could not hand back: %s", key, exc)
        self.originals.pop(key, None)
        self.controllers.pop(key, None)
        self.entries.pop(key, None)

    def release_all(self) -> None:
        for key in list(self.originals):
            self._give_back(key)
        self._write_json(self.originals_path, self.originals)

    def release_leftovers(self) -> None:
        """A previous run died holding fans: put them back before doing anything else."""
        try:
            with open(self.originals_path, encoding="utf-8") as f:
                leftovers = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(leftovers, dict) or not leftovers:
            return
        self.scan(self.clock())
        for key, original in leftovers.items():
            fan = self.fans.get(key)
            if fan is not None and (original is None or isinstance(original, int)):
                try:
                    fan.release(original)
                    log.info("%s: released after an earlier run stopped", key)
                except Exception as exc:
                    log.error("%s: could not release: %s", key, exc)
        self._write_json(self.originals_path, {})

    # — one step —
    def temps(self, need_liquid: bool) -> Dict[str, Optional[float]]:
        values = self.hwmon.source_temps()
        values["liquid"] = None
        if self.hub is not None and need_liquid:
            self.hub.refresh()
            values["liquid"] = self.hub.liquid_temp()
        return values

    def step(self) -> Dict[str, Any]:
        now = self.clock()
        dt = 0.0 if self.last is None else min(MAX_DT, max(0.0, now - self.last))
        self.last = now
        self.reload()
        self.scan(now)
        wanted = {k: e for k, e in self.config["fans"].items()
                  if e["enabled"] and k in self.fans}
        # fans that were set and aren't any more
        for key in list(self.originals):
            if key not in wanted:
                self._give_back(key)
        liquid_needed = any(e["source"] == "liquid" for e in wanted.values()) \
            or any(self.fans[k].kind == "liquidctl" for k in wanted)
        temps = self.temps(liquid_needed)
        report: Dict[str, Any] = {}
        for key, entry in wanted.items():
            fan = self.fans[key]
            if self.entries.get(key) != entry:
                previous = self.controllers.get(key)
                controller = config.controller_for(entry)
                if previous is not None and previous.duty is not None:
                    controller.duty = previous.duty          # no jump when a curve is edited
                self.controllers[key], self.entries[key] = controller, entry
            controller = self.controllers[key]
            temp = temps.get(entry["source"])
            duty = controller.update(temp, dt)
            if key not in self.originals:
                if not self._take(fan):
                    continue
            elif fan.kind == "hwmon" and fan.mode() != MANUAL:
                try:
                    fan.takeover()                           # firmware took it back (resume)
                except OSError as exc:
                    self._fail(key, f"can't keep control: {exc}")
                    continue
            try:
                fan.set_duty(duty)
                self.failed.pop(key, None)
            except Exception as exc:
                self._fail(key, f"can't write: {exc}")
                continue
            report[key] = {"duty": duty, "temp": None if temp is None else round(temp, 1),
                           "source": entry["source"], "target": round(controller.target())}
        self._write_state(report, temps)
        return report

    def _write_state(self, report: Dict[str, Any], temps: Dict[str, Optional[float]]) -> None:
        self._write_json(self.state_path, {
            "version": 1, "pid": os.getpid(), "time": time.time(), "fans": report,
            "temps": {k: v for k, v in temps.items()}, "errors": dict(self.failed),
        })

    # — running —
    def request_stop(self) -> None:
        """Ask run() to finish; safe from a signal handler. Wakes the sleep at once."""
        self.stop = True
        self._wake.set()

    def run(self) -> None:
        self.release_leftovers()
        self.reload(force=True)
        log.info("%s %s running", APP_NAME, VERSION)
        try:
            while not self.stop:
                try:
                    self.step()
                except Exception:
                    log.exception("step failed")
                # One sleep per step (it used to wake four times a second to check `stop`).
                self._wake.wait(INTERVAL_S)
        finally:
            self.release_all()
            if self.hub is not None:
                self.hub.close()
            log.info("stopped, fans handed back")


def self_test(hwmon: Hwmon, hub: Optional[LiquidHub]) -> int:
    fans = hwmon.fans()
    print(f"{APP_NAME} daemon {VERSION} self-test")
    print(f"hwmon:     {len(hwmon.chips())} chips, {len(fans)} fans, "
          f"{sum(1 for f in fans if f.controllable)} with pwm control")
    cpu, gpu = hwmon.cpu_sensor(), hwmon.gpu_sensor()
    print(f"cpu temp:  {cpu.label if cpu else 'none found'}")
    print(f"gpu temp:  {gpu.label if gpu else 'none found'}")
    print(f"liquidctl: {len(hub.devices) if hub else 0} devices"
          f"{' (' + hub.error + ')' if hub and hub.error else ''}")
    try:
        config.load(config.config_path())
        print(f"config:    {config.config_path()} ok")
    except config.ConfigError as exc:
        print(f"config:    {config.config_path()} BROKEN: {exc}")
        return 1
    print("self-test passed")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--version" in argv:
        print(f"spark-controller-daemon {VERSION}")
        return 0
    # a SIGHUP during start-up must not end the daemon; run() reads the file anyway
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    setup_logging(to_file=False)
    run_dir = os.environ.get("SPARK_CONTROLLER_RUN_DIR") or RUN_DIR
    root = os.environ.get("SPARK_CONTROLLER_HWMON") or "/sys/class/hwmon"
    hwmon = Hwmon(root)
    no_usb = "--no-usb" in argv or os.environ.get("SPARK_CONTROLLER_NO_USB") == "1"
    hub = None if no_usb else LiquidHub()
    daemon = Daemon(hwmon, hub, run_dir=run_dir)
    if "--self-test" in argv:
        return self_test(hwmon, hub)
    if "--release" in argv:
        # after the service stopped: put back anything a crash left behind
        daemon.release_leftovers()
        return 0
    if "--once" in argv:
        daemon.release_leftovers()
        # one step to show what it would do, then hand everything back
        try:
            print(json.dumps(daemon.step(), indent=2))
        finally:
            daemon.release_all()
        return 0
    signal.signal(signal.SIGTERM, lambda *_: daemon.request_stop())
    signal.signal(signal.SIGINT, lambda *_: daemon.request_stop())
    signal.signal(signal.SIGHUP, lambda *_: setattr(daemon, "config_stamp", None))
    daemon.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
